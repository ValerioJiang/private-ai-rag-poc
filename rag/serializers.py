"""Traduzione fra JSON e servizi (T-28 → T-31, RF-27).

Le API non sono una seconda implementazione del sistema: sono un involucro
HTTP attorno a ingest_document() (P2) e rispondi() (P3), che contengono gia'
deduplica, macchina a stati, recupero, fonti, non-risposta e storico. Qui si
traduce, e nient'altro. Ogni regola di dominio che comparisse anche qui
diventerebbe una seconda copia da tenere allineata a mano, e la prima a
divergere sarebbe quella meno esercitata.

E' il motivo per cui la DOMANDA VUOTA non viene rifiutata da questo modulo,
benche' un allow_blank=False costi zero: la regola e' di query.py, che solleva
DomandaVuota con un messaggio scritto per un amministratore. Due messaggi
diversi per la stessa condizione — uno in inglese di DRF, uno in italiano del
dominio — sarebbero un difetto in piu' da spiegare. La riga di confine e'
netta: il serializer valida la FORMA della richiesta, il servizio valida il
DOMINIO.

IL VOCABOLARIO E' QUELLO DELLA SORGENTE, E LE SORGENTI SONO DUE. Il documento
viaggia con i nomi del MODELLO (status, page_count), che sono quelli che
l'admin mostra e che il database ha. L'esito di una interrogazione viaggia con
i nomi di `manage.py ask --json` (domanda, risposta, fonti), che sono quelli
del servizio: RF-27 e RF-28 chiedono le stesse operazioni da due ingressi
diversi, e tradurne uno soltanto li farebbe divergere.
"""

from django.core.validators import FileExtensionValidator
from rest_framework import serializers

from .models import Document, KnowledgeBase


class DocumentSerializer(serializers.ModelSerializer):
    """Rappresentazione di lettura di un documento (T-28, T-29).

    Tutti i campi sono in sola lettura: il caricamento passa da
    DocumentUploadSerializer, e nulla di cio' che sta qui — stato, conteggi,
    impronta — e' scrivibile da un client. Sono esiti dell'ingestione, non
    parametri.

    needs_reindex e' una property del modello e non una colonna (RF-25):
    dereferenzia la base di conoscenza e i suoi due profili d'indice. Perche'
    non costi tre query per riga, la vista deve passare un queryset con le
    select_related dichiarate nella docstring di _elenco(). E' lo stesso motivo
    per cui DocumentAdmin dichiara list_select_related.
    """

    knowledge_base_name = serializers.CharField(
        source="knowledge_base.name", read_only=True
    )
    needs_reindex = serializers.BooleanField(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "knowledge_base",
            "knowledge_base_name",
            "original_filename",
            "status",
            "page_count",
            "chunk_count",
            "error_message",
            "needs_reindex",
            "uploaded_at",
            "indexed_at",
        ]
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    """Ingresso di POST /api/documents/ (T-28, RF-01, RF-09).

    NON e' un ModelSerializer, ed e' una scelta: il suo save() scriverebbe la
    riga e il file su disco, mentre la deduplica di RF-09 deve avvenire PRIMA.
    Un duplicato scoperto dopo la scrittura lascia in MEDIA_ROOT un file che
    nessuna riga possiede. La sequenza corretta sta nella vista; qui si valida
    solo la forma dell'ingresso.

    L'ESTENSIONE SI CONTROLLA QUI. Il validatore che sta su Document.file
    scatta a full_clean(), che una creazione via API non chiama: senza questo
    controllo un .txt arriverebbe fino a PyMuPDF e produrrebbe un 422 con una
    riga «Fallito» in elenco per ogni errore di battitura. Misurato in
    pianificazione, il messaggio prodotto e': «Il file con estensione "txt" non
    e' permesso. Le estensioni permesse sono: pdf.»

    knowledge_base e' FACOLTATIVA: in sua assenza si usa quella della pipeline
    predefinita (RF-26), esattamente come fa `manage.py ingest` senza --kb.
    """

    file = serializers.FileField(validators=[FileExtensionValidator(["pdf"])])
    knowledge_base = serializers.PrimaryKeyRelatedField(
        queryset=KnowledgeBase.objects.all(), required=False, allow_null=True
    )
