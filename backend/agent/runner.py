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

        from backend.llm.registry import model_registry
        if not model_registry._installed_cache:
            try:
                await model_registry.probe_installed()
            except Exception:
                pass

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

        # Close any retained browsers from previous tasks for a clean slate
        from backend.browser.pool import browser_pool
        await browser_pool.close_all_retained(reason="new_task")

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

    async def resume_blocked(self, task_id: str) -> tuple[bool, str]:
        """Verify if CAPTCHA is cleared, and resume the task from the current step."""
        task = await self.db.get_task(task_id)
        if not task:
            return False, "Task not found"
        if task.status != "blocked":
            return False, f"Task is not blocked (current status: {task.status})"

        from backend.browser.pool import browser_pool
        from backend.browser.dom import detect_captcha
        context = await browser_pool.get_task_context(task_id, task.session_id)
        if not context.pages:
            return False, "No active browser page found for task"
        page = context.pages[0]

        is_captcha, reason = await detect_captcha(page)
        if is_captcha or "/sorry/" in page.url.lower():
            logger.info("RESUME_BLOCKED check: CAPTCHA is still present on page (%s)", page.url)
            await self.db.add_event(
                task_id,
                "CAPTCHA_CHECK",
                "CAPTCHA is still present; please complete verification in the browser before resuming",
                {"url": page.url, "reason": reason},
            )
            return False, f"CAPTCHA is still present: {reason}. Please complete the verification in the browser."

        logger.info("[CAPTCHA CLEARED]\nTask %s resuming existing step", task_id)
        await self.db.add_event(task_id, "CAPTCHA_CLEARED", "CAPTCHA cleared, resuming current step", {"url": page.url})
        await self.db.update_task(task_id, status="queued")

        self._pause_events[task_id] = asyncio.Event()
        self._pause_events[task_id].set()
        self._schedule(task_id, task.input_text, approved=True, session_id=task.session_id)
        return True, "CAPTCHA cleared; task resumed from current step."

    async def switch_fallback(self, task_id: str, provider: str = "duckduckgo") -> tuple[bool, str]:
        """Switch to a safe search fallback provider and resume task execution."""
        task = await self.db.get_task(task_id)
        if not task:
            return False, "Task not found"
        if task.status != "blocked":
            return False, f"Task is not blocked (current status: {task.status})"

        from backend.agent.checkpoint import checkpoint_manager
        from backend.agent.nodes import extract_clean_search_query
        from backend.browser.pool import browser_pool
        from urllib.parse import quote_plus

        clean_query = extract_clean_search_query(task.input_text, default="search query")
        fallback_url = (
            f"https://html.duckduckgo.com/html/?q={quote_plus(clean_query)}"
            if provider.lower() == "duckduckgo"
            else f"https://www.bing.com/search?q={quote_plus(clean_query)}"
        )

        logger.warning(
            "[FALLBACK]\nGoogle blocked by CAPTCHA\nSwitching to %s",
            provider,
        )
        await self.db.add_event(
            task_id,
            "FALLBACK",
            f"Google blocked by CAPTCHA. Switching to {provider}",
            {"provider": provider, "query": clean_query, "url": fallback_url},
        )

        context = await browser_pool.get_task_context(task_id, task.session_id)
        if context.pages:
            page = context.pages[0]
            try:
                await page.goto(fallback_url, timeout=15000)
            except Exception as e:
                logger.warning("Fallback navigation error: %s", e)

        ckpt = checkpoint_manager.load_checkpoint(task_id)
        if ckpt:
            ckpt.current_url = fallback_url
            checkpoint_manager.save_checkpoint(task_id, ckpt.model_dump(), current_node="navigate")

        await self.db.update_task(task_id, status="queued")
        self._pause_events[task_id] = asyncio.Event()
        self._pause_events[task_id].set()
        self._schedule(task_id, task.input_text, approved=True, session_id=task.session_id)
        return True, f"Switched to {provider} and resumed search."

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
            await self.db.add_event(task_id, "TASK_STARTED", f"Task execution started: {input_text[:100]}", {"input_text": input_text, "status": "running"})
            logger.info("RUNNER task_starting task_id=%s input=%s", task_id, input_text[:120])

            from backend.agent.checkpoint import checkpoint_manager
            from backend.llm.parser import ParsedIntent, TaskPlan
            ckpt = checkpoint_manager.load_checkpoint(task_id)

            restored_intent = None
            if ckpt and ckpt.parsed_intent:
                restored_intent = ParsedIntent(**ckpt.parsed_intent) if isinstance(ckpt.parsed_intent, dict) else ckpt.parsed_intent

            restored_plan = None
            if ckpt and ckpt.task_plan:
                restored_plan = TaskPlan(**ckpt.task_plan) if isinstance(ckpt.task_plan, dict) else ckpt.task_plan

            restored_plugin_id = getattr(ckpt, "plugin_id", None) if ckpt else None
            if not restored_plugin_id and restored_intent:
                found_plugin = plugin_registry.find_for_intent(restored_intent)
                if found_plugin:
                    restored_plugin_id = found_plugin.plugin_id

            state = {
                "task_id": task_id,
                "input_text": input_text,
                "parsed_intent": restored_intent,
                "current_url": ckpt.current_url if ckpt else None,
                "action_manifest": None,
                "action_history": [],
                "retry_count": ckpt.retry_count if ckpt else 0,
                "status": "running",
                "approval_id": None,
                "error": None,
                "result": None,
                "plugin_id": restored_plugin_id,
                "llm_call_count": ckpt.llm_call_count if ckpt else 0,
                "planned_action": None,
                "approved": approved,
                "navigation_succeeded": False,
                "session_id": session_id,
                "task_plan": restored_plan,
                "current_step_index": ckpt.current_step_index if ckpt else 1,
                "retrieved_knowledge": ckpt.retrieved_knowledge if ckpt and ckpt.retrieved_knowledge else [],
                "retrieved_memories": ckpt.retrieved_memories if ckpt and ckpt.retrieved_memories else [],
                "retrieval_metadata": ckpt.retrieval_metadata if ckpt else {},
                "selected_model": ckpt.selected_model if ckpt else None,
                "model_role": ckpt.model_role if ckpt else None,
                "routing_reason": ckpt.routing_reason if ckpt else None,
                "model_switch": False,
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
                    elif node_name == "retrieve_context":
                        await self.db.add_event(task_id, "context_retrieved", "Context Retrieved", {
                            "rag_retrieved": len(node_state.get("retrieved_knowledge", [])),
                            "memories_retrieved": len(node_state.get("retrieved_memories", [])),
                        })
                    elif node_name == "plan_action":
                        await self.db.add_event(task_id, "action_executing", "Action Executing", {
                            "model": node_state.get("selected_model"),
                            "role": node_state.get("model_role"),
                        })
                    elif node_name == "execute_action":
                        await self.db.add_event(task_id, "evidence_stored", "Action Verified and Evidence Stored", {})
                    state.update(node_state)
                    checkpoint_manager.save_checkpoint(task_id, state, current_node=node_name)

            final_state = state
            
            # Record events and summarize to memory based on final state
            if final_state.get("status") == "waiting_approval":
                await self.db.add_event(task_id, "approval_required", "Human approval required", {"approval_id": final_state.get("approval_id")})
            else:
                from backend.memory.provider import memory_manager
                await memory_manager.summarize_task(task_id, final_state.get("result") or {}, input_text)
                
                if final_state.get("status") == "completed":
                    checkpoint_manager.clear_checkpoint(task_id)
                    await self.db.add_event(task_id, "completed", "Task Completed", final_state.get("result") or {})
                    await self.db.add_event(task_id, "TASK_COMPLETED", "Task execution completed successfully", final_state.get("result") or {})
                elif final_state.get("status") == "failed":
                    await self.db.add_event(task_id, "failed", "Task failed", {"error": final_state.get("error")})
                elif final_state.get("status") == "blocked":
                    await self.db.add_event(
                        task_id,
                        "blocked",
                        "Task blocked by CAPTCHA / bot verification",
                        {"error": final_state.get("error"), "blocked_reason": final_state.get("blocked_reason") or "CAPTCHA / bot verification detected"},
                    )

                # Record task summary in telemetry tracer (R14)
                from backend.telemetry.tracer import tracer
                duration_ms = 0
                if task_id in self._started_at:
                    duration_ms = int((datetime.now(UTC) - self._started_at[task_id]).total_seconds() * 1000)
                tracer.record_task_summary(
                    task_id=task_id,
                    status=final_state.get("status", "unknown"),
                    duration_ms=duration_ms,
                    step_count=final_state.get("llm_call_count", 0),
                    error=final_state.get("error"),
                )

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
            from backend.telemetry.tracer import tracer
            tracer.record_task_summary(task_id=task_id, status="failed", duration_ms=0, step_count=0, error=str(exc))

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
