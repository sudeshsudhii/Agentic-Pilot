"""Integration tests for RAG with LangGraph nodes, planning, and evidence provenance."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from backend.agent.nodes import execute_action_node, plan_action_node, retrieve_context_node
from backend.agent.state import AgentState
from backend.evidence.manager import EvidenceManager
from backend.llm.parser import ActionManifest, InteractiveElement, ParsedIntent, PlannedAction
from backend.rag.models import RetrievalResult, RetrievedChunk
from backend.rag.router import ContextRouter


@pytest.fixture
def mock_retrieval_chunks():
    return [
        RetrievedChunk(
            document_id="doc_payment_sop",
            chunk_id="c_pay_01",
            content="To complete transaction, click the Green 'Authorize Payment' button.",
            score=0.94,
            source="payment_sop.md",
            section="Authorization",
        )
    ]


async def test_retrieve_context_node_integration(mock_retrieval_chunks):
    """Verify retrieve_context_node executes through router and updates state."""
    with patch("backend.agent.nodes.context_router.retriever.retrieve") as mock_ret:
        mock_ret.return_value = RetrievalResult(
            query="how to complete payment according to SOP",
            chunks=mock_retrieval_chunks,
            total_found=1,
            latency_ms=8,
            strategy="vector",
            status="success",
        )

        state: AgentState = {
            "task_id": "T-INT-101",
            "input_text": "how to complete payment according to SOP",
            "parsed_intent": ParsedIntent(
                action="complete payment",
                target="payment",
                risk_level="medium",
                reasoning="sop workflow",
            ),
            "status": "running",
        }

        output = await retrieve_context_node(state)

        assert "retrieved_knowledge" in output
        assert len(output["retrieved_knowledge"]) == 1
        assert output["retrieved_knowledge"][0]["chunk_id"] == "c_pay_01"
        assert output["retrieval_metadata"]["rag_executed"] is True


async def test_plan_action_node_with_retrieved_knowledge(mock_retrieval_chunks):
    """Verify plan_action_node injects untrusted knowledge context into the planner prompt."""
    manifest = ActionManifest(
        url="https://pay.example.com/checkout",
        page_title="Checkout",
        page_state="interactive",
        interactive_elements=[
            InteractiveElement(
                element_id="btn_auth",
                tag="button",
                text_content="Authorize Payment",
                role="button",
                is_visible=True,
            )
        ],
    )

    state: AgentState = {
        "task_id": "T-INT-102",
        "input_text": "Authorize payment following SOP",
        "parsed_intent": ParsedIntent(
            action="authorize",
            target="payment",
            risk_level="medium",
            reasoning="testing rag planning",
        ),
        "action_manifest": manifest,
        "action_history": [],
        "retrieved_knowledge": [c.model_dump() for c in mock_retrieval_chunks],
        "retrieved_memories": [],
        "llm_call_count": 0,
        "status": "running",
    }

    with patch("backend.agent.nodes.OllamaGateway.complete_structured") as mock_llm:
        mock_llm.return_value = PlannedAction(action_type="click", element_id="btn_auth", reasoning="Followed SOP")
        result = await plan_action_node(state)

        assert "planned_action" in result
        assert result["planned_action"].action_type == "click"
        assert result["planned_action"].element_id == "btn_auth"

        # Verify LLM prompt contained the untrusted reference material banner
        call_prompt = mock_llm.call_args[0][1]
        assert "UNTRUSTED REFERENCE MATERIAL" in call_prompt
        assert "payment_sop.md" in call_prompt
        assert "Authorize Payment" in call_prompt


async def test_execute_action_attaches_knowledge_provenance(tmp_path: Path, mock_retrieval_chunks):
    """Verify execute_action attaches knowledge provenance references to ExecutionRecord."""
    manifest = ActionManifest(url="https://example.com", page_title="Home", page_state="interactive", interactive_elements=[])
    evidence_mgr = EvidenceManager(evidence_dir=tmp_path / "evidence")

    state: AgentState = {
        "task_id": "T-INT-103",
        "planned_action": PlannedAction(action_type="wait", value="1", reasoning="wait step"),
        "action_manifest": manifest,
        "action_history": [],
        "retrieved_knowledge": [c.model_dump() for c in mock_retrieval_chunks],
        "llm_call_count": 0,
        "status": "running",
    }

    mock_p = AsyncMock()
    mock_p.screenshot.return_value = b"\x89PNG\r\n\x1a\nfake_image_bytes"
    mock_p.url = "https://example.com"

    with patch("backend.agent.nodes.evidence_manager", evidence_mgr), \
         patch("backend.agent.nodes._get_task_page") as mock_page, \
         patch("backend.agent.nodes.database.add_event", new_callable=AsyncMock):
        mock_page.return_value = mock_p

        res = await execute_action_node(state)
        assert res.get("error") is None
        assert len(res["action_history"]) == 1

        records = evidence_mgr.load_task_records("T-INT-103")
        assert len(records) == 1
        exec_record = records[0]

        # Provenance check: record points to chunk reference without dumping raw body
        assert len(exec_record.knowledge_context) == 1
        ref = exec_record.knowledge_context[0]
        assert ref["document_id"] == "doc_payment_sop"
        assert ref["chunk_id"] == "c_pay_01"
        assert ref["score"] == 0.94


async def test_rag_disabled_graceful_degradation():
    """Verify system functions normally when RAG is disabled in configuration."""
    with patch("backend.rag.router.get_config") as mock_cfg:
        mock_cfg.return_value.enable_rag = False
        mock_cfg.return_value.enable_memory = False

        state: AgentState = {
            "task_id": "T-INT-104",
            "input_text": "navigate to home",
            "parsed_intent": ParsedIntent(
                action="navigate",
                site="home.org",
                risk_level="low",
                reasoning="nav",
            ),
            "status": "running",
        }

        output = await retrieve_context_node(state)
        assert output["retrieved_knowledge"] == []
        assert output["retrieval_metadata"]["rag_executed"] is False
