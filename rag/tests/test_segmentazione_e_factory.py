"""T-36 — la segmentazione e le factory seguono la configurazione (RF-19, RF-22).

E' il test del requisito CENTRALE della traccia: nessun parametro di
comportamento sta nel codice. Prova due cose distinte che e' facile
confondere:

1. che i valori del profilo arrivino davvero agli oggetti costruiti;
2. che una MODIFICA del profilo abbia effetto senza riavvio — e in
   particolare in un processo che il post_save non lo riceve mai, cioe' il
   worker. E' quest'ultima la parte che vale, perche' e' quella che un
   progetto puo' sbagliare restando verde.

NESSUN TEST DI QUESTO FILE TOCCA LA RETE. Tutto cio' che parlerebbe con
Ollama e' sostituito: ChatOllama da un doppio (test della cache),
Embeddings da EmbeddingsFinti e da una classe che solleva ConnectionError
(test di verify_embedding_dimension). get_splitter() e index_fingerprint()
non hanno mai avuto nulla a che fare con la rete. La suite gira quindi con
Ollama spento, ed e' un requisito della fase, non una coincidenza.

Gli import del progetto stanno DENTRO le funzioni, come in conftest.py: la
raccolta di pytest importa il modulo prima che pytest-django abbia
configurato Django.
"""

import pytest


# ----------------------------------------------------------------------
# Segmentazione: i valori del profilo arrivano allo splitter (RF-19)
# ----------------------------------------------------------------------


def test_lo_splitter_usa_dimensione_e_sovrapposizione_del_profilo():
    """RF-19: chunk_size e chunk_overlap non sono scritti nel codice."""
    from rag.models import ChunkingProfile
    from rag.services.factories import get_splitter

    profilo = ChunkingProfile(
        name="prova",
        splitter=ChunkingProfile.Splitter.RECURSIVE,
        chunk_size=200,
        chunk_overlap=0,
        separators=[],
    )
    pezzi = get_splitter(profilo).split_text("parola " * 200)

    assert len(pezzi) > 1
    assert all(len(p) <= 200 for p in pezzi)


def test_cambiare_il_profilo_cambia_la_segmentazione():
    """RF-22 sul lato indice: due profili, due esiti, nessuna riga di codice."""
    from rag.models import ChunkingProfile
    from rag.services.factories import get_splitter

    testo = "parola " * 400

    def quanti(dimensione: int) -> int:
        profilo = ChunkingProfile(
            name=f"prova-{dimensione}",
            splitter=ChunkingProfile.Splitter.RECURSIVE,
            chunk_size=dimensione,
            chunk_overlap=0,
            separators=[],
        )
        return len(get_splitter(profilo).split_text(testo))

    assert quanti(200) > quanti(1000)


def test_separatori_vuoti_significano_i_predefiniti_non_nessun_separatore():
    """factories.py, get_splitter(): e' la trappola che quel commento descrive.

    Passare [] a RecursiveCharacterTextSplitter disattiverebbe ogni confine di
    paragrafo e taglierebbe a chunk_size caratteri esatti. Il test lo osserva
    dal COMPORTAMENTO e non dagli attributi privati dello splitter: con i
    separatori predefiniti il taglio cade sulla riga vuota, quindi nessun
    segmento contiene entrambi i blocchi.
    """
    from rag.models import ChunkingProfile
    from rag.services.factories import get_splitter

    testo = "a" * 100 + "\n\n" + "b" * 100
    profilo = ChunkingProfile(
        name="predefiniti",
        splitter=ChunkingProfile.Splitter.RECURSIVE,
        chunk_size=150,
        chunk_overlap=0,
        separators=[],
    )
    pezzi = get_splitter(profilo).split_text(testo)

    assert all(not ("a" in p and "b" in p) for p in pezzi)


# ----------------------------------------------------------------------
# I limiti dichiarati sono limiti, non guasti
# ----------------------------------------------------------------------


def test_la_strategia_a_token_e_un_limite_dichiarato():
    """ARCHITECTURE §7.4: tiktoken misurerebbe qwen2.5 col metro di OpenAI."""
    from rag.models import ChunkingProfile
    from rag.services.exceptions import ConfigurazioneNonSupportata
    from rag.services.factories import get_splitter

    profilo = ChunkingProfile(
        name="token",
        splitter=ChunkingProfile.Splitter.TOKEN,
        chunk_size=800,
        chunk_overlap=120,
    )
    with pytest.raises(ConfigurazioneNonSupportata) as errore:
        get_splitter(profilo)
    assert "tiktoken" in str(errore.value)


def test_il_provider_huggingface_e_un_limite_dichiarato():
    """ARCHITECTURE §7.3: richiederebbe torch, ~2,5 GB."""
    from rag.models import EmbeddingProfile
    from rag.services.exceptions import ConfigurazioneNonSupportata
    from rag.services.factories import get_embeddings

    profilo = EmbeddingProfile(
        name="hf",
        provider=EmbeddingProfile.Provider.HUGGINGFACE,
        model_name="qualunque",
        dimension=1024,
    )
    with pytest.raises(ConfigurazioneNonSupportata) as errore:
        get_embeddings(profilo)
    assert "sentence-transformers" in str(errore.value)


def test_il_provider_openai_compatibile_e_un_limite_dichiarato():
    """RNF-01: langchain-openai e' escluso perche' si genera solo in locale."""
    from rag.models import LLMProfile
    from rag.services.exceptions import ConfigurazioneNonSupportata
    from rag.services.factories import get_llm

    profilo = LLMProfile(
        name="openai",
        provider=LLMProfile.Provider.OPENAI_COMPATIBLE,
        model_name="gpt-qualunque",
    )
    with pytest.raises(ConfigurazioneNonSupportata) as errore:
        get_llm(profilo)
    assert "langchain-openai" in str(errore.value)


