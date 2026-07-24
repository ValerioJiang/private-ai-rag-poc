"""Profili di configurazione: ogni parametro del RAG e' una riga di database.

Si dividono in due famiglie (ARCHITECTURE.md §6.1):

- configurazione d'INDICE (EmbeddingProfile, ChunkingProfile): determina come
  l'indice e' costruito, quindi modificarla impone una reindicizzazione. Vive
  sulla KnowledgeBase;
- configurazione di QUERY (LLMProfile, RetrievalProfile, PromptTemplate):
  determina come l'indice viene interrogato, ha effetto sulla richiesta
  successiva. Vive sulla RagPipeline.

I valori di default non sono inventati: sono quelli misurati in P0 sulla
macchina (cfr. il report di P0, sezione «DATI DI REALTA'»).
"""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

# Risposta esatta prodotta dal modello quando il contesto non contiene
# l'informazione. Verificata carattere per carattere in P0 (criterio CA-4);
# in P3 (T-25) sara' anche il valore restituito quando nessun chunk supera la
# soglia di similarita', senza nemmeno interrogare l'LLM.
RISPOSTA_NON_DISPONIBILE = "Non dispongo di questa informazione nei documenti forniti."

DEFAULT_SYSTEM_PROMPT = (
    "Sei un assistente che risponde ESCLUSIVAMENTE sulla base del contesto fornito. "
    "Se il contesto non contiene l'informazione, rispondi esattamente: "
    f"'{RISPOSTA_NON_DISPONIBILE}' "
    "Rispondi in italiano, in modo conciso."
)

DEFAULT_TEMPLATE = "Contesto:\n{context}\n\nDomanda: {question}"


class TimestampedModel(models.Model):
    """Base comune: quando un profilo e' stato creato e modificato."""

    created_at = models.DateTimeField("creato il", auto_now_add=True)
    updated_at = models.DateTimeField("modificato il", auto_now=True)

    class Meta:
        abstract = True


class LLMProfile(TimestampedModel):
    """Modello di generazione e suoi parametri (RF-17, RF-18)."""

    class Provider(models.TextChoices):
        OLLAMA = "ollama", "Ollama"
        OPENAI_COMPATIBLE = "openai_compatible", "API OpenAI-compatibile"

    name = models.CharField("nome", max_length=100, unique=True)
    provider = models.CharField(
        "provider", max_length=32, choices=Provider.choices, default=Provider.OLLAMA
    )
    base_url = models.URLField(
        "base URL",
        default="http://localhost:11434",
        help_text=(
            "Endpoint del servizio di inferenza. Cambiarlo sposta la generazione "
            "su un altro host: e' cio' che rende il sistema riconfigurabile, ed e' "
            "anche l'unica falla dichiarata nella garanzia di non esfiltrazione "
            "(ARCHITECTURE §8.2 e §9)."
        ),
    )
    model_name = models.CharField("modello", max_length=120, default="qwen2.5:7b-instruct")
    temperature = models.FloatField(
        "temperatura",
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(2.0)],
        help_text="0 = deterministico. Verificato in P0: a 0 la risposta e' riproducibile.",
    )
    top_p = models.FloatField(
        "top-p", default=0.9, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    top_k = models.PositiveIntegerField("top-k", default=40)
    max_tokens = models.PositiveIntegerField("token massimi", default=1024)
    timeout_s = models.PositiveIntegerField(
        "timeout (s)",
        default=180,
        help_text=(
            "Il primo caricamento del modello in VRAM ha richiesto fino a 156 s "
            "in P0, e il cold start si ripresenta a meta' sessione per contesa di "
            "VRAM. Non scendere sotto i 180 s."
        ),
    )
    is_default = models.BooleanField("predefinito", default=False)

    class Meta:
        verbose_name = "profilo LLM"
        verbose_name_plural = "profili LLM"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(temperature__gte=0) & Q(temperature__lte=2),
                name="llmprofile_temperatura_0_2",
                violation_error_message="La temperatura deve essere compresa fra 0 e 2.",
            ),
            models.CheckConstraint(
                condition=Q(top_p__gte=0) & Q(top_p__lte=1),
                name="llmprofile_top_p_0_1",
                violation_error_message="top-p deve essere compreso fra 0 e 1.",
            ),
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="llmprofile_unico_predefinito",
                violation_error_message=(
                    "Esiste gia' un profilo LLM predefinito: toglierlo da quello "
                    "attuale prima di designarne un altro."
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.model_name})"


