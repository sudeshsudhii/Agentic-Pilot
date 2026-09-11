"""Tests for shared RAG subsystem and role-adapted context formatting across models."""

from __future__ import annotations

import pytest

from backend.rag.models import RetrievedChunk
from backend.rag.router import ContextRouter


@pytest.fixture
def sample_chunks():
    return [
        RetrievedChunk(
            chunk_id="chunk_api_1",
            document_id="doc_api",
            content="def authenticate_user(token: str) -> bool: Validates user session token.",
            score=0.92,
            source="api_manual.md",
        ),
        RetrievedChunk(
            chunk_id="chunk_ui_1",
            document_id="doc_ui",
            content="Navigation header is fixed at top with z-index 1000. Search bar is centered.",
            score=0.88,
            source="ui_spec.md",
        ),
    ]


def test_build_planning_context_coding_role(sample_chunks):
    """Verify coding role produces specialized code/API context headers."""
    router = ContextRouter()
    k_dicts = [c.model_dump() for c in sample_chunks]
    knowledge_text, _ = router.build_planning_context(k_dicts, None, model_role="coding")

    assert "CODING SPECIALIST CONTEXT" in knowledge_text
    assert "api_manual.md" in knowledge_text
    assert "authenticate_user" in knowledge_text


def test_build_planning_context_vision_role(sample_chunks):
    """Verify vision role produces visual and UI specification headers."""
    router = ContextRouter()
    k_dicts = [c.model_dump() for c in sample_chunks]
    knowledge_text, _ = router.build_planning_context(k_dicts, None, model_role="vision")

    assert "VISION SPECIALIST CONTEXT" in knowledge_text
    assert "UI & VISUAL LAYOUT GUIDES" in knowledge_text
    assert "ui_spec.md" in knowledge_text


def test_build_planning_context_reasoning_role(sample_chunks):
    """Verify reasoning and recovery roles produce procedural invariant headers."""
    router = ContextRouter()
    k_dicts = [c.model_dump() for c in sample_chunks]
    knowledge_text, _ = router.build_planning_context(k_dicts, None, model_role="reasoning")

    assert "REASONING/RECOVERY CONTEXT" in knowledge_text
    assert "VERIFIED PROCEDURAL INVARIANTS" in knowledge_text


def test_build_planning_context_lightweight_role(sample_chunks):
    """Verify lightweight role produces compact representation."""
    router = ContextRouter()
    k_dicts = [c.model_dump() for c in sample_chunks]
    knowledge_text, _ = router.build_planning_context(k_dicts, None, model_role="lightweight")

    assert "[Compact Knowledge]" in knowledge_text
    # Should be concise, not full verbose boundaries
    assert len(knowledge_text) < 500


def test_build_planning_context_general_role(sample_chunks):
    """Verify default general role preserves standard untrusted knowledge formatting."""
    router = ContextRouter()
    k_dicts = [c.model_dump() for c in sample_chunks]
    knowledge_text, _ = router.build_planning_context(k_dicts, None, model_role="general")

    assert "UNTRUSTED REFERENCE MATERIAL" in knowledge_text
    assert "CODING SPECIALIST" not in knowledge_text



def test_security_boundaries_preserved_across_all_roles(sample_chunks):
    """Verify untrusted source citations exist across all role presentations."""
    router = ContextRouter()
    k_dicts = [c.model_dump() for c in sample_chunks]

    for role in ("coding", "vision", "reasoning", "general"):
        k_text, _ = router.build_planning_context(k_dicts, None, model_role=role)
        assert "api_manual.md" in k_text
        assert "ui_spec.md" in k_text
