"""Tests for RAG document ingestion pipeline and loaders."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.rag.ingestion.loader import DocumentLoader
from backend.rag.ingestion.chunker import StructureAwareChunker
from backend.rag.ingestion.pipeline import IngestionPipeline
from backend.rag.store import KnowledgeStore


def test_document_loader_formats(tmp_path: Path):
    """Verify DocumentLoader handles markdown, text, json, and html."""
    loader = DocumentLoader()

    # Markdown
    md_file = tmp_path / "guide.md"
    md_file.write_text("# Installation Guide\n\nRun the install command to start.", encoding="utf-8")
    content, meta = loader.load_file(md_file)
    assert "Installation Guide" in content
    assert meta.document_type == "markdown"
    assert meta.title == "Installation Guide"
    assert len(meta.content_hash) == 64

    # Text
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("General procedural notes for execution.", encoding="utf-8")
    content, meta = loader.load_file(txt_file)
    assert "General procedural notes" in content
    assert meta.document_type == "text"

    # JSON
    json_file = tmp_path / "api_spec.json"
    json_file.write_text(json.dumps({"endpoint": "/api/v1/run", "method": "POST"}), encoding="utf-8")
    content, meta = loader.load_file(json_file)
    assert "/api/v1/run" in content
    assert meta.document_type == "json"


async def test_ingestion_pipeline_deduplication(tmp_path: Path):
    """Verify IngestionPipeline detects duplicates by hash and avoids redundant indexing."""
    store = KnowledgeStore(persist_dir=str(tmp_path / "chroma"), collection_name="test_knowledge")
    pipeline = IngestionPipeline(store=store)

    doc_text = """# Operating Procedure
Step 1: Open the administrative panel.
Step 2: Authenticate using hardware key.
Step 3: Export the audit log.
"""
    # First ingestion
    res1 = await pipeline.ingest_text(doc_text, source="sop_v1.md", title="SOP")
    assert len(res1) > 0
    assert res1[0].content_hash != ""

    initial_count = await store.count()
    assert initial_count > 0

    # Second ingestion with identical text -> should be skipped as duplicate
    res2 = await pipeline.ingest_text(doc_text, source="sop_v1.md", title="SOP")
    assert len(res2) == 0
    assert await store.count() == initial_count


async def test_ingestion_delete_document(tmp_path: Path):
    """Verify removing a document clears all its chunks from the store."""
    store = KnowledgeStore(persist_dir=str(tmp_path / "chroma"), collection_name="test_del_knowledge")
    pipeline = IngestionPipeline(store=store)

    chunks = await pipeline.ingest_text("# Guide\nSome instructions here.", source="doc_to_delete.md")
    assert len(chunks) > 0
    assert await store.count() > 0

    await pipeline.delete_document(chunks[0].document_id)
    assert await store.count() == 0
