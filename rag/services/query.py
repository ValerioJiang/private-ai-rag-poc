"""Interrogazione: configurazione → segmenti → risposta con fonti.

E' il gemello di ingestion.py sul lato lettura, e come quello e' l'unico punto
in cui le due meta' dello schema si incontrano — qui pero' nella direzione
opposta: da un vettore recuperato si risale alla riga DocumentChunk, sempre
attraverso l'id deterministico «<document_id>:<ordinal>».

IL PUNTEGGIO ESPOSTO E' LA RILEVANZA, NON LA DISTANZA. Vale la pena scriverlo
in intestazione perche' e' la decisione che, sbagliata, produrrebbe un sistema
che ordina le fonti al contrario senza che nulla lo segnali.
PGVector.similarity_search_with_score() restituisce una DISTANZA cosine: cresce
al peggiorare della pertinenza. RF-13 chiede un «punteggio di similarita'» e
RF-14 una soglia, e RetrievalProfile.score_threshold e' dichiarato fra 0 e 1
con la semantica «piu' alto = piu' pertinente». La conversione avviene in un
solo punto — rilevanza() — e da li' in poi nel sistema circola una sola
grandezza.

Misure prese sul corpus reale il 25/07/2026 (3 segmenti, bge-m3), che sono
anche la giustificazione della soglia predefinita di 0,5:

    domanda pertinente          rilevanza 0,68-0,73
    stesso documento, altra pagina        0,35-0,46
    domanda fuori tema                    0,15-0,26

PERCHE' NON as_retriever(). Un VectorStoreRetriever restituisce list[Document]
e i punteggi si perdono, ma RF-13 (fonti col punteggio) e RF-16
(RetrievedChunk.score, FloatField non nullo) li richiedono. Si usano quindi i
metodi *_with_score di PGVector, che esistono per tutte e tre le strategie.
L'alternativa — retriever per il contesto piu' una seconda ricerca per le
fonti — costerebbe due embedding della stessa domanda (~1,2 s buttati) e
rischierebbe di mostrare fonti diverse dai segmenti effettivamente passati
all'LLM, perche' MMR non e' deterministico rispetto a fetch_k. Una citazione
che non corrisponde al contesto e' peggio di nessuna citazione.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

import httpx
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from ..models import (
    RISPOSTA_NON_DISPONIBILE,
    DocumentChunk,
    PromptTemplate as ProfiloPrompt,   # alias: il nome collide con quello di
                                       # langchain_core.prompts. Cfr. la
                                       # docstring del modello.
    RagPipeline,
    RetrievalProfile,
)
from .exceptions import DomandaVuota, LlmNonRaggiungibile, PipelineNonUtilizzabile
from .factories import get_llm, get_vectorstore
from .ingestion import vector_id

logger = logging.getLogger(__name__)

# Quanto testo di un segmento finisce nelle fonti mostrate all'utente. Il testo
# INTERO resta in SegmentoRecuperato.testo e va all'LLM: questo taglio riguarda
# solo la citazione, che deve stare in una riga di terminale o in un JSON
# leggibile.
LUNGHEZZA_ESTRATTO = 300


def rilevanza(distanza: float) -> float:
    """Converte la distanza cosine di pgvector in un punteggio di similarita'.

    Non e' una formula inventata: e' la stessa di
    langchain_core.vectorstores.VectorStore._cosine_relevance_score_fn, cioe'
    il numero che LangChain confronterebbe con score_threshold nella strategia
    «similarity_score_threshold». Usarla significa che il numero MOSTRATO
    all'utente e quello CONFRONTATO con la soglia sono lo stesso numero.

    NON si tronca a zero. Con vettori normalizzati la distanza cosine sta in
    [0, 2], quindi un segmento agli antipodi della domanda produce una
    rilevanza negativa. Nasconderlo farebbe sembrare «poco pertinente» cio' che
    e' «opposto», e il caso non si e' mai presentato nelle misure reali
    (minimo osservato: 0,1463).
    """
    return 1.0 - distanza


@dataclass(frozen=True)
class SegmentoRecuperato:
    """Un segmento restituito dalla ricerca, con la sua provenienza (RF-13).

    I metadata arrivano dal vettore e non da una seconda interrogazione: sono
    stati scritti dall'ingestione (loaders.py e ingestion.py) e riletti dal
    database in chiusura di P2. Quelli disponibili sono esattamente: page,
    source, ordinal, documento, document_id, knowledge_base_id, start_index.

    Il vector_id NON e' fra i metadata: si RICOSTRUISCE da document_id e
    ordinal, perche' e' deterministico. E' la stessa proprieta' che in P2
    permetteva di cancellare i vettori a righe DocumentChunk gia' sparite,
    usata qui nella direzione opposta.
    """

    testo: str
    punteggio: float          # RILEVANZA: e' cio' che si mostra e si confronta
    distanza: float           # grandezza grezza restituita da pgvector
    vector_id: str
    documento: str
    document_id: int | None
    pagina: int | None
    ordinale: int | None
    chunk_id: int | None = None

    @property
    def estratto(self) -> str:
        if len(self.testo) <= LUNGHEZZA_ESTRATTO:
            return self.testo
        return self.testo[:LUNGHEZZA_ESTRATTO] + "…"

    def come_fonte(self) -> dict:
        """La fonte come la vede chi legge la risposta (RF-13).

        Quattro campi richiesti dal requisito — documento, pagina, estratto,
        punteggio — piu' due che servono a chi deve poi ritrovare il segmento.
        La distanza NON compare: e' il dato interno di cui la rilevanza e' la
        traduzione, e mostrarle entrambe lascerebbe ambiguo quale sia
        confrontata con la soglia.
        """
        return {
            "documento": self.documento,
            "document_id": self.document_id,
            "pagina": self.pagina,
            "ordinale": self.ordinale,
            "estratto": self.estratto,
            "punteggio": round(self.punteggio, 4),
        }


def _da_documento_langchain(documento, distanza: float) -> SegmentoRecuperato:
    """Traduce un (Document, distanza) di LangChain in un SegmentoRecuperato."""
    md = documento.metadata or {}
    document_id = md.get("document_id")
    ordinale = md.get("ordinal")
    # Un vettore scritto prima di P2, o da un'altra applicazione, potrebbe non
    # avere questi metadata: in quel caso non e' collegabile a un DocumentChunk
    # e resta comunque citabile con cio' che ha.
    identificativo = (
        vector_id(document_id, ordinale)
        if document_id is not None and ordinale is not None
        else ""
    )
    return SegmentoRecuperato(
        testo=documento.page_content,
        punteggio=rilevanza(distanza),
        distanza=distanza,
        vector_id=identificativo,
        documento=md.get("documento") or "(documento sconosciuto)",
        document_id=document_id,
        pagina=md.get("page"),
        ordinale=ordinale,
    )


def collega_ai_chunk(segmenti: list[SegmentoRecuperato]) -> list[SegmentoRecuperato]:
    """Associa a ogni segmento la riga DocumentChunk corrispondente.

    Serve a RetrievedChunk.chunk (T-26). UNA sola query per l'intera lista, e
    nessuna euristica sul testo: si passa per vector_id, che e' indicizzato
    (db_index=True) e deterministico.

    Un segmento senza riga corrispondente resta con chunk_id a None: e' il caso
    di un vettore orfano — documento cancellato mentre la ricerca era in
    corso — e RetrievedChunk.chunk e' nullable proprio per questo.
    """
    identificativi = [s.vector_id for s in segmenti if s.vector_id]
    if not identificativi:
        return segmenti
    mappa = dict(
        DocumentChunk.objects.filter(vector_id__in=identificativi).values_list(
            "vector_id", "pk"
        )
    )
    mancanti = [i for i in identificativi if i not in mappa]
    if mancanti:
        logger.warning(
            "Recuperati %s vettori senza riga DocumentChunk (%s): probabile "
            "vettore orfano. La fonte resta citabile, ma non finira' nello "
            "storico dei segmenti recuperati.",
            len(mancanti), ", ".join(mancanti[:5]),
        )
    return [replace(s, chunk_id=mappa.get(s.vector_id)) for s in segmenti]


def esegui_ricerca(store, profilo: RetrievalProfile, domanda: str) -> list[SegmentoRecuperato]:
    """Recupera i segmenti secondo la strategia configurata (T-22, RF-20).

    Sostituisce get_retriever(): cfr. l'intestazione del modulo per il perche'
    un VectorStoreRetriever non e' utilizzabile qui.

    I tre valori di RetrievalProfile.SearchType sono le stringhe di LangChain,
    e i vincoli di database garantiscono gia' fetch_k >= top_k e le soglie
    dentro [0, 1]: non si rivalida nulla qui.
    """
    if profilo.search_type == RetrievalProfile.SearchType.MMR:
        grezzi = store.max_marginal_relevance_search_with_score(
            domanda,
            k=profilo.top_k,
            fetch_k=profilo.fetch_k,
            lambda_mult=profilo.lambda_mult,
        )
    else:
        # similarity e similarity_score_threshold condividono la ricerca: la
        # soglia e' un filtro applicato DOPO, esattamente come fa LangChain in
        # similarity_search_with_relevance_scores. Conseguenza da conoscere:
        # con top_k=4 e soglia alta si possono ottenere zero risultati anche se
        # il quinto segmento della collezione l'avrebbe superata.
        grezzi = store.similarity_search_with_score(domanda, k=profilo.top_k)

    segmenti = [_da_documento_langchain(d, punteggio) for d, punteggio in grezzi]

    if profilo.search_type == RetrievalProfile.SearchType.THRESHOLD:
        prima = len(segmenti)
        segmenti = [s for s in segmenti if s.punteggio >= profilo.score_threshold]
        if prima and not segmenti:
            # Non e' un errore: e' il caso RF-14, e va reso OSSERVABILE perche'
            # altrimenti una soglia troppo alta somiglierebbe a un indice vuoto.
            logger.info(
                "Nessuno dei %s segmenti recuperati supera la soglia %.2f del "
                "profilo «%s»: la risposta sara' la dichiarazione di non "
                "conoscenza (RF-14).",
                prima, profilo.score_threshold, profilo.name,
            )
        elif prima != len(segmenti):
            logger.debug(
                "Soglia %.2f: %s segmenti su %s conservati.",
                profilo.score_threshold, len(segmenti), prima,
            )

    return collega_ai_chunk(segmenti)


def formatta_contesto(segmenti: list[SegmentoRecuperato]) -> str:
    """Compone il contesto da passare all'LLM.

    L'intestazione di ogni blocco contiene il NOME DEL DOCUMENTO oltre alla
    pagina — lo spike citava la sola pagina, che basta con un documento solo e
    diventa ambigua con due. Serve anche al modello: e' l'unica informazione
    con cui puo' dire «secondo il manuale X» invece di «secondo il contesto».
    """
    return "\n\n".join(
        f"[{s.documento}, pagina {s.pagina}]\n{s.testo}" for s in segmenti
    )


def build_prompt(profilo: ProfiloPrompt) -> ChatPromptTemplate:
    """Compone il prompt dai due campi modificabili dall'admin (RF-21).

    IL PROMPT DI SISTEMA NON E' UN TEMPLATE, ed e' una scelta di correttezza.
    ChatPromptTemplate.from_messages([("system", testo), …]) estrarrebbe le
    {…} ANCHE dal prompt di sistema: un amministratore che vi scrivesse una
    graffa — un esempio JSON, una formula — romperebbe ogni richiesta
    successiva con un KeyError al momento dell'invoke. Il campo e' modificabile
    dall'admin per requisito, quindi e' una porta aperta.

    Passando un SystemMessage GIA' COSTRUITO, LangChain lo inserisce
    letteralmente. Verificato: input_variables resta ['context', 'question'] e
    una graffa nel prompt di sistema arriva intatta al modello.

    I VALORI sostituiti non vengono ri-analizzati (verificato), quindi anche una
    graffa nel testo di un chunk e' innocua.
    """
    return ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=profilo.system_prompt),
            HumanMessagePromptTemplate.from_template(profilo.template),
        ]
    )


def seleziona_pipeline(riferimento: str | int | None = None) -> RagPipeline:
    """Sceglie la pipeline dell'interrogazione (RF-15).

    Tre forme accettate, nell'ordine: id numerico, nome esatto, oppure —
    se il riferimento manca — la pipeline predefinita (RF-26).

    Una pipeline NON ATTIVA e' rifiutata anche se richiesta esplicitamente:
    is_active esiste per poter ritirare una configurazione senza cancellarla,
    e onorarla solo quando comodo la svuoterebbe di significato.
    """
    base = RagPipeline.objects.select_related(
        "knowledge_base",
        "knowledge_base__embedding_profile",
        "knowledge_base__chunking_profile",
        "llm_profile",
        "retrieval_profile",
        "prompt_template",
    )

    if riferimento is None or riferimento == "":
        pipeline = base.filter(is_default=True).first()
        if pipeline is None:
            disponibili = ", ".join(
                RagPipeline.objects.filter(is_active=True).values_list("name", flat=True)
            )
            raise PipelineNonUtilizzabile(
                "Nessuna pipeline predefinita configurata. Indicarne una "
                f"esplicitamente, oppure designarne una come predefinita "
                f"nell'admin. Attive: {disponibili or 'nessuna'}."
            )
    else:
        testo = str(riferimento)
        pipeline = (
            base.filter(pk=int(testo)).first()
            if testo.isdigit()
            else base.filter(name=testo).first()
        )
        if pipeline is None:
            disponibili = ", ".join(
                RagPipeline.objects.filter(is_active=True).values_list("name", flat=True)
            )
            raise PipelineNonUtilizzabile(
                f"Pipeline «{riferimento}» inesistente. Attive: "
                f"{disponibili or 'nessuna'}."
            )

    if not pipeline.is_active:
        raise PipelineNonUtilizzabile(
            f"La pipeline «{pipeline.name}» non e' attiva: riattivarla "
            "dall'admin oppure sceglierne un'altra."
        )
    return pipeline


@dataclass(frozen=True)
class CatenaRag:
    """Cio' che serve per rispondere, gia' costruito dalla configurazione.

    NON e' memorizzata in cache, e la scelta e' deliberata: ARCHITECTURE §3
    dice che build_chain() legge la configurazione a ogni richiesta, ed e'
    esattamente cio' che rende RF-22 dimostrabile. Le due parti costose —
    l'LLM e il vector store — sono memorizzate una per una dentro le factory,
    quindi «leggere a ogni richiesta» costa una query e qualche microsecondo.
    """

    pipeline: RagPipeline
    store: object            # PGVector; non tipizzato per non importarlo qui
    retrieval: RetrievalProfile
    catena: object           # Runnable LCEL: prompt | llm | StrOutputParser


def build_chain(pipeline: RagPipeline) -> CatenaRag:
    """Configurazione → catena eseguibile (T-23, RF-22).

    Tre differenze deliberate rispetto alla catena dello spike (T-06):

    1. ogni parametro viene da una riga di database, nessuno e' scritto qui;
    2. il prompt di sistema e' un SystemMessage e non un template (cfr.
       build_prompt);
    3. il recupero NON e' un anello della catena. Sta fuori, prima, perche'
       QueryLog vuole retrieval_ms e generation_ms SEPARATI (cfr. la docstring
       del modello: in P0 si e' misurato un recupero da 12 s accanto a una
       generazione da 1). Dentro una catena unica i due tempi sarebbero
       distinguibili solo con dei callback, cioe' con piu' codice per un
       risultato peggiore.
    """
    llm = get_llm(pipeline.llm_profile)
    store = get_vectorstore(pipeline.knowledge_base)
    prompt = build_prompt(pipeline.prompt_template)
    return CatenaRag(
        pipeline=pipeline,
        store=store,
        retrieval=pipeline.retrieval_profile,
        catena=prompt | llm | StrOutputParser(),
    )


@dataclass(frozen=True)
class EsitoInterrogazione:
    """Risposta, fonti e tempi (RF-11, RF-13, RF-16)."""

    domanda: str
    risposta: str
    segmenti: list[SegmentoRecuperato]
    pipeline_nome: str
    retrieval_ms: int
    generation_ms: int
    latency_ms: int
    generata: bool            # False = non-risposta a monte dell'LLM (T-25)
    query_log_id: int | None = None

    @property
    def fonti(self) -> list[dict]:
        return [s.come_fonte() for s in self.segmenti]

    def __str__(self) -> str:
        return (
            f"{len(self.segmenti)} fonti, {self.latency_ms} ms "
            f"(recupero {self.retrieval_ms}, generazione {self.generation_ms})"
        )


def rispondi(
    domanda: str,
    *,
    pipeline: RagPipeline | None = None,
    utente=None,
) -> EsitoInterrogazione:
    """Risponde a una domanda usando la configurazione della pipeline.

    Sincrona, come tutto il resto del sistema in questa fase.

    Solleva:
        DomandaVuota, PipelineNonUtilizzabile, ConfigurazioneNonSupportata,
        LlmNonRaggiungibile — tutte sottoclassi di QueryError, cioe' condizioni
        previste da riportare all'utente in forma leggibile.
    """
    domanda = (domanda or "").strip()
    if not domanda:
        raise DomandaVuota(
            "La domanda e' vuota: non c'e' nulla da cercare nei documenti."
        )

    inizio = time.perf_counter()
    if pipeline is None:
        pipeline = seleziona_pipeline()
    catena = build_chain(pipeline)

    # --- recupero, cronometrato a parte -----------------------------------
    t0 = time.perf_counter()
    segmenti = esegui_ricerca(catena.store, catena.retrieval, domanda)
    retrieval_ms = int((time.perf_counter() - t0) * 1000)

    # --- generazione, oppure la non-risposta (T-25, RF-14) ----------------
    generation_ms = 0
    if segmenti:
        t0 = time.perf_counter()
        try:
            risposta = catena.catena.invoke(
                {"context": formatta_contesto(segmenti), "question": domanda}
            ).strip()
        except (OSError, httpx.TransportError) as exc:
            # Si traducono SOLO le due famiglie del guasto di trasporto. Un
            # KeyError o un TypeError qui NON sono un LLM irraggiungibile e
            # devono restare guasti inattesi, con il loro stack: chiamare «non
            # raggiungibile» un errore di programmazione manderebbe a cercare
            # nel posto sbagliato.
            #
            # OSError e' la famiglia di ConnectionError builtin, quella che
            # langchain_ollama solleva dal lato EMBEDDING e da get_llm().
            #
            # httpx.TransportError NON e' sottoclasse di OSError, ed e' il tipo
            # MISURATO qui il 25/07/2026 con Ollama spento: ChatOllama.invoke()
            # lascia passare httpx.ConnectError grezza («[WinError 10061] No
            # connection could be made…»), senza la traduzione che le
            # OllamaEmbeddings fanno. Un `except OSError` da solo avrebbe quindi
            # lasciato sfuggire proprio il caso per cui esiste. Si cattura la
            # famiglia TransportError e non HTTPError perche' comprende tutti i
            # guasti di trasporto — connessione rifiutata, timeout di lettura
            # allo scadere di timeout_s, protocollo interrotto — mentre una
            # risposta HTTP di errore arriva come ollama.ResponseError, che e'
            # un'altra cosa e non va chiamata «servizio irraggiungibile».
            raise LlmNonRaggiungibile(
                f"Il servizio di inferenza non ha risposto durante la "
                f"generazione ({type(exc).__name__}): {exc}. Verificare che "
                f"Ollama sia in esecuzione su "
                f"{pipeline.llm_profile.base_url}."
            ) from exc
        generation_ms = int((time.perf_counter() - t0) * 1000)
        generata = True
    else:
        # Zero segmenti = nessun contesto pertinente. Si dichiara di non
        # sapere SENZA interrogare l'LLM: e' la promessa scritta in
        # rag/models/profiles.py righe 21-24, ed e' anche l'unica forma di
        # RF-14 che non dipenda dall'obbedienza del modello al prompt.
        # Copre due casi: soglia non superata, e base di conoscenza vuota.
        risposta = RISPOSTA_NON_DISPONIBILE
        generata = False
        logger.info(
            "Nessun segmento pertinente per «%.60s»: risposta dichiarata non "
            "disponibile senza interrogare l'LLM (RF-14).",
            domanda,
        )

    esito = EsitoInterrogazione(
        domanda=domanda,
        risposta=risposta,
        segmenti=segmenti,
        pipeline_nome=pipeline.name,
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        latency_ms=int((time.perf_counter() - inizio) * 1000),
        generata=generata,
    )
    logger.info("Interrogazione completata — %s", esito)
    return esito
