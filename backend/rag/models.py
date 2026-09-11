"""Structured models for Agentic Pilot RAG subsystem."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Metadata describing an ingested knowledge document."""

    document_id: str
    source: str
    title: str = "Untitled Document"
    document_type: str = "text"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: str = "1.0"
    content_hash: str = ""
    file_size: int = 0
    section_count: int = 0
    total_chunks: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)


class KnowledgeChunk(BaseModel):
    """A single atomic, structure-aware chunk of knowledge."""

    chunk_id: str
    document_id: str
    content: str
    section: str | None = None
    chunk_index: int = 0
    content_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def source(self) -> str:
        return str(self.metadata.get("source", ""))

    @property
    def title(self) -> str:
        return str(self.metadata.get("title", ""))

    @property
    def token_count(self) -> int:
        return max(1, len(self.content.split()))


class RetrievedChunk(BaseModel):
    """A retrieved knowledge chunk with relevance score and provenance."""

    document_id: str
    chunk_id: str
    content: str
    score: float = Field(ge=0.0, le=1.0, description="Relevance or similarity score")
    source: str
    section: str | None = None
    document_type: str = "text"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Structured response returned by KnowledgeRetriever."""

    query: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    total_found: int = 0
    latency_ms: int = 0
    cache_hit: bool = False
    strategy: str = "vector"  # "vector", "hybrid", "keyword"
    status: str = "success"   # "success", "empty", "error", "skipped"
    error_message: str | None = None
