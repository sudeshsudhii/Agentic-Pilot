"""Tests for execution checkpointing, latency optimizations, context reuse, and routing stickiness."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import shutil

from backend.agent.checkpoint import CheckpointManager, TaskCheckpoint
from backend.agent.nodes import parse_intent_node
from backend.agent.state import AgentState
from backend.llm.analyzer import CapabilityAnalyzer, capability_analyzer
from backend.llm.registry import ModelCapability, ModelMetadata, ModelRegistry, ModelRole
from backend.llm.router import ModelRouter, RoutingDecision
from backend.rag.context_builder import ContextBuilder, context_builder
from backend.rag.router import ContextRouter
from backend.vision.fallback import VisionAction, VisionFallback


@pytest.fixture
def temp_checkpoint_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_checkpoint_save_and_load(temp_checkpoint_dir):
    """Verify task execution checkpoint save, load, and clear."""
    manager = CheckpointManager(storage_dir=temp_checkpoint_dir)

    mock_state = {
        "task_id": "test-task-123",
        "input_text": "navigate to example.com and click login",
        "status": "running",
        "current_step_index": 2,
        "selected_model": "qwen2.5:7b",
        "model_role": "reasoning",
        "retrieved_knowledge": [{"chunk_id": "c1", "content": "login procedure"}],
        "retrieved_memories": [{"type": "episodic", "content": "clicked button"}],
        "llm_call_count": 3,
        "retry_count": 1,
    }

    # Save
    ckpt = manager.save_checkpoint("test-task-123", mock_state, current_node="plan_action")
    assert ckpt is not None
    assert ckpt.task_id == "test-task-123"
    assert ckpt.current_node == "plan_action"
    assert ckpt.current_step_index == 2

    # Load
    loaded = manager.load_checkpoint("test-task-123")
    assert loaded is not None
    assert loaded.task_id == "test-task-123"
    assert loaded.selected_model == "qwen2.5:7b"
    assert len(loaded.retrieved_knowledge) == 1

    # Can resume
    assert manager.can_resume("test-task-123") is True

    # Clear
    manager.clear_checkpoint("test-task-123")
    assert manager.load_checkpoint("test-task-123") is None
    assert manager.can_resume("test-task-123") is False


@pytest.mark.asyncio
async def test_parse_intent_checkpoint_resumption():
    """Verify parse_intent_node resumes from checkpoint without re-running LLM parsing."""
    mock_intent = MagicMock()
    mock_plan = MagicMock()

    resumed_state: AgentState = {
        "task_id": "resumed-task",
        "input_text": "open docs",
        "parsed_intent": mock_intent,
        "task_plan": mock_plan,
        "current_step_index": 2,
        "selected_model": "qwen3.5:2b",
        "model_role": "general",
        "action_manifest": None,
        "action_history": [],
        "retry_count": 0,
        "status": "running",
        "approval_id": None,
        "error": None,
        "result": None,
        "plugin_id": None,
        "llm_call_count": 2,
        "planned_action": None,
        "approved": False,
        "navigation_succeeded": True,
        "session_id": None,
        "retrieved_knowledge": [],
        "retrieved_memories": [],
        "retrieval_metadata": {},
        "routing_reason": "resumed",
        "model_switch": False,
    }

    # Calling parse_intent_node should immediately return existing parsed data without gateway call
    result = await parse_intent_node(resumed_state)
    assert result["parsed_intent"] == mock_intent
    assert result["task_plan"] == mock_plan
    assert result["current_step_index"] == 2


@pytest.mark.asyncio
async def test_context_router_single_fetch_reuse():
    """Verify ContextRouter reuses retrieved knowledge/memory without redundant database calls."""
    router = ContextRouter()

    existing_state: AgentState = {
        "task_id": "task-cache-test",
        "input_text": "perform procedure with documentation",
        "parsed_intent": None,
        "retrieved_knowledge": [{"document_id": "d1", "content": "cached doc"}],
        "retrieved_memories": [{"type": "episodic", "content": "cached memory"}],
        "retrieval_metadata": {"reused": True},
        "action_manifest": None,
        "action_history": [],
        "retry_count": 0,
        "status": "running",
        "approval_id": None,
        "error": None,
        "result": None,
        "plugin_id": None,
        "llm_call_count": 0,
        "planned_action": None,
        "approved": False,
        "navigation_succeeded": True,
        "session_id": None,
        "current_step_index": 1,
        "selected_model": None,
        "model_role": None,
        "routing_reason": None,
        "model_switch": False,
    }

    with patch.object(router.retriever, "retrieve", new_callable=AsyncMock) as mock_retrieve:
        res = await router.route_and_retrieve(existing_state)
        # Should not execute retrieve
        mock_retrieve.assert_not_called()
        assert len(res["retrieved_knowledge"]) == 1
        assert res["retrieved_knowledge"][0]["content"] == "cached doc"


def test_model_stickiness_preserves_active_model():
    """Verify model router sticks to active model when it satisfies subtask capabilities."""
    reg = ModelRegistry()
    reg.mark_installed(["qwen2.5:7b", "deepseek-r1:1.5b"])
    router = ModelRouter(registry=reg)

    # qwen2.5:7b has REASONING, PLANNING, GENERAL, TOOL_CALLING
    # Routing routine subtask with qwen2.5:7b active should NOT switch
    decision = router.route(
        task_type="general",
        input_text="navigate to page",
        active_model="qwen2.5:7b",
    )
    assert decision.selected_model == "qwen2.5:7b"
    assert decision.model_switch is False


def test_single_installed_model_bypass():
    """Verify single installed model triggers fast router bypass."""
    reg = ModelRegistry()
    # Unregister other models except one
    for m in reg.list_registered_models():
        if m.model_name != "qwen2.5:1.5b":
            reg.unregister_model(m.model_name)
    reg.mark_installed(["qwen2.5:1.5b"])

    router = ModelRouter(registry=reg)
    decision = router.route(task_type="coding", input_text="write python function")
    assert decision.selected_model == "qwen2.5:1.5b"
    assert "Single installed model bypass" in decision.reason


def test_context_builder_deduplication_and_budgeting():
    """Verify ContextBuilder deduplicates chunks and applies strict token budgets."""
    builder = ContextBuilder(token_budget=100)

    # Duplicate knowledge chunks
    chunks = [
        {"chunk_id": "c1", "content": "Repeated documentation line for testing."},
        {"chunk_id": "c2", "content": "Repeated documentation line for testing."},
        {"chunk_id": "c3", "content": "Distinct procedural rule for verification."},
    ]
    memories = [
        {"type": "episodic", "content": "Previously completed successfully."},
        {"type": "episodic", "content": "Previously completed successfully."},
    ]

    built = builder.build_context(
        retrieved_knowledge=chunks,
        retrieved_memories=memories,
        model_role="coder",
        token_budget=200,
    )

    assert built.estimated_tokens <= 200
    assert built.chunks_included <= 2  # Deduplicated from 3
    assert built.memories_included == 1  # Deduplicated from 2
    assert "CODING SPECIALIST CONTEXT" in built.knowledge_text


@pytest.mark.asyncio
async def test_vision_fallback_screenshot_caching():
    """Verify VisionFallback reuses cached inference when screenshot hash is identical."""
    vf = VisionFallback()
    dummy_screenshot = b"test_image_bytes_12345"

    with patch("backend.vision.fallback.OllamaGateway.complete_structured", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = VisionAction(
            action_type="click",
            x_percent=0.5,
            y_percent=0.5,
            reasoning="Click center",
        )

        # First call -> computes inference
        action1 = await vf.plan_action(dummy_screenshot, "find submit", "button")
        assert action1.action_type == "click"
        assert mock_complete.call_count == 1

        # Second call with identical screenshot & goal -> returns from cache
        action2 = await vf.plan_action(dummy_screenshot, "find submit", "button")
        assert action2.action_type == "click"
        assert mock_complete.call_count == 1  # Not incremented!
