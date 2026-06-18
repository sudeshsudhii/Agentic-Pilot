"""Background task runner for Pilot's local-first MVP execution loop."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus
import uuid

from backend.config import PilotConfig, get_config
from backend.db.database import Database
from backend.llm.parser import ParsedIntent
from backend.plugins.runtime import plugin_registry
from backend.security.approval import build_approval_prompt, requires_approval
from backend.evidence.manager import evidence_manager

logger = logging.getLogger("pilot.agent.runner")


class TaskRunner:
    """Run user tasks asynchronously and persist progress events."""

    def __init__(self, db: Database, config: PilotConfig | None = None) -> None:
        """Create a runner backed by SQLite."""

        self.db = db
        self.config = config or get_config()
        self._active: dict[str, asyncio.Task[None]] = {}
        self._started_at: dict[str, datetime] = {}
        self._pause_events: dict[str, asyncio.Event] = {}
        self._watchdog: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start background maintenance tasks for timeouts."""

        if self._watchdog is None:
            self._watchdog = asyncio.create_task(self._timeout_watchdog())

    async def shutdown(self) -> None:
        """Cancel active runner tasks and stop background maintenance."""

        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None
        for task in list(self._active.values()):
            task.cancel()
        if self._active:
            await asyncio.gather(*self._active.values(), return_exceptions=True)
        self._active.clear()

    async def submit(self, input_text: str, session_id: str | None = None) -> str:
        """Create and schedule a task, returning its id."""

        task_id = str(uuid.uuid4())
        self._pause_events[task_id] = asyncio.Event()
        self._pause_events[task_id].set()
        await self.db.create_task(task_id, input_text, session_id)
        await self.db.add_event(task_id, "queued", "Task queued", {"input_text": input_text})
        self._schedule(task_id, input_text, approved=False, session_id=session_id)
        return task_id

    async def approve(self, approval_id: str, decision: str) -> str:
        """Apply an approval decision and resume the task if approved."""

        approval = await self.db.respond_approval(approval_id, decision)
        task = await self.db.get_task(approval.task_id)
        if task is None:
            raise ValueError("Task not found for approval")
        if decision == "approved":
            await self.db.add_event(task.task_id, "approval_approved", "Approval accepted", {"approval_id": approval_id})
            await self.db.update_task(task.task_id, status="queued")
            self._schedule(task.task_id, task.input_text, approved=True)
        else:
            await self.db.add_event(task.task_id, "approval_rejected", "Approval rejected", {"approval_id": approval_id})
            await self.db.update_task(
                task.task_id,
                status="failed",
                error="User rejected the approval request.",
                completed_at=datetime.now(UTC).isoformat(),
            )
        return task.task_id

    def pause(self, task_id: str) -> None:
        """Pause a running task at the next node transition."""
        if task_id in self._pause_events:
            self._pause_events[task_id].clear()

    def resume(self, task_id: str) -> None:
        """Resume a paused task."""
        if task_id in self._pause_events:
            self._pause_events[task_id].set()

    async def cancel(self, task_id: str) -> None:
        """Cancel a running or queued task and persist the status."""

        if task_id in self._pause_events:
            self._pause_events[task_id].set()
            
        active = self._active.pop(task_id, None)
        if active is not None:
            active.cancel()
        await self.db.update_task(
            task_id,
            status="cancelled",
            completed_at=datetime.now(UTC).isoformat(),
        )
        await self.db.add_event(task_id, "cancelled", "Task cancelled by user")

    def _schedule(self, task_id: str, input_text: str, approved: bool, session_id: str | None = None) -> None:
        """Schedule a task coroutine and track timeout metadata."""

        self._started_at[task_id] = datetime.now(UTC)
        self._active[task_id] = asyncio.create_task(self._run(task_id, input_text, approved, session_id))

    async def _run(self, task_id: str, input_text: str, approved: bool, session_id: str | None = None) -> None:
        """Execute a task through the LangGraph state machine."""

        from backend.agent.graph import build_graph
        graph = build_graph()
        if not graph:
            raise RuntimeError("LangGraph could not be built")

        try:
            await self.db.update_task(task_id, status="running")
            await self.db.add_event(task_id, "started", "Task started via LangGraph")
            logger.info("RUNNER task_starting task_id=%s input=%s", task_id, input_text[:120])

            state = {
                "task_id": task_id,
                "input_text": input_text,
                "parsed_intent": None,
                "current_url": None,
                "action_manifest": None,
                "action_history": [],
                "retry_count": 0,
                "status": "running",
                "approval_id": None,
                "error": None,
                "result": None,
                "plugin_id": None,
                "llm_call_count": 0,
                "planned_action": None,
                "approved": approved,
                "navigation_succeeded": False,
                "session_id": session_id,
            }

            async for event in graph.astream(state):
                if task_id in self._pause_events:
                    await self._pause_events[task_id].wait()
                    
                for node_name, node_state in event.items():
                    trace_event = {
                        "node": node_name,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "status": node_state.get("status") or state.get("status"),
                        "error": node_state.get("error") or state.get("error"),
                    }
                    evidence_manager.append_trace(task_id, trace_event)

                    if node_name == "parse_intent":
                        await self.db.add_event(task_id, "plan_generated", "Intent parsed", {})
                    elif node_name == "navigate":
                        await self.db.add_event(task_id, "page_loaded", "Page loaded", {})
                    elif node_name == "extract_dom":
                        await self.db.add_event(task_id, "dom_extracted", "DOM Extracted", {})
                    elif node_name == "plan_action":
                        await self.db.add_event(task_id, "action_executing", "Action Executing", {})
                    elif node_name == "execute_action":
                        await self.db.add_event(task_id, "evidence_stored", "Action Verified and Evidence Stored", {})
                    state.update(node_state)

            final_state = state
            
            # Record events and summarize to memory based on final state
            if final_state.get("status") == "waiting_approval":
                await self.db.add_event(task_id, "approval_required", "Human approval required", {"approval_id": final_state.get("approval_id")})
            else:
                from backend.memory.provider import memory_manager
                await memory_manager.summarize_task(task_id, final_state.get("result") or {}, input_text)
                
                if final_state.get("status") == "completed":
                    await self.db.add_event(task_id, "completed", "Task Completed", final_state.get("result") or {})
                elif final_state.get("status") == "failed":
                    await self.db.add_event(task_id, "failed", "Task failed", {"error": final_state.get("error")})

        except asyncio.CancelledError:
            await self.db.add_event(task_id, "cancelled", "Task coroutine cancelled")
        except Exception as exc:
            logger.exception("RUNNER task_failed task_id=%s error=%s error_type=%s", task_id, exc, type(exc).__name__)
            await self.db.update_task(
                task_id,
                status="failed",
                error=str(exc),
                completed_at=datetime.now(UTC).isoformat(),
            )
            await self.db.add_event(task_id, "failed", "Task failed", {"error": str(exc)})
        finally:
            self._active.pop(task_id, None)
            self._started_at.pop(task_id, None)

    # Removed _execute_intent as execution is fully handled by LangGraph now.

    async def _timeout_watchdog(self) -> None:
        """Cancel tasks that exceed the configured maximum duration."""

        while True:
            await asyncio.sleep(60)
            cutoff = datetime.now(UTC) - timedelta(minutes=self.config.max_task_duration_minutes)
            for task_id, started in list(self._started_at.items()):
                if started < cutoff:
                    await self.cancel(task_id)
