"""Pannello di amministrazione.

E' l'interfaccia con cui si governa il sistema senza toccare il codice
(RF-17 → RF-25). Le descrizioni dei fieldset non sono decorative: distinguono i
parametri che hanno effetto immediato da quelli che impongono una
reindicizzazione (ARCHITECTURE §6.1).

Nota di fase: da P2 il caricamento di un documento ne innesca l'indicizzazione
(RF-29) e l'azione «Reindicizza i documenti selezionati» (T-19) corregge il
disallineamento segnalato dalla colonna omonima. Da P5 (T-32) l'ingestione e'
ASINCRONA: `DocumentAdmin.save_model()` e l'azione non indicizzano piu' in
linea, accodano un task che esegue `manage.py db_worker` in un processo
separato. La pagina non attende piu', e il documento resta «In attesa» finche'
un worker non lo prende.
"""

from pathlib import Path

from django import forms
from django.contrib import admin, messages
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Count

from .models import (
    ChunkingProfile,
    Document,
    DocumentChunk,
    EmbeddingProfile,
    KnowledgeBase,
    LLMProfile,
    PromptTemplate,
    QueryLog,
    RagPipeline,
    RetrievalProfile,
    RetrievedChunk,
)
from .services.ingestion import compute_checksum, trova_duplicato
from .tasks import accoda_indicizzazione

admin.site.site_header = "Sistema RAG — amministrazione"
admin.site.site_title = "Sistema RAG"
admin.site.index_title = "Configurazione e base di conoscenza"

TRACCIAMENTO = (
    "Tracciamento",
    {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
)


# --------------------------------------------------------------------------
# Profili di configurazione (T-11)
# --------------------------------------------------------------------------


@admin.register(LLMProfile)
class LLMProfileAdmin(admin.ModelAdmin):
    list_display = (
        "name", "model_name", "provider", "temperature", "top_p",
        "max_tokens", "timeout_s", "is_default",
    )
    list_filter = ("provider", "is_default")
    search_fields = ("name", "model_name")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "is_default")}),
        (
            "Servizio di inferenza",
            {
                "fields": ("provider", "base_url", "model_name"),
                "description": (
                    "Il modello si cambia scrivendone il nome: nessuna modifica al "
                    "codice, nessun riavvio. Deve essere gia' scaricato su Ollama."
                ),
            },
        ),
        (
            "Parametri di generazione — effetto immediato",
            {
                "fields": ("temperature", "top_p", "top_k", "max_tokens"),
                "description": "Valgono dalla richiesta successiva. Nessuna reindicizzazione.",
            },
        ),
        ("Rete", {"fields": ("timeout_s",)}),
        TRACCIAMENTO,
    )


@admin.register(EmbeddingProfile)
class EmbeddingProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "model_name", "dimension", "provider", "normalize", "batch_size")
    list_filter = ("provider", "normalize")
    search_fields = ("name", "model_name")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "provider", "model_name"),
                "description": (
                    "CONFIGURAZIONE D'INDICE: modificare modello o dimensione rende "
                    "incoerenti i vettori gia' scritti. Il salvataggio viene rifiutato "
                    "finche' esistono documenti indicizzati con questo profilo. "
                    "L'endpoint del servizio di embedding non e' configurabile qui di "
                    "proposito: resta OLLAMA_BASE_URL, cosi' che il testo dei documenti "
                    "abbia un solo punto di uscita possibile (ARCHITECTURE §9)."
                ),
            },
        ),
        (
            "Parametri",
            {
                "fields": ("dimension", "normalize", "batch_size"),
                "description": (
                    "«Dimensione» e' verificata a ogni ingestione: se il modello "
                    "produce vettori di lunghezza diversa, l'indicizzazione si "
                    "ferma con un errore invece di corrompere l'indice in silenzio. "
                    "«Dimensione del lotto» e' il numero di segmenti per chiamata di "
                    "embedding, rispettato dal servizio di ingestione. "
                    "«Normalizza» e' onorato dal modello stesso — bge-m3 restituisce "
                    "vettori a norma 1 — e resta comunque inerte con la distanza "
                    "cosine usata da pgvector, che e' invariante alla scala: il "
                    "codice non lo applica, e il campo lo dichiara."
                ),
            },
        ),
        TRACCIAMENTO,
    )


@admin.register(ChunkingProfile)
class ChunkingProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "splitter", "chunk_size", "chunk_overlap")
    list_filter = ("splitter",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "splitter"),
                "description": (
                    "CONFIGURAZIONE D'INDICE: le modifiche non hanno alcun effetto sui "
                    "documenti gia' indicizzati, che risulteranno disallineati e da "
                    "reindicizzare."
                ),
            },
        ),
        ("Segmentazione", {"fields": ("chunk_size", "chunk_overlap", "separators")}),
        TRACCIAMENTO,
    )


