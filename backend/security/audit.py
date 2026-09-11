"""Privacy audit logging for Agentic Pilot (R12).

Tracks all external network requests, LLM call metadata, and data sizes
to provide measurable privacy characteristics. All data stays local in
an append-only JSONL audit log.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.config import get_config
from backend.db.database import resolve_path

logger = logging.getLogger("pilot.security.audit")


class PrivacyAuditor:
    """Tracks external communications for privacy measurement.

    Records:
    - LLM calls (model, prompt/response sizes, destination)
    - External network requests
    - Data transmission sizes

    All logs are local — no external transmission.
    """

    def __init__(self, log_path: Path | str | None = None) -> None:
        config = get_config()
        self.enabled = config.privacy_audit_enabled
        if log_path is not None:
            p = Path(log_path)
            self.log_path = p / "privacy_audit.jsonl" if p.is_dir() else p
        else:
            self.log_path = resolve_path(config.privacy_audit_log)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stats: dict[str, int] = {

            "total_llm_calls": 0,
            "total_prompt_bytes": 0,
            "total_response_bytes": 0,
            "total_external_requests": 0,
            "total_external_bytes": 0,
        }

    def record_llm_call(
        self,
        model: str,
        destination: str,
        prompt_bytes: int,
        response_bytes: int,
        latency_ms: int,
        task_id: str = "global",
    ) -> None:
        """Record an LLM inference call for privacy audit."""
        if not self.enabled:
            return

        self._stats["total_llm_calls"] += 1
        self._stats["total_prompt_bytes"] += prompt_bytes
        self._stats["total_response_bytes"] += response_bytes

        is_local = "127.0.0.1" in destination or "localhost" in destination
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "llm_call",
            "task_id": task_id,
            "model": model,
            "destination": destination,
            "is_local": is_local,
            "prompt_bytes": prompt_bytes,
            "response_bytes": response_bytes,
            "latency_ms": latency_ms,
        }
        self._append(entry)

    def record_external_request(
        self,
        url: str,
        method: str = "GET",
        data_bytes: int = 0,
        task_id: str = "global",
        purpose: str = "browser_navigation",
    ) -> None:
        """Record an external network request for privacy audit."""
        if not self.enabled:
            return

        self._stats["total_external_requests"] += 1
        self._stats["total_external_bytes"] += data_bytes

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "external_request",
            "task_id": task_id,
            "url": url,
            "method": method,
            "data_bytes": data_bytes,
            "purpose": purpose,
        }
        self._append(entry)

    def get_privacy_summary(self) -> dict[str, Any]:
        """Return a summary of privacy-relevant metrics."""
        return {
            **self._stats,
            "audit_log_path": str(self.log_path),
            "audit_enabled": self.enabled,
        }

    def _append(self, entry: dict[str, Any]) -> None:
        """Append an entry to the audit log."""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning("Privacy audit log write failed: %s", exc)


privacy_auditor = PrivacyAuditor()
