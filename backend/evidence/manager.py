"""Evidence generation framework for verifying task execution."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from backend.config import get_config
from backend.db.database import resolve_path


class ExecutionRecord(BaseModel):
    """Structured execution record for a single step in task execution.

    This is the core schema for evidence-driven execution (R07).
    Every meaningful action produces one of these records.
    """

    task_id: str
    step_id: str
    step_index: int = 0
    action: dict[str, Any] = Field(default_factory=dict)
    before_state: dict[str, Any] = Field(default_factory=dict)
    execution_result: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    knowledge_context: list[dict[str, Any]] = Field(default_factory=list)
    model: str = ""
    model_role: str = ""
    routing_reason: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: int = 0
    node_name: str = ""



class EvidenceManager:
    """Manages the generation of hard evidence artifacts for task execution."""

    def __init__(self, evidence_dir: Path | None = None) -> None:
        self.evidence_dir = evidence_dir or (resolve_path(get_config().log_dir) / "evidence")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)


    def _get_task_dir(self, task_id: str) -> Path:
        task_dir = self.evidence_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def save_screenshot(self, task_id: str, name: str, data: bytes) -> str:
        """Save a screenshot (e.g., before.png, after.png)."""
        file_path = self._get_task_dir(task_id) / f"{name}.png"
        with open(file_path, "wb") as f:
            f.write(data)
        return str(file_path)

    def append_trace(self, task_id: str, event: dict[str, Any]) -> str:
        """Append an event to trace.json."""
        file_path = self._get_task_dir(task_id) / "trace.json"
        
        traces = []
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    traces = json.load(f)
                except json.JSONDecodeError:
                    pass
                    
        traces.append(event)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(traces, f, indent=2)
            
        return str(file_path)

    def save_dom_snapshot(self, task_id: str, manifest: BaseModel) -> str:
        """Save the DOM snapshot."""
        file_path = self._get_task_dir(task_id) / "dom_snapshot.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))
        return str(file_path)

    def save_verification(self, task_id: str, result: dict[str, Any]) -> str:
        """Save hard verification results."""
        file_path = self._get_task_dir(task_id) / "verification.json"
        
        verifications = []
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    verifications = json.load(f)
                except json.JSONDecodeError:
                    pass
                    
        verifications.append(result)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(verifications, f, indent=2)
            
        return str(file_path)

    def save_execution_log(self, task_id: str, log_data: dict[str, Any]) -> str:
        """Save a summary execution log."""
        file_path = self._get_task_dir(task_id) / "execution_log.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
        return str(file_path)

    def save_execution_record(self, record: ExecutionRecord) -> str:
        """Save a structured execution record for a single step.

        Records are appended to execution_records.json in the task's evidence
        directory. This is the core evidence-driven execution artifact (R07).
        """
        file_path = self._get_task_dir(record.task_id) / "execution_records.json"

        records: list[dict] = []
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    records = json.load(f)
                except json.JSONDecodeError:
                    pass

        records.append(record.model_dump())

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

        return str(file_path)

    def load_task_records(self, task_id: str) -> list[ExecutionRecord]:
        """Load all execution records for a task."""
        file_path = self._get_task_dir(task_id) / "execution_records.json"
        if not file_path.exists():
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return [ExecutionRecord.model_validate(r) for r in data]
            except (json.JSONDecodeError, Exception):
                return []


evidence_manager = EvidenceManager()

