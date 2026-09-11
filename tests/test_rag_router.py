"""Tests for ContextRouter query routing and selective knowledge retrieval."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import pytest

from backend.config import get_config
from backend.llm.parser import ParsedIntent, TaskPlan, TaskStep
from backend.rag.models import RetrievalResult, RetrievedChunk
from backend.rag.router import ContextRouter


def test_should_retrieve_knowledge_decisions():
    """Verify router skips simple actions and triggers on procedural documentation queries."""
    router = ContextRouter()

    # 1. Simple navigation -> Skip RAG
    nav_state = {
        "input_text": "navigate to google.com",
        "parsed_intent": ParsedIntent(action="navigate", site="google.com", risk_level="low", reasoning="nav"),
    }
    assert router.should_retrieve_knowledge(nav_state) is False

    # 2. Procedural / SOP query -> Trigger RAG
    sop_state = {
        "input_text": "follow standard operating procedure for server deployment",
        "parsed_intent": ParsedIntent(action="deploy", target="server", risk_level="low", reasoning="sop"),
    }
    assert router.should_retrieve_knowledge(sop_state) is True

    # 3. Manual / Guide keyword -> Trigger RAG
    manual_state = {
        "input_text": "look up the api documentation guide for authentication",
        "parsed_intent": ParsedIntent(action="lookup", target="api", risk_level="low", reasoning="manual"),
    }
    assert router.should_retrieve_knowledge(manual_state) is True

    # 4. Multi-step task plan -> Trigger RAG
    plan = TaskPlan(
        task_summary="Execute complex deployment",
        total_steps=3,
        steps=[
            TaskStep(step_index=1, description="Step 1", action_type="navigate", expected_outcome="Done"),
            TaskStep(step_index=2, description="Step 2", action_type="click", expected_outcome="Done"),
        ],
    )
    plan_state = {
        "input_text": "deploy cluster",
        "parsed_intent": ParsedIntent(action="deploy", risk_level="low", reasoning="plan"),
        "task_plan": plan,
    }
    assert router.should_retrieve_knowledge(plan_state) is True


def test_rag_disabled_flag():
    """Verify router always skips knowledge retrieval when enable_rag is False."""
    router = ContextRouter()
    sop_state = {
        "input_text": "follow standard operating procedure for server deployment",
        "parsed_intent": ParsedIntent(action="deploy", target="server", risk_level="low", reasoning="sop"),
    }

    with patch("backend.rag.router.get_config") as mock_cfg:
        mock_cfg.return_value.enable_rag = False
        assert router.should_retrieve_knowledge(sop_state) is False


async def test_route_and_retrieve_execution():
    """Verify route_and_retrieve outputs serializable state with both knowledge and memory."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = RetrievalResult(
        query="test query",
        chunks=[
            RetrievedChunk(
                document_id="doc_1",
                chunk_id="c_1",
                content="Procedural instructions content.",
                score=0.95,
                source="sop.md",
            )
        ],
        total_found=1,
        latency_ms=12,
        strategy="vector",
        status="success",
    )

    router = ContextRouter(retriever=mock_retriever)
    state = {
        "task_id": "T-999",
        "input_text": "how to configure database according to manual",
        "parsed_intent": ParsedIntent(action="configure", target="database manual", risk_level="low", reasoning="test"),
    }

    result = await router.route_and_retrieve(state)

    assert "retrieved_knowledge" in result
    assert "retrieved_memories" in result
    assert "retrieval_metadata" in result

    assert len(result["retrieved_knowledge"]) == 1
    assert result["retrieved_knowledge"][0]["chunk_id"] == "c_1"
    assert result["retrieval_metadata"]["rag_executed"] is True
    assert result["retrieval_metadata"]["latency_ms"] == 12
