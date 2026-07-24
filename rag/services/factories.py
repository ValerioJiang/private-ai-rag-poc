"""Configurazione (righe di database) → oggetti LangChain.

E' la cerniera dell'architettura (ARCHITECTURE §3): l'unico punto del progetto
che traduce profili in oggetti. Tutto il resto del codice riceve oggetti gia'
costruiti e non sa da dove vengano i parametri. E' il motivo per cui una
modifica dall'admin ha effetto senza toccare il codice.

LA CACHE, E PERCHE' LA CHIAVE CONTIENE I VALORI E NON SOLO L'ID.

Due costruzioni sono costose e si ripeterebbero a ogni richiesta: ChatOllama
con validate_model_on_init (0,73 s, misurato) e PGVector, che esegue DDL nel
proprio __post_init__ (0,85 s, misurato). Vengono memorizzate in un dizionario
di modulo.

NON si usa django.core.cache. LocMemCache serializza con pickle anche restando
in-process, e nessuno dei due oggetti attraversa pickle: contengono un client
httpx e un engine SQLAlchemy, cioe' lock di thread. Verificato —
`cache.set()` solleva «TypeError: cannot pickle '_thread.RLock' object» per
entrambi. Il commento in config/settings/base.py che prescrive LocMemCache per
questo scopo e' da correggere in T-40.

La chiave di ogni voce contiene qualcosa che cambia quando cambia la
CONFIGURAZIONE — updated_at per i profili, index_fingerprint() per la base di
conoscenza — e non solo la chiave primaria. E' cio' che rende corretto RF-22
anche in un processo che non ha ricevuto il post_save, cioe' con piu' worker:
chi interroga rilegge comunque quelle righe a ogni richiesta e vede subito il
valore nuovo. Il receiver di rag/signals.py serve a liberare memoria e a
rendere l'effetto immediato, NON a garantire la correttezza. Chi legge questo
file piu' avanti deve saperlo, altrimenti replichera' la forma senza la
sostanza.

Limite dichiarato: QuerySet.update() aggira sia auto_now sia post_save. Nessun
codice del progetto lo usa sui profili, e l'admin non lo usa.
"""

from __future__ import annotations

import logging
from typing import Callable, TypeVar
from urllib.parse import quote

from django.conf import settings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter, TextSplitter

from ..models import ChunkingProfile, EmbeddingProfile, KnowledgeBase, LLMProfile
from .exceptions import ConfigurazioneNonSupportata, LlmNonRaggiungibile

logger = logging.getLogger(__name__)

T = TypeVar("T")


# --------------------------------------------------------------------------
# Cache in-process (T-21, RF-22)
# --------------------------------------------------------------------------

_CACHE: dict[str, object] = {}

# Limite di guardia, non un LRU. Ogni modifica dall'admin produce una chiave
# nuova, e il receiver di signals.py svuota il dizionario nel processo che ha
# salvato; in un ALTRO processo le voci vecchie resterebbero. Trentadue e' piu'
# di quante configurazioni distinte possano essere in uso davvero, e superarlo
# significa svuotare tutto: la voce successiva costa 0,7-0,9 s di ricostruzione,
# non una perdita di correttezza.
_LIMITE_CACHE = 32


def svuota_cache() -> None:
    """Dimentica gli oggetti costruiti. La chiama il receiver di signals.py.

    Non e' cio' che garantisce RF-22 — lo garantisce la chiave, cfr. la
    docstring di modulo — ma rende l'effetto immediato nel processo che ha
    salvato e impedisce al dizionario di crescere a ogni modifica.
    """
    quanti = len(_CACHE)
    _CACHE.clear()
    if quanti:
        logger.debug("Cache delle factory svuotata (%s voci).", quanti)


def _memoizza(chiave: str, costruisci: Callable[[], T]) -> T:
    """Restituisce l'oggetto associato alla chiave, costruendolo se manca.

    La chiave DEVE contenere i valori della configurazione, non solo il suo
    id: cfr. la docstring di modulo.
    """
    memorizzato = _CACHE.get(chiave)
    if memorizzato is not None:
        return memorizzato  # type: ignore[return-value]
    if len(_CACHE) >= _LIMITE_CACHE:
        svuota_cache()
    costruito = costruisci()
    _CACHE[chiave] = costruito
    logger.debug("Costruito e memorizzato: %s", chiave)
    return costruito


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


