"""Configurazione (righe di database) → oggetti LangChain.

E' la cerniera dell'architettura (ARCHITECTURE §3): l'unico punto del progetto
che traduce profili in oggetti. Tutto il resto del codice riceve oggetti gia'
costruiti e non sa da dove vengano i parametri. E' il motivo per cui una
modifica dall'admin ha effetto senza toccare il codice.

In P2 esistono solo le tre factory della configurazione d'INDICE. get_llm() e
get_retriever() sono T-21 e T-22, in P3, insieme alla cache invalidata da
post_save: NON anticiparle qui.
"""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter, TextSplitter

from ..models import ChunkingProfile, EmbeddingProfile, KnowledgeBase
from .exceptions import ConfigurazioneNonSupportata


def connection_string() -> str:
    """URL SQLAlchemy verso lo STESSO database di Django.

    Due ORM e due driver sullo stesso database sono il prezzo dichiarato di
    ARCHITECTURE §7.9, non una svista. Le credenziali vanno quotate: una
    password contenente «@», «/» o «:» romperebbe l'URL in silenzio, e il
    messaggio d'errore parlerebbe di host inesistenti.
    """
    d = settings.DATABASES["default"]
    utente = quote(str(d["USER"]), safe="")
    password = quote(str(d["PASSWORD"]), safe="")
    return f"postgresql+psycopg://{utente}:{password}@{d['HOST']}:{d['PORT']}/{d['NAME']}"


def get_splitter(profile: ChunkingProfile) -> TextSplitter:
    """Costruisce lo splitter descritto dal profilo (RF-19).

    Solleva:
        ConfigurazioneNonSupportata: strategia dichiarata nell'enum ma non
            realizzabile in questa installazione.
    """
    if profile.splitter == ChunkingProfile.Splitter.RECURSIVE:
        parametri: dict = {
            "chunk_size": profile.chunk_size,
            "chunk_overlap": profile.chunk_overlap,
            # Aggiunge start_index ai metadata: e' l'offset del chunk dentro la
            # pagina, utile all'estratto delle citazioni di P3 (RF-13).
            "add_start_index": True,
        }
        # ATTENZIONE: separators vuoto significa «usa i predefiniti dello
        # splitter», non «nessun separatore». Passare [] esplicitamente
        # disattiverebbe ogni confine di paragrafo e produrrebbe un taglio
        # cieco a chunk_size caratteri — l'opposto di cio' che
        # ARCHITECTURE §7.4 sceglie. Il campo e' blank=True proprio per
        # significare «predefiniti».
        if profile.separators:
            parametri["separators"] = list(profile.separators)
        return RecursiveCharacterTextSplitter(**parametri)

    if profile.splitter == ChunkingProfile.Splitter.TOKEN:
        # Limite dichiarato, non dimenticanza. tiktoken implementa i BPE di
        # OpenAI: usarlo per dimensionare i chunk di qwen2.5 e bge-m3
        # significherebbe misurare col metro sbagliato, producendo un
        # conteggio plausibile e falso. Meglio rifiutare in modo esplicito.
        raise ConfigurazioneNonSupportata(
            f"Il profilo di segmentazione «{profile.name}» usa la strategia "
            "«basato su token», che questa installazione non realizza: "
            "TokenTextSplitter richiede il pacchetto tiktoken, deliberatamente "
            "escluso dalle dipendenze. Selezionare «Recursive character» nel "
            "profilo di segmentazione."
        )

    raise ConfigurazioneNonSupportata(
        f"Strategia di segmentazione sconosciuta: {profile.splitter!r}."
    )


