"""Background task runner for Pilot's local-first MVP execution loop."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus
import uuid

from backend.config import PilotConfig, get_config
from backend.db.database import Database
from backend.llm.parser import ParsedIntent, heuristic_parse_intent
from backend.plugins.runtime import plugin_registry
from backend.security.approval import build_approval_prompt, requires_approval


class TaskRunner:
    """Run user tasks asynchronously and persist progress events."""

    def __init__(self, db: Database, config: PilotConfig | None = None) -> None:
        """Create a runner backed by SQLite."""

        self.db = db
        self.config = config or get_config()
        self._active: dict[str, asyncio.Task[None]] = {}
        self._started_at: dict[str, datetime] = {}
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

    async def submit(self, input_text: str) -> str:
        """Create and schedule a task, returning its id."""

        task_id = str(uuid.uuid4())
        await self.db.create_task(task_id, input_text)
        await self.db.add_event(task_id, "queued", "Task queued", {"input_text": input_text})
        self._schedule(task_id, input_text, approved=False)
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

    async def cancel(self, task_id: str) -> None:
        """Cancel a running or queued task and persist the status."""

        active = self._active.pop(task_id, None)
        if active is not None:
            active.cancel()
        await self.db.update_task(
            task_id,
            status="cancelled",
            completed_at=datetime.now(UTC).isoformat(),
        )
        await self.db.add_event(task_id, "cancelled", "Task cancelled by user")

    def _schedule(self, task_id: str, input_text: str, approved: bool) -> None:
        """Schedule a task coroutine and track timeout metadata."""

        self._started_at[task_id] = datetime.now(UTC)
        self._active[task_id] = asyncio.create_task(self._run(task_id, input_text, approved))

    async def _run(self, task_id: str, input_text: str, approved: bool) -> None:
        """Execute a task through parse, risk, plugin, and completion steps."""

        try:
            await self.db.update_task(task_id, status="running")
            await self.db.add_event(task_id, "started", "Task started")
            intent = heuristic_parse_intent(input_text)
            await self.db.update_task(
                task_id,
                risk_level=intent.risk_level,
                parsed_intent_json=intent.model_dump_json(),
            )
            await self.db.add_event(task_id, "intent_parsed", "Intent parsed", intent.model_dump())

            if requires_approval(intent) and not approved:
                approval_id = str(uuid.uuid4())
                approval = await self.db.create_approval(
                    approval_id,
                    task_id,
                    intent.risk_level,
                    build_approval_prompt(intent),
                )
                await self.db.update_task(task_id, status="waiting_approval", approval_id=approval.approval_id)
                await self.db.add_event(
                    task_id,
                    "approval_required",
                    "Human approval required",
                    approval.model_dump(),
                )
                return

            result = await self._execute_intent(intent)
            await self.db.update_task(
                task_id,
                status="completed",
                result_json=json.dumps(result),
                completed_at=datetime.now(UTC).isoformat(),
            )
            await self.db.add_event(task_id, "completed", "Task completed", result)
        except asyncio.CancelledError:
            await self.db.add_event(task_id, "cancelled", "Task coroutine cancelled")
        except Exception as exc:
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

    async def _execute_intent(self, intent: ParsedIntent) -> dict:
        """Execute a safe MVP result for the parsed intent."""

        plugin = plugin_registry.find_for_intent(intent)
        if plugin is not None:
            plugin_result = await plugin.execute(intent)
            if not plugin_result.success:
                raise RuntimeError(plugin_result.message)
            return {
                "mode": "plugin",
                "plugin_id": plugin.plugin_id,
                "message": plugin_result.message,
                "data": plugin_result.data,
            }

        if intent.action == "search":
            query = intent.target or intent.content or ""
            return {
                "mode": "browser_plan",
                "action": "search",
                "url": "https://www.google.com/search?q=" + quote_plus(query),
                "dry_run": False,
            }

        site = intent.site if intent.site != "unknown" else "https://www.google.com"
        if not site.startswith(("http://", "https://")):
            site = "https://" + site
        return {
            "mode": "browser_plan",
            "action": intent.action,
            "url": site,
            "dry_run": intent.risk_level in {"high", "critical"},
        }

    async def _timeout_watchdog(self) -> None:
        """Cancel tasks that exceed the configured maximum duration."""

        while True:
            await asyncio.sleep(60)
            cutoff = datetime.now(UTC) - timedelta(minutes=self.config.max_task_duration_minutes)
            for task_id, started in list(self._started_at.items()):
                if started < cutoff:
                    await self.cancel(task_id)
