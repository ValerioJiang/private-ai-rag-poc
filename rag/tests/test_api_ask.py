"""T-38 — POST /api/ask/ con il servizio di inferenza sostituito.

RF-11 → RF-16, RF-27, CA-3, CA-4. I test stanno su DUE livelli, e la
distinzione e' deliberata:

- LIVELLO ALTO: si sostituisce rag.views.rispondi. Prova la sola mappatura
  dei codici della vista — 400, 503, 500 — che e' logica della vista e non
  del dominio. E' la forma gia' collaudata in P4 e in P5.
- LIVELLO PROFONDO: si sostituiscono get_llm e get_vectorstore DENTRO
  rag.services.query, e rispondi() gira per intero. Prova cio' che conta —
  la soglia, la non-risposta senza interrogare l'LLM (RF-14, CA-4), le fonti
  col punteggio, il QueryLog — senza che Ollama esista.

Un solo livello non basterebbe: il primo non tocca il dominio, il secondo non
osserva i codici HTTP.

Gli import del progetto stanno DENTRO le funzioni, come in conftest.py e in
test_ingestione.py: la raccolta di pytest importa il modulo prima che
pytest-django abbia configurato Django.
"""

import pytest


# ----------------------------------------------------------------------
# Livello profondo: rispondi() per intero, senza rete
# ----------------------------------------------------------------------


@pytest.fixture
def catena_senza_ollama(monkeypatch):
    """Sostituisce le due parti costose DENTRO rag.services.query.

    Il modulo fa `from .factories import get_llm, get_vectorstore`: i nomi
    sono gia' legati, quindi riscrivere rag.services.factories non avrebbe
    alcun effetto. E' l'errore piu' probabile di chi scrive questi test.

    Il segmento predefinito ha distanza 0,30, cioe' rilevanza 0,70: e' il
    valore alto della forbice misurata sul corpus reale il 25/07/2026 per una
    domanda pertinente (0,68-0,73, cfr. l'intestazione di query.py), quindi
    supera la soglia predefinita di 0,5 come la supererebbe una domanda vera.

    `llm is not None` e non `llm or ...`: un Runnable e' un oggetto qualunque
    e la sua verita' non e' definita dal progetto: farla decidere a `or`
    significherebbe che un finto LLM dichiarato falso verrebbe scartato in
    silenzio, e il test proverebbe la catena vera.
    """
    from langchain_core.documents import Document as LCDocument
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from rag.services import query
    from rag.tests.conftest import VectorStoreFinto

    def _monta(risposta="Si maturano 26 giorni.", segmenti=None, llm=None):
        if segmenti is None:
            segmenti = [
                (
                    LCDocument(
                        page_content="Le ferie maturano in ragione di 26 giorni.",
                        metadata={"page": 3, "documento": "manuale.pdf"},
                    ),
                    0.30,     # distanza: rilevanza 0,70
                )
            ]
        store = VectorStoreFinto(risultati=segmenti)
        monkeypatch.setattr(query, "get_vectorstore", lambda kb: store)
        monkeypatch.setattr(
            query,
            "get_llm",
            lambda profilo: llm if llm is not None else FakeListChatModel(
                responses=[risposta]
            ),
        )
        return store

    return _monta


@pytest.mark.django_db
def test_una_domanda_pertinente_riceve_risposta_e_fonti(
    client_autenticato, pipeline_predefinita, catena_senza_ollama
):
    """CA-3, RF-13: documento, pagina, estratto e punteggio per ogni fonte."""
    catena_senza_ollama()

    risposta = client_autenticato.post(
        "/api/ask/", {"domanda": "Quanti giorni di ferie?"}, format="json"
    )

    assert risposta.status_code == 200
    corpo = risposta.json()
    assert corpo["generata"] is True
    assert corpo["risposta"] == "Si maturano 26 giorni."
    assert corpo["pipeline"] == pipeline_predefinita.name
    fonte = corpo["fonti"][0]
    assert set(fonte) >= {"documento", "pagina", "estratto", "punteggio"}
    assert fonte["pagina"] == 3
    # Il punteggio esposto e' la RILEVANZA (1 - distanza), non la distanza
    assert fonte["punteggio"] == pytest.approx(0.70, abs=1e-4)


