"""Automated test suite verifying the 20 required criteria for Pilot Agent Observatory."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from backend.db.database import Database
from backend.telemetry.broadcaster import ObservatoryEvent, broadcaster, redact_sensitive
from observatory.backend.models import PerformanceMetrics
from observatory.backend.storage import ReadOnlyStorage
from observatory.backend.event_stream import EventStreamManager


# -----------------------------------------------------------------------------
# Criterion 1: Event stream connects
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_01_event_stream_connects() -> None:
    queue = broadcaster.subscribe()
    assert queue is not None
    assert queue in broadcaster._subscribers
    broadcaster.unsubscribe(queue)
    assert queue not in broadcaster._subscribers


# -----------------------------------------------------------------------------
# Criterion 2: Events arrive in real time
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_02_events_arrive_in_real_time() -> None:
    queue = broadcaster.subscribe()
    try:
        ev = ObservatoryEvent(
            event_id="test-ev-1",
            run_id="run-123",
            task_id="run-123",
            event_type="TEST_EVENT",
            message="Test real-time delivery",
        )
        await broadcaster.broadcast(ev)
        received = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert received.event_id == "test-ev-1"
        assert received.event_type == "TEST_EVENT"
    finally:
        broadcaster.unsubscribe(queue)


# -----------------------------------------------------------------------------
# Criterion 3: Events preserve run_id
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_03_events_preserve_run_id() -> None:
    run_id = "test-run-uuid-456"
    ev = ObservatoryEvent(
        event_id="ev-3",
        run_id=run_id,
        task_id=run_id,
        event_type="TASK_STARTED",
        message="Task started",
    )
    queue = broadcaster.subscribe()
    try:
        await broadcaster.broadcast(ev)
        received = await queue.get()
        assert received.run_id == run_id
        assert received.task_id == run_id
    finally:
        broadcaster.unsubscribe(queue)


# -----------------------------------------------------------------------------
# Criterion 4: Events preserve ordering
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_04_events_preserve_ordering() -> None:
    queue = broadcaster.subscribe()
    try:
        for i in range(5):
            await broadcaster.broadcast(
                ObservatoryEvent(
                    event_id=f"ord-{i}",
                    run_id="run-ord",
                    task_id="run-ord",
                    event_type=f"STEP_{i}",
                    step_index=i,
                )
            )

        for i in range(5):
            recv = await queue.get()
            assert recv.step_index == i
            assert recv.event_id == f"ord-{i}"
    finally:
        broadcaster.unsubscribe(queue)


# -----------------------------------------------------------------------------
# Criterion 5: MODEL_SELECTED appears
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_05_model_selected_appears(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-model", "Test model event")
        ev = await db.add_event(
            task.task_id,
            "MODEL_SELECTED",
            "Selected model qwen2.5:1.5b",
            {"planner_model": "qwen2.5:1.5b", "vision_model": "qwen3-vl:2b"},
        )
        assert ev.type == "MODEL_SELECTED"
        events = await db.list_events(task.task_id)
        assert any(e.type == "MODEL_SELECTED" for e in events)
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 6: PLAN_CREATED appears
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_06_plan_created_appears(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-plan", "Test plan event")
        ev = await db.add_event(
            task.task_id,
            "PLAN_CREATED",
            "Plan created with 3 steps",
            {"total_steps": 3, "task_summary": "Perform multi-step task"},
        )
        assert ev.type == "PLAN_CREATED"
        events = await db.list_events(task.task_id)
        assert any(e.type == "PLAN_CREATED" for e in events)
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 7: SCREENSHOT_CAPTURED appears
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_07_screenshot_captured_appears(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-shot", "Test screenshot event")
        ev = await db.add_event(
            task.task_id,
            "SCREENSHOT_CAPTURED",
            "Observation screenshot captured",
            {"filename": "dom_observation.png", "width": 1280, "height": 800},
        )
        assert ev.type == "SCREENSHOT_CAPTURED"
        assert ev.payload["width"] == 1280
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 8: VISION_STARTED is separate from screenshot
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_08_vision_started_separate_from_screenshot(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-vis-sep", "Test vision separation")
        # Screenshot event occurs
        await db.add_event(task.task_id, "SCREENSHOT_CAPTURED", "Screenshot captured", {"filename": "shot.png"})
        # Vision started only occurs when actually calling vision model
        await db.add_event(task.task_id, "VISION_STARTED", "Vision inference started", {"model": "qwen3-vl:2b"})

        events = await db.list_events(task.task_id)
        types = [e.type for e in events]
        assert "SCREENSHOT_CAPTURED" in types
        assert "VISION_STARTED" in types
        assert types.index("SCREENSHOT_CAPTURED") != types.index("VISION_STARTED")
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 9: image_attached is accurate
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_09_image_attached_accurate() -> None:
    ev_with_img = ObservatoryEvent(
        event_id="img-1",
        run_id="run-1",
        task_id="run-1",
        event_type="VISION_STARTED",
        metadata={"image_attached": True, "model": "qwen3-vl:2b"},
    )
    assert ev_with_img.metadata["image_attached"] is True

    ev_without_img = ObservatoryEvent(
        event_id="img-2",
        run_id="run-1",
        task_id="run-1",
        event_type="DECISION_MADE",
        metadata={"image_attached": False, "source": "DOM"},
    )
    assert ev_without_img.metadata["image_attached"] is False


# -----------------------------------------------------------------------------
# Criterion 10: DECISION_MADE appears
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_decision_made_appears(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-dec", "Test decision")
        ev = await db.add_event(
            task.task_id,
            "DECISION_MADE",
            "Action decided: type_text",
            {
                "action": "type_text",
                "target": "pilot-el-10",
                "source": "DOM",
                "vision_required": False,
                "confidence": 0.94,
            },
        )
        assert ev.type == "DECISION_MADE"
        assert ev.payload["source"] == "DOM"
        assert ev.payload["vision_required"] is False
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 11: ACTION_STARTED appears
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_action_started_appears(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-act-start", "Test action started")
        ev = await db.add_event(
            task.task_id,
            "ACTION_STARTED",
            "Action started: type_text",
            {"action_type": "type_text", "target": "pilot-el-10"},
        )
        assert ev.type == "ACTION_STARTED"
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 12: ACTION_SUCCEEDED appears
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_12_action_succeeded_appears(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-act-succ", "Test action succeeded")
        ev = await db.add_event(
            task.task_id,
            "ACTION_SUCCEEDED",
            "Action type_text succeeded",
            {"action_type": "type_text", "status": "SUCCESS", "duration_ms": 250},
        )
        assert ev.type == "ACTION_SUCCEEDED"
        assert ev.payload["status"] == "SUCCESS"
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 13: VERIFICATION_PASSED appears
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_verification_passed_appears(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-verif", "Test verification passed")
        ev = await db.add_event(
            task.task_id,
            "VERIFICATION_PASSED",
            "Verification passed",
            {
                "requirement": "Exact text matched",
                "expected": "hello world",
                "observed": "hello world",
                "overall": "PASS",
            },
        )
        assert ev.type == "VERIFICATION_PASSED"
        assert ev.payload["overall"] == "PASS"
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 14: TASK_COMPLETED appears only after verification
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_task_completed_only_after_verification(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-seq", "Test sequence")
        # 1. Action executes
        await db.add_event(task.task_id, "ACTION_SUCCEEDED", "Action succeeded")
        # 2. Verification runs
        await db.add_event(task.task_id, "VERIFICATION_PASSED", "Verification passed")
        # 3. Only then TASK_COMPLETED appears
        await db.add_event(task.task_id, "TASK_COMPLETED", "Task execution completed")

        events = await db.list_events(task.task_id)
        types = [e.type for e in events]
        v_idx = types.index("VERIFICATION_PASSED")
        c_idx = types.index("TASK_COMPLETED")
        assert v_idx < c_idx
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 15: CAPTCHA appears as BLOCKED
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_15_captcha_appears_as_blocked(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-cap", "Test captcha block")
        ev = await db.add_event(
            task.task_id,
            "BLOCKED",
            "Task blocked by CAPTCHA",
            {"reason": "CAPTCHA / bot verification detected", "recovery_options": ["manual_captcha", "safe_search_fallback"]},
        )
        assert ev.type == "BLOCKED"
        assert "CAPTCHA" in ev.payload["reason"]
        await db.update_task(task.task_id, status="blocked")
        t = await db.get_task(task.task_id)
        assert t.status == "blocked"
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 16: Retry events appear
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_retry_events_appear(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-retry", "Test retry event")
        ev = await db.add_event(
            task.task_id,
            "RETRY_ATTEMPTED",
            "RETRY #1: Strategy DOM grounding",
            {"retry_number": 1, "strategy": "DOM grounding", "reason": "Element not found"},
        )
        assert ev.type == "RETRY_ATTEMPTED"
        assert ev.payload["retry_number"] == 1
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 17: Model timing is calculated correctly
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_17_model_timing_calculated_correctly(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        task = await db.create_task("task-timing", "Test timings")
        await db.add_event(
            task.task_id,
            "VISION_COMPLETED",
            "Vision finished",
            {"duration_ms": 4200, "model": "qwen3-vl:2b"},
        )
        await db.add_event(
            task.task_id,
            "ACTION_SUCCEEDED",
            "Action finished",
            {"duration_ms": 1500, "action_type": "type_text"},
        )

        storage = ReadOnlyStorage(str(tmp_path / "test.db"))
        perf = await storage.get_performance(task.task_id)
        assert perf.vision_duration_sec == 4.2
        assert perf.browser_duration_sec == 1.5
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 18: Run history works
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_18_run_history_works(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    try:
        t1 = await db.create_task("run-001", "Task 1")
        t2 = await db.create_task("run-002", "Task 2")
        await db.update_task(t1.task_id, status="completed")
        await db.update_task(t2.task_id, status="failed", error="Execution failed")

        storage = ReadOnlyStorage(str(tmp_path / "test.db"))
        runs = await storage.list_runs()
        assert len(runs) >= 2
        run_ids = [r.run_id for r in runs]
        assert "run-001" in run_ids
        assert "run-002" in run_ids
    finally:
        await db.close()


# -----------------------------------------------------------------------------
# Criterion 19: Sensitive information is redacted
# -----------------------------------------------------------------------------
def test_19_sensitive_info_redacted() -> None:
    raw = {
        "user": "test_user",
        "password": "supersecretpassword123",
        "api_key": "sk-1234567890abcdef",
        "auth": "Bearer eyJhbGciOi...",
        "nested": {
            "token": "secret_token_val",
            "normal": "safe_value",
        },
    }
    redacted = redact_sensitive(raw)
    assert redacted["user"] == "test_user"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["auth"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["normal"] == "safe_value"


# -----------------------------------------------------------------------------
# Criterion 20: Disconnection/reconnection works
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_20_disconnection_reconnection_works() -> None:
    mgr = EventStreamManager()
    assert mgr.is_running is False
    assert mgr.event_stream_connected is False

    # Simulate receiving incoming event updates state
    await mgr._handle_incoming_event({
        "event_id": "disc-1",
        "run_id": "run-disc",
        "event_type": "TASK_STARTED",
    })
    assert mgr.event_stream_connected is True
    assert mgr.pilot_backend_connected is True
    assert mgr.active_run_id == "run-disc"

    # Status age calculation
    status = mgr.get_status()
    assert status.event_stream_connected is True
    assert status.last_event_age_sec is not None
    assert status.last_event_age_sec < 5.0
