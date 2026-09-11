"""Regression tests for Pilot browser agent multi-step pipeline and vision guardrails.

Validates the 7 required test cases:
1. Opening Google only (action succeeds, overall task NOT completed if additional work requested).
2. Google search (search executed, task continues).
3. Multi-step navigation (multiple browser actions recorded in sequence).
4. Vision unavailable (explicit VISION_UNAVAILABLE error, never reports success).
5. Action succeeds but task is incomplete (task remains running/executing).
6. All task requirements satisfied (task becomes completed).
7. Action failure (retry or failed, never completed).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.agent.nodes import execute_action_node, plan_action_node, verify_node
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
from backend.verification.manager import verification_manager
from backend.vision.fallback import VisionFallback, VisionUnavailableError


@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path):
    """Provide an isolated test database for event logging."""
    await database.close()
    database.path = resolve_path(str(tmp_path / "test_pipeline.db"))
    await database.connect()
    # Create test task so foreign key constraint in task_events succeeds
    await database.create_task("test-task-123", "Open Google, search for SRM Kattankulathur, and extract 3 campus facts.")
    yield
    await database.close()


def make_test_state(**kwargs) -> dict:
    """Helper to build a valid AgentState dictionary with defaults."""
    default_state = {
        "task_id": "test-task-123",
        "input_text": "Open Google, search for SRM Kattankulathur, and extract 3 campus facts.",
        "parsed_intent": ParsedIntent(
            action="search",
            site="google.com",
            target="SRM Institute of Science and Technology Kattankulathur",
            risk_level="low",
            confidence=0.95,
            reasoning="Parsed user search intent",
        ),
        "current_url": "https://www.google.com/",
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
        "approved": True,
        "navigation_succeeded": True,
        "session_id": "session-123",
        "task_plan": TaskPlan(
            task_summary="Search Google for SRM and extract campus facts",
            total_steps=4,
            current_step_index=1,
            steps=[
                TaskStep(step_index=1, description="Open Google", target="https://www.google.com/", action_type="navigate", expected_outcome="Google home page loaded"),
                TaskStep(step_index=2, description="Search for SRM Institute Kattankulathur", target="searchbox", action_type="type_text", expected_outcome="Search submitted"),
                TaskStep(step_index=3, description="Open relevant result", target="result", action_type="click", expected_outcome="SRM webpage loaded"),
                TaskStep(step_index=4, description="Extract 3 campus details", target="content", action_type="extract", expected_outcome="Campus details extracted"),
            ],
        ),
        "current_step_index": 1,
        "retrieved_knowledge": [],
        "retrieved_memories": [],
        "retrieval_metadata": {},
        "selected_model": "qwen2.5:1.5b",
        "model_role": "action_planner",
        "routing_reason": "default",
        "model_switch": False,
        "extracted_data": {},
        "final_answer": None,
        "last_action_status": None,
        "vision_called": False,
        "vision_model": "qwen3-vl:2b",
        "vision_status": "Active",
        "step_progress": "1 / 4",
    }
    default_state.update(kwargs)
    return default_state


# ==============================================================================
# TEST 1: Opening Google only
# Expected: browser action succeeds
# Expected overall task: NOT completed if additional work was requested
# ==============================================================================
@pytest.mark.asyncio
async def test_opening_google_does_not_prematurely_complete_task():
    """Reaching Google home page must NOT complete a multi-step task requesting search/extraction."""
    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/"
    mock_page.title = AsyncMock(return_value="Google")
    mock_page.content = AsyncMock(return_value="<html><title>Google</title><body><input name='q'></body></html>")
    mock_page.evaluate = AsyncMock(return_value="Google")

    # Step 1: Navigating to Google succeeded
    state = make_test_state(
        current_url="https://www.google.com/",
        planned_action=PlannedAction(action_type="navigate", url="https://www.google.com/", reasoning="Opened Google"),
        action_history=[ActionResult(success=True, action_type="navigate", page_state_after="loaded", duration_ms=200)],
        current_step_index=1,
    )

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor.get_screenshot_with_dimensions", AsyncMock(return_value=(b"fake_img", 1280, 720))):
        new_state = await verify_node(state)

    # Action succeeded and advanced to step 2, but task status is running, NOT completed
    assert new_state.get("status") == "running", "Task must remain running after landing on Google"
    assert new_state.get("current_step_index") == 2, "Task should advance from step 1 to step 2"
    assert new_state.get("last_action_status") == "succeeded"
    assert new_state.get("result") is None, "Result should not be set yet"

    # Also directly verify verify_task_completion rejects Google landing when search was requested
    verif_res = await verification_manager.verify_task_completion(
        page=mock_page,
        intent_action="search",
        intent_site="google.com",
        current_url="https://www.google.com/",
        navigation_succeeded=True,
        input_text=state["input_text"],
        task_plan=state["task_plan"],
        extracted_data={},
        final_answer=None,
    )
    assert verif_res.verified is False, "Verification must reject premature completion on Google landing"
    assert verif_res.observed.get("premature_completion_prevented") is True


# ==============================================================================
# TEST 2: Google search
# Expected: search action executed
# Expected: task continues
# ==============================================================================
@pytest.mark.asyncio
async def test_google_search_action_executes_and_continues():
    """Typing search query and pressing Enter executes successfully and advances to next step."""
    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/search?q=SRM+Institute+of+Science+and+Technology+Kattankulathur"
    mock_page.title = AsyncMock(return_value="SRM Search Results")
    mock_page.content = AsyncMock(return_value="<html><title>SRM Search Results</title></html>")

    state = make_test_state(
        current_step_index=2,
        current_url="https://www.google.com/",
        planned_action=PlannedAction(action_type="type_text", text="SRM Institute Kattankulathur", press_enter=True, reasoning="Entered search query"),
        action_history=[ActionResult(success=True, action_type="type_text", page_state_after="results_loaded", duration_ms=300)],
    )

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor.get_screenshot_with_dimensions", AsyncMock(return_value=(b"fake_img", 1280, 720))):
        new_state = await verify_node(state)

    # Search executed, step advanced from 2 to 3, task remains running
    assert new_state.get("status") == "running"
    assert new_state.get("current_step_index") == 3
    assert state["task_plan"].steps[1].status == "completed"


# ==============================================================================
# TEST 3: Multi-step navigation
# Expected: multiple browser actions
# ==============================================================================
@pytest.mark.asyncio
async def test_multistep_navigation_sequence():
    """Multi-step navigation executes actions sequentially and records all actions."""
    mock_page = AsyncMock()
    mock_page.url = "https://www.srmist.edu.in/"
    mock_page.title = AsyncMock(return_value="SRM Institute")

    # Simulate advancing step by step
    state = make_test_state(current_step_index=1)

    # Step 1 -> Step 2
    state["action_history"].append(ActionResult(success=True, action_type="navigate", page_state_after="ready", duration_ms=100))
    state["planned_action"] = PlannedAction(action_type="navigate", url="https://google.com", reasoning="Navigated")
    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor.get_screenshot_with_dimensions", AsyncMock(return_value=(b"img", 1280, 720))):
        s1 = await verify_node(state)
    assert s1["current_step_index"] == 2

    # Step 2 -> Step 3
    state["current_step_index"] = 2
    state["action_history"].append(ActionResult(success=True, action_type="type_text", page_state_after="ready", duration_ms=150))
    state["planned_action"] = PlannedAction(action_type="type_text", text="SRM query", reasoning="Typed query")
    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor.get_screenshot_with_dimensions", AsyncMock(return_value=(b"img", 1280, 720))):
        s2 = await verify_node(state)
    assert s2["current_step_index"] == 3

    # Step 3 -> Step 4
    state["current_step_index"] = 3
    state["action_history"].append(ActionResult(success=True, action_type="click", page_state_after="ready", duration_ms=200))
    state["planned_action"] = PlannedAction(action_type="click", element_id="srm_link", reasoning="Clicked result")
    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor.get_screenshot_with_dimensions", AsyncMock(return_value=(b"img", 1280, 720))):
        s3 = await verify_node(state)
    assert s3["current_step_index"] == 4

    assert len(state["action_history"]) == 3
    assert [a.action_type for a in state["action_history"]] == ["navigate", "type_text", "click"]


# ==============================================================================
# TEST 4: Vision unavailable
# Expected: explicit failure (VISION_UNAVAILABLE)
# Expected: never report success
# ==============================================================================
@pytest.mark.asyncio
async def test_vision_unavailable_fails_explicitly():
    """When a model does not support multimodal vision and no vision model is available, fail with VISION_UNAVAILABLE."""
    fallback = VisionFallback()

    # When Ollama returns no vision models or only text models
    with patch("backend.llm.gateway.OllamaGateway.list_model_names", AsyncMock(return_value=["qwen2.5:1.5b"])):
        avail, model = await fallback.check_vision_availability()
        assert avail is False
        assert model is None

        # Attempting fallback must raise VisionUnavailableError
        with pytest.raises(VisionUnavailableError) as exc_info:
            await fallback.plan_action(b"fake_screenshot", "click", "search box")
        assert "VISION_UNAVAILABLE" in str(exc_info.value)

    # State machine must transition to failed with VISION_UNAVAILABLE
    state = make_test_state(error="VISION_UNAVAILABLE")
    res = await verify_node(state)
    assert res.get("status") == "failed"
    assert res.get("error") == "VISION_UNAVAILABLE"
    assert res.get("vision_status") == "Unavailable"
    assert "success" not in res or res["success"] is not True


# ==============================================================================
# TEST 5: Action succeeds but task is incomplete
# Expected: task remains EXECUTING (running)
# ==============================================================================
@pytest.mark.asyncio
async def test_action_succeeds_but_task_remains_executing():
    """A successful browser action on step 2 of a 4-step task leaves the task in 'running' state."""
    mock_page = AsyncMock()
    mock_page.url = "https://www.google.com/search?q=SRM"

    state = make_test_state(
        current_step_index=2,
        planned_action=PlannedAction(action_type="click", element_id="search_button", reasoning="Clicked button"),
        action_history=[ActionResult(success=True, action_type="click", page_state_after="ready", duration_ms=100)],
    )

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor.get_screenshot_with_dimensions", AsyncMock(return_value=(b"img", 1280, 720))):
        result_state = await verify_node(state)

    assert result_state.get("status") == "running", "Task must remain running when steps remain"
    assert result_state.get("last_action_status") == "succeeded"
    assert result_state.get("current_step_index") == 3


# ==============================================================================
# TEST 6: All task requirements satisfied
# Expected: task becomes COMPLETED
# ==============================================================================
@pytest.mark.asyncio
async def test_all_task_requirements_satisfied_completes_task():
    """When all planned steps are done and extracted information is present, task becomes completed."""
    mock_page = AsyncMock()
    mock_page.url = "https://www.srmist.edu.in/"
    mock_page.title = AsyncMock(return_value="SRM Kattankulathur Campus")
    mock_page.content = AsyncMock(return_value="<html><title>SRM Kattankulathur Campus</title><body>Campus area 250+ acres, 50,000+ students, 3,200 faculty.</body></html>")
    mock_page.evaluate = AsyncMock(return_value="SRM Kattankulathur Campus")

    extracted_campus_data = {
        "SRM Kattankulathur Campus": {
            "page_title": "SRM Kattankulathur Campus",
            "extracted_items": [
                "1. Sprawling 250+ acre campus in Kattankulathur, Chennai.",
                "2. Over 50,000 enrolled students and 3,200+ faculty members across diverse disciplines.",
                "3. Advanced infrastructure including hi-tech research labs, central library, and 43-block hostel facilities.",
            ],
            "content_snippet": "SRM Kattankulathur Campus details and key facts.",
        }
    }
    final_answer = "SRM Kattankulathur campus details:\n- 250+ acre campus\n- 50,000+ students\n- State-of-the-art research facilities"

    # Step 4 out of 4 is finished
    state = make_test_state(
        current_step_index=4,
        current_url="https://www.srmist.edu.in/",
        planned_action=PlannedAction(action_type="complete", reasoning=final_answer),
        action_history=[ActionResult(success=True, action_type="extract", page_state_after="ready", duration_ms=100)],
        extracted_data=extracted_campus_data,
        final_answer=final_answer,
    )
    # Mark all steps completed
    for step in state["task_plan"].steps:
        step.status = "completed"

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor.get_screenshot_with_dimensions", AsyncMock(return_value=(b"img", 1280, 720))):
        result_state = await verify_node(state)

    assert result_state.get("status") == "completed", "Task must become completed when all requirements satisfied"
    assert result_state.get("result") is not None
    assert result_state["result"]["success"] is True
    assert result_state["result"]["answer"] == final_answer
    assert "SRM Kattankulathur Campus" in result_state["result"]["extracted_data"]


# ==============================================================================
# TEST 7: Action failure
# Expected: retry or FAILED
# Expected: never COMPLETED
# ==============================================================================
@pytest.mark.asyncio
async def test_action_failure_never_marks_completed():
    """An execution error or verification failure must increment retry or fail, never complete."""
    # Sub-case A: First failure triggers retry
    state_retry = make_test_state(
        retry_count=0,
        error="Target element not found: search_input",
    )
    res_retry = await verify_node(state_retry)
    assert res_retry.get("status") == "running"
    assert res_retry.get("retry_count") == 1
    assert res_retry.get("result") is None

    # Sub-case B: Max retries exceeded triggers failed
    state_failed = make_test_state(
        retry_count=3,
        error="Target element not found: search_input",
    )
    res_failed = await verify_node(state_failed)
    assert res_failed.get("status") == "failed"
    assert "Max retries exceeded" in res_failed.get("error", "")
    assert res_failed.get("result") is None
