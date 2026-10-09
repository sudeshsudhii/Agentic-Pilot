"""Desktop-specific LangGraph node implementations.

These nodes handle the desktop execution path while reusing
the existing shared infrastructure (model router, evidence manager,
telemetry, recovery engine, verification).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime

from backend.agent.desktop_prompts import (
    DESKTOP_ACTION_PLANNING_PROMPT,
    DESKTOP_TASK_DECOMPOSITION_PROMPT,
)
from backend.agent.environment import EnvironmentType, classify_environment
from backend.agent.state import AgentState
from backend.config import get_config
from backend.db.database import database
from backend.desktop.applications import app_launcher
from backend.desktop.grounding import GroundingResult, desktop_grounding
from backend.desktop.models import (
    DesktopAction,
    DesktopActionResult,
    DesktopActionType,
    DesktopObservation,
    GoalCondition,
    GoalPredicate,
    GoalTarget,
)
from backend.desktop.observer import desktop_observer
from backend.desktop.uia import uia_manager
from backend.desktop.verifier import desktop_verifier
from backend.desktop.windows import window_manager
from backend.evidence.manager import ExecutionRecord, evidence_manager
from backend.llm.gateway import OllamaGateway, get_llm_provider
from backend.llm.parser import ParsedIntent, PlannedAction, TaskPlan, TaskStep
from backend.llm.router import model_router
from backend.recovery.engine import recovery_engine
from backend.telemetry.tracer import tracer

logger = logging.getLogger("pilot.agent.desktop_nodes")


# ───────────────────────────────────────────────────────────────────
# 1. Environment Resolver Node
# ───────────────────────────────────────────────────────────────────

async def environment_resolver_node(state: AgentState) -> dict:
    """Classify the task environment BEFORE environment-specific execution."""
    task_id = state.get("task_id", "unknown")
    input_text = state.get("input_text", "")

    env = classify_environment(input_text)
    logger.info("NODE=environment_resolver task_id=%s env=%s", task_id, env.value)

    await database.add_event(
        task_id,
        "ENVIRONMENT_RESOLVED",
        f"Task environment: {env.value}",
        {"environment": env.value, "input": input_text[:100]},
    )

    return {"current_environment": env.value}


# ───────────────────────────────────────────────────────────────────
# 2. Desktop Observation Node
# ───────────────────────────────────────────────────────────────────

async def desktop_observe_node(state: AgentState) -> dict:
    """Observe the current Windows desktop state.

    Captures UIA tree, normalizes elements, filters, ranks, and produces
    a bounded DesktopObservation manifest.
    """
    task_id = state.get("task_id", "unknown")
    logger.info("NODE=desktop_observe ENTER task_id=%s", task_id)
    started = time.perf_counter()

    # Check for security boundaries FIRST
    is_security, security_reason = await window_manager.detect_security_boundary()
    if is_security:
        logger.warning("DESKTOP_OBSERVE SECURITY_BOUNDARY: %s", security_reason)
        await database.add_event(
            task_id, "DESKTOP_BLOCKED",
            f"Security boundary detected: {security_reason}",
            {"reason": security_reason},
        )
        return {
            "status": "blocked",
            "blocked_reason": security_reason,
            "error": f"Security boundary: {security_reason}",
        }

    # Extract goal keywords for relevance ranking
    input_text = state.get("input_text", "")
    goal_keywords = [w.lower() for w in input_text.split() if len(w) > 3]

    # Determine target window
    target_window = state.get("active_window")

    observation = await desktop_observer.observe(
        goal_keywords=goal_keywords,
        target_window=target_window,
    )

    duration_ms = int((time.perf_counter() - started) * 1000)

    # Save screenshot evidence
    try:
        from backend.desktop.executor import desktop_executor
        screenshot = await desktop_executor.take_screenshot()
        if screenshot:
            evidence_manager.save_screenshot(task_id, "desktop_observation", screenshot)
            observation.screenshot_available = True
    except Exception as exc:
        logger.warning("Desktop screenshot failed: %s", exc)

    await database.add_event(
        task_id,
        "DESKTOP_OBSERVATION",
        f"Desktop observed: {observation.element_count_total} elements, "
        f"{len(observation.elements)} actionable",
        {
            "total_elements": observation.element_count_total,
            "visible_elements": observation.element_count_visible,
            "bounded_elements": len(observation.elements),
            "active_window": observation.active_window.title if observation.active_window else "None",
            "duration_ms": duration_ms,
            "step_index": state.get("current_step_index", 1),
        },
    )

    active_win_title = observation.active_window.title if observation.active_window else None
    active_app = observation.active_window.process_name if observation.active_window else None

    return {
        "desktop_observation": observation.model_dump(),
        "active_window": active_win_title,
        "active_application": active_app,
    }


# ───────────────────────────────────────────────────────────────────
# 3. Desktop Plan Action Node
# ───────────────────────────────────────────────────────────────────

async def desktop_plan_action_node(state: AgentState) -> dict:
    """Plan a single next desktop action from current observation and goal."""
    task_id = state.get("task_id", "unknown")
    logger.info("NODE=desktop_plan_action ENTER task_id=%s", task_id)

    if state.get("status") == "blocked":
        return {
            "desktop_action": DesktopAction(
                action_type=DesktopActionType.WAIT,
                reasoning="Task is blocked",
            ).model_dump(),
            "status": "blocked",
        }

    gateway = get_llm_provider()
    obs_data = state.get("desktop_observation", {})
    task_plan = state.get("task_plan")
    cur_idx = state.get("current_step_index", 1)

    # Model routing
    routing = model_router.route(
        task_type="planning",
        input_text=state.get("input_text", ""),
        complexity="high" if (task_plan and len(task_plan.steps) > 1) else "medium",
        active_model=state.get("selected_model"),
    )
    tracer.record_model_routing(
        task_id=task_id,
        selected_model=routing.selected_model,
        role=routing.role,
        reason=routing.reason,
        model_switch=routing.model_switch,
        fallback_used=routing.fallback_used,
    )

    # Build planner context
    elements_summary = []
    for el in obs_data.get("elements", [])[:40]:  # Token budget
        entry = {
            "id": el.get("id", ""),
            "role": el.get("role", ""),
            "name": el.get("name", ""),
            "control_type": el.get("control_type", ""),
            "enabled": el.get("enabled", True),
            "toggle_state": el.get("toggle_state"),
            "patterns": el.get("patterns", []),
        }
        if el.get("automation_id"):
            entry["automation_id"] = el["automation_id"]
        if el.get("value"):
            entry["value"] = el["value"]
        elements_summary.append(entry)

    plan_context = ""
    if task_plan and task_plan.steps:
        plan_context = f"\nTask Plan ({task_plan.task_summary}):\n"
        for s in task_plan.steps:
            marker = "==>" if s.step_index == cur_idx else "   "
            plan_context += f"{marker} Step {s.step_index}: {s.description} (Status: {s.status})\n"

    prompt = f"""