class EmbeddingProfile(TimestampedModel):
    """Modello di embedding. Configurazione d'INDICE: cambiarlo invalida i vettori.

    Nota deliberata: qui NON c'e' base_url. L'endpoint degli embedding resta
    settings.OLLAMA_BASE_URL, cioe' infrastruttura. Renderlo configurabile
    aggiungerebbe un secondo punto da cui il testo dei chunk potrebbe uscire
    dal perimetro, senza alcun beneficio (e' lo stesso Ollama dell'LLM).
    Cfr. ARCHITECTURE §9.
    """

    class Provider(models.TextChoices):
        OLLAMA = "ollama", "Ollama"
        HUGGINGFACE = "huggingface", "HuggingFace (in-process)"

    name = models.CharField("nome", max_length=100, unique=True)
    provider = models.CharField(
        "provider", max_length=32, choices=Provider.choices, default=Provider.OLLAMA
    )
    model_name = models.CharField("modello", max_length=120, default="bge-m3")
    dimension = models.PositiveIntegerField(
        "dimensione del vettore",
        default=1024,
        help_text=(
            "Misurata in P0 su bge-m3: 1024. La colonna pgvector creata da "
            "langchain-postgres non dichiara la dimensione, quindi il database "
            "NON impone la coerenza: profili con dimensioni diverse vanno tenuti "
            "su collezioni diverse."
        ),
    )
    normalize = models.BooleanField("normalizza", default=True)
    batch_size = models.PositiveIntegerField(
        "dimensione del lotto",
        default=16,
        validators=[MinValueValidator(1)],
        help_text="Chunk per chiamata di embedding. In P0 il costo a caldo e' ~0,4 s/chunk.",
    )

    class Meta:
        verbose_name = "profilo di embedding"
        verbose_name_plural = "profili di embedding"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.model_name}, {self.dimension}d)"


class ChunkingProfile(TimestampedModel):
    """Strategia di segmentazione (RF-19). Configurazione d'INDICE."""

    class Splitter(models.TextChoices):
        RECURSIVE = "recursive", "Recursive character"
        TOKEN = "token", "Basato su token"

    name = models.CharField("nome", max_length=100, unique=True)
    splitter = models.CharField(
        "strategia", max_length=32, choices=Splitter.choices, default=Splitter.RECURSIVE
    )
    chunk_size = models.PositiveIntegerField(
        "dimensione del segmento", default=800, validators=[MinValueValidator(50)]
    )
    chunk_overlap = models.PositiveIntegerField("sovrapposizione", default=120)
    separators = models.JSONField(
        "separatori",
        default=list,
        blank=True,
        help_text=(
            'Elenco JSON di stringhe, in ordine di priorita\'. Esempio: '
            '["\\n\\n", "\\n", " ", ""]. Vuoto = separatori predefiniti dello splitter.'
        ),
    )

    class Meta:
        verbose_name = "profilo di segmentazione"
        verbose_name_plural = "profili di segmentazione"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(chunk_overlap__lt=F("chunk_size")),
                name="chunkingprofile_overlap_minore_di_size",
                violation_error_message=(
                    "La sovrapposizione deve essere inferiore alla dimensione del "
                    "segmento, altrimenti la segmentazione non avanza."
                ),
            ),
        ]

    def clean(self) -> None:
        super().clean()
        # Il widget JSONField dell'admin, lasciato vuoto, restituisce None: senza
        # questa normalizzazione il campo — dichiarato blank=True — sarebbe di
        # fatto obbligatorio, e l'utente vedrebbe un errore incomprensibile.
        # (forms.JSONField(required=False).clean("") -> None, verificato.)
        if self.separators is None:
            self.separators = []
        if not isinstance(self.separators, list) or any(
            not isinstance(s, str) for s in self.separators
        ):
            raise ValidationError(
                {"separators": "Deve essere un elenco JSON di stringhe, anche vuoto."}
            )

    def __str__(self) -> str:
        return f"{self.name} ({self.chunk_size}/{self.chunk_overlap})"


