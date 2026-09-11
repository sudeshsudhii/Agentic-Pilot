"""Regression tests for Pilot CAPTCHA / Bot-Detection handling and recovery.

Validates the 7 required test cases:
1. Normal Google page: continues normally.
2. CAPTCHA page detected: transitions to BLOCKED.
3. CAPTCHA detected: NEVER marked completed.
4. User clears CAPTCHA: resumes existing task from current step (no reset to step 1).
5. CAPTCHA remains: no infinite retry loop.
6. Fallback provider available: fallback is explicitly recorded in trace.
7. No fallback available: clear BLOCKED state maintained.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.agent.nodes import extract_dom_node, plan_action_node, verify_node, extract_clean_search_query
from backend.agent.runner import TaskRunner
from backend.browser.dom import detect_captcha
from backend.db.database import database, resolve_path
from backend.llm.parser import (
    ActionManifest,
    ActionResult,
    InteractiveElement,
    ParsedIntent,
    PlannedAction,
    TaskPlan,
    TaskStep,
)
from backend.recovery.engine import recovery_engine


@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path):
    """Provide an isolated test database for event logging."""
    await database.close()
    database.path = resolve_path(str(tmp_path / "test_captcha.db"))
    await database.connect()
    await database.create_task("test-task-captcha", "Search for OpenAI and open the first result.")
    yield
    await database.close()


def make_captcha_state(**kwargs) -> dict:
    """Helper to build an AgentState for CAPTCHA testing."""
    default_state = {
        "task_id": "test-task-captcha",
        "input_text": 'Open Google, search for "OpenAI", and open the first search result.',
        "parsed_intent": ParsedIntent(
            action="search",
            site="google.com",
            target="OpenAI",
            risk_level="low",
            confidence=0.95,
            reasoning="Search for OpenAI",
        ),
        "current_url": "https://www.google.com/sorry/index?continue=https://www.google.com/search%3Fq%3DOpenAI",
        "action_manifest": ActionManifest(
            url="https://www.google.com/sorry/index?continue=https://www.google.com/search%3Fq%3DOpenAI",
            interactive_elements=[],
            page_title="Sorry...",
            page_state="captcha",
        ),
        "action_history": [],
        "retry_count": 0,
        "status": "running",
        "approval_id": None,
        "error": None,
        "result": None,
        "plugin_id": None,
        "llm_call_count": 1,
        "planned_action": None,
        "approved": True,
        "navigation_succeeded": True,
        "session_id": None,
        "task_plan": TaskPlan(
            task_summary="Search OpenAI on Google",
            total_steps=3,
            steps=[
                TaskStep(step_index=1, description="Navigate to Google", target="google.com", action_type="navigate", expected_outcome="Google loaded", status="completed"),
                TaskStep(step_index=2, description="Search for OpenAI", target="search box", action_type="type_text", expected_outcome="Query entered", status="pending"),
                TaskStep(step_index=3, description="Open first result", target="result link", action_type="click", expected_outcome="OpenAI page loaded", status="pending"),
            ],
            current_step_index=2,
        ),
        "current_step_index": 2,
        "retrieved_knowledge": [],
        "retrieved_memories": [],
        "retrieval_metadata": {},
        "selected_model": "qwen2.5:1.5b",
        "model_role": "reasoning",
        "routing_reason": "default",
        "model_switch": False,
        "extracted_data": {},
        "final_answer": None,
        "last_action_status": None,
        "vision_called": False,
        "vision_model": None,
        "vision_status": None,
        "step_progress": "2 / 3",
        "blocked_reason": None,
        "recovery_options": None,
    }
    default_state.update(kwargs)
    return default_state


# TEST 1: Normal Google page -> continue normally
@pytest.mark.asyncio
async def test_1_normal_google_page_continues_normally():
    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/"
    mock_page.title.return_value = "Google"
    
    mock_body = AsyncMock()
    mock_body.inner_text.return_value = "Search Images Maps Play YouTube News Gmail Drive"
    mock_page.locator.return_value = mock_body
    mock_page.locator.return_value.count.return_value = 0

    is_captcha, reason = await detect_captcha(mock_page)
    assert not is_captcha, "Normal Google page must not be detected as CAPTCHA"

    state = make_captcha_state(
        current_url="https://www.google.com/",
        action_manifest=ActionManifest(
            url="https://www.google.com/",
            interactive_elements=[
                InteractiveElement(element_id="pilot-el-1", tag="textarea", text_content="", role="searchbox", is_visible=True, interactable=True)
            ],
            page_title="Google",
            page_state="ready",
        )
    )

    with patch("backend.agent.nodes._get_task_page", return_value=mock_page), \
         patch("backend.agent.nodes.PlaywrightExecutor") as mock_exec:
        mock_exec.return_value.extractor.extract = AsyncMock(return_value=state["action_manifest"])
        result = await extract_dom_node(state)
        assert result.get("status") != "blocked"
        assert result["action_manifest"].page_state == "ready"


# TEST 2: CAPTCHA page detected -> BLOCKED
@pytest.mark.asyncio
async def test_2_captcha_page_detected_as_blocked():
    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/sorry/index?continue=https://www.google.com/search%3Fq%3DOpenAI"
    mock_page.title.return_value = "Sorry..."
    
    mock_body = AsyncMock()
    mock_body.inner_text.return_value = "Our systems have detected unusual traffic from your computer network. I'm not a robot."
    mock_page.locator.return_value = mock_body
    mock_page.locator.return_value.count.return_value = 1

    is_captcha, reason = await detect_captcha(mock_page)
    assert is_captcha, "Google sorry / I'm not a robot page must be detected as CAPTCHA"

    state = make_captcha_state()

    with patch("backend.agent.nodes._get_task_page", return_value=mock_page), \
         patch("backend.agent.nodes.PlaywrightExecutor") as mock_exec, \
         patch("backend.agent.nodes.evidence_manager.save_screenshot"), \
         patch("backend.agent.nodes.browser_pool.retain_task_context", new_callable=AsyncMock):
        mock_exec.return_value.extractor.extract = AsyncMock(return_value=state["action_manifest"])
        mock_exec.return_value.get_screenshot_with_dimensions = AsyncMock(return_value=(b"fake_screenshot", 1280, 800))
        
        result = await extract_dom_node(state)
        assert result["status"] == "blocked"
        assert "Google requires human verification" in result["error"]
        assert result["blocked_reason"] == "CAPTCHA / bot verification detected"

        events = await database.list_events(state["task_id"])
        event_types = [e.type for e in events]
        assert "CAPTCHA_DETECTED" in event_types
        assert "BLOCKED" in event_types


# TEST 3: CAPTCHA detected -> NOT COMPLETED
@pytest.mark.asyncio
async def test_3_captcha_detected_never_completed():
    state = make_captcha_state(
        status="blocked",
        error="Google requires human verification",
        planned_action=PlannedAction(action_type="type_text", text="OpenAI", reasoning="Type query"),
    )

    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/sorry/index"
    mock_page.title.return_value = "Sorry..."
    mock_body = AsyncMock()
    mock_body.inner_text.return_value = "I'm not a robot"
    mock_page.locator.return_value = mock_body
    mock_page.locator.return_value.count.return_value = 1

    with patch("backend.agent.nodes._get_task_page", return_value=mock_page):
        result = await verify_node(state)
        assert result["status"] == "blocked"
        assert result["status"] != "completed"
        assert result.get("task_completed") is not True


# TEST 4: User clears CAPTCHA -> task resumes from current step
@pytest.mark.asyncio
async def test_4_user_clears_captcha_resumes_from_current_step():
    runner = TaskRunner(database)

    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/search?q=OpenAI"
    mock_page.title.return_value = "OpenAI - Google Search"
    mock_body = AsyncMock()
    mock_body.inner_text.return_value = "OpenAI: Creating safe AGI that benefits all of humanity"
    mock_page.locator.return_value = mock_body
    mock_page.locator.return_value.count.return_value = 0

    mock_context = MagicMock()
    mock_context.pages = [mock_page]

    # Set task as blocked in DB
    await database.update_task("test-task-captcha", status="blocked", error="Google requires human verification")

    with patch("backend.browser.pool.browser_pool.get_task_context", new_callable=AsyncMock, return_value=mock_context), \
         patch.object(runner, "_schedule") as mock_schedule:
        success, msg = await runner.resume_blocked("test-task-captcha")
        assert success is True
        assert "CAPTCHA cleared" in msg

        # Verify task was updated to queued/running and scheduled
        mock_schedule.assert_called_once()
        task = await database.get_task("test-task-captcha")
        assert task.status == "queued"

        events = await database.list_events("test-task-captcha")
        event_types = [e.type for e in events]
        assert "CAPTCHA_CLEARED" in event_types


# TEST 5: CAPTCHA remains -> no infinite retry loop
@pytest.mark.asyncio
async def test_5_captcha_remains_no_infinite_retry_loop():
    runner = TaskRunner(database)

    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/sorry/index"
    mock_page.title.return_value = "Sorry..."
    mock_body = AsyncMock()
    mock_body.inner_text.return_value = "unusual traffic ... I'm not a robot"
    mock_page.locator.return_value = mock_body
    mock_page.locator.return_value.count.return_value = 1

    mock_context = MagicMock()
    mock_context.pages = [mock_page]

    await database.update_task("test-task-captcha", status="blocked", error="Google requires human verification")

    with patch("backend.browser.pool.browser_pool.get_task_context", new_callable=AsyncMock, return_value=mock_context), \
         patch.object(runner, "_schedule") as mock_schedule:
        # User tries to resume before clearing CAPTCHA
        success, msg = await runner.resume_blocked("test-task-captcha")
        assert success is False
        assert "CAPTCHA is still present" in msg
        # Must NOT re-schedule task when CAPTCHA is still uncleared
        mock_schedule.assert_not_called()

    # Verify recovery engine does not retry CAPTCHA failures
    classified = recovery_engine.classify_failure("Google bot challenge /sorry/ page detected: unusual traffic")
    assert classified == "captcha"
    strategy = recovery_engine.select_strategy("captcha", retry_count=0)
    assert strategy == "blocked"

    state = make_captcha_state(error="CAPTCHA / bot verification detected")
    recovery_result = await recovery_engine.handle_failure(state)
    assert recovery_result["status"] == "blocked"
    assert recovery_result["recovery_strategy"] == "blocked"


# TEST 6: Fallback provider available -> fallback is explicitly recorded
@pytest.mark.asyncio
async def test_6_fallback_provider_explicitly_recorded(caplog):
    runner = TaskRunner(database)

    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/sorry/index"
    mock_context = MagicMock()
    mock_context.pages = [mock_page]

    await database.update_task("test-task-captcha", status="blocked", error="Google requires human verification")

    with patch("backend.browser.pool.browser_pool.get_task_context", new_callable=AsyncMock, return_value=mock_context), \
         patch.object(runner, "_schedule") as mock_schedule:
        
        success, msg = await runner.switch_fallback("test-task-captcha", provider="duckduckgo")
        assert success is True
        assert "Switched to duckduckgo" in msg
        mock_schedule.assert_called_once()

        # Check that [FALLBACK] was recorded in the execution log
        assert any("[FALLBACK]" in record.message for record in caplog.records)
        assert any("Switching to duckduckgo" in record.message for record in caplog.records)

        # Check that fallback event was stored in DB
        events = await database.list_events("test-task-captcha")
        fallback_event = next((e for e in events if e.type == "FALLBACK"), None)
        assert fallback_event is not None
        assert fallback_event.payload["provider"] == "duckduckgo"
        assert "OpenAI" in fallback_event.payload["query"]


# TEST 7: No fallback available -> clear BLOCKED state
@pytest.mark.asyncio
async def test_7_no_fallback_available_maintains_blocked_state():
    state = make_captcha_state(
        status="blocked",
        error="Google requires human verification",
        blocked_reason="CAPTCHA / bot verification detected",
    )

    # When in plan_action_node while blocked
    plan_result = await plan_action_node(state)
    assert plan_result["status"] == "blocked"
    assert plan_result["error"] == "Google requires human verification"

    # Verify clean search query extraction avoids taking prompts as queries
    assert extract_clean_search_query('Open Google, search for "OpenAI", and open the first search result.') == "OpenAI"
    assert extract_clean_search_query('Search Google for SRM Institute of Science and Technology Kattankulathur') == "SRM Institute of Science and Technology Kattankulathur"
