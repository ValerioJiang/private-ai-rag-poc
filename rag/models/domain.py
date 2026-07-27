"""Entita' di dominio: basi di conoscenza, pipeline, documenti e segmenti.

Le tabelle langchain_pg_collection e langchain_pg_embedding NON compaiono qui:
sono create e gestite da langchain_postgres.PGVector e restano fuori dalle
migrazioni Django (ARCHITECTURE §6.3). Il ponte fra i due mondi e'
DocumentChunk.vector_id.
"""

import hashlib
import json

from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.db.models import Q

from .profiles import (
    ChunkingProfile,
    EmbeddingProfile,
    LLMProfile,
    PromptTemplate,
    RetrievalProfile,
    TimestampedModel,
)


class KnowledgeBase(TimestampedModel):
    """Raccolta documentale (RF-02). Porta la configurazione d'INDICE."""

    name = models.CharField("nome", max_length=100, unique=True)
    collection_name = models.CharField(
        "nome della collezione",
        max_length=63,
        unique=True,
        validators=[
            RegexValidator(
                r"^[a-z][a-z0-9_]*$",
                "Solo minuscole, cifre e underscore; deve iniziare per lettera.",
            )
        ],
        help_text=(
            "Nome della collezione in pgvector. Profili di embedding diversi "
            "DEVONO stare su collezioni diverse: la colonna dei vettori non "
            "dichiara la dimensione, quindi il database non li separerebbe."
        ),
    )
    description = models.TextField("descrizione", blank=True)
    embedding_profile = models.ForeignKey(
        EmbeddingProfile,
        on_delete=models.PROTECT,
        related_name="knowledge_bases",
        verbose_name="profilo di embedding",
    )
    chunking_profile = models.ForeignKey(
        ChunkingProfile,
        on_delete=models.PROTECT,
        related_name="knowledge_bases",
        verbose_name="profilo di segmentazione",
    )

    # --- limiti di ammissione (T-44, RF-22) ---------------------------
    # Stanno qui e non nel codice per la stessa ragione di excerpt_length:
    # sono parametri di COMPORTAMENTO, e RF-22 non ne ammette fuori dal
    # database. Stanno sulla base di conoscenza e non sul profilo di
    # segmentazione perche' riguardano QUALI FILE si accettano, non come si
    # divide il testo gia' estratto.
    #
    # Zero disattiva, ed e' il default: le righe esistenti — comprese quelle
    # create dalla 0004 — mantengono il comportamento con cui P2 → P6 hanno
    # misurato.
    max_file_size_mb = models.PositiveIntegerField(
        "dimensione massima (MB)",
        default=0,
        help_text=(
            "Oltre questa dimensione il caricamento e' respinto subito, con "
            "400 e senza creare ne' la riga ne' il file. Zero disattiva il "
            "controllo. La coda e' seriale: un file molto grande non fallisce, "
            "occupa il worker e ritarda tutti gli altri documenti."
        ),
    )
    max_page_count = models.PositiveIntegerField(
        "pagine massime",
        default=0,
        help_text=(
            "Oltre questo numero di pagine il caricamento e' respinto subito. "
            "Zero disattiva il controllo E il PDF non viene nemmeno aperto: "
            "con un limite attivo un file corrotto e' scoperto dalla POST "
            "invece che dal worker, ed e' un cambio di contratto dichiarato "
            "nel README. L'indicizzazione costa circa un secondo per segmento."
        ),
    )
    min_text_page_ratio = models.FloatField(
        "rapporto minimo di pagine con testo",
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=(
            "Fra 0 e 1. Sotto questa quota di pagine con testo estraibile il "
            "documento e' marcato «Fallito» dal worker, con il conteggio nel "
            "motivo. Serve contro le scansioni PARZIALI: se NESSUNA pagina ha "
            "testo interviene gia' il controllo di RF-10. Zero disattiva. "
            "L'OCR resta fuori ambito (REQUIREMENTS §8)."
        ),
    )

    class Meta:
        verbose_name = "base di conoscenza"
        verbose_name_plural = "basi di conoscenza"
        ordering = ["name"]

    def index_fingerprint(self) -> str:
        """Hash dei VALORI dei profili d'indice attualmente configurati.

        Non degli identificativi: se un profilo viene modificato sul posto — il
        caso realistico, visto che dall'admin si editano i profili esistenti —
        l'FK resta uguale ma il fingerprint cambia. E' il criterio di RF-25.
        """
        e, c = self.embedding_profile, self.chunking_profile
        payload = {
            "embedding": {
                "provider": e.provider,
                "model_name": e.model_name,
                "dimension": e.dimension,
                "normalize": e.normalize,
            },
            "chunking": {
                "splitter": c.splitter,
                "chunk_size": c.chunk_size,
                "chunk_overlap": c.chunk_overlap,
                "separators": c.separators,
            },
        }
        canonico = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonico.encode("utf-8")).hexdigest()

    def __str__(self) -> str:
        return self.name


