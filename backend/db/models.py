"""Database record models used by the Pilot backend."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TaskRecord(BaseModel):
    """Persisted task row."""

    task_id: str
    input_text: str
    status: str
    risk_level: str | None = None
    parsed_intent: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    approval_id: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class EventRecord(BaseModel):
    """Persisted task event row."""

    id: int
    task_id: str
    type: str
    message: str
    payload: dict[str, Any] | None = None
    created_at: str


class ApprovalRecord(BaseModel):
    """Persisted approval request row."""

    approval_id: str
    task_id: str
    risk_level: str
    prompt: str
    status: str
    response: str | None = None
    created_at: str
    decided_at: str | None = None
