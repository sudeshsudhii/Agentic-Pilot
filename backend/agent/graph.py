"""LangGraph construction for Pilot with environment-aware routing.

Extends the original browser-only graph with desktop environment support.
Browser tasks follow the original path unchanged.
Desktop tasks use the new desktop observation/execution path.
Mixed tasks can transition between environments within the same task state.
"""

from __future__ import annotations

from backend.agent import nodes
from backend.agent import desktop_nodes
from backend.agent.state import AgentState


def build_graph():
    """Build and compile the Pilot LangGraph state machine when available."""

    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return None

    graph = StateGraph(AgentState)

    # ─── Shared Nodes ───────────────────────────────────────────────
    graph.add_node("parse_intent", nodes.parse_intent_node)
    graph.add_node("risk_check", nodes.risk_check_node)
    graph.add_node("environment_resolver", desktop_nodes.environment_resolver_node)

    # ─── Browser-Specific Nodes (unchanged) ─────────────────────────
    graph.add_node("auth_check", nodes.auth_check_node)
    graph.add_node("navigate", nodes.navigate_node)
    graph.add_node("extract_dom", nodes.extract_dom_node)
    graph.add_node("retrieve_context", nodes.retrieve_context_node)
    graph.add_node("plan_action", nodes.plan_action_node)
    graph.add_node("execute_action", nodes.execute_action_node)
    graph.add_node("verify", nodes.verify_node)
    graph.add_node("error_recovery", nodes.error_recovery_node)
    graph.add_node("complete", nodes.complete_node)

    # ─── Desktop-Specific Nodes ─────────────────────────────────────
    graph.add_node("desktop_observe", desktop_nodes.desktop_observe_node)
    graph.add_node("desktop_plan_action", desktop_nodes.desktop_plan_action_node)
    graph.add_node("desktop_execute", desktop_nodes.desktop_execute_action_node)
    graph.add_node("desktop_verify", desktop_nodes.desktop_verify_node)
    graph.add_node("desktop_complete", desktop_nodes.desktop_complete_node)

    # ─── Edges: START → parse_intent ────────────────────────────────
    graph.add_edge(START, "parse_intent")

    # ─── parse_intent routing ───────────────────────────────────────
    def parse_router(state: AgentState) -> str:
        if state.get("status") == "failed":
            return "error_recovery"
        return "risk_check"

    graph.add_conditional_edges("parse_intent", parse_router)

    # ─── risk_check routing ─────────────────────────────────────────
    def risk_router(state: AgentState) -> str:
        if state.get("status") == "waiting_approval":
            return "complete"
        return "environment_resolver"

    graph.add_conditional_edges("risk_check", risk_router)

    # ─── environment_resolver routing (Environment & Step Aware) ───
    def environment_router(state: AgentState) -> str:
        env = state.get("current_environment", "browser")
        if env == "desktop":
            return "desktop_observe"
        elif env == "mixed":
            # Mixed tasks must be environment/step aware (Requirement 15)
            task_plan = state.get("task_plan")
            cur_idx = state.get("current_step_index", 1)
            step_text = ""
            if task_plan and task_plan.steps and 0 < cur_idx <= len(task_plan.steps):
                step_text = task_plan.steps[cur_idx - 1].description
            if not step_text:
                step_text = state.get("input_text", "")

            from backend.agent.environment import EnvironmentType, classify_environment
            step_env = classify_environment(step_text)
            if step_env == EnvironmentType.BROWSER:
                return "auth_check"
            return "desktop_observe"
        else:
            # "browser" or default — original browser path
            return "auth_check"

    graph.add_conditional_edges("environment_resolver", environment_router)

    # ─── Browser path (UNCHANGED from original) ─────────────────────
    graph.add_edge("auth_check", "navigate")

    def navigate_router(state: AgentState) -> str:
        if state.get("status") == "blocked":
            return "complete"
        if state.get("navigation_succeeded"):
            return "extract_dom"
        return "error_recovery"

    graph.add_conditional_edges("navigate", navigate_router)

    def extract_dom_router(state: AgentState) -> str:
        if state.get("status") == "blocked":
            return "complete"
        return "retrieve_context"

    graph.add_conditional_edges("extract_dom", extract_dom_router)
    graph.add_edge("retrieve_context", "plan_action")
    graph.add_edge("plan_action", "execute_action")
    graph.add_edge("execute_action", "verify")

    def verify_router(state: AgentState) -> str:
        status = state.get("status")
        if status == "running":
            return "extract_dom"
        elif status == "failed":
            return "error_recovery"
        return "complete"

    graph.add_conditional_edges("verify", verify_router)

    def recovery_router(state: AgentState) -> str:
        """Route recovery: retry loops back to observation; exhausted/blocked to completion.
        
        ENFORCES: Desktop failure -> desktop recovery -> desktop observe (Requirement 15).
        """
        is_desktop = state.get("current_environment") == "desktop"
        if state.get("status") in ("failed", "blocked"):
            return "desktop_complete" if is_desktop else "complete"

        # Recovery strategy says retry:
        if is_desktop:
            return "desktop_observe"
        return "extract_dom"

    graph.add_conditional_edges("error_recovery", recovery_router)
    graph.add_edge("complete", END)

    # ─── Desktop path ───────────────────────────────────────────────
    graph.add_edge("desktop_observe", "desktop_plan_action")
    graph.add_edge("desktop_plan_action", "desktop_execute")
    graph.add_edge("desktop_execute", "desktop_verify")

    def desktop_verify_router(state: AgentState) -> str:
        status = state.get("status")
        if status == "running":
            return "desktop_observe"  # Re-observe → re-plan → re-execute loop
        elif status == "failed":
            return "error_recovery"
        elif status == "blocked":
            return "desktop_complete"
        return "desktop_complete"  # completed

    graph.add_conditional_edges("desktop_verify", desktop_verify_router)
    graph.add_edge("desktop_complete", END)

    return graph.compile()
