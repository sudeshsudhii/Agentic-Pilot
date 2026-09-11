"""Document ingestion pipeline for Agentic Pilot RAG."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.rag.ingestion.chunker import StructureAwareChunker
from backend.rag.ingestion.loader import DocumentLoader
from backend.rag.models import DocumentMetadata, KnowledgeChunk
from backend.rag.store import KnowledgeStore, knowledge_store

logger = logging.getLogger("pilot.rag.pipeline")


class IngestionPipeline:
    """Manages the end-to-end ingestion of knowledge documents into the vector store.

    Steps:
    File/Text -> DocumentLoader -> StructureAwareChunker -> Deduplication -> KnowledgeStore
    """

    def __init__(
        self,
        store: KnowledgeStore | None = None,
        loader: DocumentLoader | None = None,
        chunker: StructureAwareChunker | None = None,
    ) -> None:
        self.store = store or knowledge_store
        self.loader = loader or DocumentLoader()
        self.chunker = chunker or StructureAwareChunker()
        self._ingested_hashes: set[str] = set()

    async def ingest_file(
        self,
        file_path: Path | str,
        force: bool = False,
    ) -> list[KnowledgeChunk]:
        """Load, chunk, and store a file into the knowledge base."""
        path = Path(file_path)
        text, metadata = self.loader.load_file(path)

        # Deduplication check
        if not force and metadata.content_hash in self._ingested_hashes:
            logger.info("PIPELINE skip_unchanged file=%s hash=%s", path.name, metadata.content_hash[:8])
            return []

        chunks = self.chunker.chunk_document(text, metadata)
        if chunks:
            # Delete old chunks if re-ingesting modified document
            if force:
                await self.store.delete_document(metadata.document_id)

            await self.store.add_chunks(chunks)
            self._ingested_hashes.add(metadata.content_hash)
            logger.info(
                "PIPELINE ingested_file file=%s doc_id=%s chunks=%d",
                path.name, metadata.document_id, len(chunks),
            )

        return chunks

    async def ingest_text(
        self,
        text: str,
        source: str = "direct_input",
        title: str = "Untitled Document",
        doc_type: str = "text",
    ) -> list[KnowledgeChunk]:
        """Ingest raw text or documentation directly into the knowledge base."""
        text, metadata = self.loader.load_text(text, source=source, title=title, doc_type=doc_type)

        if metadata.content_hash in self._ingested_hashes:
            return []

        chunks = self.chunker.chunk_document(text, metadata)
        if chunks:
            await self.store.add_chunks(chunks)
            self._ingested_hashes.add(metadata.content_hash)

        return chunks

    async def ingest_directory(
        self,
        dir_path: Path | str,
        extensions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Batch-ingest all supported documents in a directory."""
        directory = Path(dir_path)
        if not directory.exists() or not directory.is_dir():
            return {"files_processed": 0, "total_chunks": 0, "errors": [f"Directory not found: {directory}"]}

        allowed_exts = set(extensions or DocumentLoader.SUPPORTED_EXTENSIONS)
        total_chunks = 0
        files_processed = 0
        errors: list[str] = []

        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in allowed_exts:
                try:
                    chunks = await self.ingest_file(path)
                    files_processed += 1
                    total_chunks += len(chunks)
                except Exception as exc:
                    logger.warning("PIPELINE failed_file path=%s error=%s", path, exc)
                    errors.append(f"{path.name}: {exc}")

        return {
            "files_processed": files_processed,
            "total_chunks": total_chunks,
            "errors": errors,
        }

    async def delete_document(self, document_id: str) -> None:
        """Remove all chunks associated with a document ID from the knowledge store."""
        await self.store.delete_document(document_id)


ingestion_pipeline = IngestionPipeline()
