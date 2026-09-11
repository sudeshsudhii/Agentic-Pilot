"""Execution state checkpointing and recovery for Agentic Pilot.

Prevents repeated agent analysis and token waste by persisting state at node boundaries.
If execution is interrupted or a new step is initiated, the agent can resume from the
latest checkpoint without re-running intent parsing, task decomposition, and RAG retrieval.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from backend.config import get_config

logger = logging.getLogger("pilot.agent.checkpoint")


class TaskCheckpoint(BaseModel):
    """Serializable execution state checkpoint."""

    task_id: str
    execution_id: str = ""
    timestamp: float = Field(default_factory=time.time)
    current_node: str = "init"
    current_step_index: int = 1
    status: str = "running"
    task_plan: dict[str, Any] | None = None
    parsed_intent: dict[str, Any] | None = None
    plugin_id: str | None = None
    selected_model: str | None = None
    model_role: str | None = None
    routing_reason: str | None = None
    retrieved_knowledge: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_memories: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
    completed_actions: list[dict[str, Any]] = Field(default_factory=list)
    retry_count: int = 0
    llm_call_count: int = 0
    current_url: str | None = None
    context_hash: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class CheckpointManager:
    """Manages disk persistence and restoration of task execution checkpoints."""

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        if storage_dir is None:
            config = get_config()
            from backend.db.database import resolve_path
            base_dir = resolve_path(getattr(config, "data_dir", "~/.pilot/data"))
            self.storage_dir = base_dir / "checkpoints"
        else:
            self.storage_dir = Path(storage_dir)

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._in_memory_cache: dict[str, TaskCheckpoint] = {}

    def _get_checkpoint_path(self, task_id: str) -> Path:
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in task_id)
        return self.storage_dir / f"{safe_name}.json"

    def _serialize_object(self, obj: Any) -> Any:
        """Helper to convert Pydantic objects, lists, and dicts to JSON-serializable types."""
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, list):
            return [self._serialize_object(item) for item in obj]
        if isinstance(obj, dict):
            return {k: self._serialize_object(v) for k, v in obj.items()}
        return obj

    def save_checkpoint(
        self,
        task_id: str,
        state: dict[str, Any],
        current_node: str,
        execution_id: str = "",
    ) -> TaskCheckpoint | None:
        """Save current task execution state to checkpoint storage."""
        if not task_id or task_id == "unknown":
            return None

        try:
            completed_acts = []
            for act in state.get("action_history", []):
                completed_acts.append(self._serialize_object(act))

            checkpoint = TaskCheckpoint(
                task_id=task_id,
                execution_id=execution_id or (state.get("session_id") or ""),
                timestamp=time.time(),
                current_node=current_node,
                current_step_index=state.get("current_step_index", 1),
                status=state.get("status", "running"),
                task_plan=self._serialize_object(state.get("task_plan")),
                parsed_intent=self._serialize_object(state.get("parsed_intent")),
                plugin_id=state.get("plugin_id"),
                selected_model=state.get("selected_model"),
                model_role=state.get("model_role"),
                routing_reason=state.get("routing_reason"),
                retrieved_knowledge=self._serialize_object(state.get("retrieved_knowledge", [])) or [],
                retrieved_memories=self._serialize_object(state.get("retrieved_memories", [])) or [],
                retrieval_metadata=self._serialize_object(state.get("retrieval_metadata", {})) or {},
                completed_actions=completed_acts,
                retry_count=state.get("retry_count", 0),
                llm_call_count=state.get("llm_call_count", 0),
                current_url=state.get("current_url"),
            )

            # Update cache
            self._in_memory_cache[task_id] = checkpoint

            # Write atomically to file
            path = self._get_checkpoint_path(task_id)
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(checkpoint.model_dump_json(indent=2))
            os.replace(tmp_path, path)

            logger.debug(
                "CHECKPOINT saved task_id=%s node=%s step=%d status=%s",
                task_id, current_node, checkpoint.current_step_index, checkpoint.status,
            )
            return checkpoint

        except Exception as exc:
            logger.warning("Failed to save checkpoint for task_id=%s: %s", task_id, exc)
            return None

    def load_checkpoint(self, task_id: str) -> TaskCheckpoint | None:
        """Load the execution checkpoint for a task if available."""
        if task_id in self._in_memory_cache:
            return self._in_memory_cache[task_id]

        path = self._get_checkpoint_path(task_id)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            checkpoint = TaskCheckpoint.model_validate(data)
            self._in_memory_cache[task_id] = checkpoint
            logger.info(
                "CHECKPOINT loaded task_id=%s node=%s step=%d",
                task_id, checkpoint.current_node, checkpoint.current_step_index,
            )
            return checkpoint
        except Exception as exc:
            logger.warning("Failed to load checkpoint for task_id=%s: %s", task_id, exc)
            return None

    def can_resume(self, task_id: str) -> bool:
        """Check whether a valid checkpoint exists from which the task can resume."""
        ckpt = self.load_checkpoint(task_id)
        if not ckpt:
            return False
        # Do not resume completed or permanently failed tasks
        return ckpt.status in ("running", "paused", "waiting_approval")

    def clear_checkpoint(self, task_id: str) -> bool:
        """Remove checkpoint after final completion or purge."""
        self._in_memory_cache.pop(task_id, None)
        path = self._get_checkpoint_path(task_id)
        try:
            if path.exists():
                path.unlink()
                return True
        except Exception as exc:
            logger.warning("Failed to remove checkpoint file for task_id=%s: %s", task_id, exc)
        return False


# Global checkpoint manager singleton
checkpoint_manager = CheckpointManager()