@pytest.mark.django_db
def test_sotto_soglia_si_dichiara_di_non_sapere_senza_interrogare_l_llm(
    client_autenticato, pipeline_predefinita, catena_senza_ollama
):
    """RF-14, CA-4. La promessa non e' «il modello dice di non sapere» — quella
    dipenderebbe dalla sua obbedienza al prompt — ma che l'LLM NON VENGA
    INTERROGATO AFFATTO. Si prova contando le invocazioni: il finto LLM non
    conta fino a uno, solleva alla prima.

    IL FINTO LLM E' UN RunnableLambda, ed e' il ripiego dichiarato dal piano di
    P6, non una preferenza. MISURATO su langchain_core 1.5.1, l'installata: un
    oggetto che espone solo `invoke`, `__or__` e `__ror__` NON regge la
    composizione `prompt | llm | StrOutputParser()`. ChatPromptTemplate e' un
    Runnable, quindi Python chiama il SUO `__or__` per primo, che passa
    l'operando a coerce_to_runnable(); questa solleva TypeError («Expected a
    Runnable, callable or dict. Instead got an unsupported type») invece di
    restituire NotImplemented, e senza NotImplemented Python non ripiega mai
    sul `__ror__` dell'operando destro. RunnableLambda e' un Runnable per
    costruzione e compone senza artifici; la promessa provata resta la stessa,
    perche' il corpo solleva se qualcuno lo invoca.
    """
    from langchain_core.documents import Document as LCDocument
    from langchain_core.runnables import RunnableLambda

    from rag.models import RISPOSTA_NON_DISPONIBILE, RetrievalProfile

    profilo = pipeline_predefinita.retrieval_profile
    profilo.search_type = RetrievalProfile.SearchType.THRESHOLD
    profilo.score_threshold = 0.5
    profilo.save()

    def non_deve_essere_chiamato(_):
        raise AssertionError("l'LLM e' stato interrogato: RF-14 violato")

    catena_senza_ollama(
        segmenti=[
            (
                LCDocument(page_content="tutt'altro argomento", metadata={"page": 1}),
                0.80,      # rilevanza 0,20: sotto la soglia di 0,5
            )
        ],
        llm=RunnableLambda(non_deve_essere_chiamato),
    )

    risposta = client_autenticato.post(
        "/api/ask/", {"domanda": "Qual e' la capitale del Perù?"}, format="json"
    )

    assert risposta.status_code == 200
    corpo = risposta.json()
    assert corpo["risposta"] == RISPOSTA_NON_DISPONIBILE
    assert corpo["generata"] is False
    assert corpo["fonti"] == []
    assert corpo["generation_ms"] == 0


@pytest.mark.django_db
def test_ogni_interrogazione_lascia_un_QueryLog_con_i_tempi_separati(
    client_autenticato, utente, catena_senza_ollama
):
    """RF-16: retrieval_ms e generation_ms sono due campi e non uno, perche'
    in P0 si e' misurato un recupero da 12 s accanto a una generazione da 1."""
    from rag.models import QueryLog

    catena_senza_ollama()
    risposta = client_autenticato.post(
        "/api/ask/", {"domanda": "Quanti giorni di ferie?"}, format="json"
    )

    log = QueryLog.objects.get(pk=risposta.json()["query_log_id"])
    assert log.question == "Quanti giorni di ferie?"
    assert log.answer == "Si maturano 26 giorni."
    assert log.user == utente
    assert log.error == ""
    assert log.latency_ms >= log.retrieval_ms + log.generation_ms
    assert log.retrieved_chunks.count() == 1
    assert log.retrieved_chunks.first().rank == 1     # parte da 1, non da 0


