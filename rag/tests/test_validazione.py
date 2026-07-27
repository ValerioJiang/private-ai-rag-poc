"""Ammissibilita' dei file in ingresso (T-44).

Nessuno di questi test tocca la rete: la validazione non parla ne' con Ollama
ne' con pgvector. Il PDF lo costruisce pymupdf, la stessa libreria che il
sistema usa per leggerlo.

Tre gruppi: la funzione da sola, l'aggancio alla POST e l'aggancio all'admin.
L'admin ha due test e non uno perche' li' il file viene letto DUE volte —
checksum e conteggio delle pagine — e la seconda lettura, senza il seek(0),
lascerebbe salvare un PDF di zero byte: e' il difetto pagato in P2. Il terzo
innesco, `manage.py ingest`, non ha test qui e resta verificato a mano (il
comando scrive in MEDIA_ROOT e provarlo qui costerebbe piu' di quanto renda).
"""

import pytest

from rag.services.exceptions import (
    FileTroppoGrande,
    PdfIllegibile,
    TroppePagine,
)
from rag.services.loaders import conta_pagine
from rag.services.validation import verifica_ammissibilita


@pytest.fixture
def pdf_di_tre_pagine() -> bytes:
    import pymupdf

    documento = pymupdf.open()
    for numero in range(3):
        pagina = documento.new_page()
        pagina.insert_text((72, 100), f"Pagina {numero + 1} con del testo.")
    dati = documento.tobytes()
    documento.close()
    return dati


