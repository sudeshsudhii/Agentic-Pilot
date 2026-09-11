"""Tests for KnowledgeRetriever: vector search, hybrid scoring, caching, and thresholding."""

from __future__ import annotations

from pathlib import Path
import pytest

from backend.rag.ingestion.pipeline import IngestionPipeline
from backend.rag.models import RetrievalResult, RetrievedChunk
from backend.rag.retriever import KnowledgeRetriever, QueryCache
from backend.rag.store import KnowledgeStore


@pytest.fixture
async def populated_store(tmp_path: Path):
    """Fixture providing a temporary store populated with distinct SOP documents."""
    store = KnowledgeStore(persist_dir=str(tmp_path / "chroma"), collection_name="test_retrieval")
    pipeline = IngestionPipeline(store=store)

    doc_aws = """# AWS Deployment Procedure
To deploy the worker service to AWS:
1. Authenticate with AWS CLI using temporary session tokens.
2. Build the Docker container image tagged with commit sha.
3. Push the image to Amazon ECR registry.
4. Update the ECS task definition and trigger a rolling service update.
"""
    doc_k8s = """# Kubernetes Cluster Setup
To configure the production Kubernetes namespace:
1. Apply namespace YAML definition with resource quotas.
2. Configure ingress-nginx controller with cert-manager TLS.
3. Deploy stateful sets with persistent volume claims.
"""
    await pipeline.ingest_text(doc_aws, source="sop_aws.md", title="AWS SOP")
    await pipeline.ingest_text(doc_k8s, source="sop_k8s.md", title="K8s SOP")
    return store


async def test_retrieval_provenance_and_structure(populated_store):
    """Verify retriever returns structured chunks with score, document_id, and provenance."""
    retriever = KnowledgeRetriever(store=populated_store)

    result = await retriever.retrieve("deploy Docker container to AWS ECR", top_k=2)

    assert isinstance(result, RetrievalResult)
    assert result.status == "success"
    assert len(result.chunks) > 0
    assert result.latency_ms >= 0

    top_chunk = result.chunks[0]
    assert isinstance(top_chunk, RetrievedChunk)
    assert top_chunk.source == "sop_aws.md"
    assert top_chunk.document_id != ""
    assert top_chunk.chunk_id != ""
    assert 0.0 <= top_chunk.score <= 1.0
    assert "Docker" in top_chunk.content or "ECR" in top_chunk.content


async def test_retrieval_query_cache(populated_store):
    """Verify QueryCache accelerates repeated queries and marks cache_hit=True."""
    cache = QueryCache(max_size=50, ttl_seconds=60)
    retriever = KnowledgeRetriever(store=populated_store, cache=cache)

    query = "Kubernetes ingress controller cert-manager"

    # Call 1: Cache miss
    res1 = await retriever.retrieve(query, top_k=2)
    assert res1.cache_hit is False

    # Call 2: Cache hit
    res2 = await retriever.retrieve(query, top_k=2)
    assert res2.cache_hit is True
    assert len(res2.chunks) == len(res1.chunks)
    assert res2.chunks[0].chunk_id == res1.chunks[0].chunk_id


async def test_retrieval_empty_when_no_matches(tmp_path: Path):
    """Verify retriever gracefully handles empty knowledge base without error."""
    empty_store = KnowledgeStore(persist_dir=str(tmp_path / "empty_chroma"), collection_name="empty")
    retriever = KnowledgeRetriever(store=empty_store)

    result = await retriever.retrieve("any arbitrary search query", top_k=5)
    assert isinstance(result, RetrievalResult)
    assert len(result.chunks) == 0
    assert result.status in {"empty", "success"}


async def test_hybrid_search_scoring(populated_store):
    """Verify hybrid search combines lexical overlap with semantic scoring."""
    retriever = KnowledgeRetriever(store=populated_store)

    result = await retriever.retrieve("resource quotas stateful sets persistent volume", top_k=2, hybrid=True)
    assert result.strategy == "hybrid"
    assert len(result.chunks) > 0
    assert result.chunks[0].source == "sop_k8s.md"
