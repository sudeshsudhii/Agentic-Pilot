"""Structure-aware document chunker for Agentic Pilot RAG."""

from __future__ import annotations

import hashlib
import logging
import re

from backend.rag.models import DocumentMetadata, KnowledgeChunk

logger = logging.getLogger("pilot.rag.chunker")


class StructureAwareChunker:
    """Chunks documents into atomic, meaningful semantic units.

    Respects headings, paragraphs, lists, and code blocks rather than
    blindly cutting text at fixed character offsets.
    """

    def __init__(
        self,
        target_chunk_size: int = 600,
        overlap: int = 60,
        min_chunk_size: int = 50,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        if chunk_size is not None:
            target_chunk_size = chunk_size
        if chunk_overlap is not None:
            overlap = chunk_overlap
        self.target_chunk_size = target_chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def chunk_document(
        self,
        text: str,
        metadata: DocumentMetadata,
    ) -> list[KnowledgeChunk]:
        """Split document text into structured KnowledgeChunks."""
        if not text.strip():
            return []

        if metadata.document_type in {"markdown", "md"}:
            raw_chunks = self._chunk_markdown(text)
        else:
            raw_chunks = self._chunk_prose(text)

        chunks: list[KnowledgeChunk] = []
        for idx, (content, section) in enumerate(raw_chunks, 1):
            cleaned = content.strip()
            if len(cleaned) < self.min_chunk_size and len(raw_chunks) > 1:
                continue

            chunk_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
            chunk_id = f"{metadata.document_id}_c{idx:03d}"

            chunk_meta = {
                "source": metadata.source,
                "title": metadata.title,
                "document_type": metadata.document_type,
                "section": section or "General",
                "created_at": metadata.created_at,
                "version": metadata.version,
                "chunk_index": idx,
            }

            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    document_id=metadata.document_id,
                    content=cleaned,
                    section=section or None,
                    chunk_index=idx,
                    content_hash=chunk_hash,
                    metadata=chunk_meta,
                )
            )

        metadata.total_chunks = len(chunks)
        return chunks

    def _chunk_markdown(self, text: str) -> list[tuple[str, str | None]]:
        """Split Markdown by heading sections, keeping sections intact."""
        lines = text.split("\n")
        sections: list[tuple[str, str | None]] = []
        current_heading: str | None = None
        current_lines: list[str] = []

        in_code_block = False

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block

            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match and not in_code_block:
                if current_lines:
                    sec_text = "\n".join(current_lines).strip()
                    if sec_text:
                        # If section is too big, sub-chunk it
                        if len(sec_text) > self.target_chunk_size * 1.5:
                            sections.extend(self._split_large_block(sec_text, current_heading))
                        else:
                            sections.append((sec_text, current_heading))
                    current_lines = []

                current_heading = heading_match.group(2).strip()

            current_lines.append(line)

        if current_lines:
            sec_text = "\n".join(current_lines).strip()
            if sec_text:
                if len(sec_text) > self.target_chunk_size * 1.5:
                    sections.extend(self._split_large_block(sec_text, current_heading))
                else:
                    sections.append((sec_text, current_heading))

        return sections

    def _chunk_prose(self, text: str) -> list[tuple[str, str | None]]:
        """Split plain text by paragraphs and sentences."""
        paragraphs = re.split(r"\n\s*\n", text)
        chunks: list[tuple[str, str | None]] = []
        current_buf: list[str] = []
        current_len = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if current_len + len(para) > self.target_chunk_size and current_buf:
                chunks.append(("\n\n".join(current_buf), None))
                # Add slight overlap if possible
                if self.overlap > 0 and len(current_buf[-1]) <= self.overlap:
                    current_buf = [current_buf[-1], para]
                    current_len = len(current_buf[0]) + len(para)
                else:
                    current_buf = [para]
                    current_len = len(para)
            else:
                current_buf.append(para)
                current_len += len(para)

        if current_buf:
            chunks.append(("\n\n".join(current_buf), None))

        return chunks

    def _split_large_block(self, text: str, heading: str | None) -> list[tuple[str, str | None]]:
        """Subdivide an excessively large section along paragraph boundaries."""
        paras = re.split(r"\n\s*\n", text)
        results: list[tuple[str, str | None]] = []
        buf: list[str] = []
        curr_len = 0

        for p in paras:
            p = p.strip()
            if not p:
                continue
            if curr_len + len(p) > self.target_chunk_size and buf:
                results.append(("\n\n".join(buf), heading))
                buf = [p]
                curr_len = len(p)
            else:
                buf.append(p)
                curr_len += len(p)

        if buf:
            results.append(("\n\n".join(buf), heading))

        return results if results else [(text, heading)]
