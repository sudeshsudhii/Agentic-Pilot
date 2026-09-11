"""Vector store abstraction for the Agentic Pilot RAG knowledge base."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import chromadb

from backend.config import get_config
from backend.db.database import resolve_path
from backend.rag.models import KnowledgeChunk, RetrievedChunk

logger = logging.getLogger("pilot.rag.store")


class KnowledgeStore:
    """Manages the persistent vector store for external/static knowledge documents.

    Maintains a dedicated collection ('pilot_knowledge') separate from episodic memory,
    reusing ChromaDB persistence infrastructure.
    """

    def __init__(self, collection_name: str | None = None, persist_dir: Path | str | None = None) -> None:
        config = get_config()
        self.collection_name = collection_name or config.rag_knowledge_collection

        if persist_dir is not None:
            self.db_path = Path(persist_dir)
        else:
            self.db_path = resolve_path(config.db_path).parent / "chroma"

        self.db_path.mkdir(parents=True, exist_ok=True)
        self.chroma = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.chroma.get_or_create_collection(self.collection_name)

    async def add_chunks(self, chunks: list[KnowledgeChunk]) -> int:
        """Add knowledge chunks to the vector collection."""
        if not chunks:
            return 0

        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        for chunk in chunks:
            documents.append(chunk.content)
            meta = {
                "document_id": chunk.document_id,
                "section": chunk.section or "",
                "chunk_index": chunk.chunk_index,
                "content_hash": chunk.content_hash,
                "source": chunk.metadata.get("source", "unknown"),
                "title": chunk.metadata.get("title", "Untitled"),
                "document_type": chunk.metadata.get("document_type", "text"),
            }
            metadatas.append(meta)
            ids.append(chunk.chunk_id)

        try:
            await asyncio.to_thread(
                self.collection.upsert,
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
            logger.info("STORE added_chunks count=%d collection=%s", len(chunks), self.collection_name)
            return len(chunks)
        except Exception as exc:
            logger.exception("STORE add_chunks_failed: %s", exc)
            return 0

    async def search(
        self,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Search for relevant chunks via vector similarity."""
        if not query.strip():
            return []

        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": top_k,
            }
            if where:
                kwargs["where"] = where

            results = await asyncio.to_thread(self.collection.query, **kwargs)
        except Exception as exc:
            logger.warning("STORE search_failed query=%s error=%s", query[:50], exc)
            return []

        retrieved: list[RetrievedChunk] = []
        ids_list = results.get("ids", [[]])[0]
        docs_list = results.get("documents", [[]])[0]
        metas_list = results.get("metadatas", [[]])[0]
        distances_list = results.get("distances", [[]])[0] if "distances" in results and results["distances"] else []

        for i, chunk_id in enumerate(ids_list):
            content = docs_list[i] if i < len(docs_list) else ""
            meta = metas_list[i] if i < len(metas_list) else {}

            # Distance to normalized similarity score [0.0, 1.0]
            if distances_list and i < len(distances_list):
                dist = distances_list[i]
                # Cosine distance ranges from 0 to 2; convert to similarity [0, 1]
                score = max(0.0, min(1.0, 1.0 - (float(dist) / 2.0)))
            else:
                score = 1.0

            retrieved.append(
                RetrievedChunk(
                    document_id=meta.get("document_id", "unknown"),
                    chunk_id=chunk_id,
                    content=content,
                    score=round(score, 4),
                    source=meta.get("source", "unknown"),
                    section=meta.get("section") or None,
                    document_type=meta.get("document_type", "text"),
                    metadata=meta,
                )
            )

        return retrieved

    async def delete_document(self, document_id: str) -> int:
        """Delete all chunks belonging to a document."""
        try:
            chunks = await asyncio.to_thread(
                self.collection.get,
                where={"document_id": document_id},
            )
            ids = chunks.get("ids", [])
            if ids:
                await asyncio.to_thread(self.collection.delete, ids=ids)
                logger.info("STORE deleted_document document_id=%s chunks=%d", document_id, len(ids))
            return len(ids)
        except Exception as exc:
            logger.warning("STORE delete_document_failed document_id=%s error=%s", document_id, exc)
            return 0

    async def count(self) -> int:
        """Return total chunks in the knowledge collection."""
        try:
            return await asyncio.to_thread(self.collection.count)
        except Exception:
            return 0

    async def clear(self) -> None:
        """Clear all chunks from the knowledge collection."""
        try:
            count = await self.count()
            if count > 0:
                await asyncio.to_thread(self.chroma.delete_collection, self.collection_name)
                self.collection = self.chroma.get_or_create_collection(self.collection_name)
                logger.info("STORE cleared collection=%s", self.collection_name)
        except Exception as exc:
            logger.warning("STORE clear_failed error=%s", exc)


knowledge_store = KnowledgeStore()