# ----------------------------------------------------------------------
# verify_embedding_dimension(): l'invariante di ARCHITECTURE §8.1
# ----------------------------------------------------------------------


def test_la_dimensione_dichiarata_e_un_invariante_verificato():
    """§8.1: la colonna pgvector non ha dimensione, quindi il DB non protegge."""
    from rag.models import EmbeddingProfile
    from rag.services.exceptions import ConfigurazioneNonSupportata
    from rag.services.factories import verify_embedding_dimension
    from rag.tests.conftest import EmbeddingsFinti

    profilo = EmbeddingProfile(name="p", model_name="bge-m3", dimension=1024)

    assert verify_embedding_dimension(EmbeddingsFinti(1024), profilo) == 1024

    with pytest.raises(ConfigurazioneNonSupportata) as errore:
        verify_embedding_dimension(EmbeddingsFinti(384), profilo)
    assert "384" in str(errore.value) and "1024" in str(errore.value)


def test_il_servizio_di_embedding_spento_diventa_un_messaggio_leggibile():
    """E' il punto in cui «Ollama e' spento» smette di essere uno stack."""
    from rag.models import EmbeddingProfile
    from rag.services.exceptions import ConfigurazioneNonSupportata
    from rag.services.factories import verify_embedding_dimension

    class EmbeddingsSpenti:
        def embed_query(self, testo):
            raise ConnectionError("[WinError 10061] connessione rifiutata")

    profilo = EmbeddingProfile(name="p", model_name="bge-m3", dimension=1024)
    with pytest.raises(ConfigurazioneNonSupportata) as errore:
        verify_embedding_dimension(EmbeddingsSpenti(), profilo)
    assert "ollama pull bge-m3" in str(errore.value)


# ----------------------------------------------------------------------
# La cache: e' la CHIAVE a garantire RF-22, non il receiver dei segnali
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_la_cache_segue_la_configurazione_anche_senza_il_segnale(
    monkeypatch, processo_senza_segnali
):
    """RF-22, il caso del worker (factories.py, docstring di modulo).

    Con il receiver scollegato — cioe' in un processo che il post_save non lo
    riceve mai — una modifica al profilo DEVE comunque produrre un oggetto
    nuovo. Se la chiave contenesse il solo pk, la terza asserzione
    fallirebbe: e' l'unico modo di provare che a garantire RF-22 e' la
    chiave, e non il receiver.

    CONTROPROVA ESEGUITA in P6 e riportata nel report della fase: sostituendo
    la chiave di get_llm() con f"llm:{profile.pk}" questo test fallisce sulla
    seconda asserzione su len(costruzioni), con il messaggio scritto qui
    sotto. Un test che non puo' fallire non prova nulla.
    """
    from rag.models import LLMProfile
    from rag.services import factories

    costruzioni = []

    class ChatOllamaFinto:
        def __init__(self, **kwargs):
            costruzioni.append(kwargs)

    monkeypatch.setattr(factories, "ChatOllama", ChatOllamaFinto)

    profilo = LLMProfile.objects.create(
        name="prova", model_name="qwen2.5:7b-instruct", temperature=0.0
    )

    factories.get_llm(profilo)
    factories.get_llm(profilo)
    assert len(costruzioni) == 1, "il secondo passaggio doveva usare la cache"

    profilo.temperature = 0.7
    profilo.save()                      # auto_now aggiorna updated_at
    profilo.refresh_from_db()

    factories.get_llm(profilo)
    assert len(costruzioni) == 2, (
        "la chiave non segue i valori della configurazione: contiene "
        "probabilmente il solo pk"
    )
    assert costruzioni[-1]["temperature"] == 0.7


@pytest.mark.django_db
def test_l_impronta_dell_indice_cambia_se_il_profilo_cambia_sul_posto(
    pipeline_predefinita,
):
    """RF-25: e' il caso realistico — dall'admin si modificano i profili
    esistenti, quindi l'FK resta identica e a cambiare sono i VALORI."""
    kb = pipeline_predefinita.knowledge_base
    prima = kb.index_fingerprint()

    kb.chunking_profile.chunk_size = 1200
    kb.chunking_profile.save()
    kb.refresh_from_db()

    assert kb.index_fingerprint() != prima


# ----------------------------------------------------------------------
# L'estratto: configurazione anch'esso, da P6
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_la_lunghezza_dell_estratto_viene_dal_profilo(pipeline_predefinita):
    """RF-22 applicato al debito chiuso in P6: era una costante di modulo."""
    from langchain_core.documents import Document as LCDocument

    from rag.models import RetrievalProfile
    from rag.services.query import esegui_ricerca
    from rag.tests.conftest import VectorStoreFinto

    lungo = LCDocument(page_content="x" * 500, metadata={"page": 1})
    store = VectorStoreFinto(risultati=[(lungo, 0.3)])

    profilo = pipeline_predefinita.retrieval_profile
    profilo.search_type = RetrievalProfile.SearchType.SIMILARITY

    profilo.excerpt_length = 50
    corto = esegui_ricerca(store, profilo, "domanda")[0].estratto

    profilo.excerpt_length = 400
    lungo_estratto = esegui_ricerca(store, profilo, "domanda")[0].estratto

    assert len(corto) == 51            # 50 caratteri piu' l'ellissi
    assert len(lungo_estratto) == 401
