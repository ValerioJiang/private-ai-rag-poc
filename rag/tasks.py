"""Ingestione asincrona: il task e l'unico punto di accodamento (T-32, RNF-03).

PERCHE' ESISTE. Fino a P4 l'indicizzazione avveniva dentro il ciclo
richiesta/risposta: 14,53 s misurati a freddo su POST /api/documents/, 4,25 s
a caldo, con punte di 30,2 s sulla prima richiesta di un processo appena
avviato. RNF-03 chiede che non sia cosi'. Qui la richiesta si limita ad
ACCODARE, e a lavorare e' un processo separato — `manage.py db_worker`.

L'IMPORT E' `django_tasks`, CON L'UNDERSCORE. Django 6.0 ha una propria
`django.tasks` nella stdlib che legge lo STESSO setting TASKS ma spedisce solo
i backend `immediate` e `dummy` (ARCHITECTURE §7.5). Importare `django.tasks`
non darebbe alcun errore: darebbe un task accodato su un altro handler, che
nessun worker verrebbe mai a prendere.

IL TASK RICEVE UN INTERO, NON UN DOCUMENTO. Gli argomenti attraversano la coda
come JSON: `django_tasks.utils.normalize_json()` accetta solo tipi primitivi e
solleva TypeError su tutto il resto (verificato sul sorgente della 0.12.0).
Non e' un limite da aggirare, e' la forma giusta: fra l'accodamento e
l'esecuzione il documento puo' essere cambiato o cancellato, e il worker deve
leggere lo stato ATTUALE, non una fotografia.

UN SOLO PUNTO DI ACCODAMENTO. Gli inneschi dell'ingestione sono quattro —
salvataggio dall'admin, azione «Reindicizza», POST /api/documents/,
`manage.py ingest --async` — e tutti passano da accoda_indicizzazione(). Se
ciascuno scrivesse per conto proprio lo stato e l'enqueue, la prima modifica a
quella coppia di righe si dimenticherebbe in tre punti su quattro.
"""

from __future__ import annotations

import logging

from django_tasks import task

from .models import Document
from .services.ingestion import ingest_document

logger = logging.getLogger(__name__)


@task()
def indicizza_documento(document_id: int) -> dict:
    """Indicizza un documento gia' salvato. Eseguito dal worker, non dal server.

    LE ECCEZIONI NON SI INGHIOTTONO, ed e' una scelta. Il Worker cattura
    BaseException e marca la riga DBTaskResult come «Fallita» con il traceback
    (verificato sul sorgente della 0.12.0); ingest_document() ha gia'
    persistito, prima di rilanciare, stato «Fallito» e motivo LEGGIBILE sul
    documento (RNF-04). Lasciando propagare si ottiene la registrazione due
    volte in due posti con due scopi: il motivo per l'amministratore
    nell'admin dei documenti, lo stack per chi sviluppa nell'admin dei task.
    Inghiottire l'eccezione qui lascerebbe una coda tutta verde sopra a
    documenti falliti.

    Il documento sparito e' invece un NON-evento: fra l'accodamento e
    l'esecuzione qualcuno puo' averlo cancellato, e cancellare un documento e'
    un'operazione legittima. Si registra e si esce.

    Il valore restituito finisce in DBTaskResult.return_value e deve essere
    serializzabile in JSON: solo interi e stringhe.
    """
    documento = (
        Document.objects.select_related("knowledge_base").filter(pk=document_id).first()
    )
    if documento is None:
        logger.warning(
            "Documento %s cancellato prima dell'indicizzazione: task senza effetto.",
            document_id,
        )
        return {"document_id": document_id, "esito": "documento inesistente"}

    esito = ingest_document(documento)
    return {
        "document_id": esito.document_id,
        "page_count": esito.page_count,
        "chunk_count": esito.chunk_count,
        "durata_s": round(esito.durata_s, 1),
    }


def accoda_indicizzazione(documento: Document) -> str:
    """Riporta il documento «In attesa» e lo mette in coda. Restituisce l'id del task.

    LO STATO SI SCRIVE QUI, E ANCHE IN REINDICIZZAZIONE. «In attesa» era fino a
    P4 uno stato che nessun documento occupava davvero, perche' l'ingestione
    partiva nello stesso istante del salvataggio; da qui in avanti e' lo stato
    in cui il documento vive finche' un worker non lo prende, ed e' cio' che
    rende osservabile RF-06 sul serio. Senza l'azzeramento, un documento gia'
    indicizzato rimesso in coda continuerebbe a dichiararsi «Indicizzato»
    mentre attende, e uno gia' fallito mostrerebbe il motivo di un fallimento
    superato.

    NESSUN transaction.on_commit(). DatabaseBackend.enqueue() crea la riga del
    task direttamente (verificato sul sorgente): dall'admin, che avvolge il
    POST in una transazione propria, la riga nasce DENTRO quella transazione e
    diventa visibile al worker INSIEME al documento — che e' esattamente cio'
    che serve. Un on_commit sposterebbe la creazione dopo il commit, aprendo
    una finestra in cui il documento esiste e il task no.

    Resta una finestra dichiarata: se il processo muore fra il salvataggio del
    documento e questa chiamata (vista API, che non e' in transazione), resta
    un documento «In attesa» senza task. Si vede nell'admin, e l'azione
    «Reindicizza» lo rimette in coda. E' il verso giusto del guasto: nessun
    dato perso, nessun indice che mente.
    """
    documento.status = Document.Status.PENDING
    documento.error_message = ""
    documento.save(update_fields=["status", "error_message"])

    risultato = indicizza_documento.enqueue(documento.pk)
    logger.info(
        "Documento %s accodato per l'indicizzazione (task %s).",
        documento.pk,
        risultato.id,
    )
    return str(risultato.id)
