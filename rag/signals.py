"""Rimozione dei residui alla cancellazione di un documento (RF-08, T-20, T-34).

Serve un hook perche' i due lati dello schema hanno proprietari diversi
(ARCHITECTURE §6.3): il CASCADE di Django elimina le righe DocumentChunk, ma
langchain_pg_embedding non e' una tabella che Django conosca, quindi i vettori
sopravvivrebbero al documento — e resterebbero recuperabili dal retrieval di
P3, che risponderebbe citando un documento cancellato.

Perche' TRE meccanismi e non uno:

- `pre_delete` raccoglie i vector_id FINCHE' le righe DocumentChunk esistono:
  il collector di Django cancella i figli prima del padre, quindi in
  `post_delete` sarebbero gia' spariti;
- `post_delete` programma la pulizia solo dopo che la cancellazione e' andata
  a buon fine;
- `transaction.on_commit()` la rinvia al commit, perche' pgvector sta su
  un'altra connessione: eseguirla subito e vedere poi un rollback di Django
  lascerebbe un documento vivo SENZA vettori, che e' la direzione sbagliata del
  guasto. Al contrario, dei vettori orfani sono innocui e ricalcolabili, perche'
  gli id sono deterministici.

In caso di errore si registra nel log e NON si risolleva: il documento e' gia'
cancellato, e una 500 dopo un'operazione riuscita sarebbe una bugia.

IL SECONDO RESIDUO E' IL FILE (T-34, P5). I vettori non sono l'unica meta' che
sopravviverebbe alla riga: `FileField` non cancella il PDF da MEDIA_ROOT, per
scelta di Django, e fino a P4 ogni documento cancellato ne lasciava uno orfano
sul disco — da P4 anche un'API poteva produrne, con meno attrito dell'admin.
`rimuovi_file` chiude quel debito accanto a `rimuovi_vettori` e con la STESSA
disciplina — post_delete, on_commit, errori loggati e non risollevati — perche'
le ragioni sono le stesse: il verso giusto del guasto e' un residuo innocuo sul
disco, non una riga viva senza il suo file.

LIMITE RESIDUO SUI VETTORI, dichiarato. Gli id da rimuovere si ricavano dalle
righe DocumentChunk e, se mancano, da Document.chunk_count. Resta scoperta una sola
finestra: un documento MAI indicizzato con successo (chunk_count a zero) i cui
vettori erano gia' stati scritti quando la scrittura Django e' fallita. In quel
caso nulla, in nessuna delle due meta' dello schema, dice quanti vettori
esistano, e cancellare il documento li lascia orfani. Chiuderla richiederebbe
una DELETE per metadata (cmetadata->>'document_id') sulla connessione di
pgvector: rumore sproporzionato alla finestra, che si apre solo se il processo
muore fra la scrittura dei vettori e quella delle righe.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from .models import (
    ChunkingProfile,
    Document,
    EmbeddingProfile,
    KnowledgeBase,
    LLMProfile,
    PromptTemplate,
    RagPipeline,
    RetrievalProfile,
)

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=Document, dispatch_uid="rag.documento.raccogli_vettori")
def raccogli_vettori(sender, instance: Document, **kwargs) -> None:
    """Fotografa cio' che servira' dopo la cancellazione.

    Anche la KnowledgeBase va letta ora: se la cancellazione arriva in cascata
    dalla KB, in post_delete quella riga potrebbe non esserci piu'.
    """
    ids = list(instance.chunks.exclude(vector_id="").values_list("vector_id", flat=True))
    if not ids and instance.chunk_count:
        # Le righe non ci sono ma il documento dichiara di essere stato
        # indicizzato: gli id sono deterministici, quindi si ricostruiscono
        # senza consultare l'altra meta' dello schema. E' esattamente cio' per
        # cui sono stati scelti cosi'.
        from .services.ingestion import vector_id

        ids = [vector_id(instance.pk, o) for o in range(instance.chunk_count)]
    instance._vettori_da_rimuovere = ids
    instance._kb_per_pulizia = instance.knowledge_base


@receiver(post_delete, sender=Document, dispatch_uid="rag.documento.rimuovi_vettori")
def rimuovi_vettori(sender, instance: Document, **kwargs) -> None:
    ids = getattr(instance, "_vettori_da_rimuovere", None)
    kb = getattr(instance, "_kb_per_pulizia", None)
    if not ids or kb is None:
        return

    document_pk = instance.pk

    def pulisci() -> None:
        # Import locale: importare le factory a livello di modulo tirerebbe
        # dentro LangChain al caricamento delle app.
        from .services.factories import get_vectorstore

        try:
            get_vectorstore(kb).delete(ids=list(ids))
            logger.info(
                "Rimossi %s vettori del documento %s dalla collezione «%s».",
                len(ids), document_pk, kb.collection_name,
            )
        except Exception:  # noqa: BLE001 - il documento e' gia' cancellato
            logger.exception(
                "Vettori del documento %s non rimossi dalla collezione «%s»: "
                "restano orfani, ricalcolabili perche' gli id sono "
                "deterministici (%s…).",
                document_pk, kb.collection_name, ids[0],
            )

    transaction.on_commit(pulisci)


@receiver(post_delete, sender=Document, dispatch_uid="rag.documento.rimuovi_file")
def rimuovi_file(sender, instance: Document, **kwargs) -> None:
    """Porta via anche il PDF da MEDIA_ROOT (T-34, completa RF-08).

    FileField NON cancella il file quando la riga sparisce — e' un
    comportamento voluto di Django dalla 1.3, perche' due righe potrebbero
    puntare allo stesso nome. Fino a P4 ogni documento cancellato lasciava
    quindi un PDF orfano sul disco, e da P4 anche un'API poteva produrne, con
    meno attrito dell'admin.

    Stessa disciplina dei vettori, per le stesse ragioni: on_commit, perche' un
    rollback dopo la cancellazione del file lascerebbe una riga viva senza il
    suo PDF — il verso sbagliato del guasto; e in caso di errore si registra
    senza risollevare, perche' il documento e' gia' cancellato e una 500 dopo
    un'operazione riuscita sarebbe una bugia. Su Windows il caso concreto e'
    PermissionError [WinError 32] con un handle ancora aperto sul file.

    LIMITE DICHIARATO: sostituire il file di un documento esistente continua a
    lasciare il precedente in MEDIA_ROOT. Chiuderlo richiederebbe un pre_save
    che confronta il vecchio nome col nuovo, cioe' una lettura in piu' a ogni
    salvataggio per un caso che l'admin rende raro (il campo file e' l'unico
    modificabile su un documento gia' caricato).
    """
    nome = instance.file.name if instance.file else ""
    if not nome:
        return
    storage = instance.file.storage
    document_pk = instance.pk

    def pulisci() -> None:
        try:
            storage.delete(nome)
            logger.info(
                "File «%s» del documento %s rimosso da MEDIA_ROOT.", nome, document_pk
            )
        except Exception:  # noqa: BLE001 - il documento e' gia' cancellato
            logger.exception(
                "File «%s» del documento %s non rimosso: resta in MEDIA_ROOT.",
                nome,
                document_pk,
            )

    transaction.on_commit(pulisci)


# --------------------------------------------------------------------------
# Invalidazione della cache delle factory (T-21, RF-22)
# --------------------------------------------------------------------------

# Sette modelli: tutto cio' che concorre a costruire un LLM o un vector store,
# piu' RagPipeline che li compone. NON DocumentChunk ne' Document: il contenuto
# dell'indice cambia di continuo e non ha alcun effetto sugli OGGETTI costruiti.
MODELLI_DI_CONFIGURAZIONE = (
    LLMProfile,
    EmbeddingProfile,
    ChunkingProfile,
    RetrievalProfile,
    PromptTemplate,
    KnowledgeBase,
    RagPipeline,
)


def invalida_cache_factory(sender, **kwargs) -> None:
    """Svuota la cache delle factory a ogni modifica della configurazione.

    Attenzione a cosa questo receiver E' e a cosa NON e'. NON e' cio' che
    garantisce RF-22: la garanzia sta nella CHIAVE della cache, che contiene
    updated_at e index_fingerprint() e quindi cambia da se' — anche in un
    processo che questo segnale non lo riceve mai, cioe' con piu' worker.
    Questo receiver rende l'effetto immediato nel processo che ha salvato e
    impedisce al dizionario di crescere a ogni modifica. Cfr. la docstring di
    rag/services/factories.py.
    """
    from .services.factories import svuota_cache  # import locale: cfr. sopra

    svuota_cache()
    logger.debug("Configurazione modificata (%s): cache invalidata.", sender.__name__)


for _modello in MODELLI_DI_CONFIGURAZIONE:
    post_save.connect(
        invalida_cache_factory,
        sender=_modello,
        dispatch_uid=f"rag.cache.salvataggio.{_modello.__name__}",
    )
    post_delete.connect(
        invalida_cache_factory,
        sender=_modello,
        dispatch_uid=f"rag.cache.cancellazione.{_modello.__name__}",
    )
