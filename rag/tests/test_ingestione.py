"""T-37 — la macchina a stati dell'ingestione, casi di errore compresi.

RF-06, RF-09, RF-10, RF-16, RF-25, RNF-04, CA-2, CA-8. Il valore di questi test
non e' «l'ingestione funziona» — quello lo dimostrano le prove reali di ogni
fase, eseguite su Ollama vero — ma che OGNI fallimento lasci una traccia
leggibile: ingest_document() e' un involucro che persiste l'esito, riuscito o
fallito, attorno a un corpo che non se ne occupa, ed e' la parte che una
regressione romperebbe in silenzio. Un documento che resta «In elaborazione»
per sempre, o «Fallito» senza motivo, e' esattamente il guasto che RNF-04
vieta e che nessuna prova manuale nota.

LE SOSTITUZIONI SONO TRE E STANNO TUTTE IN rag.services.ingestion, cioe' nel
modulo che le CHIAMA: ingestion.py fa `from .factories import …`, quindi il
riferimento e' gia' legato al momento dell'import e riscrivere
rag.services.factories non avrebbe alcun effetto. I nomi sono get_embeddings,
verify_embedding_dimension e get_vectorstore. get_splitter NON e' sostituito:
e' codice puro, senza rete, e sostituirlo toglierebbe al test dei lotti e a
quello della configurazione irrealizzabile proprio cio' che devono provare.

NESSUN TEST DI QUESTO FILE TOCCA LA RETE ne' scrive in MEDIA_ROOT: i PDF sono
generati in memoria dalle fixture di conftest.py e il documento vive in un
MEDIA_ROOT temporaneo, montato da `crea_documento`.

Gli import del progetto stanno DENTRO le funzioni, come in conftest.py: la
raccolta di pytest importa il modulo prima che pytest-django abbia configurato
Django.
"""

import pytest


# ----------------------------------------------------------------------
# Presupposti: un documento vero, su disco vero, senza Ollama
# ----------------------------------------------------------------------


@pytest.fixture
def ingestione_senza_ollama(monkeypatch):
    """Rende ingest_document() eseguibile senza rete, restituendo lo store finto.

    Le tre sostituzioni sono sul modulo CHIAMANTE (cfr. l'intestazione). Lo
    store finto viene restituito perche' due test lo interrogano: e' l'unico
    modo di osservare la meta' dello schema che non e' Django — gli id dei
    vettori e il taglio a lotti — senza una pgvector vera.
    """
    from rag.services import ingestion
    from rag.tests.conftest import EmbeddingsFinti, VectorStoreFinto

    store = VectorStoreFinto()
    monkeypatch.setattr(
        ingestion, "get_embeddings", lambda profilo: EmbeddingsFinti(profilo.dimension)
    )
    monkeypatch.setattr(
        ingestion,
        "verify_embedding_dimension",
        lambda embeddings, profilo: profilo.dimension,
    )
    monkeypatch.setattr(ingestion, "get_vectorstore", lambda kb, embeddings=None: store)
    return store


