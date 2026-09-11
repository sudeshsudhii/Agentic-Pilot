"""Unit tests for capability-aware ModelRouter and 4-stage routing pipeline."""

from __future__ import annotations

from unittest.mock import patch
import pytest

from backend.config import get_config
from backend.llm.registry import ModelCapability, ModelMetadata, ModelRegistry
from backend.llm.router import ModelRouter, RoutingDecision


@pytest.fixture
def mock_registry():
    """Create a clean registry with predictable models and installation statuses."""
    reg = ModelRegistry()
    # Mark standard models as installed for deterministic testing
    reg.mark_installed([
        "qwen2.5:7b",
        "qwen2.5:1.5b",
        "deepseek-r1:1.5b",
        "moondream",
        "qwen2.5-coder:3b",
    ])
    return reg


def test_single_model_mode(mock_registry):
    """Verify single-model ablation mode returns base model without routing."""
    router = ModelRouter(registry=mock_registry)
    with patch("backend.llm.router.get_config") as mock_cfg:
        cfg = get_config().model_copy()
        cfg.enable_multi_model = False
        cfg.ollama_model = "qwen2.5:1.5b"
        cfg.ollama_vision_model = "moondream"
        mock_cfg.return_value = cfg

        # Coding task with multi-model disabled
        decision = router.route(task_type="coding", input_text="write python code")
        assert decision.selected_model == "qwen2.5:1.5b"
        assert decision.role == "general"

        # Vision task with multi-model disabled
        v_decision = router.route(has_image=True)
        assert v_decision.selected_model == "moondream"
        assert v_decision.role == "vision"


def test_dynamic_vision_routing(mock_registry):
    """Verify vision queries route to the vision-capable model."""
    router = ModelRouter(registry=mock_registry)
    decision = router.route(has_image=True, task_type="vision")
    assert decision.role == "vision"
    assert "moondream" in decision.selected_model or "vl" in decision.selected_model
    assert "vision" in decision.required_capabilities


def test_dynamic_coding_routing(mock_registry):
    """Verify coding keywords and tasks route to coding specialist."""
    router = ModelRouter(registry=mock_registry)
    decision = router.route(
        task_type="coding",
        input_text="write code to calculate primes and fix syntax errors",
    )
    assert decision.role == "coding"
    assert "coder" in decision.selected_model
    assert "coding" in decision.required_capabilities


def test_dynamic_recovery_routing(mock_registry):
    """Verify error recovery tasks route to recovery / high-reasoning specialist."""
    router = ModelRouter(registry=mock_registry)
    decision = router.route(
        task_type="recovery",
        is_recovery=True,
        input_text="retry navigation on timeout",
    )
    assert decision.role == "recovery"
    assert decision.selected_model == "qwen2.5:7b"
    assert "recovery" in decision.required_capabilities


def test_dynamic_intent_parsing_routing(mock_registry):
    """Verify intent parsing / low complexity routes to fast / lightweight model."""
    router = ModelRouter(registry=mock_registry)
    decision = router.route(
        task_type="intent_parsing",
        input_text="go to google.com",
        complexity="low",
    )
    assert decision.role == "lightweight"
    assert decision.selected_model in ("deepseek-r1:1.5b", "qwen2.5:1.5b")


def test_anti_thrashing_preserves_capable_active_model(mock_registry):
    """Verify router does not switch models if the active model already satisfies requirements."""
    router = ModelRouter(registry=mock_registry)

    # If qwen2.5:7b is already active, and task requires reasoning/planning
    decision = router.route(
        task_type="planning",
        complexity="high",
        active_model="qwen2.5:7b",
    )
    assert decision.selected_model == "qwen2.5:7b"
    assert decision.model_switch is False


def test_fallback_when_specialized_model_missing():
    """Verify router falls back to base model if specialized models are absent."""
    bare_registry = ModelRegistry()
    # Unregister both coding specialists
    bare_registry.unregister_model("qwen2.5-coder:3b")
    bare_registry.unregister_model("qwen2.5-coder:1.5b")

    router = ModelRouter(registry=bare_registry)
    decision = router.route(task_type="coding", input_text="write python code")
    assert decision.selected_model in ("qwen2.5:7b", "qwen2.5:1.5b")
    assert decision.fallback_used is True

