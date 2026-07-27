"""Health check e API REST (RF-27).

Le viste sono involucri HTTP attorno ai servizi: da P5 (T-32) il caricamento e'
un involucro attorno ad accoda_indicizzazione() — a chiamare ingest_document()
e' il worker, in un processo separato — e l'interrogazione lo e' attorno a
rispondi(). Nessuna regola di dominio vive qui — cfr. l'intestazione di
rag/serializers.py per dove passa il confine.
"""

import logging

import httpx
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import connection
from django.shortcuts import redirect, render, resolve_url
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response

from .models import Document, KnowledgeBase, RagPipeline
from .serializers import (
    AskSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
    RagPipelineSerializer,
)
from .services.exceptions import IngestionError, LlmNonRaggiungibile, QueryError
from .services.ingestion import compute_checksum, trova_duplicato
from .services.query import rispondi
from .services.validation import verifica_ammissibilita
from .tasks import accoda_indicizzazione

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


def _check_coda() -> tuple[bool, str]:
    """Stato della coda dei task (T-32, T-34).

    NON FA MAI FALLIRE L'HEALTH CHECK, ed e' deliberato: una coda con dei task
    in attesa e' il funzionamento normale, non un guasto, e /health e' la sonda
    del docker-compose. Il valore di questo controllo e' diagnostico —
    distinguere «worker occupato» da «worker mai avviato», che sara' il modo
    piu' probabile di sbagliare l'avvio del progetto.

    Il backend si legge da settings e non da `default_task_backend`: quello e'
    un ConnectionProxy, e `type(...)` restituirebbe il proxy invece del
    backend vero.
    """
    percorso = settings.TASKS["default"]["BACKEND"]
    if not percorso.endswith("DatabaseBackend"):
        return True, f"{percorso.rsplit('.', 1)[-1]}: esecuzione in linea, nessun worker necessario"
    try:
        from django_tasks_db.models import DBTaskResult

        in_attesa = DBTaskResult.objects.ready().count()
        in_corso = DBTaskResult.objects.running().count()
    except Exception as exc:  # noqa: BLE001 - l'health check riporta, non gestisce
        return False, str(exc)
    return True, (
        f"coda su database: {in_attesa} in attesa, {in_corso} in esecuzione "
        f"(le lavora `manage.py db_worker`)"
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    checks = {
        "database": _check_database(),
        "pgvector": _check_pgvector(),
        "ollama": _check_ollama(),
        "coda": _check_coda(),
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
    """POST /api/documents/ — carica un PDF e lo mette in coda (T-28, T-32, RF-01).

    ASINCRONA da P5: la risposta arriva ad accodamento avvenuto, non a
    indicizzazione conclusa. E' il contratto che P4 aveva gia' annunciato in
    questa stessa docstring — «il passaggio alla coda cambiera' il codice
    restituito (202 invece di 201) e non la forma della risorsa ne' il modo in
    cui un client scopre che il documento e' pronto». La misura che lo
    giustifica: 14,53 s a freddo e 4,25 s a caldo in P4, contro l'accodamento
    che non tocca ne' Ollama ne' pgvector.

    Tre esiti:

    - 202 file accettato, documento creato in stato «in attesa», task
      accodato. Per sapere com'e' finita si interroga
      GET /api/documents/{id}/ finche' lo stato non e' «indexed» o «failed»;
    - 400 file mancante, non PDF, base di conoscenza inesistente, oppure
      oltre i limiti di ammissione della base (T-44: dimensione, pagine).
      Nessuna riga viene creata e nessun file scritto;
    - 409 stesso contenuto gia' presente nella base (RF-09). La riga NON viene
      creata e il file NON viene scritto: la deduplica precede la scrittura,
      altrimenti ogni duplicato rifiutato lascerebbe un file orfano.

    IL 422 NON ESISTE PIU', e non e' una svista. Un PDF illeggibile o senza
    testo (RF-10) e' scoperto dal worker, quando la risposta e' gia' partita:
    la condizione resta osservabile su GET /api/documents/{id}/, che riporta
    status «failed» ed error_message. E' l'unico cambio di contratto di P5, e
    va nel README.

    GET sullo stesso percorso restituisce l'elenco (T-29): il metodo si
    dirama qui perche' una rotta Django corrisponde a una sola vista, e
    dividere in due funzioni imporrebbe due percorsi diversi per la stessa
    risorsa.

    IL 422 NON TORNA. Con max_page_count configurato la POST apre il PDF e
    puo' quindi scoprire un file corrotto, che senza quel limite resta di
    competenza del worker: la risposta e' comunque 400 e non 422, perche' la
    condizione e' nota PRIMA di ogni scrittura. Il cambio di contratto e'
    dichiarato nel README insieme al limite.
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

    # I limiti di ammissione (T-44), DOPO la deduplica: il 409 e la sua
    # garanzia — niente riga, niente file — sono gia' documentati e provati,
    # e anteporre questo controllo cambierebbe la risposta a un duplicato che
    # eccede anche un limite. Un duplicato e' anche la risposta piu' utile:
    # «ce l'hai gia'» batte «e' troppo grande».
    try:
        verifica_ammissibilita(file, kb)
    except IngestionError as exc:
        # 400 e non 422: e' una condizione della richiesta, scoperta prima di
        # qualunque scrittura. Nessuna riga «Fallito» resta in elenco.
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    documento = Document(
        knowledge_base=kb, file=file, original_filename=file.name
    )
    documento.save()

    task_id = accoda_indicizzazione(documento)
    logger.info(
        "Documento %s caricato via API e accodato (task %s).", documento.pk, task_id
    )
    return Response(
        DocumentSerializer(documento).data, status=status.HTTP_202_ACCEPTED
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

    E' l'endpoint con cui un client scopre che l'indicizzazione e' finita, e da
    P5 e' l'UNICO: la POST risponde 202 e non attende piu'. Si interroga
    finche' `status` non e' «indexed» oppure «failed» — nel secondo caso
    `error_message` porta il motivo (RF-10, RNF-04).

    NotFound esplicita e non get_object_or_404: quest'ultima solleva Http404
    con un messaggio in inglese che DRF propaga scavalcando la propria
    traduzione, ed era il difetto cosmetico accertato in P4. Il messaggio
    scritto qui dice anche QUALE id non esiste, che il testo generico non
    direbbe.
    """
    istanza = (
        Document.objects.select_related(
            "knowledge_base",
            "knowledge_base__embedding_profile",
            "knowledge_base__chunking_profile",
        )
        .filter(pk=pk)
        .first()
    )
    if istanza is None:
        raise NotFound(f"Nessun documento con id {pk}.")
    return Response(DocumentSerializer(istanza).data)


class SoloLaRispostaRichiedeSessione(BasePermission):
    """Lascia passare il GET di /api/ask/, che non risponde a domande.

    Serve perche' il GET e' un semplice rimando a /chiedi/ e non espone nulla:
    ne' documenti, ne' risposte, ne' l'elenco delle configurazioni. Col
    permesso predefinito (IsAuthenticated) chi apre /api/ask/ col browser senza
    sessione riceve un 401 in JSON — corretto per un client di un'API,
    illeggibile per una persona, e per giunta un vicolo cieco: la pagina che
    gli serve esiste, ed e' a un rimando di distanza.

    Il POST resta autenticato come prima, ed e' l'unico verbo che raggiunge
    rispondi(). /chiedi/ ha una sua login_required, quindi chi non ha sessione
    finisce su /accedi/ invece che su un errore: e' la via d'uscita che il 401
    non offriva.
    """

    def has_permission(self, request, view) -> bool:
        if request.method == "GET":
            return True
        return bool(request.user and request.user.is_authenticated)


@api_view(["GET", "POST"])
@permission_classes([SoloLaRispostaRichiedeSessione])
def ask(request):
    """POST /api/ask/ — risponde citando le fonti (T-30, RF-11 → RF-16, RF-27).

    IL GET NON RISPONDE A DOMANDE: rimanda a /chiedi/, e serve solo a chi
    arriva qui col browser. Prima restituiva 405 «Method Not Allowed» — corretto
    per un endpoint di sola scrittura, ma chi apre /api/ask/ perche' l'ha letto
    nel README trova un errore invece di una via d'uscita, e non ha modo di
    sapere che la pagina esiste. Il rimando e' 302 e non un contenuto: cosi'
    l'endpoint resta uno solo, e l'HTML continua a stare in una vista sola.

    Il contratto per i client resta INVARIATO: la risposta si ottiene con POST,
    e nessuna verifica esistente osservava il 405 (accertato con grep su
    rag/tests/ e sul README prima di cambiarlo).

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
    if request.method == "GET":
        return redirect("chiedi")

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


class Accesso(LoginView):
    """GET/POST /accedi/ — la porta d'ingresso, con smistamento per ruolo.

    Prima di questa vista LOGIN_URL puntava ad `admin:login`, e la conseguenza
    non era voluta: AdminAuthenticationForm rifiuta chi non ha `is_staff`,
    quindi un utente ordinario NON aveva modo di entrare — nemmeno per
    raggiungere /chiedi/, che e' fatta per lui. Non c'era una decisione dietro:
    mancava una porta che non fosse quella dell'amministrazione.

    LO SMISTAMENTO E' INSTRADAMENTO, NON AUTORIZZAZIONE. Qui si decide soltanto
    su quale pagina si atterra: chi amministra nel pannello di gestione, gli
    altri sull'interrogazione. Nessuno guadagna un permesso che non aveva —
    l'admin continua a difendersi da se', e un utente ordinario che digitasse
    /admin/ verrebbe respinto da Django come prima.

    get_default_redirect_url() e non get_success_url(): la seconda decide anche
    quando c'e' un `next`, e sovrascriverla farebbe perdere la pagina che
    l'utente aveva chiesto prima di essere mandato al login. Il ramo per ruolo
    e' il RIPIEGO, cioe' il caso in cui nessuno ha espresso una destinazione.

    `is_staff` e non `is_superuser`: e' lo stesso discriminante che Django usa
    per decidere chi entra nell'admin, e usarne un altro creerebbe la categoria
    di chi viene smistato in un posto che poi lo respinge.
    """

    template_name = "registration/login.html"
    # Chi ha gia' una sessione non ha nulla da fare qui: lo si porta dove
    # sarebbe finito comunque, invece di mostrargli un modulo da riempire.
    redirect_authenticated_user = True

    def get_default_redirect_url(self) -> str:
        return resolve_url("admin:index" if self.request.user.is_staff else "chiedi")


def radice(request):
    """GET / — smista e non rende nulla.

    La radice non era instradata, e l'admin ci mandava «Visualizza sito» su un
    404: e' il motivo per cui config/urls.py aveva azzerato `site_url`. Ora
    esiste una destinazione sensata per ciascuno, e la radice e' il posto in cui
    dirlo una volta sola — chi apre l'indirizzo del server senza sapere quali
    rotte esistano non deve indovinare `/chiedi/`.

    Uno `redirect` e non una pagina di scelta: una schermata che chiede «dove
    vuoi andare?» a chi ha gia' un ruolo e' una domanda di cui il sistema
    conosce gia' la risposta.
    """
    if not request.user.is_authenticated:
        return redirect("accedi")
    return redirect("admin:index" if request.user.is_staff else "chiedi")


@login_required
def chiedi(request):
    """GET /chiedi/ — la pagina che interroga POST /api/ask/.

    E' l'unica vista del progetto che restituisce HTML e la sola che non sia un
    involucro attorno a un servizio: non chiama rispondi(), non tocca il
    dominio, non scrive un QueryLog. Rende un template e basta; a interrogare
    e' il browser, con una fetch verso l'endpoint gia' esistente. Il confine
    dichiarato nell'intestazione del modulo resta quindi dove sta.

    Perche' esiste, dato che T-33 — il «playground» nell'admin — e' stata
    tagliata in P5. Il taglio aveva una conseguenza scritta: senza, non c'e'
    modo di provare una pipeline dall'interfaccia. L'API navigabile di DRF su
    una vista funzionale non offre un form a campi, ma una casella in cui il
    corpo va scritto a mano come JSON, sotto un'intestazione «Method Not
    Allowed» che sul GET e' corretta e si legge come un guasto. Questa pagina
    copre quel vuoto senza rientrare nel perimetro tagliato: sta fuori
    dall'admin, non aggiunge endpoint e non duplica alcuna regola.

    login_required e non IsAuthenticated di DRF: qui si serve HTML, e a chi non
    ha una sessione va mostrato un login, non un 401 in JSON. Il rimando e'
    LOGIN_URL, che i settings puntano ad Accesso — la porta d'ingresso comune.
    Puntava al login dell'admin, che pero' rifiuta chi non ha is_staff: proprio
    l'utente per cui questa pagina esiste non poteva raggiungerla. Restare
    autenticati serve comunque: la fetch verso /api/ask/ passa da
    SessionAuthentication, e senza sessione il browser riceverebbe 403 dopo
    aver visto la pagina.

    Nessun parametro di comportamento raggiunge il template (RF-22): le
    pipeline le chiede il browser a GET /api/pipelines/, coi loro valori, e a
    decidere resta il server.
    """
    return render(request, "rag/chiedi.html")