@admin.register(RetrievalProfile)
class RetrievalProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "search_type", "top_k", "fetch_k", "lambda_mult", "score_threshold")
    list_filter = ("search_type",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "search_type"),
                "description": (
                    "Effetto immediato. «Similarita' con soglia» usa "
                    "score_threshold, «MMR» usa fetch_k e lambda: gli altri "
                    "campi restano inerti."
                ),
            },
        ),
        (
            "Parametri",
            {
                "fields": ("top_k", "fetch_k", "lambda_mult", "score_threshold"),
                "description": (
                    "La «soglia di punteggio» si confronta con la RILEVANZA "
                    "(1 − distanza cosine), non con la distanza grezza di "
                    "pgvector: 1 = identico, 0 = estraneo. E' lo stesso numero "
                    "mostrato accanto a ogni fonte nella risposta. Misure sul "
                    "corpus di prova: domanda pertinente 0,68–0,73; stesso "
                    "documento ma pagina sbagliata 0,35–0,46; domanda fuori "
                    "tema 0,15–0,26. Il valore predefinito 0,5 cade fra la "
                    "prima e la seconda banda. La soglia si applica DOPO "
                    "«segmenti recuperati»: alzarla puo' restituire zero fonti."
                ),
            },
        ),
        TRACCIAMENTO,
    )


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "anteprima")
    search_fields = ("name", "system_prompt", "template")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name",)}),
        (
            "Prompt",
            {
                "fields": ("system_prompt", "template"),
                "description": (
                    "Il template deve contenere {context} e {question}. Effetto "
                    "immediato sulla richiesta successiva."
                ),
            },
        ),
        TRACCIAMENTO,
    )

    @admin.display(description="anteprima del prompt di sistema")
    def anteprima(self, obj):
        testo = obj.system_prompt or ""
        return f"{testo[:80]}…" if len(testo) > 80 else testo


# --------------------------------------------------------------------------
# Dominio (T-12)
# --------------------------------------------------------------------------


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = (
        "name", "collection_name", "embedding_profile", "chunking_profile", "numero_documenti",
    )
    list_select_related = ("embedding_profile", "chunking_profile")
    search_fields = ("name", "collection_name")
    readonly_fields = ("created_at", "updated_at", "impronta")
    fieldsets = (
        (None, {"fields": ("name", "collection_name", "description")}),
        (
            "Configurazione d'indice",
            {
                "fields": ("embedding_profile", "chunking_profile", "impronta"),
                "description": (
                    "Cambiare questi profili rende disallineati i documenti gia' "
                    "indicizzati: l'elenco dei documenti lo segnala."
                ),
            },
        ),
        TRACCIAMENTO,
    )

    def get_queryset(self, request):
        # Senza l'annotazione, numero_documenti farebbe una COUNT per riga.
        return super().get_queryset(request).annotate(_documenti=Count("documents"))

    @admin.display(description="documenti", ordering="_documenti")
    def numero_documenti(self, obj):
        return obj._documenti

    @admin.display(description="impronta della configurazione")
    def impronta(self, obj):
        return obj.index_fingerprint() if obj.pk else "—"


@admin.register(RagPipeline)
class RagPipelineAdmin(admin.ModelAdmin):
    list_display = (
        "name", "knowledge_base", "llm_profile", "retrieval_profile",
        "prompt_template", "is_active", "is_default",
    )
    list_filter = ("is_active", "is_default", "knowledge_base")
    list_select_related = (
        "knowledge_base", "llm_profile", "retrieval_profile", "prompt_template",
    )
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "is_active", "is_default"),
                "description": (
                    "Piu' pipeline possono coesistere sulla stessa base di conoscenza "
                    "e si confrontano selezionandole nella richiesta (RF-23, CA-7)."
                ),
            },
        ),
        ("Composizione", {"fields": ("knowledge_base", "llm_profile", "retrieval_profile", "prompt_template")}),
        TRACCIAMENTO,
    )


class DocumentChunkInline(admin.TabularInline):
    """Segmenti in sola lettura: li crea l'ingestione (P2), non l'amministratore."""

    model = DocumentChunk
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("ordinal", "page_number", "char_count", "estratto", "vector_id")
    readonly_fields = fields
    ordering = ("ordinal",)

    @admin.display(description="estratto")
    def estratto(self, obj):
        testo = obj.content or ""
        return f"{testo[:120]}…" if len(testo) > 120 else testo

    def has_add_permission(self, request, obj=None):
        return False


