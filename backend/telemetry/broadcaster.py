"""Real-time event broadcaster for Pilot Agent Observability."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import logging
import re
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger("pilot.telemetry.broadcaster")

# Patterns for sensitive credentials to redact from telemetry/observability
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^'\",\s]+)", re.IGNORECASE),
    re.compile(r"(?i)(bearer|token|api_key|apikey|secret)\s*[:=]\s*['\"]?([^'\",\s]+)", re.IGNORECASE),
    re.compile(r"(?i)(auth|authorization)\s*[:=]\s*['\"]?([^'\",\s]+)", re.IGNORECASE),
    re.compile(r"(?i)(cookie)\s*[:=]\s*['\"]?([^'\",\s]+)", re.IGNORECASE),
]


def redact_sensitive(obj: Any) -> Any:
    """Recursively redact passwords, tokens, API keys, and authorization secrets."""
    if isinstance(obj, str):
        redacted = obj
        for pattern in SENSITIVE_PATTERNS:
            redacted = pattern.sub(r"\1: [REDACTED]", redacted)
        return redacted
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if any(term in k.lower() for term in ("password", "passwd", "token", "secret", "cookie", "auth", "api_key", "apikey", "credential")):
                result[k] = "[REDACTED]"
            else:
                result[k] = redact_sensitive(v)
        return result
    if isinstance(obj, list):
        return [redact_sensitive(item) for item in obj]
    return obj


class ObservatoryEvent(BaseModel):
    """Standardized event payload for the Pilot Agent Observatory."""

    event_id: str
    run_id: str
    task_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    event_type: str
    status: str = "running"
    step_index: int = 0
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservabilityBroadcaster:
    """Manages real-time pub-sub distribution of agent execution events."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[ObservabilityEvent]] = set()
        self._history: list[ObservabilityEvent] = []
        self._max_history = 500

    def subscribe(self) -> asyncio.Queue[ObservabilityEvent]:
        """Subscribe a new WebSocket or SSE stream queue."""
        queue: asyncio.Queue[ObservabilityEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        logger.debug("Observability subscriber added (total: %d)", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[ObservabilityEvent]) -> None:
        """Unsubscribe an active stream queue."""
        self._subscribers.discard(queue)
        logger.debug("Observability subscriber removed (total: %d)", len(self._subscribers))

    def get_recent_events(self, task_id: str | None = None, limit: int = 100) -> list[ObservabilityEvent]:
        """Return buffered recent events, optionally filtered by task_id."""
        if task_id:
            filtered = [e for e in self._history if e.task_id == task_id or e.run_id == task_id]
            return filtered[-limit:]
        return self._history[-limit:]

    async def broadcast(self, event: ObservatoryEvent) -> None:
        """Broadcast an event to all subscribers and append to recent history."""
        # Redact sensitive metadata before broadcasting
        safe_metadata = redact_sensitive(event.metadata)
        safe_event = event.model_copy(update={"metadata": safe_metadata})

        self._history.append(safe_event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        dead_subscribers = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(safe_event)
            except asyncio.QueueFull:
                # If a client is too slow, pop oldest event to preserve memory
                try:
                    queue.get_nowait()
                    queue.put_nowait(safe_event)
                except Exception:
                    dead_subscribers.append(queue)
            except Exception:
                dead_subscribers.append(queue)

        for dead in dead_subscribers:
            self._subscribers.discard(dead)

    def publish_sync(
        self,
        event_id: str,
        task_id: str,
        event_type: str,
        message: str = "",
        status: str = "running",
        step_index: int = 0,
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> None:
        """Helper to create and broadcast an event from synchronous code."""
        event = ObservatoryEvent(
            event_id=str(event_id),
            run_id=str(run_id or task_id),
            task_id=str(task_id),
            event_type=str(event_type),
            status=str(status),
            step_index=step_index,
            message=str(message),
            metadata=metadata or {},
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(event))
        except RuntimeError:
            pass


# Global singleton broadcaster
broadcaster = ObservabilityBroadcaster()