def get_llm(profile: LLMProfile) -> BaseChatModel:
    """Costruisce il modello di generazione descritto dal profilo (T-21, RF-22).

    A differenza di get_embeddings(), l'endpoint viene DAL PROFILO
    (LLMProfile.base_url) e non da settings: e' l'asimmetria dichiarata in
    ARCHITECTURE §9 e nel help_text del campo. Spostare la generazione su un
    altro host e' una funzionalita' richiesta; spostare gli embedding no,
    perche' aggiungerebbe un secondo punto d'uscita per il testo dei documenti
    senza alcun beneficio.

    validate_model_on_init=True costa una chiamata a /api/tags (0,73 s alla
    costruzione, misurato) e vale il prezzo: e' il punto in cui «modello non
    scaricato» e «Ollama spento» diventano messaggi leggibili invece di un
    guasto a meta' generazione. E' il gemello di verify_embedding_dimension().

    TRAPPOLA VERIFICATA — le due condizioni sollevano eccezioni di famiglie
    DIVERSE:

      - modello non scaricato -> pydantic_core.ValidationError, che e'
        sottoclasse di ValueError;
      - Ollama spento -> ConnectionError BUILTIN, sottoclasse di OSError, che
        sfugge del tutto al validatore pydantic.

    Un `except ValueError` da solo lascerebbe passare il secondo — che e' il
    caso piu' frequente — come guasto inatteso. Da qui `(ValueError, OSError)`.

    Il risultato e' memorizzato: cfr. la docstring di modulo per il perche'
    della chiave.

    Solleva:
        ConfigurazioneNonSupportata: provider dichiarato nell'enum ma non
            realizzabile in questa installazione.
        LlmNonRaggiungibile: servizio spento o modello non disponibile.
    """
    if profile.provider != LLMProfile.Provider.OLLAMA:
        # Il provider «API OpenAI-compatibile» richiederebbe langchain-openai,
        # che non e' fra le dipendenze (verificato: ModuleNotFoundError). Il
        # valore resta nell'enum come alternativa documentata, non come opzione
        # attivabile. Stessa forma del rifiuto di «huggingface» in
        # get_embeddings().
        raise ConfigurazioneNonSupportata(
            f"Il profilo LLM «{profile.name}» usa il provider "
            f"«{profile.get_provider_display()}», che questa installazione non "
            "realizza: richiederebbe il pacchetto langchain-openai, escluso "
            "dalle dipendenze perche' il progetto genera solo in locale "
            "(ARCHITECTURE §9). Selezionare il provider «Ollama»."
        )

    def costruisci() -> BaseChatModel:
        try:
            return ChatOllama(
                model=profile.model_name,
                base_url=profile.base_url,
                temperature=profile.temperature,
                top_p=profile.top_p,
                top_k=profile.top_k,
                # In Ollama il limite di token GENERATI si chiama num_predict.
                # ChatOllama non ha un campo max_tokens: verificato sui
                # model_fields della 1.1.0.
                num_predict=profile.max_tokens,
                validate_model_on_init=True,
                # ChatOllama non espone un campo timeout: i kwargs finiscono
                # a httpx attraverso ollama.Client(host=..., **kwargs).
                # Verificato sul sorgente di _set_clients().
                client_kwargs={"timeout": profile.timeout_s},
            )
        except (ValueError, OSError) as exc:
            raise LlmNonRaggiungibile(
                f"Il modello «{profile.model_name}» del profilo «{profile.name}» "
                f"non e' utilizzabile su {profile.base_url}: {exc}. Verificare "
                f"che Ollama sia in esecuzione e che il modello sia stato "
                f"scaricato (`ollama pull {profile.model_name}`)."
            ) from exc

    return _memoizza(f"llm:{profile.pk}:{profile.updated_at.timestamp()}", costruisci)


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

    MEMORIZZATO da T-21, e la chiave e' la coppia (id, impronta dei profili
    d'indice): cambiare modello di embedding produce una chiave nuova, quindi
    un oggetto nuovo. E' anche il motivo per cui il DDL di cui sopra si paga
    UNA volta per processo e non a ogni richiesta.

    CONSEGUENZA da conoscere: al secondo passaggio con la stessa chiave
    l'argomento `embeddings` viene IGNORATO, perche' l'oggetto memorizzato e'
    gia' costruito. Non e' un problema — l'impronta nella chiave copre i valori
    del profilo di embedding, quindi due oggetti con la stessa chiave sono
    equivalenti — ma va saputo prima di passare un embeddings «speciale»
    aspettandosi che venga usato.

    Secondo limite dichiarato: l'oggetto memorizzato tiene vivo un engine
    SQLAlchemy. Se il database viene riavviato, la voce in cache resta e le sue
    connessioni sono da riaprire; il pool di SQLAlchemy lo fa da se', ma una
    collezione cancellata a mano DA FUORI non verrebbe piu' ricreata dal DDL
    finche' la voce resta.
    """
    def costruisci() -> PGVector:
        return PGVector(
            embeddings=embeddings or get_embeddings(knowledge_base.embedding_profile),
            collection_name=knowledge_base.collection_name,
            connection=connection_string(),
            use_jsonb=True,
            create_extension=False,
        )

    return _memoizza(
        f"store:{knowledge_base.pk}:{knowledge_base.index_fingerprint()}", costruisci
    )