class DocumentAdminForm(forms.ModelForm):
    """Deduplica al momento del caricamento (RF-09).

    Perche' serve un form invece del solo vincolo di database: il ModelForm
    dell'admin esclude dalla validazione i campi in readonly_fields, e
    `checksum` e' fra quelli. Il vincolo document_checksum_unico_per_kb non
    viene quindi mai verificato dalla pagina, e un duplicato arriverebbe al
    database come IntegrityError, cioe' una 500. Accertato in P1, passo 4.5.

    Il controllo qui evita anche di CREARE la riga: l'alternativa —
    intercettare in ingest_document e marcare «Fallito» — lascerebbe in elenco
    un documento inutile per ogni tentativo.
    """

    class Meta:
        model = Document
        fields = "__all__"

    def clean(self):
        dati = super().clean()
        file = dati.get("file")
        # Su un documento esistente knowledge_base e' in sola lettura (cfr.
        # DocumentAdmin.get_readonly_fields), quindi non arriva in cleaned_data:
        # va ripreso dall'istanza, altrimenti sostituire il file di un documento
        # gia' salvato aggirerebbe il controllo di deduplica.
        kb = dati.get("knowledge_base") or getattr(self.instance, "knowledge_base", None)
        if not file or not kb:
            return dati

        # Solo sui file appena CARICATI. Su una modifica che non tocca il file,
        # cleaned_data["file"] e' il FieldFile gia' salvato: ricalcolarne il
        # checksum vorrebbe dire rileggere dal disco per confrontarlo con se
        # stesso, e su Windows lascerebbe un handle aperto.
        # isinstance(..., UploadedFile) e' il discriminante corretto: verificato
        # che un FieldFile NON e' un UploadedFile, mentre un upload lo e'.
        if not isinstance(file, UploadedFile):
            return dati

        checksum = compute_checksum(file)   # seek(0) incluso: senza, si
                                            # salverebbe un file vuoto
        esistente = trova_duplicato(kb.pk, checksum, escludi_id=self.instance.pk)
        if esistente is not None:
            raise forms.ValidationError(
                {
                    "file": (
                        f"Questo file e' gia' presente nella base di conoscenza "
                        f"«{kb.name}» come documento {esistente.pk} "
                        f"({esistente}). Per rifarne l'indice usare l'azione "
                        "«Reindicizza i documenti selezionati»."
                    )
                }
            )
        return dati


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentAdminForm
    actions = ["reindicizza"]
    list_display = (
        "__str__", "knowledge_base", "status", "page_count", "chunk_count",
        "disallineato", "uploaded_at",
    )
    list_filter = ("status", "knowledge_base")
    list_select_related = (
        "knowledge_base",
        "knowledge_base__embedding_profile",
        "knowledge_base__chunking_profile",
    )
    search_fields = ("original_filename", "checksum")
    date_hierarchy = "uploaded_at"
    inlines = [DocumentChunkInline]
    readonly_fields = (
        "status", "checksum", "page_count", "chunk_count", "error_message",
        "indexed_embedding_profile", "indexed_chunking_profile", "index_fingerprint",
        "uploaded_at", "indexed_at", "disallineato",
    )
    fieldsets = (
        (
            None,
            {
                "fields": ("knowledge_base", "file", "original_filename"),
                "description": (
                    "Il salvataggio mette il documento in coda per "
                    "l'indicizzazione, che e' ASINCRONA da P5: la pagina non "
                    "attende piu'. Il documento resta «In attesa» finche' "
                    "`manage.py db_worker` non lo prende, e lo stato si "
                    "aggiorna da solo. Se nessun worker e' in esecuzione, resta "
                    "«In attesa» a tempo indeterminato. Lo stesso file non puo' "
                    "essere caricato due volte nella stessa base di conoscenza."
                ),
            },
        ),
        ("Stato", {"fields": ("status", "page_count", "chunk_count", "error_message")}),
        (
            "Indicizzazione",
            {
                "fields": (
                    "indexed_embedding_profile", "indexed_chunking_profile",
                    "index_fingerprint", "disallineato", "indexed_at",
                ),
                "description": (
                    "Snapshot della configurazione usata. «Disallineato» segnala che i "
                    "profili sono cambiati dopo l'indicizzazione (RF-25). Per "
                    "riallineare un documento, usare l'azione «Reindicizza i "
                    "documenti selezionati»."
                ),
            },
        ),
        ("File", {"fields": ("checksum", "uploaded_at"), "classes": ("collapse",)}),
    )

    @admin.display(boolean=True, description="disallineato")
    def disallineato(self, obj):
        return obj.needs_reindex

    def get_readonly_fields(self, request, obj=None):
        """La base di conoscenza si sceglie al caricamento e poi non si tocca.

        Non e' una restrizione prudenziale: spostare un documento gia'
        indicizzato lo renderebbe INVISIBILE in silenzio. I suoi vettori
        restano nella collezione di partenza, e nulla lo segnala — il
        fingerprint di RF-25 confronta i VALORI dei profili, non l'identita'
        della base, quindi fra due basi configurate uguali «disallineato»
        resta falso.

        Nemmeno reindicizzare basterebbe: l'upsert di langchain-postgres
        aggiorna `embedding`, `document` e `cmetadata` ma NON `collection_id`
        (verificato sul sorgente della 0.0.17), quindi il vettore verrebbe
        riscritto restando agganciato alla collezione vecchia.

        Per spostare un documento si cancella e si ricarica: la cancellazione
        porta via i vettori (RF-08) e il nuovo caricamento li scrive nella
        collezione giusta.
        """
        campi = super().get_readonly_fields(request, obj)
        if obj is not None:
            return tuple(campi) + ("knowledge_base",)
        return campi

    def save_model(self, request, obj, form, change):
        """Salva e ACCODA l'indicizzazione (RF-29, T-32).

        L'innesco sta qui e non in un signal post_save: il servizio salva il
        documento piu' volte — «In elaborazione», poi lo stato finale — e un
        post_save si richiamerebbe da se'.

        Da P5 la pagina non attende piu' l'indicizzazione: era il punto in cui
        l'admin restava appeso fino a ~18 s a freddo. Il documento resta «In
        attesa» finche' `manage.py db_worker` non lo prende; se nessun worker
        e' in esecuzione, resta «In attesa» a tempo indeterminato — ed e'
        esattamente cio' che /health riporta sotto la voce «coda».
        """
        if not obj.original_filename and obj.file:
            obj.original_filename = Path(obj.file.name).name
        super().save_model(request, obj, form, change)

        # Un documento gia' indicizzato che viene salvato senza cambiare file
        # non va reindicizzato di nascosto: per quello c'e' l'azione.
        if change and obj.status == Document.Status.INDEXED and "file" not in form.changed_data:
            return

        accoda_indicizzazione(obj)
        self.message_user(
            request,
            "Documento messo in coda per l'indicizzazione. Lo stato si aggiorna "
            "da solo: ricaricare l'elenco fra qualche secondo. Se resta «In "
            "attesa», nessun worker e' in esecuzione (manage.py db_worker).",
            messages.INFO,
        )

    @admin.action(description="Reindicizza i documenti selezionati")
    def reindicizza(self, request, queryset):
        """RF-07 e RF-25: rielaborare senza ricaricare.

        Da P5 la richiesta non dura piu' N ingestioni: accoda N task e torna
        subito. E' il limite di P2 che T-32 rimuove — con N documenti
        l'azione costava N volte fino a 18 s, e su un elenco lungo l'admin
        finiva in timeout.
        """
        accodati = 0
        for documento in queryset:
            accoda_indicizzazione(documento)
            accodati += 1
        self.message_user(
            request,
            f"{accodati} documenti messi in coda. L'esito di ciascuno compare "
            f"sul documento stesso: stato «Indicizzato», oppure «Fallito» con "
            f"il motivo.",
            messages.SUCCESS,
        )


