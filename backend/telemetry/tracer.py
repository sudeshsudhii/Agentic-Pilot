"""Observability and execution tracing for Agentic Pilot."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.config import get_config
from backend.db.database import resolve_path


class TelemetryTracer:
    """Logs detailed execution traces for research and debugging."""

    def __init__(self) -> None:
        """Initialize the tracer and ensure log directory exists."""
        self.log_dir = resolve_path(get_config().log_dir)
        self.trace_file = self.log_dir / "traces.jsonl"

    def record_trace(self, task_id: str, component: str, event: str, metadata: dict[str, Any] | None = None) -> None:
        """Append a trace record to the JSONL log file."""
        trace = {
            "timestamp": datetime.now(UTC).isoformat(),
            "task_id": task_id,
            "component": component,
            "event": event,
            "metadata": metadata or {},
        }
        
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace) + "\n")

    def record_llm_call(self, task_id: str, prompt: str, response: str, latency_ms: int, model: str) -> None:
        """Record an LLM generation event."""
        self.record_trace(task_id, "llm", "completion", {
            "model": model,
            "prompt_length": len(prompt),
            "response_length": len(response),
            "latency_ms": latency_ms
        })

    def record_browser_action(self, task_id: str, action_type: str, success: bool, duration_ms: int, error: str | None = None) -> None:
        """Record a browser action execution."""
        self.record_trace(task_id, "browser", action_type, {
            "success": success,
            "duration_ms": duration_ms,
            "error": error
        })


tracer = TelemetryTracer()