def _carica(dati: bytes, nome: str = "prova.pdf"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(nome, dati, content_type="application/pdf")


# --- conta_pagine ----------------------------------------------------


def test_conta_pagine_legge_il_totale_senza_estrarre_il_testo(pdf_di_tre_pagine):
    assert conta_pagine(pdf_di_tre_pagine) == 3


def test_conta_pagine_rifiuta_cio_che_non_e_un_pdf():
    with pytest.raises(PdfIllegibile):
        conta_pagine(b"Questo non e' un PDF.")


def test_conta_pagine_da_percorso_da_lo_stesso_risultato(pdf_di_tre_pagine, tmp_path):
    """Le due vie devono concordare: sopra i 2,5 MB si usa quella per
    percorso, e una discordanza renderebbe il limite dipendente dalla
    dimensione del file invece che dal suo contenuto."""
    from rag.services.loaders import conta_pagine_da_percorso

    percorso = tmp_path / "tre-pagine.pdf"
    percorso.write_bytes(pdf_di_tre_pagine)
    assert conta_pagine_da_percorso(str(percorso)) == conta_pagine(pdf_di_tre_pagine) == 3


# --- limiti disattivati ----------------------------------------------


def test_con_i_limiti_a_zero_non_si_verifica_nulla(
    pipeline_predefinita, pdf_di_tre_pagine
):
    """Il default della 0006 non cambia il comportamento consegnato."""
    kb = pipeline_predefinita.knowledge_base
    assert kb.max_file_size_mb == 0
    assert kb.max_page_count == 0
    verifica_ammissibilita(_carica(pdf_di_tre_pagine), kb)


def test_con_le_pagine_a_zero_il_pdf_non_viene_nemmeno_aperto(pipeline_predefinita):
    """Un file illeggibile passa la validazione se il limite non c'e'.

    E' la decisione di §3.4 del piano: senza limite il contratto resta quello
    consegnato, e a scoprire un PDF corrotto e' il worker.
    """
    kb = pipeline_predefinita.knowledge_base
    kb.max_page_count = 0
    verifica_ammissibilita(_carica(b"non un pdf"), kb)


# --- dimensione -------------------------------------------------------


def test_un_file_oltre_il_limite_di_dimensione_e_respinto(
    pipeline_predefinita, pdf_di_tre_pagine
):
    kb = pipeline_predefinita.knowledge_base
    kb.max_file_size_mb = 1
    grande = _carica(b"x" * (2 * 1024 * 1024))
    with pytest.raises(FileTroppoGrande) as exc:
        verifica_ammissibilita(grande, kb)
    assert "2.0 MB" in str(exc.value)
    assert kb.name in str(exc.value)


def test_il_file_esattamente_al_limite_passa(pipeline_predefinita):
    """Il confronto e' `>`, non `>=`: il caso limite e' ammesso (§3.9)."""
    kb = pipeline_predefinita.knowledge_base
    kb.max_file_size_mb = 1
    kb.max_page_count = 0
    verifica_ammissibilita(_carica(b"x" * (1024 * 1024)), kb)


# --- pagine -----------------------------------------------------------


def test_un_pdf_oltre_il_limite_di_pagine_e_respinto(
    pipeline_predefinita, pdf_di_tre_pagine
):
    kb = pipeline_predefinita.knowledge_base
    kb.max_page_count = 2
    with pytest.raises(TroppePagine) as exc:
        verifica_ammissibilita(_carica(pdf_di_tre_pagine), kb)
    assert "3 pagine" in str(exc.value)


def test_il_puntatore_torna_a_zero_dopo_il_conteggio(
    pipeline_predefinita, pdf_di_tre_pagine
):
    """Il difetto gia' pagato in P2 su compute_checksum: senza il seek(0)
    il salvataggio successivo scriverebbe zero byte."""
    kb = pipeline_predefinita.knowledge_base
    kb.max_page_count = 10
    file = _carica(pdf_di_tre_pagine)
    verifica_ammissibilita(file, kb)
    assert file.tell() == 0
    assert file.read() == pdf_di_tre_pagine


def test_col_percorso_dichiarato_il_file_non_viene_letto_in_memoria(
    pipeline_predefinita, pdf_di_tre_pagine, tmp_path, monkeypatch
):
    """`manage.py ingest` passa il percorso, e il ramo in memoria NON si tocca.

    Un ramo non preso e' invisibile: il conteggio tornerebbe giusto lo stesso,
    e a cambiare sarebbe solo il profilo di memoria — cioe' esattamente cio'
    che §3.10 esiste per governare. Qui la prova e' diretta: conta_pagine(),
    che legge da byte, viene sostituita con qualcosa che esplode, e la
    validazione passa comunque.

    Il piano dava per scontato che bastasse temporary_file_path(). MISURATO in
    esecuzione: django.core.files.File che incarta un file aperto non espone
    ne' quello ne' `.path`, e senza il percorso esplicito il comando cadrebbe
    sul ramo in memoria.
    """
    from django.core.files import File

    from rag.services import validation

    def _non_deve_essere_chiamata(_dati):
        raise AssertionError(
            "letto in memoria: il ramo del percorso non e' stato preso"
        )

    monkeypatch.setattr(validation, "conta_pagine", _non_deve_essere_chiamata)

    percorso = tmp_path / "tre-pagine.pdf"
    percorso.write_bytes(pdf_di_tre_pagine)

    kb = pipeline_predefinita.knowledge_base
    kb.max_page_count = 2
    with percorso.open("rb") as aperto:
        # Il wrapper da solo non basta, ed e' il punto del test.
        assert not hasattr(File(aperto), "temporary_file_path")
        with pytest.raises(TroppePagine) as exc:
            verifica_ammissibilita(File(aperto), kb, percorso=str(percorso))
    assert "3 pagine" in str(exc.value)


# --- aggancio alla POST ------------------------------------------------


@pytest.mark.django_db
def test_la_post_respinge_con_400_e_non_crea_nulla(
    client_autenticato, pipeline_predefinita, pdf_di_tre_pagine, settings, tmp_path
):
    """400, e soprattutto: nessuna riga e nessun file. E' il punto del
    controllo sincrono — un limite che lasciasse residui non varrebbe la pena."""
    from rag.models import Document

    settings.MEDIA_ROOT = tmp_path
    kb = pipeline_predefinita.knowledge_base
    kb.max_page_count = 2
    kb.save()

    risposta = client_autenticato.post(
        "/api/documents/",
        {"file": _carica(pdf_di_tre_pagine, "troppe-pagine.pdf")},
        format="multipart",
    )

    assert risposta.status_code == 400
    assert "3 pagine" in risposta.json()["detail"]
    assert Document.objects.count() == 0
    assert list(tmp_path.rglob("*.pdf")) == []


@pytest.mark.django_db
def test_la_post_resta_202_quando_i_limiti_sono_disattivati(
    client_autenticato,
    pipeline_predefinita,
    pdf_di_tre_pagine,
    settings,
    tmp_path,
    monkeypatch,
):
    """Controprova: la 0006 non cambia il comportamento consegnato."""
    from rag import views

    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(views, "accoda_indicizzazione", lambda documento: "task-finto")

    risposta = client_autenticato.post(
        "/api/documents/",
        {"file": _carica(pdf_di_tre_pagine, "ammesso.pdf")},
        format="multipart",
    )

    assert risposta.status_code == 202


# --- aggancio all'admin ------------------------------------------------


@pytest.mark.django_db
def test_il_form_dell_admin_respinge_un_file_oltre_i_limiti(
    pipeline_predefinita, pdf_di_tre_pagine, settings, tmp_path
):
    """Senza questo aggancio l'admin — il flusso di CA-2 — scavalcherebbe
    ogni limite: e' il difetto che il ricontrollo del piano ha trovato."""
    from rag.admin import DocumentAdminForm

    settings.MEDIA_ROOT = tmp_path
    kb = pipeline_predefinita.knowledge_base
    kb.max_page_count = 2
    kb.save()

    form = DocumentAdminForm(
        data={"knowledge_base": kb.pk},
        files={"file": _carica(pdf_di_tre_pagine, "troppe-pagine.pdf")},
    )

    assert not form.is_valid()
    assert "3 pagine" in " ".join(form.errors["file"])


@pytest.mark.django_db
def test_il_file_ammesso_dall_admin_si_salva_intero(
    pipeline_predefinita, pdf_di_tre_pagine, settings, tmp_path
):
    """Due letture del file dove prima ce n'era una (checksum + conteggio):
    senza i seek(0) si salverebbe un PDF di zero byte, difetto di P2."""
    from rag.admin import DocumentAdminForm
    from rag.models import Document

    settings.MEDIA_ROOT = tmp_path
    kb = pipeline_predefinita.knowledge_base
    kb.max_page_count = 10
    kb.max_file_size_mb = 5
    kb.save()

    form = DocumentAdminForm(
        data={
            "knowledge_base": kb.pk,
            # Il form dichiara fields = "__all__": status, page_count e
            # chunk_count hanno un default sul modello ma non sono blank, e
            # senza di essi is_valid() e' False. Nella pagina vera non si
            # vedono perche' DocumentAdmin li tiene in readonly_fields e il
            # ModelForm dell'admin li esclude: qui il form si costruisce nudo,
            # e vanno forniti. (Letti sul modello, non indovinati.)
            "status": Document.Status.PENDING,
            "page_count": 0,
            "chunk_count": 0,
        },
        files={"file": _carica(pdf_di_tre_pagine, "ammesso.pdf")},
    )

    assert form.is_valid(), form.errors
    documento = form.save()
    assert documento.file.size == len(pdf_di_tre_pagine)
