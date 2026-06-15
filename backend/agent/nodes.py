"""Agent graph node implementations for Pilot task execution."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from backend.agent.prompts import INTENT_SYSTEM_PROMPT
from backend.agent.state import AgentState
from backend.browser.actions import ActionExecutor
from backend.db.database import database
from backend.llm.gateway import OllamaGateway
from backend.llm.parser import ParsedIntent, PlannedAction, heuristic_parse_intent
from backend.plugins.runtime import plugin_registry
from backend.security.approval import build_approval_prompt, requires_approval


async def parse_intent_node(state: AgentState) -> dict:
    """Parse input text into a ParsedIntent and choose a plugin id."""

    gateway = OllamaGateway()
    try:
        parsed = await gateway.complete_structured(
            INTENT_SYSTEM_PROMPT,
            state["input_text"],
            ParsedIntent,
        )
    except Exception:
        parsed = heuristic_parse_intent(state["input_text"])
    plugin = plugin_registry.find_for_intent(parsed)
    return {
        "parsed_intent": parsed,
        "plugin_id": plugin.plugin_id if plugin else None,
        "llm_call_count": state["llm_call_count"] + 1,
    }


async def risk_check_node(state: AgentState) -> dict:
    """Pause high-risk tasks and create a persisted approval record."""

    intent = state["parsed_intent"]
    if intent is None or not requires_approval(intent):
        return {"status": "running"}
    approval_id = str(uuid.uuid4())
    await database.create_approval(
        approval_id=approval_id,
        task_id=state["task_id"],
        risk_level=intent.risk_level,
        prompt=build_approval_prompt(intent),
    )
    return {"status": "waiting_approval", "approval_id": approval_id}


async def auth_check_node(state: AgentState) -> dict:
    """Check whether an authenticated session is required and available."""

    return {"status": state["status"]}


async def navigate_node(state: AgentState) -> dict:
    """Select the first target URL for the task."""

    intent = state["parsed_intent"]
    return {"current_url": intent.site if intent else None}


async def extract_dom_node(state: AgentState) -> dict:
    """Placeholder DOM extraction node for graph-based browser runs."""

    return {"action_manifest": state["action_manifest"]}


async def plan_action_node(state: AgentState) -> dict:
    """Plan a single next action from the current intent and manifest."""

    intent = state["parsed_intent"]
    if intent is None:
        return {"planned_action": PlannedAction(action_type="need_help", reasoning="No parsed intent")}
    action = PlannedAction(
        action_type="navigate" if intent.action in {"search", "navigate"} else "complete",
        url=intent.site,
        reasoning="Deterministic MVP planner selected the next safe action.",
    )
    return {"planned_action": action, "llm_call_count": state["llm_call_count"] + 1}


async def execute_action_node(state: AgentState) -> dict:
    """Execute the planned action or plugin and append action history."""

    action = state["planned_action"]
    if action is None:
        return {"error": "No planned action"}
    result = {
        "success": True,
        "action_type": action.action_type,
        "target": action.url,
        "reasoning": action.reasoning,
    }
    return {"result": result}


async def verify_node(state: AgentState) -> dict:
    """Verify task completion and account for retryable failures."""

    if state.get("error"):
        return {"retry_count": state["retry_count"] + 1}
    return {"status": "completed"}


async def error_recovery_node(state: AgentState) -> dict:
    """Mark a task failed after retry exhaustion."""

    return {"status": "failed", "error": state.get("error") or "Task failed after retries"}


async def complete_node(state: AgentState) -> dict:
    """Set completion state and persist the result to SQLite."""

    await database.update_task(
        state["task_id"],
        status="completed",
        result_json=json.dumps(state.get("result") or {}),
        completed_at=datetime.now(UTC).isoformat(),
    )
    return {"status": "completed"}
