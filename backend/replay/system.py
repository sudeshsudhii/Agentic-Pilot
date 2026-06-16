"""Replay system for debugging and reviewing past task executions."""

from __future__ import annotations
import json
from pathlib import Path

class ReplaySystem:
    """Loads evidence and traces to replay task execution steps."""

    def __init__(self):
        self.evidence_dir = Path.home() / ".pilot" / "evidence"
        
    def list_replays(self) -> list[str]:
        """List all task IDs that have available replays."""
        if not self.evidence_dir.exists():
            return []
        return [d.name for d in self.evidence_dir.iterdir() if d.is_dir()]
        
    def load_replay(self, task_id: str) -> dict:
        """Load all artifacts for a specific task to reconstruct execution."""
        task_dir = self.evidence_dir / task_id
        if not task_dir.exists():
            raise ValueError(f"No evidence found for task {task_id}")
            
        replay_data = {
            "task_id": task_id,
            "trace": self._load_json(task_dir / "trace.json"),
            "execution_log": self._load_json(task_dir / "execution_log.json"),
            "dom_snapshot": self._load_json(task_dir / "dom_snapshot.json"),
            "verification": self._load_json(task_dir / "verification.json"),
            "telemetry": self._load_json(task_dir / "telemetry.json"),
            "screenshots": [f.name for f in task_dir.glob("*.png")]
        }
        
        return replay_data
        
    def _load_json(self, path: Path) -> dict | list | None:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

replay_system = ReplaySystem()
