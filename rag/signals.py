"""Rimozione dei vettori alla cancellazione di un documento (RF-08, T-20).

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
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from .models import Document

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=Document, dispatch_uid="rag.documento.raccogli_vettori")
def raccogli_vettori(sender, instance: Document, **kwargs) -> None:
    """Fotografa cio' che servira' dopo la cancellazione.

    Anche la KnowledgeBase va letta ora: se la cancellazione arriva in cascata
    dalla KB, in post_delete quella riga potrebbe non esserci piu'.
    """
    instance._vettori_da_rimuovere = list(
        instance.chunks.exclude(vector_id="").values_list("vector_id", flat=True)
    )
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
