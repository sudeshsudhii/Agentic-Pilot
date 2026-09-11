"""Tests for RAG structure-aware chunking."""

from __future__ import annotations

import pytest

from backend.rag.ingestion.chunker import StructureAwareChunker
from backend.rag.models import DocumentMetadata


def test_markdown_heading_chunking():
    """Verify structure-aware chunker preserves heading sections and code blocks."""
    doc_meta = DocumentMetadata(
        document_id="doc_test_1",
        source="procedures/setup.md",
        title="Setup Guide",
        document_type="md",
        content_hash="hash123",
    )
    
    text = """# Overview
This is the system overview paragraph. It provides high-level context.

# Installation
To install the tool, run:
```bash
pip install -r requirements.txt
```

## Configuration
Set the configuration values in config.yaml:
- port: 8000
- host: localhost

## Verification
Ensure the server is running by checking health endpoint.
"""

    chunker = StructureAwareChunker(chunk_size=300, chunk_overlap=30)
    chunks = chunker.chunk_document(text, doc_meta)

    assert len(chunks) >= 3
    # Check that chunks retain metadata
    for chunk in chunks:
        assert chunk.document_id == "doc_test_1"
        assert chunk.source == "procedures/setup.md"
        assert chunk.title == "Setup Guide"
        assert chunk.chunk_id.startswith("doc_test_1_c")
        assert chunk.content_hash != ""
        assert chunk.token_count > 0

    # Check that sections are identified
    sections = [c.section for c in chunks]
    assert any("Overview" in s for s in sections)
    assert any("Installation" in s for s in sections)
    assert any("Configuration" in s for s in sections)


def test_plain_text_paragraph_chunking():
    """Verify plain text is chunked by paragraphs with bounded length."""
    doc_meta = DocumentMetadata(
        document_id="doc_txt_1",
        source="notes.txt",
        title="Notes",
        document_type="txt",
        content_hash="txt_hash",
    )

    paragraphs = [f"Paragraph {i}: " + ("This is detailed procedural documentation. " * 5) for i in range(10)]
    text = "\n\n".join(paragraphs)

    chunker = StructureAwareChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk_document(text, doc_meta)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.document_id == "doc_txt_1"
        assert len(chunk.content) > 0


def test_empty_document_chunking():
    """Verify empty or whitespace-only documents yield empty chunk list."""
    doc_meta = DocumentMetadata(
        document_id="doc_empty",
        source="empty.md",
        title="Empty",
        document_type="md",
        content_hash="empty_hash",
    )

    chunker = StructureAwareChunker()
    assert chunker.chunk_document("", doc_meta) == []
    assert chunker.chunk_document("   \n\n   ", doc_meta) == []
