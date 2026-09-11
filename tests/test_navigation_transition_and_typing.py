"""Automated regression tests for Pilot browser navigation transition and text entry flow.

Validates the 10 required regression scenarios:
1. Successful navigation transitions to observation
2. Navigation is not repeated indefinitely
3. Input field is identified via DOM heuristics
4. type_text executes with press_enter=False
5. Screenshot is captured after typing
6. Exact text verification succeeds
7. Task completes only after verification
8. Task does not complete after navigation alone
9. Task does not complete after type_text alone
10. Vision invocation is separately verified from screenshot capture
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.agent.graph import build_graph
from backend.agent.nodes import (
    execute_action_node,
    extract_dom_node,
    identify_main_text_input,
    navigate_node,
    plan_action_node,
    verify_node,
)
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
from backend.verification.manager import extract_exact_text_to_type, verification_manager


@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path):
    """Provide an isolated test database for event logging."""
    await database.close()
    database.path = resolve_path(str(tmp_path / "test_nav_typing.db"))
    await database.connect()
    # Create test task so foreign key constraint in task_events succeeds
    await database.create_task(
        "test-task-cp",
        "Open https://cp.sudhii.in\nFind the main text input field.\nEnter exactly:\nhii i am agentic ai powered by local llm qwen\nDo NOT click Save.\nDo NOT submit.\nDo NOT modify anything else."
    )
    yield
    await database.close()


def make_test_state(**kwargs) -> dict:
    """Helper to build a valid AgentState dictionary with defaults."""
    default_state = {
        "task_id": "test-task-cp",
        "input_text": (
            "Open https://cp.sudhii.in\n"
            "Find the main text input field.\n"
            "Enter exactly:\n"
            "hii i am agentic ai powered by local llm qwen\n"
            "Do NOT click Save.\n"
            "Do NOT submit.\n"
            "Do NOT modify anything else."
        ),
        "parsed_intent": ParsedIntent(
            action="type_text",
            site="https://cp.sudhii.in",
            target="main text input",
            content="hii i am agentic ai powered by local llm qwen",
            risk_level="low",
            confidence=0.95,
            reasoning="Navigate to cp.sudhii.in and enter exact text",
        ),
        "current_url": "https://cp.sudhii.in/",
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
        "navigation_succeeded": False,
        "session_id": "session-cp",
        "task_plan": TaskPlan(
            task_summary="Enter text into main input on https://cp.sudhii.in",
            total_steps=1,
            current_step_index=1,
            steps=[
                TaskStep(
                    step_index=1,
                    description="Enter text into main input",
                    target="https://cp.sudhii.in",
                    action_type="type_text",
                    expected_outcome="Exact text entered into main text input",
                    status="pending",
                )
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
        "step_progress": "1 / 1",
    }
    default_state.update(kwargs)
    return default_state


def make_sample_manifest() -> ActionManifest:
    """Create sample ActionManifest modeled after cp.sudhii.in."""
    return ActionManifest(
        url="https://cp.sudhii.in/",
        page_title="Control Plane",
        page_state="ready",
        interactive_elements=[
            InteractiveElement(
                element_id="pilot-el-1",
                tag="a",
                role="link",
                text_content="Home",
                is_visible=True,
                interactable=True,
            ),
            InteractiveElement(
                element_id="pilot-el-2",
                tag="button",
                role="button",
                text_content="Save",
                is_visible=True,
                interactable=True,
            ),
            InteractiveElement(
                element_id="pilot-el-10",
                tag="textarea",
                role="textbox",
                placeholder="What do you want to save? Paste, type, or drop anything...",
                aria_label="Capture content",
                is_visible=True,
                interactable=True,
                bounding_box={"x": 100, "y": 200, "width": 800, "height": 300},
            ),
        ]
    )


# ==============================================================================
# TEST 1: Successful navigation transitions to observation
# ==============================================================================
@pytest.mark.asyncio
async def test_1_successful_navigation_transitions_to_observation():
    """Successful navigation marks action succeeded and emits ACTION_RESULT & PAGE_READY."""
    mock_page = AsyncMock()
    mock_page.url = "about:blank"
    mock_page.wait_for_load_state = AsyncMock()

    state = make_test_state()
    async def fake_navigate(p, u):
        mock_page.url = "https://cp.sudhii.in/"
        return ActionResult(success=True, action_type="navigate", page_state_after="ready", duration_ms=200)

    mock_executor = MagicMock()
    mock_executor.navigate = AsyncMock(side_effect=fake_navigate)
    mock_executor.get_screenshot_with_dimensions = AsyncMock(return_value=(b"fake_png", 1280, 800))

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor", return_value=mock_executor):
        result_state = await navigate_node(state)

    assert result_state["navigation_succeeded"] is True
    assert result_state["last_action_status"] == "succeeded"
    assert result_state["current_url"] == "https://cp.sudhii.in/"

    events = await database.list_events(state["task_id"])
    event_types = [e.type for e in events]
    assert "NAVIGATION_COMPLETED" in event_types
    assert "PAGE_READY" in event_types
    assert "ACTION_RESULT" in event_types

    action_res_event = next(e for e in events if e.type == "ACTION_RESULT")
    assert action_res_event.payload.get("action_type") == "navigate"
    assert action_res_event.payload.get("status") == "succeeded"


# ==============================================================================
# TEST 2: Navigation is not repeated indefinitely
# ==============================================================================
@pytest.mark.asyncio
async def test_2_navigation_is_not_repeated_indefinitely():
    """When already at target URL with navigation_succeeded, navigation is skipped."""
    mock_page = AsyncMock()
    mock_page.url = "https://cp.sudhii.in/"

    state = make_test_state(
        current_url="https://cp.sudhii.in/",
        navigation_succeeded=True,
    )
    mock_executor = MagicMock()
    mock_executor.navigate = AsyncMock()

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor", return_value=mock_executor):
        result_state = await navigate_node(state)

    # Must NOT call executor.navigate again
    mock_executor.navigate.assert_not_called()
    assert result_state["navigation_succeeded"] is True

    # Loop protection in plan_action_node
    manifest = make_sample_manifest()
    state["action_manifest"] = manifest
    with patch("backend.agent.nodes.OllamaGateway.complete_structured", AsyncMock(return_value=PlannedAction(action_type="navigate", url="https://cp.sudhii.in", reasoning="Navigate again"))):
        plan_res = await plan_action_node(state)
        # Action must NOT remain navigate to target
        assert plan_res["planned_action"].action_type != "navigate"


# ==============================================================================
# TEST 3: Input field is identified via DOM heuristics
# ==============================================================================
def test_3_input_field_is_identified():
    """DOM heuristics identify pilot-el-10 as the primary text entry field."""
    manifest = make_sample_manifest()
    target_input = identify_main_text_input(manifest)
    assert target_input is not None
    assert target_input.element_id == "pilot-el-10"
    assert target_input.tag == "textarea"


# ==============================================================================
# TEST 4: type_text executes with press_enter=False
# ==============================================================================
@pytest.mark.asyncio
async def test_4_type_text_executes():
    """type_text executes on target element and respects do not submit instruction."""
    mock_page = AsyncMock()
    mock_page.url = "https://cp.sudhii.in/"
    mock_page.evaluate = AsyncMock(return_value="hii i am agentic ai powered by local llm qwen")

    manifest = make_sample_manifest()
    action = PlannedAction(
        action_type="type_text",
        element_id="pilot-el-10",
        text="hii i am agentic ai powered by local llm qwen",
        press_enter=False,
        reasoning="Type into main text area",
    )
    state = make_test_state(action_manifest=manifest, planned_action=action)

    mock_executor = MagicMock()
    mock_executor.type_text = AsyncMock(return_value=ActionResult(
        success=True,
        action_type="type_text",
        element_id="pilot-el-10",
        page_state_after="ready",
        duration_ms=150,
    ))
    mock_executor.get_screenshot_with_dimensions = AsyncMock(return_value=(b"after_png", 1280, 800))

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor", return_value=mock_executor):
        exec_res = await execute_action_node(state)

    assert exec_res["last_action_status"] == "succeeded"
    # Ensure press_enter was False
    mock_executor.type_text.assert_called_once()
    _, call_kwargs = mock_executor.type_text.call_args
    assert call_kwargs.get("press_enter") is False

    events = await database.list_events(state["task_id"])
    type_event = next(e for e in events if e.type == "ACTION_RESULT" and e.payload.get("action_type") == "type_text")
    assert type_event.payload.get("status") == "succeeded"
    assert type_event.payload.get("success") is True


# ==============================================================================
# TEST 5: Screenshot is captured after typing
# ==============================================================================
@pytest.mark.asyncio
async def test_5_screenshot_is_captured_after_typing():
    """Post-action screenshot and DOM observation are captured after typing."""
    mock_page = AsyncMock()
    mock_page.url = "https://cp.sudhii.in/"
    mock_page.evaluate = AsyncMock(return_value="hii i am agentic ai powered by local llm qwen")

    manifest = make_sample_manifest()
    action = PlannedAction(
        action_type="type_text",
        element_id="pilot-el-10",
        text="hii i am agentic ai powered by local llm qwen",
        press_enter=False,
        reasoning="Type into main text area",
    )
    state = make_test_state(action_manifest=manifest, planned_action=action)

    mock_executor = MagicMock()
    mock_executor.type_text = AsyncMock(return_value=ActionResult(
        success=True, action_type="type_text", element_id="pilot-el-10", page_state_after="ready", duration_ms=150
    ))
    mock_executor.get_screenshot_with_dimensions = AsyncMock(return_value=(b"post_action_png", 1280, 800))

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor", return_value=mock_executor), \
         patch("backend.evidence.manager.evidence_manager.save_screenshot") as mock_save:
        await execute_action_node(state)

    mock_save.assert_called()
    events = await database.list_events(state["task_id"])
    screenshot_events = [e for e in events if e.type == "SCREENSHOT_TAKEN"]
    assert len(screenshot_events) >= 1


# ==============================================================================
# TEST 6: Exact text verification succeeds
# ==============================================================================
@pytest.mark.asyncio
async def test_6_exact_text_verification_succeeds():
    """When exact requested text is present in the DOM input, verification passes."""
    mock_page = AsyncMock()
    mock_page.url = "https://cp.sudhii.in/"
    mock_page.title = AsyncMock(return_value="Control Plane")
    # Simulate page evaluate returning input values containing the exact text
    mock_page.evaluate = AsyncMock(return_value=["hii i am agentic ai powered by local llm qwen"])

    v_res = await verification_manager.verify_task_completion(
        page=mock_page,
        intent_action="type_text",
        intent_site="https://cp.sudhii.in",
        current_url="https://cp.sudhii.in/",
        navigation_succeeded=True,
        input_text="Open https://cp.sudhii.in and enter exactly:\nhii i am agentic ai powered by local llm qwen\nDo NOT click Save.",
        task_plan=None,
    )
    assert v_res.verified is True
    assert v_res.observed.get("text_verified") == "hii i am agentic ai powered by local llm qwen"


# ==============================================================================
# TEST 7: Task completes only after verification
# ==============================================================================
@pytest.mark.asyncio
async def test_7_task_completes_only_after_verification():
    """verify_node transitions status to completed only when exact text is verified."""
    mock_page = AsyncMock()
    mock_page.url = "https://cp.sudhii.in/"
    mock_page.title = AsyncMock(return_value="Control Plane")
    mock_page.evaluate = AsyncMock(return_value=["hii i am agentic ai powered by local llm qwen"])

    action = PlannedAction(
        action_type="type_text",
        element_id="pilot-el-10",
        text="hii i am agentic ai powered by local llm qwen",
        reasoning="Typed text",
    )
    history = [ActionResult(success=True, action_type="type_text", element_id="pilot-el-10", page_state_after="ready", duration_ms=100)]
    state = make_test_state(planned_action=action, action_history=history, navigation_succeeded=True)

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor.get_screenshot_with_dimensions", AsyncMock(return_value=(b"proof", 1280, 800))):
        res = await verify_node(state)

    assert res.get("status") == "completed"
    assert res.get("result", {}).get("success") is True


# ==============================================================================
# TEST 8: Task does not complete after navigation alone
# ==============================================================================
@pytest.mark.asyncio
async def test_8_task_does_not_complete_after_navigation_alone():
    """Reaching target URL without typing the required text rejects completion."""
    mock_page = AsyncMock()
    mock_page.url = "https://cp.sudhii.in/"
    mock_page.title = AsyncMock(return_value="Control Plane")
    # Empty inputs on landing
    mock_page.evaluate = AsyncMock(return_value=[])

    v_res = await verification_manager.verify_task_completion(
        page=mock_page,
        intent_action="navigate",
        intent_site="https://cp.sudhii.in",
        current_url="https://cp.sudhii.in/",
        navigation_succeeded=True,
        input_text="Open https://cp.sudhii.in and enter exactly:\nhii i am agentic ai powered by local llm qwen\nDo NOT click Save.",
        task_plan=None,
    )
    assert v_res.verified is False
    assert v_res.observed.get("premature_completion_prevented") is True


# ==============================================================================
# TEST 9: Task does not complete after type_text alone
# ==============================================================================
@pytest.mark.asyncio
async def test_9_task_does_not_complete_after_type_text_alone():
    """Even if type_text returned success, if DOM verification fails, task remains running."""
    mock_page = AsyncMock()
    mock_page.url = "https://cp.sudhii.in/"
    mock_page.title = AsyncMock(return_value="Control Plane")
    # DOM evaluation returns mismatched text
    mock_page.evaluate = AsyncMock(return_value=["mismatched text"])

    action = PlannedAction(
        action_type="type_text",
        element_id="pilot-el-10",
        text="hii i am agentic ai powered by local llm qwen",
        reasoning="Typed text",
    )
    history = [ActionResult(success=True, action_type="type_text", element_id="pilot-el-10", page_state_after="ready", duration_ms=100)]
    state = make_test_state(planned_action=action, action_history=history, navigation_succeeded=True)

    with patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)):
        res = await verify_node(state)

    # Must NOT be completed
    assert res.get("status") == "running"


# ==============================================================================
# TEST 10: Vision invocation is separately verified from screenshot capture
# ==============================================================================
@pytest.mark.asyncio
async def test_10_vision_invocation_is_separately_verified_from_screenshot_capture():
    """Taking a screenshot does not falsely report vision_called = True."""
    mock_page = AsyncMock()
    mock_page.url = "https://cp.sudhii.in/"

    manifest = make_sample_manifest()
    # Case A: DOM identification succeeds deterministically -> Vision is NOT called
    state = make_test_state(action_manifest=manifest)
    with patch("backend.agent.nodes.OllamaGateway.complete_structured", AsyncMock(return_value=PlannedAction(action_type="need_help", reasoning="Ambiguous"))):
        plan_res = await plan_action_node(state)
        # Because pilot-el-10 was identified via DOM heuristics, vision_called is False
        assert plan_res.get("vision_called") is False
        assert plan_res["planned_action"].action_type == "type_text"
        assert plan_res["planned_action"].element_id == "pilot-el-10"

    # Case B: Empty manifest forces vision fallback -> Vision IS called
    empty_manifest = ActionManifest(url="https://cp.sudhii.in/", page_title="Empty", page_state="ready", interactive_elements=[])
    state_empty = make_test_state(action_manifest=empty_manifest)
    mock_vision_action = PlannedAction(action_type="type_text", reasoning="0.5,0.5")
    mock_executor = MagicMock()
    mock_executor.get_screenshot_with_dimensions = AsyncMock(return_value=(b"screenshot", 1280, 800))

    with patch("backend.agent.nodes.OllamaGateway.complete_structured", AsyncMock(return_value=PlannedAction(action_type="need_help", reasoning="need_help"))), \
         patch("backend.agent.nodes._get_task_page", AsyncMock(return_value=mock_page)), \
         patch("backend.agent.nodes.PlaywrightExecutor", return_value=mock_executor), \
         patch("backend.vision.provider.vision_provider.plan_action", AsyncMock(return_value=mock_vision_action)):
        plan_res_vision = await plan_action_node(state_empty)
        assert plan_res_vision.get("vision_called") is True
