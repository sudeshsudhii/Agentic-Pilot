"""LangGraph construction for Pilot with a simple fallback runner."""

from __future__ import annotations

from backend.agent import nodes
from backend.agent.state import AgentState


def build_graph():
    """Build and compile the Pilot LangGraph state machine when available."""

    try:
        from langgraph.graph import END, START, StateGraph
    except Exception:
        return None

    graph = StateGraph(AgentState)
    graph.add_node("parse_intent", nodes.parse_intent_node)
    graph.add_node("risk_check", nodes.risk_check_node)
    graph.add_node("auth_check", nodes.auth_check_node)
    graph.add_node("navigate", nodes.navigate_node)
    graph.add_node("extract_dom", nodes.extract_dom_node)
    graph.add_node("plan_action", nodes.plan_action_node)
    graph.add_node("execute_action", nodes.execute_action_node)
    graph.add_node("verify", nodes.verify_node)
    graph.add_node("error_recovery", nodes.error_recovery_node)
    graph.add_node("complete", nodes.complete_node)

    graph.add_edge(START, "parse_intent")
    
    def parse_router(state: AgentState) -> str:
        if state.get("status") == "failed":
            return "error_recovery"
        return "risk_check"
        
    graph.add_conditional_edges("parse_intent", parse_router)
    def risk_router(state: AgentState) -> str:
        if state.get("status") == "waiting_approval":
            return "complete"
        return "auth_check"

    graph.add_conditional_edges("risk_check", risk_router)
    graph.add_edge("auth_check", "navigate")
    graph.add_edge("navigate", "extract_dom")
    graph.add_edge("extract_dom", "plan_action")
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
    graph.add_edge("error_recovery", "complete")
    graph.add_edge("complete", END)
    return graph.compile()
