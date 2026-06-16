"""Structured models and parsing helpers for Pilot LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class ParsedIntent(BaseModel):
    """Structured interpretation of a user's natural-language task."""

    action: str = Field(description="Primary action: post, send_email, fill_form, search, navigate")
    target: str | None = Field(default=None, description="Target entity or user, if applicable")
    content: str | None = Field(default=None, description="Content payload or search query")
    site: str = Field(default="unknown", description="Website required, e.g., 'twitter.com'")
    risk_level: str = Field(description="Risk classification: low, medium, high, critical")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0) for parsing accuracy")
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
    interactable: bool = True
    xpath: str | None = None
    css_selector: str | None = None
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
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    selector_quality: float = Field(default=1.0, ge=0.0, le=1.0)
    grounding_quality: float = Field(default=1.0, ge=0.0, le=1.0)


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


# Heuristic fallbacks have been removed to enforce hard execution verification.
