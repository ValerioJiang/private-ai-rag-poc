"""Health check e API REST (RF-27).

Le viste sono involucri HTTP attorno ai servizi: ingest_document() per il
caricamento, rispondi() per l'interrogazione. Nessuna regola di dominio vive
qui — cfr. l'intestazione di rag/serializers.py per dove passa il confine.
"""

import logging

import httpx
from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Document, KnowledgeBase, RagPipeline
from .serializers import (
    AskSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
    RagPipelineSerializer,
)
from .services.exceptions import IngestionError, LlmNonRaggiungibile, QueryError
from .services.ingestion import compute_checksum, ingest_document, trova_duplicato
from .services.query import rispondi

logger = logging.getLogger(__name__)


def _check_database() -> tuple[bool, str]:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - l'health check riporta, non gestisce
        return False, str(exc)


def _check_pgvector() -> tuple[bool, str]:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cur.fetchone()
        if row:
            return True, f"vector {row[0]}"
        return False, "estensione 'vector' non installata"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _check_ollama() -> tuple[bool, str]:
    try:
        resp = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return True, f"{len(models)} modelli disponibili"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    checks = {
        "database": _check_database(),
        "pgvector": _check_pgvector(),
        "ollama": _check_ollama(),
    }
    healthy = all(ok for ok, _ in checks.values())
    return Response(
        {
            "status": "ok" if healthy else "degraded",
            "checks": {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()},
        },
        status=200 if healthy else 503,
    )


# --------------------------------------------------------------------------
# API REST (P4)
# --------------------------------------------------------------------------


def _base_di_conoscenza_predefinita() -> KnowledgeBase:
    """La base della pipeline predefinita (RF-26).

    Stessa regola di `manage.py ingest` senza --kb: nell'installazione
    predefinita la base e' una sola, e chiedere un id a chi carica il primo PDF
    sarebbe attrito senza contropartita.

    Solleva la ValidationError di DRF (400) e non un'eccezione di dominio:
    l'assenza di una pipeline predefinita e' una configurazione mancante, e il
    messaggio dice al client come procedere lo stesso.
    """
    pipeline = (
        RagPipeline.objects.select_related("knowledge_base")
        .filter(is_default=True)
        .first()
    )
    if pipeline is None:
        raise ValidationError(
            {
                "knowledge_base": (
                    "Nessuna pipeline predefinita configurata: indicare "
                    "esplicitamente la base di conoscenza."
                )
            }
        )
    return pipeline.knowledge_base


