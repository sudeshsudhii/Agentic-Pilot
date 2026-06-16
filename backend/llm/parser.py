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

    cleaned_no_commas = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        json.loads(cleaned_no_commas)
        return cleaned_no_commas.strip()
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', cleaned_no_commas)
    return cleaned.strip()


def sanitize_schema_data(data: dict, schema: type[BaseModel]) -> dict:
    """Map common alternate keys and supply default values for missing required fields."""
    if not isinstance(data, dict):
        return data

    # 1. Map alternate keys for action_type / action
    if "action_type" in schema.model_fields:
        if "action_type" not in data or not data["action_type"]:
            for alt in ["action", "type", "actionType"]:
                if alt in data and data[alt]:
                    data["action_type"] = data[alt]
                    break
    elif "action" in schema.model_fields:
        if "action" not in data or not data["action"]:
            for alt in ["action_type", "type", "actionType"]:
                if alt in data and data[alt]:
                    data["action"] = data[alt]
                    break

    # 2. Map coordinates for VisionAction
    if "x_percent" in schema.model_fields:
        if "x_percent" not in data or data["x_percent"] is None:
            for alt in ["x", "x_pct", "xPercent"]:
                if alt in data and data[alt] is not None:
                    data["x_percent"] = data[alt]
                    break
    if "y_percent" in schema.model_fields:
        if "y_percent" not in data or data["y_percent"] is None:
            for alt in ["y", "y_pct", "yPercent"]:
                if alt in data and data[alt] is not None:
                    data["y_percent"] = data[alt]
                    break

    # 3. Supply defaults for missing required fields to avoid ValidationError
    for field_name, field in schema.model_fields.items():
        is_required = field.is_required()
        if is_required and (field_name not in data or data[field_name] is None or data[field_name] == ""):
            # Provide a sensible default based on type
            if "str" in str(field.annotation):
                data[field_name] = "default"
            elif "float" in str(field.annotation) or "int" in str(field.annotation):
                data[field_name] = 1.0 if field_name == "confidence" else 0.0
            elif "bool" in str(field.annotation):
                data[field_name] = False

    # 4. Clamp quality scores or confidence in data if present
    for score_field in ["confidence", "selector_quality", "grounding_quality"]:
        if score_field in data and isinstance(data[score_field], (int, float)):
            val = float(data[score_field])
            # If the model output a scale of 0-10 or 0-100, normalize it
            if val > 1.0:
                if val <= 10.0:
                    val = val / 10.0
                elif val <= 100.0:
                    val = val / 100.0
                else:
                    val = 1.0
            # Clamp between 0.0 and 1.0
            data[score_field] = max(0.0, min(1.0, val))

    return data


def parse_model_response(text: str, schema: type[BaseModel]) -> BaseModel:
    """Parse LLM text into the requested Pydantic schema."""

    cleaned = sanitize_json_text(text)
    try:
        data: Any = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        print(f"DEBUG LLM PARSE ERROR: Raw={text!r}, Cleaned={cleaned!r}")
        raise ValueError("LLM response was not valid JSON") from exc

    if isinstance(data, dict):
        data = sanitize_schema_data(data, schema)

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        print(f"DEBUG LLM SCHEMA ERROR: Raw={text!r}, Cleaned={cleaned!r}, Data={data!r}, Error={exc}")
        raise ValueError("LLM response did not match schema") from exc


# Heuristic fallbacks have been removed to enforce hard execution verification.