# --------------------------------------------------------------------------
# Osservabilita' (T-10)
# --------------------------------------------------------------------------


class RetrievedChunkInline(admin.TabularInline):
    """Segmenti recuperati da una interrogazione (RF-16).

    «Punteggio» e' la RILEVANZA — 1 meno la distanza cosine — cioe' la stessa
    grandezza confrontata con la soglia del profilo di recupero e mostrata
    accanto a ogni fonte nella risposta.
    """

    model = RetrievedChunk
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("rank", "chunk", "documento", "pagina", "score")
    readonly_fields = fields
    ordering = ("rank",)

    @admin.display(description="documento")
    def documento(self, obj):
        # Il segmento puo' essere sparito: RetrievedChunk.chunk e' SET_NULL
        # perche' lo storico deve sopravvivere alla cancellazione del
        # documento (ARCHITECTURE §6.4). Qui si vede come «—».
        return obj.chunk.document if obj.chunk else "—"

    @admin.display(description="pagina")
    def pagina(self, obj):
        return obj.chunk.page_number if obj.chunk else "—"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    """Sola lettura: lo storico lo scrive il sistema (P3, T-26), non l'amministratore."""

    list_display = (
        "__str__", "pipeline", "user", "fonti", "retrieval_ms", "generation_ms",
        "latency_ms", "created_at",
    )
    list_filter = ("pipeline", "created_at")
    list_select_related = ("pipeline", "user")
    search_fields = ("question", "answer")
    date_hierarchy = "created_at"
    inlines = [RetrievedChunkInline]
    readonly_fields = (
        "pipeline", "user", "question", "answer", "retrieval_ms",
        "generation_ms", "latency_ms", "error", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # Senza l'annotazione, «fonti» farebbe una COUNT per riga.
        return super().get_queryset(request).annotate(_fonti=Count("retrieved_chunks"))

    @admin.display(description="fonti", ordering="_fonti")
    def fonti(self, obj):
        return obj._fonti
