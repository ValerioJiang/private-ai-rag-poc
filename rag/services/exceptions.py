"""Eccezioni di dominio del sistema RAG.

Perche' esistono: i servizi devono distinguere un errore ATTESO e imputabile
al documento, alla domanda o alla configurazione — un PDF scansionato, un
duplicato, una strategia non realizzabile, un LLM spento — da un guasto del
sistema. I primi sono esiti PREVISTI (RF-06, RF-10, RF-14, CA-8) e vengono
persistiti in forma leggibile; i secondi restano eccezioni inattese, vengono
comunque persistite (RNF-04) ma anche registrate nel log con lo stack
completo.

Due famiglie con una radice comune:

    RagError
    ├── IngestionError    condizioni dell'ingestione (P2)
    ├── QueryError        condizioni dell'interrogazione (P3)
    └── ConfigurazioneNonSupportata(IngestionError, QueryError)

L'ereditarieta' multipla di ConfigurazioneNonSupportata NON e' un vezzo: le
factory che la sollevano — get_splitter(), get_embeddings(), get_llm() — sono
chiamate da ENTRAMBI i lati. Cosi' `except IngestionError` in
ingest_document() continua a catturarla senza che una riga di ingestion.py
cambi, e `except QueryError` la cattura dal lato interrogazione.

Tutti i messaggi sono scritti per essere letti da un amministratore
nell'admin Django, non da uno sviluppatore in un file di log.
"""


class RagError(Exception):
    """Radice delle condizioni PREVISTE del sistema RAG."""


class IngestionError(RagError):
    """Base delle condizioni imputabili al documento o alla configurazione."""


class QueryError(RagError):
    """Base delle condizioni previste di una interrogazione (P3)."""


class PdfIllegibile(IngestionError):
    """Il file non e' apribile come PDF: corrotto, vuoto o protetto."""


class PdfSenzaTesto(IngestionError):
    """Nessun testo estraibile: probabile scansione senza OCR (RF-10)."""


class FileTroppoGrande(IngestionError):
    """Il file eccede KnowledgeBase.max_file_size_mb (T-44).

    Condizione SINCRONA: la scopre chi carica, non il worker. La coda e'
    seriale, e un file molto grande non fallisce — occupa il worker e ritarda
    ogni altro documento.
    """


class TroppePagine(IngestionError):
    """Il PDF eccede KnowledgeBase.max_page_count (T-44).

    Sincrona come FileTroppoGrande. Il conteggio richiede di aprire il file,
    quindi si esegue SOLO se il limite e' configurato: cfr. la docstring di
    verifica_ammissibilita().
    """


class PdfTestoInsufficiente(IngestionError):
    """Troppe pagine senza testo rispetto a min_text_page_ratio (T-44).

    NON e' PdfSenzaTesto, che copre il caso in cui NESSUNA pagina abbia testo
    (RF-10). Questa copre la scansione PARZIALE, che oggi passa in silenzio:
    un PDF di 100 pagine di cui 10 con testo diventa «Indicizzato» con 10
    segmenti, e nulla dice che il 90% non e' stato indicizzato.

    Asincrona: richiede l'estrazione, quindi la scopre il worker.
    """


class DocumentoDuplicato(IngestionError):
    """Lo stesso file e' gia' presente in questa base di conoscenza (RF-09)."""

    def __init__(self, messaggio: str, *, esistente_id: int | None = None) -> None:
        super().__init__(messaggio)
        self.esistente_id = esistente_id


class ConfigurazioneNonSupportata(IngestionError, QueryError):
    """La configurazione e' una riga di database valida ma non realizzabile.

    Esempi: ChunkingProfile.Splitter.TOKEN, che richiederebbe tiktoken;
    LLMProfile.Provider.OPENAI_COMPATIBLE, che richiederebbe langchain-openai.
    Non e' un errore dell'utente ne' un guasto: e' un limite dichiarato.
    """


class LlmNonRaggiungibile(QueryError):
    """Il servizio di inferenza non risponde, o il modello non e' scaricato.

    E' il caso 4a di UC-2. Due condizioni distinte con una sola classe,
    perche' la reazione dell'amministratore e' la stessa: guardare Ollama.
    Il messaggio le distingue.
    """


class PipelineNonUtilizzabile(QueryError):
    """Nessuna pipeline selezionabile, o quella indicata non e' attiva (RF-15)."""


class DomandaVuota(QueryError):
    """La domanda e' vuota o composta di soli spazi.

    Non e' pedanteria: una domanda vuota produrrebbe un embedding privo di
    significato, un recupero casuale e una risposta inventata su di esso.
    """
