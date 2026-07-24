"""Osservabilita' nativa (RF-16, ARCHITECTURE §7.8).

Nessun servizio di tracing esterno: lo storico vive nell'admin Django, cioe'
dove la traccia chiede che il sistema sia governabile. Il punto d'aggancio
opzionale per Langfuse e' T-35, dietro flag e spento di default.
"""

from django.conf import settings
from django.db import models

from .domain import DocumentChunk, RagPipeline


class QueryLog(models.Model):
    """Una interrogazione, con i suoi tempi separati.

    I tempi sono tre e non uno di proposito: in P0 si e' misurato che il
    retrieval puo' costare 12 s per ricarico del modello di embedding in VRAM
    mentre la generazione ne costa 1. Un solo `latency_ms` renderebbe
    indistinguibili i due casi.
    """

    pipeline = models.ForeignKey(
        RagPipeline, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="query_logs", verbose_name="pipeline",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="query_logs", verbose_name="utente",
    )
    question = models.TextField("domanda")
    answer = models.TextField("risposta", blank=True)
    retrieval_ms = models.PositiveIntegerField("recupero (ms)", default=0)
    generation_ms = models.PositiveIntegerField("generazione (ms)", default=0)
    latency_ms = models.PositiveIntegerField("totale (ms)", default=0)
    error = models.TextField("errore", blank=True)
    created_at = models.DateTimeField("eseguita il", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "interrogazione"
        verbose_name_plural = "interrogazioni"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        testo = self.question[:60]
        return f"{testo}…" if len(self.question) > 60 else testo


class RetrievedChunk(models.Model):
    """Segmento recuperato da una interrogazione, con posizione e punteggio.

    La FK al segmento e' SET_NULL: lo storico deve sopravvivere alla
    cancellazione del documento (ARCHITECTURE §6.4).
    """

    query_log = models.ForeignKey(
        QueryLog, on_delete=models.CASCADE, related_name="retrieved_chunks",
        verbose_name="interrogazione",
    )
    chunk = models.ForeignKey(
        DocumentChunk, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="retrievals", verbose_name="segmento",
    )
    rank = models.PositiveIntegerField("posizione")
    score = models.FloatField("punteggio")

    class Meta:
        verbose_name = "segmento recuperato"
        verbose_name_plural = "segmenti recuperati"
        ordering = ["query_log", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["query_log", "rank"], name="retrievedchunk_posizione_unica_per_query"
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.rank} (score {self.score:.3f})"