@api_view(["GET", "POST"])
def documenti(request):
    """POST /api/documents/ — carica un PDF e lo indicizza (T-28, RF-01, RF-27).

    SINCRONA, come ogni altro innesco dell'ingestione fino a T-32: la risposta
    arriva a indicizzazione CONCLUSA, quindi dopo ~3 s a caldo e fino a ~25 s se
    i modelli vanno caricati in VRAM. Il client deve prevedere un timeout
    generoso.

    Il contratto e' pero' gia' quello di P5: la risposta porta lo STATO del
    documento e GET /api/documents/{id}/ lo rilegge, quindi il passaggio alla
    coda cambiera' il codice restituito (202 invece di 201) e non la forma della
    risorsa ne' il modo in cui un client scopre che il documento e' pronto.

    Quattro esiti:

    - 201 documento creato e indicizzato;
    - 400 file mancante, non PDF, o base di conoscenza inesistente;
    - 409 stesso contenuto gia' presente nella base (RF-09). La riga NON viene
      creata e il file NON viene scritto: la deduplica precede la scrittura,
      altrimenti ogni duplicato rifiutato lascerebbe un file orfano;
    - 422 PDF illeggibile o senza testo (RF-10). La riga in questo caso RESTA,
      con stato «Fallito» e il motivo — e' la stessa scelta dell'admin (RNF-04),
      e cancellarla distruggerebbe la traccia del guasto. La risposta non e' 2xx
      perche' la risorsa creata non e' utilizzabile.

    Un guasto inatteso propaga e diventa 500: il documento resta «Fallito» con
    il motivo, persistito dal servizio.

    GET sullo stesso percorso restituisce l'elenco (T-29): il metodo si
    dirama qui perche' una rotta Django corrisponde a una sola vista, e
    dividere in due funzioni imporrebbe due percorsi diversi per la stessa
    risorsa.
    """
    if request.method == "GET":
        return _elenco(request)

    serializer = DocumentUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    file = serializer.validated_data["file"]
    kb = serializer.validated_data.get("knowledge_base") or _base_di_conoscenza_predefinita()

    # PRIMA la deduplica, POI la scrittura (decisione 5). compute_checksum()
    # riporta il puntatore del file a zero: senza quel seek(0) si salverebbe un
    # PDF di zero byte, accertato in P2.
    checksum = compute_checksum(file)
    esistente = trova_duplicato(kb.pk, checksum)
    if esistente is not None:
        return Response(
            {
                "detail": (
                    f"Questo file e' gia' presente nella base di conoscenza "
                    f"«{kb.name}» come documento {esistente.pk}. Per rifarne "
                    f"l'indice usare l'azione «Reindicizza» dell'admin oppure "
                    f"`manage.py ingest --reindex {esistente.pk}`."
                ),
                "documento_esistente": esistente.pk,
            },
            status=status.HTTP_409_CONFLICT,
        )

    documento = Document(
        knowledge_base=kb, file=file, original_filename=file.name
    )
    documento.save()

    try:
        esito = ingest_document(documento)
    except IngestionError as exc:
        # Stato «Fallito» e motivo sono GIA' persistiti dal servizio: qui si
        # riporta, non si gestisce.
        return Response(
            {"detail": str(exc), "documento": DocumentSerializer(documento).data},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    logger.info("Documento caricato via API — %s", esito)
    return Response(
        DocumentSerializer(documento).data, status=status.HTTP_201_CREATED
    )


def _elenco(request):
    """GET /api/documents/ — elenco con stato (T-29, RF-27).

    LE select_related NON SONO UN'OTTIMIZZAZIONE FACOLTATIVA. needs_reindex
    (RF-25) dereferenzia la base di conoscenza e i suoi due profili d'indice
    per OGNI riga: senza di esse l'elenco costa tre query per documento. E' lo
    stesso motivo per cui DocumentAdmin dichiara list_select_related, ed e' il
    difetto che la verifica incrociata di P3 ha trovato nell'inline dello
    storico — vale la pena non ripeterlo il giorno dopo averlo annotato.

    Nessuna paginazione: limite dichiarato (cfr. il README). Il corpus della
    prova sta in poche righe, e una paginazione a meta' — senza contatore,
    senza link — sarebbe peggio della sua assenza.
    """
    documenti_qs = Document.objects.select_related(
        "knowledge_base",
        "knowledge_base__embedding_profile",
        "knowledge_base__chunking_profile",
    ).order_by("-uploaded_at")

    stato = request.query_params.get("status")
    if stato:
        if stato not in Document.Status.values:
            # 400 e non elenco vuoto: un elenco vuoto sembrerebbe una risposta,
            # e chi ha sbagliato a scrivere lo stato non lo saprebbe mai.
            raise ValidationError(
                {
                    "status": (
                        f"Stato «{stato}» inesistente. Ammessi: "
                        f"{', '.join(Document.Status.values)}."
                    )
                }
            )
        documenti_qs = documenti_qs.filter(status=stato)

    return Response(DocumentSerializer(documenti_qs, many=True).data)


@api_view(["GET"])
def documento(request, pk: int):
    """GET /api/documents/{id}/ — stato di un documento (T-29, RF-27).

    E' l'endpoint con cui un client scopre che l'indicizzazione e' finita, ed e'
    gia' scritto per P5: quando la POST diventera' asincrona e restituira' 202,
    questa vista sara' quella da interrogare in attesa dello stato «indexed».
    """
    istanza = get_object_or_404(
        Document.objects.select_related(
            "knowledge_base",
            "knowledge_base__embedding_profile",
            "knowledge_base__chunking_profile",
        ),
        pk=pk,
    )
    return Response(DocumentSerializer(istanza).data)


@api_view(["POST"])
def ask(request):
    """POST /api/ask/ — risponde citando le fonti (T-30, RF-11 → RF-16, RF-27).

    E' un involucro attorno a rispondi(): recupero, soglia, non-risposta, fonti
    e storico stanno gia' nel servizio, e questa vista non ne rifa' nemmeno una
    parte. In particolare NON scrive il QueryLog — quando un'eccezione arriva
    qui, la riga esiste gia', anche per le richieste rifiutate.

    La mappatura dei codici e' la risposta alla domanda che P3 aveva lasciato
    aperta:

    - 400 condizioni previste imputabili alla richiesta: domanda vuota,
      pipeline inesistente o disattivata, configurazione non realizzabile;
    - 503 LlmNonRaggiungibile. E' un QueryError, ma NON e' colpa di chi ha
      chiesto: il servizio di inferenza a valle non risponde. Un 400 manderebbe
      il client a correggere una domanda che era giusta, e 503 e' anche il
      codice che un bilanciatore sa leggere;
    - 500 tutto il resto, con lo stack nel log. Ci rientra ollama.ResponseError
      — la 500 di out-of-memory incontrata davvero in P3 — che non e' un guasto
      di trasporto: il servizio HA risposto, dicendo di non farcela.

    L'ORDINE DELLE CLAUSOLE E' SIGNIFICATIVO: LlmNonRaggiungibile e'
    sottoclasse di QueryError, quindi la sua clausola deve stare PRIMA, o non
    sara' mai raggiunta. Invertirle non romperebbe nessuna verifica scritta con
    domande pertinenti.
    """
    dati = AskSerializer(data=request.data)
    dati.is_valid(raise_exception=True)

    try:
        esito = rispondi(
            dati.validated_data["domanda"],
            # `or None` e non `.get(...)`: una stringa vuota significa «non
            # l'ho indicata», e seleziona_pipeline() la tratterebbe comunque
            # cosi', ma passare None rende esplicito quale ramo si vuole.
            pipeline=dati.validated_data.get("pipeline") or None,
            # AnonymousUser diventa None dentro _registra() senza sollevare
            # (verificato in P3): request.user si passa cosi' com'e' in
            # entrambi i casi.
            utente=request.user,
        )
    except LlmNonRaggiungibile as exc:
        return Response(
            {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except QueryError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(esito.come_payload())


@api_view(["GET"])
def pipelines(request):
    """GET /api/pipelines/ — le configurazioni disponibili (T-31, RF-23, RF-27).

    Restituisce ANCHE quelle non attive, con il loro flag: RF-23 riguarda la
    coesistenza di piu' configurazioni, e nascondere le ritirate darebbe
    l'impressione che non esistano. Chi ne indicasse una disattivata riceve un
    400 con il motivo, che e' informazione migliore di un elenco potato.

    La predefinita compare per prima: e' quella che si usa senza indicare nulla
    (RF-26).
    """
    qs = RagPipeline.objects.select_related(
        "knowledge_base", "llm_profile", "retrieval_profile", "prompt_template"
    ).order_by("-is_default", "name")
    return Response(RagPipelineSerializer(qs, many=True).data)
