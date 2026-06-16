"""Typed state object used by the Pilot agent graph."""

from __future__ import annotations

from typing import TypedDict

from backend.llm.parser import ActionManifest, ActionResult, ParsedIntent, PlannedAction


class AgentState(TypedDict):
    """State passed between graph nodes during task execution."""

    task_id: str
    input_text: str
    parsed_intent: ParsedIntent | None
    current_url: str | None
    action_manifest: ActionManifest | None
    action_history: list[ActionResult]
    retry_count: int
    status: str
    approval_id: str | None
    error: str | None
    result: dict | None
    plugin_id: str | None
    llm_call_count: int
    planned_action: PlannedAction | None
    approved: bool
