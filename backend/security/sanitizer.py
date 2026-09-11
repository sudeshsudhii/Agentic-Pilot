"""Input sanitization for untrusted content (R13).

Detects and neutralizes prompt injection patterns in web page content,
tool outputs, and other external sources before they reach LLM prompts.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("pilot.security.sanitizer")

# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    # Direct instruction overrides
    r"(?i)ignore\s+(all\s+)?previous\s+instructions?",
    r"(?i)forget\s+(all\s+)?previous\s+(instructions?|context)",
    r"(?i)disregard\s+(all\s+)?previous",
    r"(?i)you\s+are\s+now\s+a",
    r"(?i)act\s+as\s+(if\s+you\s+are|a)\s+",
    r"(?i)new\s+instructions?:",
    r"(?i)system\s*:\s*",
    r"(?i)\[system\]",
    r"(?i)<\s*system\s*>",
    # Delimiter-based injection
    r"(?i)```\s*system",
    r"(?i)---\s*new\s+prompt",
    r"(?i)###\s*(instruction|system|prompt)",
    # Data exfiltration attempts
    r"(?i)send\s+(this|the|all)\s+(data|info|content|text)\s+to",
    r"(?i)transmit\s+.{0,30}\s+to\s+https?://",
    r"(?i)email\s+.{0,30}\s+to\s+\S+@\S+",
    # Role manipulation
    r"(?i)you\s+must\s+(always|never)\s+",
    r"(?i)override\s+(your|the)\s+(instructions?|rules?|constraints?)",
]

# Compiled patterns for performance
_COMPILED_PATTERNS = [re.compile(p) for p in INJECTION_PATTERNS]


class InputSanitizer:
    """Sanitizes untrusted external content before LLM processing.

    Treats web page content, DOM text, tool outputs, and email content
    as potentially untrusted input that may contain prompt injection.
    """

    def __init__(self) -> None:
        self.injection_count = 0

    def sanitize_text(self, text: str, source: str = "unknown") -> str:
        """Sanitize text content, neutralizing potential injection patterns.

        Args:
            text: The raw text to sanitize
            source: Where the text came from (e.g., "dom", "email", "tool_output")

        Returns:
            Sanitized text with injection patterns neutralized
        """
        if not text:
            return text

        sanitized = text
        detections: list[str] = []

        for pattern in _COMPILED_PATTERNS:
            match = pattern.search(sanitized)
            if match:
                detections.append(match.group(0))
                # Replace the injection attempt with a neutralized marker
                sanitized = pattern.sub("[SANITIZED_CONTENT]", sanitized)

        if detections:
            self.injection_count += len(detections)
            logger.warning(
                "SANITIZER injection_detected source=%s count=%d patterns=%s",
                source, len(detections), detections[:3],  # Log only first 3
            )

        return sanitized

    def sanitize_dom_elements(self, elements: list[dict]) -> list[dict]:
        """Sanitize interactive element text content from DOM extraction."""
        for element in elements:
            for field in ("text_content", "aria_label", "placeholder"):
                if element.get(field):
                    element[field] = self.sanitize_text(
                        element[field], source="dom"
                    )
        return elements

    def sanitize_page_content(self, content: str) -> str:
        """Sanitize full page text content before sending to LLM."""
        return self.sanitize_text(content, source="page_content")

    def get_stats(self) -> dict[str, Any]:
        """Return sanitization statistics."""
        return {
            "total_injections_blocked": self.injection_count,
        }


input_sanitizer = InputSanitizer()