@pytest.mark.django_db
def test_anche_una_domanda_rifiutata_lascia_traccia(client_autenticato):
    """RNF-04: un fallimento che non lascia traccia rende inutile RF-16
    proprio nel caso in cui servirebbe."""
    from rag.models import QueryLog

    risposta = client_autenticato.post("/api/ask/", {"domanda": "   "}, format="json")

    assert risposta.status_code == 400
    assert QueryLog.objects.filter(error__icontains="vuota").exists()


# ----------------------------------------------------------------------
# Livello alto: la mappatura dei codici della vista
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_l_llm_irraggiungibile_e_un_503_non_un_400(
    client_autenticato, catena_senza_ollama
):
    """views.py: un 400 manderebbe il client a correggere una domanda giusta.

    L'ordine delle clausole conta: LlmNonRaggiungibile e' sottoclasse di
    QueryError, quindi se la sua clausola finisse dopo non sarebbe mai
    raggiunta — e nessuna verifica scritta con domande pertinenti se ne
    accorgerebbe. Questo test se ne accorge.

    Si solleva httpx.ConnectError e non ConnectionError builtin perche' e' il
    tipo MISURATO in P3 con Ollama spento: ChatOllama.invoke() lo lascia
    passare grezzo, e httpx.TransportError non e' sottoclasse di OSError. E'
    il caso per cui la seconda famiglia esiste nella except di query.py.
    """
    import httpx
    from langchain_core.runnables import RunnableLambda

    def spento(_):
        raise httpx.ConnectError("[WinError 10061] connessione rifiutata")

    catena_senza_ollama(llm=RunnableLambda(spento))

    risposta = client_autenticato.post(
        "/api/ask/", {"domanda": "Quanti giorni di ferie?"}, format="json"
    )
    assert risposta.status_code == 503
    assert "Ollama" in risposta.json()["detail"]


@pytest.mark.django_db
def test_una_pipeline_disattivata_e_rifiutata_anche_se_richiesta(
    client_autenticato, pipeline_predefinita
):
    """RF-15: is_active esiste per poter ritirare una configurazione senza
    cancellarla, e onorarlo solo quando comodo lo svuoterebbe di significato."""
    pipeline_predefinita.is_default = False
    pipeline_predefinita.is_active = False
    pipeline_predefinita.save()

    risposta = client_autenticato.post(
        "/api/ask/",
        {"domanda": "Quanti giorni di ferie?", "pipeline": pipeline_predefinita.name},
        format="json",
    )
    assert risposta.status_code == 400
    assert "non e' attiva" in risposta.json()["detail"]


@pytest.mark.django_db
def test_senza_credenziali_e_401(pipeline_predefinita):
    """RF-27: tutto sotto /api/ e' autenticato; /health no, di proposito."""
    from rest_framework.test import APIClient

    assert APIClient().post("/api/ask/", {"domanda": "x"}, format="json").status_code == 401


@pytest.mark.django_db
def test_un_guasto_inatteso_risponde_json_anche_con_debug_acceso(
    client_autenticato, monkeypatch, settings
):
    """rag/errors.py: sulle rotte /api/ non c'e' piu' la pagina di debug HTML.

    settings.DEBUG va RIALZATO a mano: pytest-django lo forza a False, quindi
    senza questa riga il test proverebbe l'esatto contrario di cio' che
    afferma di provare. Il messaggio interno non deve trapelare al client.
    """
    from rag import views

    settings.DEBUG = True

    def esplode(*args, **kwargs):
        raise RuntimeError("dettaglio interno che non deve uscire")

    monkeypatch.setattr(views, "rispondi", esplode)

    risposta = client_autenticato.post(
        "/api/ask/", {"domanda": "Quanti giorni di ferie?"}, format="json"
    )

    assert risposta.status_code == 500
    assert risposta["Content-Type"].startswith("application/json")
    assert "dettaglio interno" not in risposta.content.decode()


@pytest.mark.django_db
def test_un_documento_inesistente_da_404_in_italiano(client_autenticato):
    """T-34: era «No Document matches the given query.» in un'API italiana."""
    risposta = client_autenticato.get("/api/documents/999999/")
    assert risposta.status_code == 404
    assert risposta.json()["detail"] == "Nessun documento con id 999999."
