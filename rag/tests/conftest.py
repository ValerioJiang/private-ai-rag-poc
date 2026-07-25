"""Fixture comuni ai test di P6.

Gli oggetti finti stanno qui e non nei singoli file perche' due dei tre file
li usano entrambi, e due copie divergerebbero alla prima aggiunta di un
metodo.

GLI IMPORT DEL PROGETTO SONO DENTRO LE FUNZIONI, non in testa al modulo:
conftest.py viene importato all'avvio della raccolta, e pytest-django
configura Django nel proprio pytest_configure. Un `from rag.models import …`
in testa e' quindi una scommessa sull'ordine; dentro la fixture non lo e'.
"""

import pytest


# ----------------------------------------------------------------------
# Igiene fra un test e l'altro
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def cache_delle_factory_pulita():
    """Svuota il dizionario di modulo di factories.py attorno a ogni test.

    NON e' igiene generica. `_CACHE` e' un dizionario di MODULO: l'isolamento
    transazionale di pytest-django non lo tocca, quindi un LLM finto
    memorizzato da un test resterebbe visibile al successivo, che ne
    costruirebbe uno proprio senza accorgersene.
    """
    from rag.services.factories import svuota_cache

    svuota_cache()
    yield
    svuota_cache()


@pytest.fixture
def processo_senza_segnali():
    """Scollega il receiver che svuota la cache alla modifica di un profilo.

    Riproduce fedelmente lo scenario che la docstring di factories.py
    descrive: un ALTRO processo — il worker — che il post_save non lo riceve
    mai. E' l'unica condizione in cui il test della chiave prova qualcosa: con
    il receiver collegato la cache verrebbe svuotata dal segnale, e il test
    resterebbe verde anche se la chiave contenesse il solo pk.
    """
    from django.db.models.signals import post_save

    from rag.signals import MODELLI_DI_CONFIGURAZIONE, invalida_cache_factory

    for modello in MODELLI_DI_CONFIGURAZIONE:
        post_save.disconnect(
            sender=modello,
            dispatch_uid=f"rag.cache.salvataggio.{modello.__name__}",
        )
    yield
    for modello in MODELLI_DI_CONFIGURAZIONE:
        post_save.connect(
            invalida_cache_factory,
            sender=modello,
            dispatch_uid=f"rag.cache.salvataggio.{modello.__name__}",
        )


# ----------------------------------------------------------------------
# Configurazione: quella vera, creata dalla migrazione 0004
# ----------------------------------------------------------------------


@pytest.fixture
def pipeline_predefinita(db):
    """La RagPipeline creata da 0004_configurazione_predefinita.

    Non se ne costruisce una nuova: le migrazioni di dati girano alla
    creazione del database di prova, quindi la configurazione predefinita
    c'e' gia'. Provarla e' anche una verifica implicita di RF-26.
    """
    from rag.models import RagPipeline

    return RagPipeline.objects.select_related(
        "knowledge_base",
        "knowledge_base__embedding_profile",
        "knowledge_base__chunking_profile",
        "llm_profile",
        "retrieval_profile",
        "prompt_template",
    ).get(is_default=True)


@pytest.fixture
def utente(db, django_user_model):
    return django_user_model.objects.create_user(
        username="collaudo", password="collaudo"
    )


@pytest.fixture
def client_autenticato(utente):
    """APIClient gia' autenticato.

    force_authenticate scavalca BasicAuthentication di proposito: qui si
    provano le viste, non l'autenticazione. Il 401 senza credenziali ha un
    test dedicato in test_api_ask.py.
    """
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=utente)
    return client


# ----------------------------------------------------------------------
# PDF, generati con la stessa libreria che il sistema usa per leggerli
# ----------------------------------------------------------------------


@pytest.fixture
def pdf_con_testo() -> bytes:
    """Un PDF di una pagina con testo estraibile.

    Document.tobytes() e' stato MISURATO su pymupdf 1.28.0 (MuPDF 1.29.0),
    l'installata: restituisce 790 byte per questa pagina. Il ripiego previsto
    in pianificazione — salvare su file e restituire il percorso — non serve.
    """
    import pymupdf

    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text(
        (72, 100),
        "Le ferie maturano in ragione di 26 giorni lavorativi all'anno.",
    )
    dati = documento.tobytes()
    documento.close()
    return dati


@pytest.fixture
def pdf_senza_testo() -> bytes:
    """Un PDF di una pagina VUOTA: e' la scansione senza OCR di RF-10.

    Non serve un'immagine vera: load_pdf() salta le pagine il cui
    get_text().strip() e' vuoto, e una pagina bianca lo e' esattamente come
    una scansione.
    """
    import pymupdf

    documento = pymupdf.open()
    documento.new_page()
    dati = documento.tobytes()
    documento.close()
    return dati


@pytest.fixture
def pdf_illeggibile() -> bytes:
    """Byte che non sono un PDF, con estensione .pdf.

    Fa scattare pymupdf.FileDataError, che loaders.py traduce in
    PdfIllegibile. E' il caso «file corrotto» di CA-8.
    """
    return b"Questo non e' un PDF, e' testo semplice con il nome sbagliato."


# ----------------------------------------------------------------------
# Sostituti di cio' che parla con la rete
# ----------------------------------------------------------------------


class EmbeddingsFinti:
    """Il minimo che il codice del progetto usa di un Embeddings.

    Restituisce vettori costanti della dimensione richiesta: nessun test
    giudica la qualita' del recupero, che senza un modello vero non e'
    verificabile. Serve a far passare verify_embedding_dimension() e a non
    toccare la rete.
    """

    def __init__(self, dimensione: int = 1024) -> None:
        self.dimensione = dimensione
        self.chiamate = 0

    def embed_query(self, testo: str) -> list[float]:
        self.chiamate += 1
        return [0.1] * self.dimensione

    def embed_documents(self, testi: list[str]) -> list[list[float]]:
        self.chiamate += 1
        return [[0.1] * self.dimensione for _ in testi]


class VectorStoreFinto:
    """Sostituto di PGVector: registra invece di scrivere.

    Registra i LOTTI e non solo i documenti, perche' e' cosi' che si verifica
    che EmbeddingProfile.batch_size non sia un campo decorativo — il taglio a
    lotti in ingestion.py esiste proprio perche' PGVector.add_texts() manda
    tutto in una POST sola.
    """

    def __init__(self, risultati=None) -> None:
        self.lotti: list[list] = []
        self.ids: list[str] = []
        self.cancellati: list[str] = []
        self._risultati = risultati or []

    def add_documents(self, documenti, ids=None, **kwargs):
        self.lotti.append(list(documenti))
        self.ids.extend(ids or [])
        return ids or []

    def delete(self, ids=None, **kwargs):
        self.cancellati.extend(ids or [])

    def similarity_search_with_score(self, domanda, k=4, **kwargs):
        return self._risultati[:k]

    def max_marginal_relevance_search_with_score(self, domanda, k=4, **kwargs):
        return self._risultati[:k]
