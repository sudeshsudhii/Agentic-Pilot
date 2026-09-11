"""Unit tests for ModelCapability, ModelMetadata, and ModelRegistry."""

from __future__ import annotations

import pytest

from backend.llm.registry import (
    DEFAULT_KNOWN_MODELS,
    ModelCapability,
    ModelMetadata,
    ModelRegistry,
)


def test_model_capability_enum():
    """Verify core capabilities are defined in the enum."""
    assert ModelCapability.REASONING.value == "reasoning"
    assert ModelCapability.PLANNING.value == "planning"
    assert ModelCapability.VISION.value == "vision"
    assert ModelCapability.CODING.value == "coding"
    assert ModelCapability.LIGHTWEIGHT.value == "lightweight"
    assert ModelCapability.RECOVERY.value == "recovery"
    assert ModelCapability.FALLBACK.value == "fallback"


def test_model_metadata_capabilities():
    """Verify ModelMetadata capability inspection methods."""
    meta = ModelMetadata(
        model_name="test-model:1b",
        capabilities=[ModelCapability.CODING, ModelCapability.FAST],
        priority=5,
    )
    assert meta.has_capability(ModelCapability.CODING) is True
    assert meta.has_capability("coding") is True
    assert meta.has_capability(ModelCapability.VISION) is False

    assert meta.has_all_capabilities([ModelCapability.CODING, ModelCapability.FAST]) is True
    assert meta.has_all_capabilities([ModelCapability.CODING, ModelCapability.VISION]) is False


def test_default_known_models_populated():
    """Verify default known local models are pre-configured."""
    registry = ModelRegistry()
    assert len(registry.list_registered_models()) >= 5

    coder = registry.get_model("qwen2.5-coder:3b")
    assert coder is not None
    assert coder.has_capability(ModelCapability.CODING) is True

    vision = registry.get_model("moondream")
    assert vision is not None
    assert vision.has_capability(ModelCapability.VISION) is True

    reasoning = registry.get_model("qwen2.5:7b")
    assert reasoning is not None
    assert reasoning.has_capability(ModelCapability.REASONING) is True


def test_dynamic_registration_and_unregistration():
    """Verify adding and removing models dynamically in registry."""
    registry = ModelRegistry()
    custom = ModelMetadata(
        model_name="custom-expert:latest",
        capabilities=[ModelCapability.CODING, ModelCapability.REASONING],
        priority=20,
    )
    registry.register_model(custom)

    retrieved = registry.get_model("custom-expert:latest")
    assert retrieved is not None
    assert retrieved.priority == 20
    assert retrieved.has_capability(ModelCapability.CODING) is True

    # Unregister
    removed = registry.unregister_model("custom-expert:latest")
    assert removed is True
    assert registry.get_model("custom-expert:latest") is None


def test_mark_installed():
    """Verify marking installed status reflects in registry."""
    registry = ModelRegistry()
    # Mark specific installed models
    registry.mark_installed(["qwen2.5:7b", "moondream"])

    m_7b = registry.get_model("qwen2.5:7b")
    assert m_7b is not None and m_7b.installed is True

    m_moon = registry.get_model("moondream")
    assert m_moon is not None and m_moon.installed is True

    installed_list = registry.list_installed_models()
    assert any(m.model_name == "qwen2.5:7b" for m in installed_list)
    assert any(m.model_name == "moondream" for m in installed_list)


def test_get_models_with_capability_priority():
    """Verify capability querying sorts models by priority descending."""
    registry = ModelRegistry()
    coding_models = registry.get_models_with_capability(ModelCapability.CODING)
    assert len(coding_models) > 0

    # Ensure priority is descending
    priorities = [m.priority for m in coding_models]
    assert priorities == sorted(priorities, reverse=True)


def test_get_preferred_model_fallback():
    """Verify get_preferred_model falls back to base model when none match."""
    registry = ModelRegistry()
    # Query an imaginary capability not present
    preferred = registry.get_preferred_model("nonexistent_cap", fallback="fallback-base:1b")
    assert preferred == "fallback-base:1b"
