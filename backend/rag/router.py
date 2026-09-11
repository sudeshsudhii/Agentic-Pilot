"""Context router for selective RAG and Episodic Memory retrieval."""

from __future__ import annotations

import logging
from typing import Any

from backend.agent.state import AgentState
from backend.config import get_config
from backend.memory.provider import memory_manager
from backend.rag.models import RetrievalResult, RetrievedChunk
from backend.rag.retriever import KnowledgeRetriever, knowledge_retriever
from backend.rag.security import format_untrusted_knowledge_context
from backend.telemetry.tracer import tracer

logger = logging.getLogger("pilot.rag.router")

# Keywords that indicate the task requires external knowledge / procedural documentation
RAG_TRIGGER_KEYWORDS = {
    "how to", "procedure", "sop", "manual", "guide", "docs", "documentation",
    "api", "spec", "protocol", "instructions", "policy", "rules", "steps to",
    "workflow", "standard operating", "setup", "configure", "install",
}


class ContextRouter:
    """Intelligently routes between static Knowledge RAG and past Episodic Memory.

    Implements query routing to avoid unnecessary retrieval overhead for simple
    browser actions, while activating knowledge retrieval for unfamiliar procedures.
    """

    def __init__(self, retriever: KnowledgeRetriever | None = None) -> None:
        self.retriever = retriever or knowledge_retriever

    def should_retrieve_knowledge(self, state: AgentState) -> bool:
        """Determine whether the current task warrants external knowledge retrieval."""
        config = get_config()
        if not config.enable_rag:
            return False

        input_text = state.get("input_text", "").lower()
        intent = state.get("parsed_intent")

        # 1. Check for explicit documentation or procedure keywords
        if any(keyword in input_text for keyword in RAG_TRIGGER_KEYWORDS):
            return True

        # 2. Check if complex multi-step task plan exists
        task_plan = state.get("task_plan")
        if task_plan and task_plan.total_steps > 1:
            return True

        # 3. If action is navigation or simple search without procedural keywords, skip RAG
        action = intent.action.lower() if intent else ""
        if action in {"navigate", "go", "visit", "browse"} and len(input_text.split()) <= 6:
            return False

        # Default: if knowledge store has documents, attempt retrieval for non-trivial tasks
        return len(input_text.split()) > 4

    async def route_and_retrieve(self, state: AgentState, force_refresh: bool = False) -> dict[str, Any]:
        """Perform selective knowledge retrieval and episodic memory lookup.

        Enforces single-fetch context reuse across steps of the same execution to avoid
        redundant ~600ms database/vector queries.
        """
        task_id = state.get("task_id", "unknown")

        # 0. Reuse existing context if already retrieved for this task (Section 16: Memory Performance)
        if not force_refresh and state.get("retrieved_knowledge") is not None and state.get("retrieved_memories") is not None:
            logger.debug("ROUTER context_reuse task_id=%s (skipping redundant retrieval)", task_id)
            return {
                "retrieved_knowledge": state.get("retrieved_knowledge", []),
                "retrieved_memories": state.get("retrieved_memories", []),
                "retrieval_metadata": state.get("retrieval_metadata", {"reused": True, "rag_executed": False}),
            }

        intent = state.get("parsed_intent")
        input_text = state.get("input_text", "")

        query = f"{intent.action} {intent.target or intent.content or ''}".strip() if intent else input_text
        if not query:
            query = input_text

        retrieved_knowledge: list[dict[str, Any]] = []
        retrieval_metadata: dict[str, Any] = {
            "query": query,
            "rag_executed": False,
            "cache_hit": False,
            "latency_ms": 0,
            "sources": [],
        }

        # 1. Selective Knowledge RAG Retrieval
        if self.should_retrieve_knowledge(state):
            logger.info("ROUTER activating_rag task_id=%s query=%s", task_id, query[:40])
            rag_result = await self.retriever.retrieve(query)
            retrieved_knowledge = [c.model_dump() for c in rag_result.chunks]
            retrieval_metadata.update({
                "rag_executed": True,
                "cache_hit": rag_result.cache_hit,
                "latency_ms": rag_result.latency_ms,
                "total_found": rag_result.total_found,
                "strategy": rag_result.strategy,
                "status": rag_result.status,
                "sources": [c.source for c in rag_result.chunks],
                "scores": [c.score for c in rag_result.chunks],
            })

            # Record telemetry
            tracer.record_trace(task_id, "rag", "retrieval", retrieval_metadata)
        else:
            logger.info("ROUTER skipping_rag task_id=%s reason=simple_task", task_id)

        # 2. Episodic Memory Retrieval
        retrieved_memories: list[dict[str, Any]] = []
        config = get_config()
        if config.enable_memory:
            try:
                memories = await memory_manager.retrieve_relevant(query, limit=3)
                strategies = await memory_manager.retrieve_strategies(query, limit=2)
                for m in memories:
                    retrieved_memories.append({"type": "episodic", "content": m.content, "task_id": m.task_id})
                for s in strategies:
                    retrieved_memories.append({"type": "strategy", "content": s.content, "task_id": s.task_id})
            except Exception as mem_err:
                logger.warning("ROUTER memory_lookup_failed task_id=%s error=%s", task_id, mem_err)

        return {
            "retrieved_knowledge": retrieved_knowledge,
            "retrieved_memories": retrieved_memories,
            "retrieval_metadata": retrieval_metadata,
        }

    def build_planning_context(
        self,
        retrieved_knowledge: list[dict[str, Any]] | None,
        retrieved_memories: list[dict[str, Any]] | None,
        model_role: str = "general",
    ) -> tuple[str, str]:
        """Build distinct knowledge and memory context strings for the planner.

        Delegates to unified ContextBuilder for token budgeting, deduplication,
        and role-specific layout.
        """
        from backend.rag.context_builder import context_builder
        built = context_builder.build_context(
            retrieved_knowledge=retrieved_knowledge,
            retrieved_memories=retrieved_memories,
            model_role=model_role,
        )
        return built.knowledge_text, built.memory_text


context_router = ContextRouter()
