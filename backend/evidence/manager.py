"""Evidence generation framework for verifying task execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel

from backend.config import get_config
from backend.db.database import resolve_path


class EvidenceManager:
    """Manages the generation of hard evidence artifacts for task execution."""

    def __init__(self) -> None:
        self.evidence_dir = resolve_path(get_config().log_dir) / "evidence"
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


evidence_manager = EvidenceManager()