Overall Goal: {state.get('input_text', '')}
Current Step Index: {cur_idx}
{plan_context}

Active Window: {obs_data.get('active_window', {}).get('title', 'None') if isinstance(obs_data.get('active_window'), dict) else state.get('active_window', 'None')}
Active Application: {state.get('active_application', 'None')}

Previous Action: {state.get('desktop_action', {}).get('action_type', 'None') if state.get('desktop_action') else 'None'}
Previous Result: {state.get('desktop_action_result', {}).get('success', 'N/A') if state.get('desktop_action_result') else 'N/A'}

Interactive Elements:
{json.dumps(elements_summary, indent=2)}
"""

    try:
        action = await gateway.complete_structured(
            DESKTOP_ACTION_PLANNING_PROMPT,
            prompt,
            DesktopAction,
            model_override=routing.selected_model,
        )
    except Exception as e:
        logger.exception("Desktop plan_action LLM failed: %s", e)
        action = DesktopAction(
            action_type=DesktopActionType.REQUEST_REOBSERVATION,
            reasoning=f"LLM planning failure: {e}",
        )

    # ENFORCE: planner cannot return "complete" (Requirement 10)
    action_type_str = action.action_type.value if isinstance(action.action_type, DesktopActionType) else str(action.action_type)
    if "complete" in action_type_str.lower():
        logger.warning("PLANNER tried to return 'complete' — overriding to request_reobservation")
        action = DesktopAction(
            action_type=DesktopActionType.REQUEST_REOBSERVATION,
            reasoning="Planner attempted completion — verification required instead",
        )

    # ENFORCE: Prohibit arbitrary code / shell execution (Requirement 9)
    prohibited_tokens = [
        "powershell", "cmd.exe", "bash", "sh -c", "start-process", "invoke-expression",
        "iex ", "rmdir", "del ", "reg add", "reg delete", "python -c", "eval(", "exec("
    ]
    check_payload = f"{action.text or ''} {action.target_id or ''} {action.application or ''}".lower()
    if any(tok in check_payload for tok in prohibited_tokens):
        logger.warning("PLANNER returned prohibited shell/code token: %s — rejecting action", check_payload)
        action = DesktopAction(
            action_type=DesktopActionType.REQUEST_REOBSERVATION,
            reasoning="Security validation rejected arbitrary code/shell pattern in planned action",
        )

    # ENFORCE: Preserve Bluetooth toggle if ALREADY ON (Requirements 8 & 14)
    goal_lower = state.get("input_text", "").lower()
    if "bluetooth" in goal_lower and any(w in goal_lower for w in ["on", "enable", "turn on", "make sure"]):
        for el in obs_data.get("elements", []):
            el_name = (el.get("name") or "").lower()
            if "bluetooth" in el_name and el.get("toggle_state") == "On":
                if action.action_type in (DesktopActionType.CLICK_ELEMENT, DesktopActionType.DOUBLE_CLICK):
                    if action.target_id == el.get("id") or "bluetooth" in str(action.target_id or "").lower():
                        logger.info("BLUETOOTH_ALREADY_ON: Preserving active state without unnecessary toggle")
                        action = DesktopAction(
                            action_type=DesktopActionType.WAIT,
                            reasoning="Bluetooth is already ON. Preserving state without toggling, advancing to verification.",
                        )
                        break

    logger.info(
        "NODE=desktop_plan_action action=%s target=%s",
        action.action_type.value, action.target_id or action.application or "",
    )

    await database.add_event(
        task_id,
        "DECISION_MADE",
        f"Desktop action decided: {action.action_type.value}",
        {
            "action": action.action_type.value,
            "target": action.target_id or action.application or "",
            "confidence": action.confidence,
            "reasoning": action.reasoning[:200],
            "source": "DESKTOP_UIA",
            "step_index": cur_idx,
        },
    )

    return {
        "desktop_action": action.model_dump(),
        "llm_call_count": state.get("llm_call_count", 0) + 1,
        "selected_model": routing.selected_model,
        "model_role": routing.role,
        "routing_reason": routing.reason,
        "model_switch": routing.model_switch,
    }


# ───────────────────────────────────────────────────────────────────
# 4. Desktop Execute Action Node
# ───────────────────────────────────────────────────────────────────

async def desktop_execute_action_node(state: AgentState) -> dict:
    """Execute a single typed desktop action."""
    task_id = state.get("task_id", "unknown")
    action_data = state.get("desktop_action", {})
    if not action_data:
        return {"error": "No desktop action to execute", "last_action_status": "failed"}

    action = DesktopAction.model_validate(action_data)
    obs_data = state.get("desktop_observation", {})
    observation = DesktopObservation.model_validate(obs_data) if obs_data else None

    logger.info(
        "NODE=desktop_execute action=%s target=%s task_id=%s",
        action.action_type.value, action.target_id or action.application or "", task_id,
    )

    started = time.perf_counter()

    # Before screenshot
    try:
        from backend.desktop.executor import desktop_executor
        before_ss = await desktop_executor.take_screenshot()
        if before_ss:
            step_count = state.get("llm_call_count", 0)
            evidence_manager.save_screenshot(task_id, f"desktop_before_{step_count}", before_ss)
    except Exception:
        pass

    await database.add_event(
        task_id,
        "DESKTOP_ACTION_STARTED",
        f"Desktop action: {action.action_type.value}",
        {
            "action_type": action.action_type.value,
            "target": action.target_id or action.application or "",
            "step_index": state.get("current_step_index", 1),
        },
    )

    result = await _execute_desktop_action(action, observation, state)

    duration_ms = int((time.perf_counter() - started) * 1000)
    result.duration_ms = duration_ms

    # After screenshot
    try:
        from backend.desktop.executor import desktop_executor
        after_ss = await desktop_executor.take_screenshot()
        if after_ss:
            step_count = state.get("llm_call_count", 0)
            evidence_manager.save_screenshot(task_id, f"desktop_after_{step_count}", after_ss)
    except Exception:
        pass

    # UI settlement wait
    await asyncio.sleep(0.5)

    await database.add_event(
        task_id,
        "DESKTOP_ACTION_COMPLETED",
        f"Desktop action {action.action_type.value} {'succeeded' if result.success else 'failed'}",
        {
            "action_type": action.action_type.value,
            "success": result.success,
            "error": result.error,
            "grounding_level": result.grounding_level,
            "duration_ms": duration_ms,
            "step_index": state.get("current_step_index", 1),
        },
    )

    # Save evidence record
    config = get_config()
    if config.enable_evidence:
        step_count = state.get("llm_call_count", 0)
        exec_record = ExecutionRecord(
            task_id=task_id,
            step_id=f"D{step_count:03d}",
            step_index=step_count,
            action={
                "type": action.action_type.value,
                "target_id": action.target_id,
                "application": action.application,
                "text": action.text,
            },
            before_state={
                "active_window": state.get("active_window"),
                "active_application": state.get("active_application"),
            },
            execution_result=result.model_dump(),
            after_state={
                "grounding_level": result.grounding_level,
            },
            evidence={
                "before_screenshot": f"desktop_before_{step_count}.png",
                "after_screenshot": f"desktop_after_{step_count}.png",
            },
            verification={
                "action_success": result.success,
                "error": result.error,
            },
            model=state.get("selected_model") or "",
            model_role=state.get("model_role") or "",
            routing_reason=state.get("routing_reason") or "",
            duration_ms=duration_ms,
            node_name="desktop_execute_action",
        )
        evidence_manager.save_execution_record(exec_record)

    return {
        "desktop_action_result": result.model_dump(),
        "last_action_status": "succeeded" if result.success else "failed",
        "error": result.error if not result.success else None,
    }


async def _execute_desktop_action(
    action: DesktopAction,
    observation: DesktopObservation | None,
    state: AgentState,
) -> DesktopActionResult:
    """Dispatch a typed desktop action to the appropriate executor."""
    from backend.desktop.executor import desktop_executor

    at = action.action_type
    started = time.perf_counter()

    try:
        if at == DesktopActionType.LAUNCH_APPLICATION:
            return await app_launcher.launch(action.application or "")

        elif at == DesktopActionType.FOCUS_WINDOW:
            success = await window_manager.focus_window(action.window_title or "")
            return DesktopActionResult(
                success=success,
                action_type="focus_window",
                target_id=action.window_title,
                error=None if success else "Window not found",
                grounding_level="semantic",
            )

        elif at == DesktopActionType.SWITCH_WINDOW:
            success = await window_manager.focus_window(action.window_title or "")
            return DesktopActionResult(
                success=success,
                action_type="switch_window",
                target_id=action.window_title,
                error=None if success else "Window not found",
                grounding_level="semantic",
            )

        elif at == DesktopActionType.CLOSE_WINDOW:
            success = await window_manager.close_window(action.window_title or state.get("active_window", ""))
            return DesktopActionResult(
                success=success,
                action_type="close_window",
                grounding_level="semantic",
            )

        elif at == DesktopActionType.CLICK_ELEMENT:
            return await _execute_click_element(action, observation, state)

        elif at == DesktopActionType.CLICK_COORDINATE:
            if action.x is None or action.y is None:
                return DesktopActionResult(
                    success=False,
                    action_type="click_coordinate",
                    error="Missing coordinates",
                    grounding_level="coordinate",
                )
            result = await desktop_executor.click(action.x, action.y, clicks=action.clicks, button=action.button)
            return DesktopActionResult(
                success=result.success,
                action_type="click_coordinate",
                error=result.error,
                grounding_level="coordinate",
            )

        elif at == DesktopActionType.DOUBLE_CLICK:
            return await _execute_click_element(action, observation, state, clicks=2)

        elif at == DesktopActionType.TYPE_TEXT:
            if not action.text:
                return DesktopActionResult(success=False, action_type="type_text", error="No text provided")
            result = await desktop_executor.type_text(action.text)
            return DesktopActionResult(
                success=result.success,
                action_type="type_text",
                error=result.error,
                grounding_level="keyboard",
            )

        elif at == DesktopActionType.PRESS_KEY:
            key = action.key or "Enter"
            result = await desktop_executor.hotkey(key)
            return DesktopActionResult(
                success=result.success,
                action_type="press_key",
                target_id=key,
                error=result.error,
                grounding_level="keyboard",
            )

        elif at == DesktopActionType.HOTKEY:
            keys = action.keys or []
            if not keys:
                return DesktopActionResult(success=False, action_type="hotkey", error="No keys provided")
            result = await desktop_executor.hotkey(*keys)
            return DesktopActionResult(
                success=result.success,
                action_type="hotkey",
                target_id="+".join(keys),
                error=result.error,
                grounding_level="keyboard",
            )

        elif at == DesktopActionType.SCROLL:
            direction = action.direction or "down"
            try:
                import pyautogui
                amount = -3 if direction == "down" else 3
                await asyncio.to_thread(pyautogui.scroll, amount)
                return DesktopActionResult(success=True, action_type="scroll", grounding_level="keyboard")
            except Exception as e:
                return DesktopActionResult(success=False, action_type="scroll", error=str(e))

        elif at == DesktopActionType.WAIT:
            await asyncio.sleep(1.0)
            return DesktopActionResult(success=True, action_type="wait", grounding_level="semantic")

        elif at == DesktopActionType.CLIPBOARD_COPY:
            result = await desktop_executor.hotkey("ctrl", "c")
            return DesktopActionResult(success=result.success, action_type="clipboard_copy", grounding_level="keyboard")

        elif at == DesktopActionType.CLIPBOARD_PASTE:
            result = await desktop_executor.hotkey("ctrl", "v")
            return DesktopActionResult(success=result.success, action_type="clipboard_paste", grounding_level="keyboard")

        elif at == DesktopActionType.REQUEST_REOBSERVATION:
            return DesktopActionResult(success=True, action_type="request_reobservation", grounding_level="semantic")

        elif at == DesktopActionType.REQUEST_VISUAL_GROUNDING:
            return DesktopActionResult(success=True, action_type="request_visual_grounding", grounding_level="vlm")

        elif at == DesktopActionType.MOVE_MOUSE:
            if action.x is not None and action.y is not None:
                try:
                    import pyautogui
                    await asyncio.to_thread(pyautogui.moveTo, action.x, action.y, duration=0.3)
                    return DesktopActionResult(success=True, action_type="move_mouse", grounding_level="coordinate")
                except Exception as e:
                    return DesktopActionResult(success=False, action_type="move_mouse", error=str(e))
            return DesktopActionResult(success=False, action_type="move_mouse", error="Missing coordinates")

        elif at == DesktopActionType.DRAG:
            return DesktopActionResult(success=False, action_type="drag", error="Drag not yet implemented")

        else:
            return DesktopActionResult(
                success=False, action_type=str(at), error=f"Unknown action type: {at}"
            )

    except Exception as e:
        logger.exception("Desktop action execution error: %s", e)
        return DesktopActionResult(
            success=False,
            action_type=str(at),
            error=str(e),
        )


async def _execute_click_element(
    action: DesktopAction,
    observation: DesktopObservation | None,
    state: AgentState,
    clicks: int = 1,
) -> DesktopActionResult:
    """Click an element using the grounding escalation chain."""
    from backend.desktop.executor import desktop_executor

    if observation is None:
        return DesktopActionResult(
            success=False,
            action_type="click_element",
            error="No desktop observation available",
        )

    grounding = await desktop_grounding.ground_target(
        action, observation, window_title=state.get("active_window"),
    )

    if not grounding.success:
        return DesktopActionResult(
            success=False,
            action_type="click_element",
            target_id=action.target_id,
            error=grounding.error or "Grounding failed",
            grounding_level=grounding.level,
        )

    # Try UIA-based interaction first (semantic)
    if grounding.uia_control is not None:
        if clicks == 1:
            # For toggles, use TogglePattern
            element = grounding.element
            if element and element.toggle_state is not None:
                new_state = await uia_manager.toggle_element(grounding.uia_control)
                if new_state is not None:
                    return DesktopActionResult(
                        success=True,
                        action_type="click_element",
                        target_id=action.target_id,
                        grounding_level="semantic",
                        observed_state={"toggle_state": new_state},
                    )

            # Try InvokePattern
            invoked = await uia_manager.invoke_element(grounding.uia_control)
            if invoked:
                return DesktopActionResult(
                    success=True,
                    action_type="click_element",
                    target_id=action.target_id,
                    grounding_level="semantic",
                )

            # Fallback to clicking center of element
            clicked = await uia_manager.click_element_center(grounding.uia_control)
            if clicked:
                return DesktopActionResult(
                    success=True,
                    action_type="click_element",
                    target_id=action.target_id,
                    grounding_level="pattern",
                )

    # Coordinate-based fallback
    if grounding.coordinates:
        cx, cy = grounding.coordinates
        result = await desktop_executor.click(cx, cy, clicks=clicks)
        return DesktopActionResult(
            success=result.success,
            action_type="click_element",
            target_id=action.target_id,
            error=result.error,
            grounding_level=grounding.level,
        )

    return DesktopActionResult(
        success=False,
        action_type="click_element",
        target_id=action.target_id,
        error="All grounding levels exhausted",
        grounding_level="failed",
    )


# ───────────────────────────────────────────────────────────────────
# 5. Desktop Verify Node
# ───────────────────────────────────────────────────────────────────

async def desktop_verify_node(state: AgentState) -> dict:
    """Verify desktop action results and evaluate goal conditions.

    INVARIANT: ACTION_DISPATCHED != ACTION_VERIFIED != TASK_COMPLETED
    """
    task_id = state.get("task_id", "unknown")
    task_plan = state.get("task_plan")
    cur_idx = state.get("current_step_index", 1)
    total_steps = len(task_plan.steps) if (task_plan and task_plan.steps) else 1
    goal_conditions = state.get("goal_conditions", [])

    logger.info("NODE=desktop_verify ENTER task_id=%s step=%d/%d", task_id, cur_idx, total_steps)

    # Check blocked
    if state.get("status") == "blocked":
        return {"status": "blocked"}

    # Check action result
    action_result_data = state.get("desktop_action_result", {})
    action_succeeded = action_result_data.get("success", False)

    # Handle reobservation / VLM requests
    action_type = action_result_data.get("action_type", "")
    if action_type in ("request_reobservation", "request_visual_grounding"):
        return {"status": "running", "error": None}

    # Check for hard errors
    if state.get("error") and not action_succeeded:
        retry_count = state.get("retry_count", 0)
        if retry_count >= 3:
            return {"status": "failed", "error": f"Max retries exceeded: {state.get('error')}"}
        return {"retry_count": retry_count + 1, "status": "running"}

    # Step advancement
    if action_succeeded and task_plan and task_plan.steps and cur_idx <= len(task_plan.steps):
        task_plan.steps[cur_idx - 1].status = "completed"
        task_plan.steps[cur_idx - 1].result_summary = f"Action {action_type} succeeded"

        if cur_idx < len(task_plan.steps):
            next_idx = cur_idx + 1
            task_plan.current_step_index = next_idx
            step_desc = task_plan.steps[next_idx - 1].description

            await database.add_event(
                task_id, "STEP_PROGRESS",
                f"Step {next_idx} / {total_steps}: {step_desc}",
                {"step": next_idx, "total": total_steps, "description": step_desc},
            )

            return {
                "status": "running",
                "current_step_index": next_idx,
                "task_plan": task_plan,
                "last_action_status": "succeeded",
                "error": None,
            }

    # Evaluate goal conditions for task completion
    if goal_conditions and (cur_idx >= total_steps or not task_plan):
        await database.add_event(task_id, "DESKTOP_VERIFICATION_STARTED", "Evaluating goal conditions")

        # Parse goal conditions from state
        parsed_conditions = []
        for gc_data in goal_conditions:
            try:
                if isinstance(gc_data, dict):
                    target_data = gc_data.get("target", {})
                    parsed_conditions.append(GoalCondition(
                        predicate=GoalPredicate(gc_data["predicate"]),
                        target=GoalTarget(**target_data) if isinstance(target_data, dict) else GoalTarget(),
                        expected_value=gc_data.get("expected_value", True),
                    ))
                elif isinstance(gc_data, GoalCondition):
                    parsed_conditions.append(gc_data)
            except Exception as e:
                logger.warning("Failed to parse goal condition: %s — %s", gc_data, e)

        if parsed_conditions:
            all_passed, results = await desktop_verifier.verify_all_goals(parsed_conditions)

            for r in results:
                evidence_manager.save_verification(task_id, r.model_dump())
                await database.add_event(
                    task_id,
                    "DESKTOP_VERIFICATION_COMPLETED",
                    f"Goal check: {r.type} — {'PASS' if r.verified else 'FAIL'}",
                    {"verified": r.verified, "expected": r.expected, "observed": r.observed},
                )

            if all_passed:
                logger.info("DESKTOP_VERIFY ALL_GOALS_PASSED task_id=%s", task_id)

                # Final proof screenshot
                try:
                    from backend.desktop.executor import desktop_executor
                    proof_ss = await desktop_executor.take_screenshot()
                    if proof_ss:
                        evidence_manager.save_screenshot(task_id, "completion_proof", proof_ss)
                except Exception:
                    pass

                await database.add_event(
                    task_id, "VERIFICATION_PASSED",
                    "All desktop goal conditions verified",
                    {"conditions_passed": len(parsed_conditions)},
                )

                return {
                    "status": "completed",
                    "result": {
                        "success": True,
                        "answer": f"Task completed: all {len(parsed_conditions)} goal conditions verified.",
                        "environment": "desktop",
                    },
                }
            else:
                failed = [r for r in results if not r.verified]
                logger.warning(
                    "DESKTOP_VERIFY GOALS_NOT_MET task_id=%s failed=%d",
                    task_id, len(failed),
                )
                # Continue loop if not max iterations
                if state.get("llm_call_count", 0) >= 15:
                    return {"status": "failed", "error": "Max iterations exceeded without satisfying desktop goals"}
                return {"status": "running", "error": None}

    # If no goal conditions but task plan completed
    if task_plan and cur_idx >= len(task_plan.steps) and action_succeeded:
        # Re-observe to get final state — use active window or input text for targeting
        active_win = state.get("active_window")
        obs = await desktop_observer.observe(
            goal_keywords=[w.lower() for w in state.get("input_text", "").split() if len(w) > 3],
            target_window=active_win,
        )

        # Validate: If the observation sees NO elements and NO active window,
        # the desktop action likely didn't produce visible results — don't mark complete
        has_active_window = obs.active_window is not None
        has_elements = obs.element_count_total > 0

        if not has_active_window and not has_elements:
            retry_count = state.get("retry_count", 0)
            if retry_count < 3:
                logger.warning(
                    "DESKTOP_VERIFY NO_OBSERVABLE_STATE task_id=%s retry=%d — re-observing",
                    task_id, retry_count,
                )
                await asyncio.sleep(1.5)  # Wait for app to render
                return {
                    "status": "running",
                    "retry_count": retry_count + 1,
                    "error": None,
                }
            else:
                logger.warning(
                    "DESKTOP_VERIFY COMPLETING_DESPITE_NO_STATE task_id=%s — max retries reached",
                    task_id,
                )

        # Take completion proof
        try:
            from backend.desktop.executor import desktop_executor
            proof_ss = await desktop_executor.take_screenshot()
            if proof_ss:
                evidence_manager.save_screenshot(task_id, "completion_proof", proof_ss)
        except Exception:
            pass

        return {
            "status": "completed",
            "result": {
                "success": True,
                "answer": "Desktop task completed — all plan steps executed and verified.",
                "environment": "desktop",
                "active_window": obs.active_window.title if obs.active_window else None,
            },
        }

    # Iteration limit
    if state.get("llm_call_count", 0) >= 15:
        return {"status": "failed", "error": "Max iterations exceeded"}

    return {"status": "running"}


# ───────────────────────────────────────────────────────────────────
# 6. Desktop Complete Node (reuses existing complete_node structure)
# ───────────────────────────────────────────────────────────────────

async def desktop_complete_node(state: AgentState) -> dict:
    """Finalize desktop task, persist result, and clean up."""
    task_id = state.get("task_id", "unknown")
    final_status = state.get("status", "completed")
    if final_status == "running":
        final_status = "completed"

    error_msg = state.get("error")
    res = state.get("result") or {}

    logger.info("NODE=desktop_complete task_id=%s status=%s", task_id, final_status)

    await database.update_task(
        task_id,
        status=final_status,
        result_json=json.dumps(res),
        error=error_msg,
        completed_at=datetime.now(UTC).isoformat() if final_status not in ("blocked",) else None,
    )

    if final_status == "completed":
        await database.add_event(task_id, "TASK_COMPLETED", "Desktop task completed", res)
    elif final_status == "failed":
        await database.add_event(task_id, "failed", "Desktop task failed", {"error": error_msg})
    elif final_status == "blocked":
        await database.add_event(task_id, "blocked", "Desktop task blocked", {"error": error_msg})

    # Store outcome in memory
    config = get_config()
    if config.enable_memory and final_status != "blocked":
        try:
            from backend.memory.provider import memory_manager
            intent = state.get("parsed_intent")
            goal_desc = state.get("input_text", "desktop task")
            if final_status == "completed":
                await memory_manager.store_strategy(
                    task_id=task_id,
                    goal=goal_desc,
                    strategy={"environment": "desktop", "steps": state.get("llm_call_count", 0)},
                    outcome="success",
                )
            elif final_status == "failed":
                await memory_manager.store_failure(
                    task_id=task_id,
                    goal=goal_desc,
                    failure={"error": error_msg},
                    diagnosis=error_msg or "Desktop task failure",
                )
        except Exception as mem_err:
            logger.warning("Desktop memory store failed: %s", mem_err)

    # Telemetry
    from backend.telemetry.tracer import tracer
    tracer.record_task_summary(
        task_id=task_id,
        status=final_status,
        duration_ms=0,
        step_count=state.get("llm_call_count", 0),
        error=error_msg,
    )

    return {"status": final_status, "result": res}
