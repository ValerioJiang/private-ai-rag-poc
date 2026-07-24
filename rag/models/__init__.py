"""Modelli del sistema RAG.

Suddivisi in moduli per leggibilita'. Django li considera comunque modelli
dell'app `rag`, perche' il package e' `rag.models`: l'app_label si deduce dal
percorso, non dal file.
"""

from .domain import Document, DocumentChunk, KnowledgeBase, RagPipeline
from .logs import QueryLog, RetrievedChunk
from .profiles import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPLATE,
    RISPOSTA_NON_DISPONIBILE,
    ChunkingProfile,
    EmbeddingProfile,
    LLMProfile,
    PromptTemplate,
    RetrievalProfile,
    TimestampedModel,
)

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_TEMPLATE",
    "RISPOSTA_NON_DISPONIBILE",
    "ChunkingProfile",
    "Document",
    "DocumentChunk",
    "EmbeddingProfile",
    "KnowledgeBase",
    "LLMProfile",
    "PromptTemplate",
    "QueryLog",
    "RagPipeline",
    "RetrievalProfile",
    "RetrievedChunk",
    "TimestampedModel",
]
