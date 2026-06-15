"""Tests for Pilot's local task runner."""

import asyncio

import pytest

from backend.agent.runner import TaskRunner
from backend.db.database import Database


@pytest.mark.asyncio
async def test_low_risk_search_completes(tmp_path) -> None:
    """Low-risk search tasks should complete without approval."""

    db = Database(str(tmp_path / "pilot.db"))
    await db.connect()
    runner = TaskRunner(db)
    await runner.start()
    try:
        task_id = await runner.submit("Search Google for playwright python")
        task = await wait_for_status(db, task_id, {"completed"})
        assert task.result is not None
        assert "google.com/search" in str(task.result["url"])
    finally:
        await runner.shutdown()
        await db.close()


@pytest.mark.asyncio
async def test_high_risk_post_waits_for_approval(tmp_path) -> None:
    """High-risk social posts should pause until approved."""

    db = Database(str(tmp_path / "pilot.db"))
    await db.connect()
    runner = TaskRunner(db)
    await runner.start()
    try:
        task_id = await runner.submit("Post this to Twitter: Hello from Pilot")
        task = await wait_for_status(db, task_id, {"waiting_approval"})
        assert task.approval_id is not None
        await runner.approve(task.approval_id, "approved")
        completed = await wait_for_status(db, task_id, {"completed"})
        assert completed.result is not None
        assert completed.result["plugin_id"] == "twitter"
    finally:
        await runner.shutdown()
        await db.close()


async def wait_for_status(db: Database, task_id: str, statuses: set[str]):
    """Poll a task until it reaches one of the requested statuses."""

    for _ in range(30):
        task = await db.get_task(task_id)
        if task is not None and task.status in statuses:
            return task
        await asyncio.sleep(0.1)
    raise AssertionError("Task did not reach expected status")