class RagPipeline(TimestampedModel):
    """Configurazione completa e selezionabile per singola interrogazione.

    E' l'entita' che rende dimostrabili RF-23 e CA-7: due pipeline sulla stessa
    base di conoscenza, una «veloce» e una «accurata», si confrontano cambiando
    un campo nella richiesta.
    """

    name = models.CharField("nome", max_length=100, unique=True)
    knowledge_base = models.ForeignKey(
        KnowledgeBase, on_delete=models.PROTECT, related_name="pipelines",
        verbose_name="base di conoscenza",
    )
    llm_profile = models.ForeignKey(
        LLMProfile, on_delete=models.PROTECT, related_name="pipelines",
        verbose_name="profilo LLM",
    )
    retrieval_profile = models.ForeignKey(
        RetrievalProfile, on_delete=models.PROTECT, related_name="pipelines",
        verbose_name="profilo di recupero",
    )
    prompt_template = models.ForeignKey(
        PromptTemplate, on_delete=models.PROTECT, related_name="pipelines",
        verbose_name="prompt",
    )
    is_active = models.BooleanField("attiva", default=True)
    is_default = models.BooleanField("predefinita", default=False)

    class Meta:
        verbose_name = "pipeline RAG"
        verbose_name_plural = "pipeline RAG"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="ragpipeline_unica_predefinita",
                violation_error_message=(
                    "Esiste gia' una pipeline predefinita: toglierlo da quella "
                    "attuale prima di designarne un'altra."
                ),
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.is_default and not self.is_active:
            raise ValidationError(
                {"is_active": "La pipeline predefinita deve essere attiva."}
            )

    def __str__(self) -> str:
        return self.name


class Document(models.Model):
    """PDF caricato in una base di conoscenza (RF-01, RF-06).

    La macchina a stati e' scritta qui ma la fanno girare i servizi di P2: in P1
    un documento creato dall'admin resta in stato «in attesa», perche' non
    esiste ancora nulla che lo indicizzi.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "In attesa"
        PROCESSING = "processing", "In elaborazione"
        INDEXED = "indexed", "Indicizzato"
        FAILED = "failed", "Fallito"

    knowledge_base = models.ForeignKey(
        KnowledgeBase, on_delete=models.CASCADE, related_name="documents",
        verbose_name="base di conoscenza",
    )
    file = models.FileField(
        "file",
        upload_to="documents/%Y/%m/",
        validators=[FileExtensionValidator(["pdf"])],
        help_text="Solo PDF. I PDF scansionati senza testo verranno rifiutati in fase di ingestione (RF-10).",
    )
    original_filename = models.CharField("nome originale", max_length=255, blank=True)
    checksum = models.CharField(
        "checksum",
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 del file. Calcolato dall'ingestione (T-20), vuoto finche' il documento non e' stato elaborato.",
    )
    status = models.CharField(
        "stato", max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    page_count = models.PositiveIntegerField("pagine", default=0)
    chunk_count = models.PositiveIntegerField("segmenti", default=0)
    error_message = models.TextField("errore", blank=True)

    # Snapshot dei profili usati all'indicizzazione: servono alla leggibilita'
    # nell'admin (si vede QUALE profilo era attivo). Il criterio effettivo di
    # disallineamento e' pero' il fingerprint. Cfr. ARCHITECTURE §6.1.
    indexed_embedding_profile = models.ForeignKey(
        EmbeddingProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="profilo di embedding usato",
    )
    indexed_chunking_profile = models.ForeignKey(
        ChunkingProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="profilo di segmentazione usato",
    )
    index_fingerprint = models.CharField(
        "impronta dell'indice", max_length=64, blank=True,
        help_text="Hash dei valori dei profili al momento dell'indicizzazione.",
    )

    uploaded_at = models.DateTimeField("caricato il", auto_now_add=True)
    indexed_at = models.DateTimeField("indicizzato il", null=True, blank=True)

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documenti"
        ordering = ["-uploaded_at"]
        constraints = [
            # Parziale: in P1 il checksum e' vuoto per tutti, e senza la
            # condizione il secondo documento della stessa KB colliderebbe con
            # il primo. La deduplica vera (RF-09) entra in funzione in P2, quando
            # il checksum viene calcolato.
            models.UniqueConstraint(
                fields=["knowledge_base", "checksum"],
                condition=~Q(checksum=""),
                name="document_checksum_unico_per_kb",
                violation_error_message=(
                    "Questo file e' gia' presente in questa base di conoscenza."
                ),
            ),
        ]

    @property
    def needs_reindex(self) -> bool:
        """RF-25: il documento e' disallineato rispetto alla configurazione corrente."""
        if self.status != self.Status.INDEXED:
            return False
        return self.index_fingerprint != self.knowledge_base.index_fingerprint()

    def __str__(self) -> str:
        return self.original_filename or (self.file.name if self.file else f"documento {self.pk}")


class DocumentChunk(models.Model):
    """Segmento indicizzato.

    Il testo esiste due volte: qui e in langchain_pg_embedding.document. E'
    ridondanza accettata di proposito (ARCHITECTURE §6.5): senza di essa l'admin
    sarebbe cieco sul contenuto effettivamente indicizzato, che e' proprio cio'
    che la traccia chiede di poter governare.
    """

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="chunks", verbose_name="documento"
    )
    ordinal = models.PositiveIntegerField("ordinale")
    page_number = models.PositiveIntegerField("pagina")
    content = models.TextField("contenuto")
    char_count = models.PositiveIntegerField("caratteri", default=0)
    vector_id = models.CharField(
        "id del vettore",
        max_length=64,
        blank=True,
        db_index=True,
        help_text=(
            "Corrisponde a langchain_pg_embedding.id, che in P0 e' risultato di "
            "tipo character varying e non uuid: qui e' quindi una stringa."
        ),
    )

    class Meta:
        verbose_name = "segmento"
        verbose_name_plural = "segmenti"
        ordering = ["document", "ordinal"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "ordinal"], name="documentchunk_ordinale_unico_per_documento"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document} — segmento {self.ordinal} (pagina {self.page_number})"
