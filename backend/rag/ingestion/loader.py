"""Document loaders for local file ingestion in Agentic Pilot RAG."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from backend.rag.models import DocumentMetadata

logger = logging.getLogger("pilot.rag.loader")


class DocumentLoader:
    """Loads and extracts text and metadata from local files."""

    SUPPORTED_EXTENSIONS = {".md", ".txt", ".json", ".csv", ".html", ".htm", ".pdf"}

    def load_file(self, file_path: Path | str) -> tuple[str, DocumentMetadata]:
        """Load a file from disk and return (content, metadata)."""
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file extension: {ext}. Supported: {self.SUPPORTED_EXTENSIONS}")

        file_bytes = path.read_bytes()
        content_hash = hashlib.sha256(file_bytes).hexdigest()
        file_size = len(file_bytes)

        if ext == ".md":
            text = file_bytes.decode("utf-8", errors="replace")
            doc_type = "markdown"
            title = self._extract_markdown_title(text, path.stem)
        elif ext in {".txt"}:
            text = file_bytes.decode("utf-8", errors="replace")
            doc_type = "text"
            title = path.stem.replace("_", " ").title()
        elif ext == ".json":
            doc_type = "json"
            title = path.stem.replace("_", " ").title()
            text = self._format_json(file_bytes)
        elif ext == ".csv":
            doc_type = "csv"
            title = path.stem.replace("_", " ").title()
            text = file_bytes.decode("utf-8", errors="replace")
        elif ext in {".html", ".htm"}:
            doc_type = "html"
            raw_html = file_bytes.decode("utf-8", errors="replace")
            text, title = self._extract_html(raw_html, path.stem)
        elif ext == ".pdf":
            doc_type = "pdf"
            title = path.stem.replace("_", " ").title()
            text = self._extract_pdf(file_bytes, path.name)
        else:
            text = file_bytes.decode("utf-8", errors="replace")
            doc_type = "text"
            title = path.stem

        doc_id = f"doc_{content_hash[:12]}"
        metadata = DocumentMetadata(
            document_id=doc_id,
            source=str(path.name),
            title=title,
            document_type=doc_type,
            content_hash=content_hash,
            file_size=file_size,
            extra={"absolute_path": str(path)},
        )

        return text, metadata

    def load_text(
        self,
        text: str,
        source: str = "direct_input",
        title: str = "Untitled Document",
        doc_type: str = "text",
    ) -> tuple[str, DocumentMetadata]:
        """Wrap in-memory text as a document."""
        content_bytes = text.encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        doc_id = f"doc_{content_hash[:12]}"

        metadata = DocumentMetadata(
            document_id=doc_id,
            source=source,
            title=title,
            document_type=doc_type,
            content_hash=content_hash,
            file_size=len(content_bytes),
        )
        return text, metadata

    def _extract_markdown_title(self, text: str, default: str) -> str:
        """Extract first # Heading 1 as title."""
        match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return default.replace("_", " ").title()

    def _format_json(self, raw_bytes: bytes) -> str:
        """Parse JSON and format into human-readable text."""
        try:
            data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
            return json.dumps(data, indent=2)
        except Exception:
            return raw_bytes.decode("utf-8", errors="replace")

    def _extract_html(self, html: str, default_title: str) -> tuple[str, str]:
        """Strip HTML tags and extract title."""
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else default_title

        # Remove scripts, styles
        cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        # Strip all HTML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned, title

    def _extract_pdf(self, pdf_bytes: bytes, filename: str) -> str:
        """Extract text from PDF locally."""
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages).strip()
        except ImportError:
            # Fallback: extract ASCII/UTF-8 streams from PDF binary
            logger.info("pypdf not installed — using basic text extraction for %s", filename)
            text_parts = re.findall(rb"\(([\w\s.,!?:;'\-\(\)]+)\)\s*Tj", pdf_bytes)
            if text_parts:
                return b" ".join(text_parts).decode("latin-1", errors="replace")
            # Plain string extraction fallback
            ascii_strings = re.findall(rb"[\x20-\x7E\n\r\t]{5,}", pdf_bytes)
            return b"\n".join(ascii_strings).decode("ascii", errors="replace")
        except Exception as exc:
            logger.warning("PDF extraction error for %s: %s", filename, exc)
            return f"[PDF document: {filename}]"
