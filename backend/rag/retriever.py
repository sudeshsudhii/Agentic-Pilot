"""Knowledge retrieval engine with caching, score filtering, and hybrid search."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any

from backend.config import get_config
from backend.rag.models import RetrievalResult, RetrievedChunk
from backend.rag.store import KnowledgeStore, knowledge_store

logger = logging.getLogger("pilot.rag.retriever")


def normalize_query(query: str) -> str:
    """Normalize query by lowering, removing punctuation, and collapsing whitespace."""
    q = query.strip().lower()
    q = re.sub(r"[^\w\s]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


class QueryCache:
    """Bounded in-memory LRU query cache with TTL and query normalization."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[RetrievalResult, float, float]] = {}  # key -> (result, expires_at, last_access)
        self.hits = 0
        self.misses = 0

    def _get_key(self, query: str) -> str:
        norm = normalize_query(query)
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def get(self, query: str) -> RetrievalResult | None:
        key = self._get_key(query)
        if key in self._cache:
            res, expires_at, _ = self._cache[key]
            now = time.time()
            if now < expires_at:
                self.hits += 1
                self._cache[key] = (res, expires_at, now)
                res.cache_hit = True
                return res
            del self._cache[key]
        self.misses += 1
        return None

    def put(self, query: str, result: RetrievalResult) -> None:
        key = self._get_key(query)
        now = time.time()
        if len(self._cache) >= self.max_size and key not in self._cache:
            # Evict least recently accessed entry
            lru_key = min(self._cache.keys(), key=lambda k: self._cache[k][2])
            del self._cache[lru_key]
        self._cache[key] = (result, now + self.ttl_seconds, now)

    def clear(self) -> None:
        self._cache.clear()
        self.hits = 0
        self.misses = 0


class KnowledgeRetriever:
    """Unified retrieval API for the Agentic Pilot knowledge base."""

    def __init__(self, store: KnowledgeStore | None = None, cache: QueryCache | None = None) -> None:
        self.store = store or knowledge_store
        self.cache = cache or QueryCache()

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        hybrid: bool | None = None,
        rerank: bool | None = None,
    ) -> RetrievalResult:
        """Retrieve relevant knowledge chunks matching the query.

        Args:
            query: The search query string
            top_k: Number of chunks to retrieve (defaults to config.rag_top_k)
            similarity_threshold: Minimum similarity score threshold
            hybrid: Whether to perform hybrid vector+keyword search
            rerank: Whether to apply reranking

        Returns:
            RetrievalResult containing ranked chunks and metadata.
        """
        config = get_config()
        if not config.enable_rag:
            return RetrievalResult(query=query, status="skipped", total_found=0)

        top_k = top_k or config.rag_top_k
        threshold = similarity_threshold if similarity_threshold is not None else config.rag_similarity_threshold
        use_hybrid = hybrid if hybrid is not None else config.rag_hybrid_search
        use_rerank = rerank if rerank is not None else config.rag_reranking

        # Check cache
        if config.rag_cache_enabled:
            cached = self.cache.get(query)
            if cached:
                logger.info("RETRIEVER cache_hit query=%s chunks=%d", query[:40], len(cached.chunks))
                return cached

        started = time.perf_counter()

        try:
            # 1. Vector Search
            vector_chunks = await self.store.search(query, top_k=top_k * 2 if use_hybrid or use_rerank else top_k)

            # 2. Hybrid Lexical Scoring (if enabled)
            if use_hybrid and vector_chunks:
                ranked_chunks = self._apply_hybrid_scoring(query, vector_chunks)
                strategy = "hybrid"
            else:
                ranked_chunks = vector_chunks
                strategy = "vector"

            # 3. Optional Reranking
            if use_rerank and len(ranked_chunks) > 1:
                ranked_chunks = self._apply_reranking(query, ranked_chunks)

            # 4. Score Filtering & Truncation
            filtered_chunks = [c for c in ranked_chunks if c.score >= threshold][:top_k]

            duration_ms = int((time.perf_counter() - started) * 1000)

            result = RetrievalResult(
                query=query,
                chunks=filtered_chunks,
                total_found=len(filtered_chunks),
                latency_ms=duration_ms,
                cache_hit=False,
                strategy=strategy,
                status="success" if filtered_chunks else "empty",
            )

            # Save in cache
            if config.rag_cache_enabled and result.chunks:
                self.cache.put(query, result)

            logger.info(
                "RETRIEVER success query=%s chunks=%d latency_ms=%d strategy=%s",
                query[:40], len(filtered_chunks), duration_ms, strategy,
            )
            return result

        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("RETRIEVER error query=%s error=%s", query[:40], exc)
            return RetrievalResult(
                query=query,
                chunks=[],
                total_found=0,
                latency_ms=duration_ms,
                status="error",
                error_message=str(exc),
            )

    def _apply_hybrid_scoring(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        alpha: float = 0.7,
    ) -> list[RetrievedChunk]:
        """Combine vector similarity with lexical term overlap (Hybrid Search)."""
        query_terms = set(re.findall(r"\w+", query.lower()))
        if not query_terms:
            return chunks

        for chunk in chunks:
            chunk_words = set(re.findall(r"\w+", chunk.content.lower()))
            overlap = len(query_terms.intersection(chunk_words))
            lexical_score = overlap / max(len(query_terms), 1)

            # Weighted combination
            combined = (alpha * chunk.score) + ((1.0 - alpha) * lexical_score)
            chunk.score = round(max(0.0, min(1.0, combined)), 4)
            chunk.metadata["hybrid_lexical_overlap"] = overlap

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks

    def _apply_reranking(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """Lightweight local reranking based on exact phrase matches and heading proximity."""
        query_lower = query.lower()

        for chunk in chunks:
            bonus = 0.0
            content_lower = chunk.content.lower()

            # Exact phrase bonus
            if query_lower in content_lower:
                bonus += 0.15

            # Section heading match bonus
            if chunk.section and any(w in chunk.section.lower() for w in query_lower.split()):
                bonus += 0.10

            chunk.score = round(min(1.0, chunk.score + bonus), 4)

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks


knowledge_retriever = KnowledgeRetriever()
