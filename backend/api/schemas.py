"""Shared FastAPI request and response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Structured API error response."""

    detail: str


class TaskCreateRequest(BaseModel):
    """Request body for creating a task."""

    input_text: str = Field(min_length=1)
    session_id: str | None = None


class TaskCreateResponse(BaseModel):
    """Response returned after task submission."""

    task_id: str
    status: str
    stream_url: str


class TaskResponse(BaseModel):
    """Task state returned by the API."""

    task_id: str
    input_text: str
    status: str
    session_id: str | None = None
    risk_level: str | None = None
    parsed_intent: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    approval_id: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class TaskListResponse(BaseModel):
    """Paginated task list response."""

    tasks: list[TaskResponse]


class TaskEventResponse(BaseModel):
    """Task event response."""

    id: int
    task_id: str
    type: str
    message: str
    payload: dict[str, Any] | None = None
    created_at: str


class ApprovalResponse(BaseModel):
    """Approval request response."""

    approval_id: str
    task_id: str
    risk_level: str
    prompt: str
    status: str
    response: str | None = None
    created_at: str
    decided_at: str | None = None


class ApprovalListResponse(BaseModel):
    """Pending approval list response."""

    approvals: list[ApprovalResponse]


class ApprovalDecisionRequest(BaseModel):
    """Approval decision request body."""

    decision: str = Field(pattern="^(approved|rejected)$")


class SettingsResponse(BaseModel):
    """Application settings exposed to the frontend."""

    setup_complete: bool
    ollama_base_url: str
    ollama_model: str
    debug_mode: bool
    auto_approve_low_risk: bool


class SettingsUpdateRequest(BaseModel):
    """Mutable settings accepted from the frontend."""

    setup_complete: bool | None = None
    ollama_model: str | None = None
    debug_mode: bool | None = None
    auto_approve_low_risk: bool | None = None


class PluginListResponse(BaseModel):
    """Plugin list response."""

    plugins: list[dict[str, Any]]


class DetailedHealthResponse(BaseModel):
    """Detailed health response for monitoring."""

    status: str
    components: dict[str, Any]
    uptime_seconds: int
    version: str


class SessionListResponse(BaseModel):
    """Session status response."""

    sessions: list[dict[str, Any]]


class ModelPullRequest(BaseModel):
    """Request body for model download streaming."""

    model: str


class BrowserStatusResponse(BaseModel):
    """Status of the retained browser context after task completion."""

    open: bool
    task_id: str | None = None
    url: str | None = None
    idle_seconds: int = 0
    timeout_minutes: int = 15
