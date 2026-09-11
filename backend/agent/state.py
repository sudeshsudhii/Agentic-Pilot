"""Typed state object used by the Pilot agent graph."""

from __future__ import annotations

from typing import TypedDict

from backend.llm.parser import ActionManifest, ActionResult, ParsedIntent, PlannedAction, TaskPlan


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
    navigation_succeeded: bool
    session_id: str | None
    task_plan: TaskPlan | None
    current_step_index: int
    retrieved_knowledge: list[dict] | None
    retrieved_memories: list[dict] | None
    retrieval_metadata: dict | None
    selected_model: str | None
    model_role: str | None
    routing_reason: str | None
    model_switch: bool
    extracted_data: dict | None
    final_answer: str | None
    last_action_status: str | None
    vision_called: bool
    vision_model: str | None
    vision_status: str | None
    step_progress: str | None
    blocked_reason: str | None
    recovery_options: list[str] | None


