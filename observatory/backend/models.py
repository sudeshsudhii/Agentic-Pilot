"""Pydantic data models for Pilot Agent Observatory."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ObservatoryEventModel(BaseModel):
    """Event model conforming to the Observatory specification."""

    event_id: str
    run_id: str
    task_id: str
    timestamp: str
    event_type: str
    status: str = "running"
    step_index: int = 0
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    """Summary of an agent run."""

    run_id: str
    task_id: str
    input_text: str
    status: str
    created_at: str
    completed_at: str | None = None
    duration_sec: float | None = None
    step_count: int = 0
    model: str = "UNKNOWN"
    vision_status: str = "UNKNOWN"
    error: str | None = None


class PerformanceMetrics(BaseModel):
    """Detailed performance timings for an agent run."""

    total_duration_sec: float = 0.0
    planner_duration_sec: float = 0.0
    vision_duration_sec: float = 0.0
    browser_duration_sec: float = 0.0
    verification_duration_sec: float = 0.0
    waiting_duration_sec: float = 0.0
    retry_duration_sec: float = 0.0
    model_latencies: list[dict[str, Any]] = Field(default_factory=list)


class SystemStatus(BaseModel):
    """Observatory connection status."""

    pilot_backend_connected: bool = False
    event_stream_connected: bool = False
    last_event_timestamp: str | None = None
    last_event_age_sec: float | None = None
    active_run_id: str | None = None
    event_buffer_size: int = 0
