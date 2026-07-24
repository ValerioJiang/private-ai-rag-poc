"""Pannello di amministrazione.

E' l'interfaccia con cui si governa il sistema senza toccare il codice
(RF-17 → RF-25). Le descrizioni dei fieldset non sono decorative: distinguono i
parametri che hanno effetto immediato da quelli che impongono una
reindicizzazione (ARCHITECTURE §6.1).

Nota di fase: da P2 il caricamento di un documento ne innesca l'indicizzazione
(RF-29) e l'azione «Reindicizza i documenti selezionati» (T-19) corregge il
disallineamento segnalato dalla colonna omonima. L'ingestione e' SINCRONA:
diventera' asincrona in P5 (T-32), e l'unico punto da cambiare e'
`DocumentAdmin.save_model()`.
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
from .services.exceptions import IngestionError
from .services.ingestion import compute_checksum, ingest_document, trova_duplicato

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
                    "Effetto immediato. «Similarita' con soglia» usa score_threshold, "
                    "«MMR» usa fetch_k e lambda: gli altri campi restano inerti."
                ),
            },
        ),
        ("Parametri", {"fields": ("top_k", "fetch_k", "lambda_mult", "score_threshold")}),
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
        kb = dati.get("knowledge_base")
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
                    "Il salvataggio avvia immediatamente l'indicizzazione, che e' "
                    "SINCRONA: la pagina resta in attesa per tutta la sua durata, e "
                    "il primo embedding dopo l'avvio puo' richiedere ~20 s per il "
                    "caricamento del modello in VRAM. Lo stesso file non puo' essere "
                    "caricato due volte nella stessa base di conoscenza."
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

    def save_model(self, request, obj, form, change):
        """Salva e indicizza (RF-29).

        L'innesco sta qui e non in un signal post_save: il servizio salva il
        documento piu' volte — «In elaborazione», poi lo stato finale — e un
        post_save si richiamerebbe da se'. In P5 (T-32) questa chiamata
        diventa un enqueue e resta l'unico punto da modificare.
        """
        if not obj.original_filename and obj.file:
            obj.original_filename = Path(obj.file.name).name
        super().save_model(request, obj, form, change)

        # Un documento gia' indicizzato che viene salvato senza cambiare file
        # non va reindicizzato di nascosto: per quello c'e' l'azione.
        if change and obj.status == Document.Status.INDEXED and "file" not in form.changed_data:
            return

        try:
            esito = ingest_document(obj)
        except IngestionError as exc:
            self.message_user(request, f"Indicizzazione non riuscita: {exc}", messages.ERROR)
        except Exception as exc:  # noqa: BLE001 - l'admin non deve mostrare una 500
            self.message_user(
                request,
                f"Indicizzazione interrotta da un errore inatteso: {exc}. "
                "Il motivo e' registrato sul documento.",
                messages.ERROR,
            )
        else:
            self.message_user(
                request,
                f"Documento indicizzato: {esito.chunk_count} segmenti su "
                f"{esito.page_count} pagine in {esito.durata_s:.1f}s.",
                messages.SUCCESS,
            )

    @admin.action(description="Reindicizza i documenti selezionati")
    def reindicizza(self, request, queryset):
        """RF-07 e RF-25: rielaborare senza ricaricare.

        Sincrona, quindi con N documenti la richiesta dura N ingestioni. E' il
        limite dichiarato di P2, che T-32 rimuove.
        """
        riusciti = falliti = 0
        for documento in queryset:
            try:
                ingest_document(documento)
                riusciti += 1
            except Exception as exc:  # noqa: BLE001 - un fallimento non ferma gli altri
                falliti += 1
                self.message_user(request, f"{documento}: {exc}", messages.ERROR)
        if riusciti:
            self.message_user(
                request, f"{riusciti} documenti reindicizzati.", messages.SUCCESS
            )
        if falliti:
            self.message_user(
                request,
                f"{falliti} documenti non reindicizzati: il motivo e' sul singolo documento.",
                messages.WARNING,
            )


# --------------------------------------------------------------------------
# Osservabilita' (T-10)
# --------------------------------------------------------------------------


class RetrievedChunkInline(admin.TabularInline):
    model = RetrievedChunk
    extra = 0
    max_num = 0
    can_delete = False
    fields = ("rank", "chunk", "score")
    readonly_fields = fields
    ordering = ("rank",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    """Sola lettura: lo storico lo scrive il sistema (P3, T-26), non l'amministratore."""

    list_display = (
        "__str__", "pipeline", "user", "retrieval_ms", "generation_ms",
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
