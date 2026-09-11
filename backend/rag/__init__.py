"""Agentic Pilot Local RAG Subsystem.

Provides local knowledge document ingestion, structure-aware chunking,
vector storage in ChromaDB, cached retrieval, hybrid lexical/vector scoring,
untrusted security boundaries, and selective context routing for autonomous agents.
"""

from backend.rag.ingestion.chunker import StructureAwareChunker
from backend.rag.ingestion.loader import DocumentLoader
from backend.rag.ingestion.pipeline import IngestionPipeline, ingestion_pipeline
from backend.rag.models import (
    DocumentMetadata,
    KnowledgeChunk,
    RetrievalResult,
    RetrievedChunk,
)
from backend.rag.context_builder import BuiltContext, ContextBuilder, context_builder
from backend.rag.retriever import KnowledgeRetriever, knowledge_retriever
from backend.rag.router import ContextRouter, context_router
from backend.rag.security import format_untrusted_knowledge_context
from backend.rag.store import KnowledgeStore, knowledge_store

__all__ = [
    "BuiltContext",
    "ContextBuilder",
    "ContextRouter",
    "DocumentLoader",
    "DocumentMetadata",
    "IngestionPipeline",
    "KnowledgeChunk",
    "KnowledgeRetriever",
    "KnowledgeStore",
    "RetrievalResult",
    "RetrievedChunk",
    "StructureAwareChunker",
    "context_builder",
    "context_router",
    "format_untrusted_knowledge_context",
    "ingestion_pipeline",
    "knowledge_retriever",
    "knowledge_store",
]
