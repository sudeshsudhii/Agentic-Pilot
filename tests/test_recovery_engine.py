"""Targeted regression tests for error recovery engine, checkpoint serialization, and browser lifecycle."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agent.checkpoint import checkpoint_manager
from backend.agent.state import AgentState
from backend.recovery.engine import RecoveryEngine, recovery_engine


def test_diagnose_with_none_error():
    """Verify diagnose handles None error without raising TypeError: 'NoneType' object is not subscriptable."""
    engine = RecoveryEngine()
    state: AgentState = {
        "task_id": "test-task",
        "input_text": "test task",
        "parsed_intent": None,
        "current_url": None,
        "action_manifest": None,
        "action_history": [],
        "retry_count": 0,
        "status": "failed",
        "approval_id": None,
        "error": None,
        "result": None,
        "plugin_id": None,
        "llm_call_count": 0,
        "planned_action": None,
    }

    # Test unknown failure type which accesses error[:100]
    diagnosis_unknown = engine.diagnose("unknown", None, state)
    assert isinstance(diagnosis_unknown, str)
    assert "Unclassified failure" in diagnosis_unknown

    # Test other failure types with error=None
    for ft in ["transient", "element_not_found", "verification_failed", "navigation_failed", "vision_needed", "llm_failure"]:
        diag = engine.diagnose(ft, None, state)
        assert isinstance(diag, str)


@pytest.mark.asyncio
async def test_handle_failure_with_none_error_in_state():
    """Verify handle_failure gracefully handles state containing error=None."""
    engine = RecoveryEngine()
    state: AgentState = {
        "task_id": "test-task-none-err",
        "input_text": "open website",
        "parsed_intent": None,
        "current_url": None,
        "action_manifest": None,
        "action_history": [],
        "retry_count": 0,
        "status": "running",
        "approval_id": None,
        "error": None,
        "result": None,
        "plugin_id": None,
        "llm_call_count": 1,
        "planned_action": None,
    }

    result = await engine.handle_failure(state)
    assert result is not None
    assert result["retry_count"] == 1
    assert result["status"] == "running"
    assert result["error"] is None
    assert "recovery_strategy" in result


def test_checkpoint_with_none_session_id():
    """Verify checkpoint save does not fail validation when session_id in state is None."""
    state = {
        "task_id": "test-task-ckpt",
        "session_id": None,
        "input_text": "sample",
        "status": "running",
        "action_history": [],
        "retry_count": 0,
        "llm_call_count": 0,
    }

    ckpt = checkpoint_manager.save_checkpoint(
        task_id="test-task-ckpt",
        state=state,
        current_node="verify",
    )
    assert ckpt is not None
    assert ckpt.execution_id == ""
    assert ckpt.task_id == "test-task-ckpt"


@pytest.mark.asyncio
async def test_browser_context_single_logging():
    """Verify that multiple calls to _get_task_page only log BROWSER_LAUNCHED once."""
    from backend.agent.nodes import _get_task_page
    from backend.browser.pool import browser_pool
    from backend.db.database import database

    task_id = "test-task-single-log"
    state: AgentState = {
        "task_id": task_id,
        "session_id": None,
        "input_text": "test",
        "parsed_intent": None,
        "current_url": None,
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
    }

    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_page.url = "about:blank"
    mock_context.pages = [mock_page]

    events_added = []

    async def mock_add_event(tid, event_type, desc, data=None):
        events_added.append((tid, event_type, desc))

    with patch.object(browser_pool, "get_task_context", new=AsyncMock(return_value=mock_context)), \
         patch.object(database, "add_event", new=mock_add_event):

        # First call: context key is not in _task_contexts -> is_new is True
        browser_pool._task_contexts.pop(task_id, None)
        browser_pool._retained_contexts.pop(task_id, None)
        
        await _get_task_page(state)

        # Simulate context being registered in pool
        browser_pool._task_contexts[task_id] = mock_context

        # Second call: context key is already in _task_contexts -> is_new is False
        await _get_task_page(state)

        # Third call: another node accesses the page
        await _get_task_page(state)

        # Clean up pool dictionary
        browser_pool._task_contexts.pop(task_id, None)

    # BROWSER_LAUNCHED should have been added EXACTLY once
    launched_events = [e for e in events_added if e[1] == "BROWSER_LAUNCHED"]
    assert len(launched_events) == 1, f"Expected 1 BROWSER_LAUNCHED event, got {len(launched_events)}"
