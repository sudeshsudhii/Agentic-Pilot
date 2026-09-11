"""Tests for RAG and episodic memory context construction."""

from __future__ import annotations

import pytest

from backend.rag.models import RetrievedChunk
from backend.rag.router import ContextRouter
from backend.rag.security import UNTRUSTED_KNOWLEDGE_BANNER


def test_build_planning_context_separation():
    """Verify context builder cleanly separates domain knowledge from episodic memory."""
    router = ContextRouter()

    knowledge_chunks = [
        RetrievedChunk(
            document_id="doc_sop",
            chunk_id="c001",
            content="Click the Blue 'Deploy' button on the navigation toolbar.",
            score=0.91,
            source="deployment_sop.md",
            section="Deployment Execution",
        ).model_dump()
    ]

    memories = [
        {"type": "strategy", "content": "When Deploy button fails, scroll into view first.", "task_id": "T001"},
        {"type": "episodic", "content": "Previously completed deployment in 3 steps.", "task_id": "T002"},
    ]

    knowledge_ctx, memory_ctx = router.build_planning_context(knowledge_chunks, memories)

    # Verify Knowledge Context
    assert UNTRUSTED_KNOWLEDGE_BANNER in knowledge_ctx
    assert "deployment_sop.md" in knowledge_ctx
    assert "Click the Blue 'Deploy' button" in knowledge_ctx
    # Knowledge must NOT contain memory tags
    assert "[Past Strategy]" not in knowledge_ctx
    assert "[Past Experience]" not in knowledge_ctx

    # Verify Memory Context
    assert "PAST EXECUTION EXPERIENCE" in memory_ctx
    assert "[Past Strategy] When Deploy button fails" in memory_ctx
    assert "[Past Experience] Previously completed" in memory_ctx
    # Memory must NOT contain untrusted reference banners
    assert "UNTRUSTED REFERENCE MATERIAL" not in memory_ctx


def test_build_planning_context_none_handling():
    """Verify empty inputs return clean empty strings."""
    router = ContextRouter()
    k_ctx, m_ctx = router.build_planning_context(None, None)
    assert k_ctx == ""
    assert m_ctx == ""

    k_ctx, m_ctx = router.build_planning_context([], [])
    assert k_ctx == ""
    assert m_ctx == ""
