"""Orchestrazione dell'ingestione: PDF → chunk → vettori → righe di database.

E' il punto UNICO in cui le due meta' dello schema si riconciliano
(ARCHITECTURE §6.3, §6.5).

L'ORDINE DELLE SCRITTURE E' UNA SCELTA DI CORRETTEZZA, NON DI STILE.

PGVector usa un engine SQLAlchemy con una connessione propria, distinta da
quella di Django: non esiste alcun transaction.atomic() che comprenda
entrambe. ARCHITECTURE §6.5 lo dichiara e descrive l'ordine scelto qui sotto.
Dovendo scegliere quale meta' puo' restare indietro, si
scrive PRIMA in pgvector e POI in Django:

- se cade la scrittura Django restano VETTORI ORFANI: invisibili al sistema, e
  sovrascritti dalla prossima esecuzione perche' gli id sono deterministici.
  Il guasto si ripara da solo;
- l'ordine inverso lascerebbe CHUNK CHE PUNTANO A VETTORI INESISTENTI, cioe' un
  indice che mente al retrieval di P3. Un guasto silenzioso e permanente.

Gli id dei vettori sono deterministici — «<document_id>:<ordinal>» — e questo
e' cio' che rende possibili sia l'idempotenza (l'upsert di
langchain-postgres 0.0.17 e' ON CONFLICT (id) DO UPDATE, verificato sul
sorgente) sia la pulizia in cascata di RF-08, che deve poter ricostruire gli id
dei vettori quando le righe DocumentChunk sono GIA' state cancellate.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from ..models import Document, DocumentChunk
from .exceptions import DocumentoDuplicato, IngestionError, PdfSenzaTesto
from .factories import (
    get_embeddings,
    get_splitter,
    get_vectorstore,
    verify_embedding_dimension,
)
from .loaders import load_pdf

logger = logging.getLogger(__name__)


def vector_id(document_id: int, ordinal: int) -> str:
    """Identificativo del vettore in langchain_pg_embedding.

    Deterministico di proposito (cfr. l'intestazione del modulo). Ricalcolabile
    da entrambe le meta' dello schema senza consultare l'altra: e' cio' che
    rende la reindicizzazione idempotente e la pulizia dei vettori possibile a
    chunk gia' cancellati.

    langchain_pg_embedding.id e' `character varying`, verificato in P0: una
    stringa e' un valore legittimo, non un UUID mascherato.
    """
    return f"{document_id}:{ordinal}"


def compute_checksum(file) -> str:
    """SHA-256 del file, a blocchi (RF-09).

    A blocchi e non con read(): un PDF puo' pesare decine di MB e non va
    caricato tutto in memoria.

    La funzione RIPRISTINA lo stato di partenza del file, e nessuna delle due
    metà e' cosmetica:

    - se il file era APERTO — il caso del form dell'admin, che valida un upload
      prima che lo storage lo scriva — si riporta il puntatore a zero. Senza il
      seek(0) finale si salverebbe un PDF di ZERO BYTE;
    - se era CHIUSO — il caso di un FieldFile appena letto dal database — lo si
      richiude. Su Windows un handle aperto su quel percorso fa fallire con
      PermissionError [WinError 32] la cancellazione o la sostituzione del file
      da parte di un'ALTRA istanza di FieldFile. Osservato in fase di
      pianificazione.

    `FieldFile.closed` e' True finche' nessuno legge; il seek() apre il file e
    close() lo richiude. Verificato.
    """
    era_chiuso = getattr(file, "closed", False)
    digest = hashlib.sha256()
    file.seek(0)
    for blocco in file.chunks():
        digest.update(blocco)
    if era_chiuso:
        file.close()
    else:
        file.seek(0)
    return digest.hexdigest()


def trova_duplicato(knowledge_base_id: int, checksum: str, *, escludi_id=None):
    """Restituisce il Document con lo stesso checksum nella stessa KB, se c'e'.

    Il vincolo di unicita' e' per base di conoscenza, non globale: lo stesso PDF
    in due raccolte distinte e' legittimo (ARCHITECTURE §6.4).
    """
    qs = Document.objects.filter(knowledge_base_id=knowledge_base_id, checksum=checksum)
    if escludi_id is not None:
        qs = qs.exclude(pk=escludi_id)
    return qs.first()


@dataclass(frozen=True)
class EsitoIngestione:
    document_id: int
    page_count: int
    chunk_count: int
    vettori_rimossi: int
    durata_s: float

    def __str__(self) -> str:
        return (
            f"documento {self.document_id}: {self.chunk_count} segmenti su "
            f"{self.page_count} pagine in {self.durata_s:.1f}s"
            + (
                f" ({self.vettori_rimossi} vettori obsoleti rimossi)"
                if self.vettori_rimossi
                else ""
            )
        )


def ingest_document(document: Document) -> EsitoIngestione:
    """Indicizza (o reindicizza) un documento.

    Idempotente: rieseguirla sullo stesso documento sovrascrive i vettori e
    aggiorna le righe DocumentChunk, senza duplicare nulla. E' cio' che rende
    T-19 («reindicizza») una semplice rilettura di questa funzione.

    LA CHIAMA IL WORKER, da P5 (T-32): questa funzione BLOCCA il chiamante per
    tutta la durata dell'indicizzazione, e il chiamante e' `db_worker` in un
    processo separato. Gli inneschi HTTP e l'admin non la chiamano piu'
    direttamente — passano da rag.tasks.accoda_indicizzazione(). L'unica via
    sincrona rimasta e' `manage.py ingest` senza --async, dove attendere e'
    esattamente cio' che si vuole.

    Solleva:
        IngestionError: condizione imputabile al documento o alla sua
            configurazione. Lo stato «Fallito» e' GIA' stato persistito quando
            l'eccezione arriva al chiamante: il rilancio serve solo a
            informarlo.
        Exception: guasto inatteso. Anch'esso persistito (RNF-04), e in piu'
            registrato nel log con lo stack completo.
    """
    inizio = time.perf_counter()
    try:
        return _esegui_ingestione(document, inizio)
    except IngestionError as exc:
        _marca_fallito(document, str(exc))
        logger.warning("Ingestione del documento %s rifiutata: %s", document.pk, exc)
        raise
    except Exception as exc:
        # Non e' una condizione prevista: il messaggio persistito deve restare
        # leggibile, ma lo stack va nel log perche' serve a chi sviluppa.
        _marca_fallito(
            document,
            f"Errore inatteso durante l'indicizzazione "
            f"({type(exc).__name__}): {exc}",
        )
        logger.exception("Ingestione del documento %s fallita", document.pk)
        raise


def _marca_fallito(document: Document, messaggio: str) -> None:
    """Persiste lo stato «Fallito» e il motivo (RF-06, RNF-04, CA-8).

    Fuori da qualunque transazione del chiamante: se fosse dentro quella che
    sta fallendo, il rollback cancellerebbe anche la spiegazione del
    fallimento.
    """
    document.status = Document.Status.FAILED
    document.error_message = messaggio
    document.save(update_fields=["status", "error_message"])


def _esegui_ingestione(document: Document, inizio: float) -> EsitoIngestione:
    kb = document.knowledge_base
    profilo_embedding = kb.embedding_profile
    profilo_chunking = kb.chunking_profile

    # --- 1. Deduplica (RF-09), prima di qualunque lavoro costoso -----------
    checksum = compute_checksum(document.file)
    esistente = trova_duplicato(kb.pk, checksum, escludi_id=document.pk)
    if esistente is not None:
        raise DocumentoDuplicato(
            f"Questo file e' gia' presente nella base di conoscenza "
            f"«{kb.name}» come documento {esistente.pk} "
            f"({esistente.original_filename or esistente.file.name}). "
            "Lo stesso contenuto non viene indicizzato due volte.",
            esistente_id=esistente.pk,
        )

    # --- 2. Configurazione → oggetti, e verifica dei presupposti ----------
    # Prima dello stato «In elaborazione»: una configurazione irrealizzabile o
    # un Ollama spento devono produrre un errore chiaro senza far passare il
    # documento per uno stato che non ha mai avuto.
    splitter = get_splitter(profilo_chunking)
    embeddings = get_embeddings(profilo_embedding)
    verify_embedding_dimension(embeddings, profilo_embedding)
    store = get_vectorstore(kb, embeddings=embeddings)

    # --- 3. «In elaborazione», salvato PRIMA del lavoro -------------------
    # Fuori dalla transazione finale: se stesse dentro, lo stato non
    # esisterebbe mai come momento osservabile (RNF-04).
    # Da P5 la garanzia e' PIENA sulla via che conta: a scrivere questo stato
    # e' il worker, in autocommit, quindi «In elaborazione» e' visibile
    # nell'admin mentre dura. Resta parziale da `manage.py ingest` sincrono e
    # con TASKS_BACKEND=ImmediateBackend, dove il chiamante e' il processo che
    # attende comunque.
    document.status = Document.Status.PROCESSING
    document.error_message = ""
    document.save(update_fields=["status", "error_message"])

    # --- 4. Estrazione e segmentazione ------------------------------------
    # document.file.path presuppone uno storage su filesystem locale, che e'
    # quello configurato (MEDIA_ROOT). Con uno storage remoto servirebbe
    # scrivere il file in un temporaneo: fuori ambito.
    estratto = load_pdf(
        document.file.path,
        metadata_extra={
            "document_id": document.pk,
            "knowledge_base_id": kb.pk,
            "documento": document.original_filename or Path(document.file.name).name,
        },
        # Dal database, mai una costante: RF-22. Zero — il default della
        # colonna — disattiva il controllo, e il comportamento resta quello
        # consegnato da P2 a P6. E' l'unico dei tre limiti di T-44 che si
        # verifica QUI e non all'ingresso: richiede l'estrazione del testo,
        # quindi lo scopre il worker (cfr. PdfTestoInsufficiente).
        min_text_page_ratio=kb.min_text_page_ratio,
    )
    pezzi = splitter.split_documents(estratto.pagine)
    if not pezzi:
        # Difesa: pagine con testo ma nessun chunk significa configurazione
        # patologica, non PDF scansionato. Il messaggio deve dirlo.
        raise PdfSenzaTesto(
            f"La segmentazione non ha prodotto alcun segmento dalle "
            f"{len(estratto.pagine)} pagine con testo. Verificare il profilo "
            f"«{profilo_chunking.name}»."
        )

    for ordinale, pezzo in enumerate(pezzi):
        pezzo.metadata["ordinal"] = ordinale

    # --- 5. PRIMA i vettori: upsert a lotti di batch_size -----------------
    # OllamaEmbeddings non sa batchare e PGVector.add_texts() invia TUTTI i
    # testi in una sola POST a /api/embed (verificato sul sorgente della
    # 0.0.17). L'affettamento e' quindi l'unico modo di far rispettare
    # EmbeddingProfile.batch_size, che altrimenti sarebbe un campo decorativo.
    dimensione_lotto = max(1, profilo_embedding.batch_size)
    for da in range(0, len(pezzi), dimensione_lotto):
        lotto = pezzi[da : da + dimensione_lotto]
        store.add_documents(
            lotto,
            ids=[vector_id(document.pk, da + i) for i in range(len(lotto))],
        )
        logger.debug(
            "Documento %s: indicizzati %s/%s segmenti",
            document.pk,
            da + len(lotto),
            len(pezzi),
        )

    # --- 6. Vettori obsoleti di una indicizzazione precedente piu' lunga --
    ordinali_precedenti = set(document.chunks.values_list("ordinal", flat=True))
    ordinali_precedenti.update(range(document.chunk_count))
    obsoleti = sorted(o for o in ordinali_precedenti if o >= len(pezzi))
    if obsoleti:
        store.delete(ids=[vector_id(document.pk, o) for o in obsoleti])

    # --- 7. POI Django, in una transazione --------------------------------
    with transaction.atomic():
        # update_or_create e non delete + bulk_create: RetrievedChunk.chunk e'
        # SET_NULL, quindi ricreare le righe azzererebbe lo storico delle
        # interrogazioni (RF-16). Cosi' i chunk il cui ordinale non e'
        # cambiato conservano la chiave primaria. Le due meta' dello schema
        # finiscono per usare la STESSA semantica: upsert per
        # (documento, ordinale).
        for ordinale, pezzo in enumerate(pezzi):
            DocumentChunk.objects.update_or_create(
                document=document,
                ordinal=ordinale,
                defaults={
                    "page_number": pezzo.metadata["page"],
                    "content": pezzo.page_content,
                    "char_count": len(pezzo.page_content),
                    "vector_id": vector_id(document.pk, ordinale),
                },
            )
        document.chunks.filter(ordinal__gte=len(pezzi)).delete()

        document.status = Document.Status.INDEXED
        document.checksum = checksum
        document.page_count = estratto.page_count
        document.chunk_count = len(pezzi)
        document.error_message = ""
        if not document.original_filename:
            # Debito lasciato aperto da P1: il campo esiste e nessuno lo
            # valorizzava.
            document.original_filename = Path(document.file.name).name
        document.indexed_embedding_profile = profilo_embedding
        document.indexed_chunking_profile = profilo_chunking
        document.index_fingerprint = kb.index_fingerprint()
        document.indexed_at = timezone.now()
        document.save(
            update_fields=[
                "status",
                "checksum",
                "page_count",
                "chunk_count",
                "error_message",
                "original_filename",
                "indexed_embedding_profile",
                "indexed_chunking_profile",
                "index_fingerprint",
                "indexed_at",
            ]
        )

    esito = EsitoIngestione(
        document_id=document.pk,
        page_count=estratto.page_count,
        chunk_count=len(pezzi),
        vettori_rimossi=len(obsoleti),
        durata_s=time.perf_counter() - inizio,
    )
    logger.info("Ingestione completata — %s", esito)
    return esito