class RetrievalProfile(TimestampedModel):
    """Strategia di recupero (RF-20). Configurazione di QUERY."""

    class SearchType(models.TextChoices):
        # Il VALORE memorizzato e' la stringa attesa da VectorStore.as_retriever():
        # in P2/P3 la factory la passa cosi' com'e', senza conversioni.
        SIMILARITY = "similarity", "Similarita'"
        MMR = "mmr", "MMR (diversificata)"
        THRESHOLD = "similarity_score_threshold", "Similarita' con soglia"

    name = models.CharField("nome", max_length=100, unique=True)
    search_type = models.CharField(
        "strategia", max_length=32, choices=SearchType.choices, default=SearchType.SIMILARITY
    )
    top_k = models.PositiveIntegerField(
        "segmenti recuperati", default=4, validators=[MinValueValidator(1)]
    )
    fetch_k = models.PositiveIntegerField(
        "candidati esaminati (MMR)",
        default=20,
        help_text="Usato solo da MMR: quanti candidati recuperare prima di diversificare.",
    )
    lambda_mult = models.FloatField(
        "lambda (MMR)",
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="1 = massima pertinenza, 0 = massima diversita'.",
    )
    score_threshold = models.FloatField(
        "soglia di punteggio",
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Usata solo dalla strategia «Similarita' con soglia» (RF-14).",
    )

    class Meta:
        verbose_name = "profilo di recupero"
        verbose_name_plural = "profili di recupero"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fetch_k__gte=F("top_k")),
                name="retrievalprofile_fetch_k_gte_top_k",
                violation_error_message=(
                    "I candidati esaminati non possono essere meno dei segmenti "
                    "restituiti."
                ),
            ),
            models.CheckConstraint(
                condition=Q(lambda_mult__gte=0) & Q(lambda_mult__lte=1),
                name="retrievalprofile_lambda_0_1",
                violation_error_message="Lambda deve essere compreso fra 0 e 1.",
            ),
            models.CheckConstraint(
                condition=Q(score_threshold__gte=0) & Q(score_threshold__lte=1),
                name="retrievalprofile_soglia_0_1",
                violation_error_message="La soglia deve essere compresa fra 0 e 1.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_search_type_display()}, k={self.top_k})"


class PromptTemplate(TimestampedModel):
    """Prompt di generazione, modificabile dall'admin (RF-21).

    Attenzione in P3: il nome coincide con langchain_core.prompts.PromptTemplate.
    Nella factory importare l'uno o l'altro con un alias esplicito.
    """

    name = models.CharField("nome", max_length=100, unique=True)
    system_prompt = models.TextField(
        "prompt di sistema",
        default=DEFAULT_SYSTEM_PROMPT,
        help_text=(
            "Verificato in P0: con questo testo il modello dichiara di non sapere "
            "invece di inventare, anche ricevendo contesto irrilevante (CA-4)."
        ),
    )
    template = models.TextField(
        "template",
        default=DEFAULT_TEMPLATE,
        help_text="Deve contenere i segnaposto {context} e {question}.",
    )

    class Meta:
        verbose_name = "prompt"
        verbose_name_plural = "prompt"
        ordering = ["name"]

    def clean(self) -> None:
        super().clean()
        mancanti = [p for p in ("{context}", "{question}") if p not in (self.template or "")]
        if mancanti:
            raise ValidationError(
                {
                    "template": (
                        "Segnaposto mancanti: "
                        + ", ".join(mancanti)
                        + ". Senza di essi la catena ignorerebbe il contesto o la domanda."
                    )
                }
            )

    def __str__(self) -> str:
        return self.name