def get_embeddings(profile: EmbeddingProfile) -> Embeddings:
    """Costruisce il modello di embedding descritto dal profilo.

    L'endpoint NON viene dal profilo: e' settings.OLLAMA_BASE_URL. E' una
    scelta di P1 (decisione 2 del piano di P1) e di ARCHITECTURE §9: il testo
    dei chunk deve avere un solo punto di uscita possibile, e renderlo
    configurabile ne aggiungerebbe un secondo senza alcun beneficio.

    normalize NON viene applicato: misurato in fase di pianificazione, bge-m3
    restituisce gia' vettori a norma 1,000000, e PGVector usa distanza cosine,
    che e' invariante alla scala. Un decoratore che normalizza sarebbe codice
    dimostrabilmente inerte. La descrizione nell'admin lo dichiara.

    dimension non viene passato al costruttore: cfr. verify_embedding_dimension.
    """
    if profile.provider != EmbeddingProfile.Provider.OLLAMA:
        # Il provider «huggingface» dell'enum richiederebbe
        # sentence-transformers e quindi torch (~2,5 GB), che
        # ARCHITECTURE §7.3 esclude esplicitamente. Il valore resta nell'enum
        # come alternativa documentata, non come opzione attivabile.
        raise ConfigurazioneNonSupportata(
            f"Il profilo di embedding «{profile.name}» usa il provider "
            f"«{profile.get_provider_display()}», che questa installazione non "
            "realizza: richiederebbe sentence-transformers e torch, esclusi per "
            "scelta (ARCHITECTURE §7.3). Selezionare il provider «Ollama»."
        )
    return OllamaEmbeddings(
        model=profile.model_name,
        base_url=settings.OLLAMA_BASE_URL,
    )


def verify_embedding_dimension(embeddings: Embeddings, profile: EmbeddingProfile) -> int:
    """Verifica che il modello produca vettori della dimensione dichiarata.

    Serve perche' la colonna creata da langchain-postgres e' `vector` SENZA
    dimensione (verificato in P0): il database NON rifiuterebbe un vettore di
    lunghezza sbagliata, e l'indice si corromperebbe in silenzio. Il controllo
    trasforma EmbeddingProfile.dimension da campo descrittivo in invariante
    verificato (ARCHITECTURE §8.1).

    Costa una chiamata di embedding (≈0,8 s a caldo, fino a ~18 s a freddo) e
    ha un secondo effetto utile: e' il punto in cui «Ollama e' spento» diventa
    un messaggio leggibile, prima che il documento passi a «In elaborazione».
    """
    try:
        sonda = embeddings.embed_query("verifica della dimensione del vettore")
    except Exception as exc:  # noqa: BLE001 - qualunque guasto va tradotto
        raise ConfigurazioneNonSupportata(
            f"Il servizio di embedding non risponde su {settings.OLLAMA_BASE_URL}: "
            f"{exc}. Verificare che Ollama sia in esecuzione e che il modello "
            f"«{profile.model_name}» sia stato scaricato (`ollama pull "
            f"{profile.model_name}`)."
        ) from exc

    if len(sonda) != profile.dimension:
        raise ConfigurazioneNonSupportata(
            f"Il modello «{profile.model_name}» produce vettori di "
            f"{len(sonda)} dimensioni, ma il profilo «{profile.name}» dichiara "
            f"{profile.dimension}. Correggere il profilo oppure cambiare "
            "modello: indicizzare con questa incoerenza renderebbe il recupero "
            "inaffidabile senza alcun errore visibile."
        )
    return len(sonda)


def get_vectorstore(
    knowledge_base: KnowledgeBase, *, embeddings: Embeddings | None = None
) -> PGVector:
    """Costruisce il vector store della base di conoscenza.

    ATTENZIONE — costruire questo oggetto ha EFFETTI COLLATERALI. Verificato
    sul sorgente della 0.0.17: PGVector.__post_init__ esegue DDL a ogni
    costruzione — create_tables_if_not_exists() e create_collection() — su una
    connessione SQLAlchemy distinta da quella di Django. Due conseguenze
    operative:

    1. si costruisce UNA volta per ingestione, mai dentro un ciclo sui lotti;
    2. create_extension=False, perche' la migrazione 0001 ha gia' installato
       l'estensione e ripetere CREATE EXTENSION a ogni costruzione e' DDL
       inutile.

    Il lato positivo di quel DDL: la collezione di una base di conoscenza nuova
    viene creata alla prima ingestione, senza bisogno di alcun passo esplicito.

    embeddings e' iniettabile per non pagare due volte la costruzione quando il
    chiamante lo ha gia'.
    """
    return PGVector(
        embeddings=embeddings or get_embeddings(knowledge_base.embedding_profile),
        collection_name=knowledge_base.collection_name,
        connection=connection_string(),
        use_jsonb=True,
        create_extension=False,
    )