@pytest.fixture
def crea_documento(pipeline_predefinita, settings, tmp_path):
    """Crea un Document con un file vero, in un MEDIA_ROOT temporaneo.

    MEDIA_ROOT si sposta QUI e non nella fixture delle sostituzioni: e' questa
    la fixture che scrive su disco, e il test dell'accodamento (T-32) crea un
    documento senza aver bisogno di sostituire alcuna factory. Legandolo alla
    fixture sbagliata quel test sporcherebbe la media/ del progetto.

    Il file e' vero e non un doppio perche' ingest_document() usa
    document.file.path e compute_checksum() legge a blocchi: entrambe cose che
    con un file finto non si proverebbero.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    from rag.models import Document

    settings.MEDIA_ROOT = tmp_path

    def _crea(contenuto: bytes, nome: str = "prova.pdf"):
        return Document.objects.create(
            knowledge_base=pipeline_predefinita.knowledge_base,
            file=SimpleUploadedFile(nome, contenuto, content_type="application/pdf"),
            original_filename=nome,
        )

    return _crea


# ----------------------------------------------------------------------
# Il percorso felice, e le due meta' dello schema
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_un_pdf_con_testo_arriva_a_indicizzato(
    ingestione_senza_ollama, crea_documento, pdf_con_testo
):
    """CA-2: stato «Indicizzato», pagine e segmenti valorizzati.

    L'impronta e needs_reindex non sono un contorno: sono cio' su cui poggia
    RF-25, e sono anche l'unica prova che lo snapshot della configurazione
    venga scritto NELLA STESSA transazione dello stato finale.
    """
    from rag.models import Document
    from rag.services.ingestion import ingest_document

    documento = crea_documento(pdf_con_testo)
    esito = ingest_document(documento)
    documento.refresh_from_db()

    assert documento.status == Document.Status.INDEXED
    assert documento.page_count == 1
    assert documento.chunk_count == esito.chunk_count > 0
    assert documento.checksum != ""
    assert documento.indexed_at is not None
    assert documento.error_message == ""
    assert documento.index_fingerprint == documento.knowledge_base.index_fingerprint()
    assert documento.needs_reindex is False


@pytest.mark.django_db
def test_i_vettori_hanno_id_deterministici_e_le_righe_li_ripetono(
    ingestione_senza_ollama, crea_documento, pdf_con_testo
):
    """Il ponte fra le due meta' dello schema e' vector_id, non una join.

    ARCHITECTURE §6.5: langchain_pg_embedding sta fuori dalle migrazioni
    Django, su una connessione SQLAlchemy distinta. Se i due lati calcolassero
    l'id in modo diverso — o se uno dei due smettesse di calcolarlo —
    l'indice mentirebbe al retrieval senza che nulla lo segnali.
    """
    from rag.services.ingestion import ingest_document, vector_id

    documento = crea_documento(pdf_con_testo)
    ingest_document(documento)
    documento.refresh_from_db()

    attesi = [vector_id(documento.pk, o) for o in range(documento.chunk_count)]
    assert ingestione_senza_ollama.ids == attesi
    assert (
        list(documento.chunks.order_by("ordinal").values_list("vector_id", flat=True))
        == attesi
    )


@pytest.mark.django_db
def test_la_reindicizzazione_e_idempotente(
    ingestione_senza_ollama, crea_documento, pdf_con_testo
):
    """T-19: rieseguire non duplica nulla, e conserva le chiavi primarie.

    Le chiavi contano: RetrievedChunk.chunk e' SET_NULL, quindi ricreare le
    righe azzererebbe lo storico delle interrogazioni (RF-16). E' il motivo
    per cui ingestion.py usa update_or_create e non delete + bulk_create, e
    una regressione a delete + bulk_create passerebbe ogni altro test di
    questo file.

    LA SECONDA ISTANZA SI RILEGGE DAL DATABASE, e non e' una comodita': e'
    esattamente cio' che fa il vero innesco della reindicizzazione. L'azione
    «Reindicizza» accoda, e a lavorare e' indicizza_documento(), che ricarica
    il documento per pk (tasks.py). MISURATO in P6: riusare la STESSA istanza
    Document per due ingestioni consecutive solleva
    «ValueError: seek of closed file» in compute_checksum(), perche' la prima
    chiamata richiude il FieldFile — voluto, su Windows un handle aperto fa
    fallire la sostituzione del file — e FieldFile.close() non azzera
    `_file`, quindi il seek() successivo trova un oggetto chiuso invece di
    riaprirlo. Nessun percorso di produzione lo fa (il worker ricarica, e
    `manage.py ingest` ingerisce una volta per invocazione), ma il limite e'
    reale e va conosciuto prima di chiamare ingest_document() due volte da un
    unico processo.
    """
    from rag.models import Document
    from rag.services.ingestion import ingest_document

    documento = crea_documento(pdf_con_testo)
    ingest_document(documento)
    chiavi = list(documento.chunks.order_by("ordinal").values_list("pk", flat=True))
    assert chiavi, "senza segmenti il test non proverebbe nulla"

    ricaricato = Document.objects.select_related("knowledge_base").get(pk=documento.pk)
    ingest_document(ricaricato)
    ricaricato.refresh_from_db()

    assert ricaricato.status == Document.Status.INDEXED
    assert ricaricato.chunks.count() == len(chiavi)
    assert (
        list(ricaricato.chunks.order_by("ordinal").values_list("pk", flat=True)) == chiavi
    )


@pytest.mark.django_db
def test_i_segmenti_vengono_scritti_a_lotti_di_batch_size(
    ingestione_senza_ollama, crea_documento, pdf_con_testo, pipeline_predefinita
):
    """EmbeddingProfile.batch_size non e' un campo decorativo.

    PGVector.add_texts() invia TUTTI i testi in una sola POST a /api/embed
    (verificato sul sorgente della 0.0.17): il taglio a lotti in ingestion.py
    e' l'unico punto in cui quel campo ha effetto. Senza l'affettamento lo
    store finto registrerebbe UN lotto solo.

    chunk_size scende a 20 perche' la pagina della fixture e' una riga sola:
    con la segmentazione predefinita produrrebbe un segmento unico, e
    «un lotto da uno» sarebbe vero anche senza alcun taglio. Un test che non
    puo' fallire non prova nulla.
    """
    from rag.services.ingestion import ingest_document

    kb = pipeline_predefinita.knowledge_base
    kb.chunking_profile.chunk_size = 20
    kb.chunking_profile.chunk_overlap = 0
    kb.chunking_profile.save()
    kb.embedding_profile.batch_size = 1
    kb.embedding_profile.save()

    documento = crea_documento(pdf_con_testo)
    ingest_document(documento)
    documento.refresh_from_db()

    assert documento.chunk_count > 1, "il test sarebbe vacuo con un solo segmento"
    assert len(ingestione_senza_ollama.lotti) == documento.chunk_count
    assert all(len(lotto) == 1 for lotto in ingestione_senza_ollama.lotti)


# ----------------------------------------------------------------------
# I fallimenti: e' il cuore di T-37 (CA-8, RNF-04)
# ----------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fixture_pdf, frammento_atteso",
    [
        ("pdf_senza_testo", "OCR"),
        ("pdf_illeggibile", "PDF leggibile"),
    ],
)
def test_un_pdf_non_indicizzabile_lascia_stato_fallito_e_motivo(
    request, ingestione_senza_ollama, crea_documento, fixture_pdf, frammento_atteso
):
    """CA-8 + RNF-04: lo stato E il motivo sono persistiti PRIMA del rilancio.

    L'eccezione si propaga di proposito — il chiamante, cioe' il worker, deve
    saperlo e marcare fallita anche la riga DBTaskResult — ma quando arriva, la
    riga del documento e' gia' scritta: e' la forma «involucro attorno a un
    corpo» di ingestion.py. Il frammento atteso e' cercato nel messaggio
    persistito e non in quello dell'eccezione, perche' e' il primo che un
    amministratore legge nell'admin.

    RF-10 per il PDF senza testo, CA-8 «file corrotto» per l'illeggibile.
    """
    from rag.models import Document
    from rag.services.exceptions import IngestionError
    from rag.services.ingestion import ingest_document

    documento = crea_documento(request.getfixturevalue(fixture_pdf))

    with pytest.raises(IngestionError):
        ingest_document(documento)

    documento.refresh_from_db()
    assert documento.status == Document.Status.FAILED
    assert frammento_atteso in documento.error_message
    assert documento.chunk_count == 0
    assert documento.chunks.count() == 0


@pytest.mark.django_db
def test_lo_stesso_file_due_volte_nella_stessa_base_e_un_duplicato(
    ingestione_senza_ollama, crea_documento, pdf_con_testo
):
    """RF-09. La deduplica precede QUALUNQUE lavoro costoso.

    Si osserva anche questo: lo store finto non registra un solo lotto in piu'
    del primo documento, perche' il secondo si ferma prima delle factory. E'
    la ragione per cui il controllo sta al punto 1 di _esegui_ingestione() e
    non dopo l'estrazione.
    """
    from rag.models import Document
    from rag.services.exceptions import DocumentoDuplicato
    from rag.services.ingestion import ingest_document

    primo = crea_documento(pdf_con_testo, "primo.pdf")
    ingest_document(primo)
    lotti_del_primo = len(ingestione_senza_ollama.lotti)

    secondo = crea_documento(pdf_con_testo, "secondo.pdf")
    with pytest.raises(DocumentoDuplicato) as errore:
        ingest_document(secondo)

    assert errore.value.esistente_id == primo.pk
    secondo.refresh_from_db()
    assert secondo.status == Document.Status.FAILED
    assert str(primo.pk) in secondo.error_message
    assert len(ingestione_senza_ollama.lotti) == lotti_del_primo


@pytest.mark.django_db
def test_una_configurazione_irrealizzabile_ferma_prima_di_elaborazione(
    ingestione_senza_ollama, crea_documento, pdf_con_testo, pipeline_predefinita
):
    """ingestion.py §2: le factory girano PRIMA dello stato «In elaborazione».

    Cosi' un profilo non realizzabile — o un Ollama spento — non fa passare il
    documento per uno stato che non ha mai avuto davvero. Lo si osserva
    dall'esito: il documento e' «Fallito» e non ha ne' pagine ne' segmenti,
    cioe' nulla e' stato letto dal file.

    ConfigurazioneNonSupportata eredita da IngestionError, quindi la cattura di
    ingest_document() la comprende senza una riga in piu' — e' il motivo
    dell'ereditarieta' multipla in exceptions.py.
    """
    from rag.models import ChunkingProfile, Document
    from rag.services.exceptions import ConfigurazioneNonSupportata
    from rag.services.ingestion import ingest_document

    profilo = pipeline_predefinita.knowledge_base.chunking_profile
    profilo.splitter = ChunkingProfile.Splitter.TOKEN
    profilo.save()

    documento = crea_documento(pdf_con_testo)
    with pytest.raises(ConfigurazioneNonSupportata):
        ingest_document(documento)

    documento.refresh_from_db()
    assert documento.status == Document.Status.FAILED
    assert "tiktoken" in documento.error_message
    assert documento.page_count == 0
    assert documento.chunk_count == 0


# ----------------------------------------------------------------------
# La scansione PARZIALE: il buco che T-44 chiude
# ----------------------------------------------------------------------


@pytest.fixture
def pdf_meta_scansionato() -> bytes:
    """Quattro pagine, una sola con testo: rapporto 0,25.

    E' il caso che prima di T-44 passava in silenzio — «Indicizzato» con un
    solo segmento su quattro pagine, e nulla nell'admin a dirlo. Sta qui e non
    in conftest.py perche' lo usano soltanto i due test che seguono: le
    fixture di conftest.py sono quelle condivise fra piu' file.
    """
    import pymupdf

    documento = pymupdf.open()
    prima = documento.new_page()
    prima.insert_text((72, 100), "L'unica pagina con del testo estraibile.")
    for _ in range(3):
        documento.new_page()
    dati = documento.tobytes()
    documento.close()
    return dati


@pytest.mark.django_db
def test_una_scansione_parziale_sotto_la_quota_lascia_stato_fallito(
    ingestione_senza_ollama, crea_documento, pdf_meta_scansionato
):
    """Il buco piu' insidioso dei tre limiti di T-44.

    Gli altri due — dimensione e numero di pagine — si vedono all'ingresso e
    danno un 400 immediato. Questo no: senza il controllo il documento diventa
    «Indicizzato» e nulla dice che tre pagine su quattro sono rimaste fuori
    dall'indice. Il conteggio nel motivo non e' un dettaglio di forma: e' cio'
    che permette a un amministratore di decidere se il file va rifatto con
    l'OCR o se la soglia e' troppo severa (RNF-04, CA-8).

    La soglia arriva dalla base di conoscenza e non da una costante (RF-22):
    il test la scrive sulla riga, come farebbe l'admin.
    """
    from rag.models import Document
    from rag.services.exceptions import PdfTestoInsufficiente
    from rag.services.ingestion import ingest_document

    # ATTENZIONE all'ordine: la fixture e' _crea(contenuto, nome), col
    # CONTENUTO per primo. Invertirli creerebbe un documento il cui file
    # contiene il nome del file.
    documento = crea_documento(pdf_meta_scansionato, "meta-scansionato.pdf")
    kb = documento.knowledge_base
    kb.min_text_page_ratio = 0.5
    kb.save()

    with pytest.raises(PdfTestoInsufficiente):
        ingest_document(documento)

    documento.refresh_from_db()
    assert documento.status == Document.Status.FAILED
    assert "1 pagine su 4" in documento.error_message


@pytest.mark.django_db
def test_con_la_quota_a_zero_la_scansione_parziale_viene_indicizzata(
    ingestione_senza_ollama, crea_documento, pdf_meta_scansionato
):
    """Controprova: il default non cambia il comportamento consegnato.

    Zero significa «controllo disattivato» (§3.9 del piano), e lo stesso file
    che il test precedente rifiuta arriva qui a «Indicizzato». E' anche la
    verifica che CA-2 non regredisca: page_count resta il totale del FILE.
    """
    from rag.models import Document
    from rag.services.ingestion import ingest_document

    # ATTENZIONE all'ordine: la fixture e' _crea(contenuto, nome), col
    # CONTENUTO per primo. Invertirli creerebbe un documento il cui file
    # contiene il nome del file.
    documento = crea_documento(pdf_meta_scansionato, "meta-scansionato.pdf")
    assert documento.knowledge_base.min_text_page_ratio == 0.0

    ingest_document(documento)

    documento.refresh_from_db()
    assert documento.status == Document.Status.INDEXED
    # page_count resta il totale del FILE, non delle pagine con testo (CA-2).
    assert documento.page_count == 4


# ----------------------------------------------------------------------
# L'accodamento: un solo punto, e riporta a «In attesa» (T-32)
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_accodare_riporta_il_documento_in_attesa_e_azzera_l_errore(
    settings, crea_documento, pdf_con_testo
):
    """tasks.py: senza l'azzeramento, un documento fallito rimesso in coda
    mostrerebbe il motivo di un fallimento superato.

    ImmediateBackend NON va bene qui: eseguirebbe l'ingestione in linea, che e'
    l'opposto di cio' che il test osserva. Si usa `dummy`, che accoda e non
    esegue.

    MISURATO in P6 sulla django-tasks 0.12.0 installata: la classe
    django_tasks.backends.dummy.DummyBackend esiste a quel percorso, e
    django_tasks/signals.py registra un receiver di `setting_changed` che al
    cambio di TASKS ricostruisce le impostazioni del gestore e ne azzera le
    connessioni. Poiche' Task.enqueue() risolve il backend a ogni chiamata
    (`task_backends[self.backend]`, base.py), la riscrittura a caldo di
    settings.TASKS ha effetto: il ripiego con un finto `.enqueue()` previsto in
    pianificazione non e' servito. L'asserzione sui risultati del backend e'
    proprio la verifica che il dummy sia quello in uso — se la riscrittura non
    avesse effetto, ad accodare sarebbe DatabaseBackend e quella lista sarebbe
    vuota.
    """
    from django_tasks import task_backends

    from rag.models import Document
    from rag.tasks import accoda_indicizzazione

    settings.TASKS = {
        "default": {
            "BACKEND": "django_tasks.backends.dummy.DummyBackend",
            "QUEUES": ["default"],
        }
    }

    documento = crea_documento(pdf_con_testo)
    documento.status = Document.Status.FAILED
    documento.error_message = "un guasto precedente"
    documento.save()

    id_task = accoda_indicizzazione(documento)
    documento.refresh_from_db()

    assert documento.status == Document.Status.PENDING
    assert documento.error_message == ""

    # Il task e' stato ACCODATO, non eseguito, e riceve l'intero, non il
    # documento. Gli argomenti si rileggono come LISTA e non come tupla:
    # normalize_json() li ha gia' fatti passare per JSON al momento
    # dell'accodamento — misurato qui, ed e' la conferma osservabile di cio'
    # che la docstring di tasks.py dichiara.
    accodati = task_backends["default"].results
    assert [risultato.id for risultato in accodati] == [id_task]
    assert accodati[0].args == [documento.pk]
