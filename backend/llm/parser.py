"""Structured models and parsing helpers for Pilot LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class ParsedIntent(BaseModel):
    """Structured interpretation of a user's natural-language task."""

    action: str
    site: str
    content: str | None = None
    target: str | None = None
    attachments: list[str] = Field(default_factory=list)
    risk_level: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class InteractiveElement(BaseModel):
    """Compact description of an actionable page element."""

    element_id: str
    tag: str
    role: str | None = None
    aria_label: str | None = None
    text_content: str | None = None
    placeholder: str | None = None
    input_type: str | None = None
    is_visible: bool
    bounding_box: dict[str, float] | None = None
    selector: str | None = None


class ActionManifest(BaseModel):
    """Compact DOM manifest sent to the planning layer."""

    url: str
    interactive_elements: list[InteractiveElement] = Field(default_factory=list)
    page_title: str
    page_state: str


class PlannedAction(BaseModel):
    """Single browser action selected by the planner."""

    action_type: str
    element_id: str | None = None
    text: str | None = None
    value: str | None = None
    url: str | None = None
    reasoning: str


class ActionResult(BaseModel):
    """Result returned by browser action executors and plugins."""

    success: bool
    action_type: str
    element_id: str | None = None
    error: str | None = None
    page_state_after: str
    duration_ms: int


def sanitize_json_text(text: str) -> str:
    """Return a best-effort JSON object string from an LLM response."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]

    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    cleaned = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', cleaned)
    return cleaned.strip()


def parse_model_response(text: str, schema: type[BaseModel]) -> BaseModel:
    """Parse LLM text into the requested Pydantic schema."""

    cleaned = sanitize_json_text(text)
    try:
        data: Any = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response was not valid JSON") from exc

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise ValueError("LLM response did not match schema") from exc


def heuristic_parse_intent(input_text: str) -> ParsedIntent:
    """Parse common browser intents without requiring a live LLM."""

    text = input_text.strip()
    lowered = text.lower()

    action = "navigate"
    if any(word in lowered for word in ("buy", "purchase", "order", "transfer", "delete")):
        action = "purchase"
        risk = "critical"
    elif any(word in lowered for word in ("post", "tweet", "publish")):
        action = "post"
        risk = "high"
    elif "send" in lowered and "email" in lowered:
        action = "send_email"
        risk = "high"
    elif any(word in lowered for word in ("submit", "sign up", "register")):
        action = "submit_form"
        risk = "high"
    elif any(word in lowered for word in ("fill", "compose", "draft")):
        action = "fill_form" if "fill" in lowered else "compose"
        risk = "medium"
    elif "search" in lowered:
        action = "search"
        risk = "low"
    else:
        risk = "low"

    site = _guess_site(lowered)
    content = _extract_content(text)
    target = _extract_target(text)
    confidence = 0.86 if site != "unknown" or action != "navigate" else 0.55
    reasoning = "Parsed using Pilot's deterministic fallback intent parser."

    return ParsedIntent(
        action=action,
        site=site,
        content=content,
        target=target,
        attachments=[],
        risk_level=risk,
        confidence=confidence,
        reasoning=reasoning,
    )


def _guess_site(lowered: str) -> str:
    """Infer a target site from common aliases or explicit domains."""

    aliases = {
        "twitter": "twitter.com",
        "x.com": "x.com",
        "gmail": "mail.google.com",
        "google mail": "mail.google.com",
        "google forms": "docs.google.com/forms",
        "google form": "docs.google.com/forms",
        "google": "google.com",
        "amazon": "amazon.com",
    }
    for needle, site in aliases.items():
        if needle in lowered:
            return site

    match = re.search(r"\b([a-z0-9-]+\.(?:com|org|net|io|ai|dev|co)(?:/[^\s]*)?)", lowered)
    return match.group(1) if match else "unknown"


def _extract_content(text: str) -> str | None:
    """Extract the likely content payload from a user instruction."""

    if ":" in text:
        return text.split(":", 1)[1].strip().strip("\"'")

    quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"", text)
    if quoted:
        first = quoted[0]
        return first[0] or first[1]

    return None


def _extract_target(text: str) -> str | None:
    """Extract a likely recipient, URL target, or search query."""

    email = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text)
    if email:
        return email.group(0)

    search = re.search(r"search\s+(?:google\s+)?for\s+(.+)", text, flags=re.IGNORECASE)
    if search:
        return search.group(1).strip().strip("\"'")

    return None
