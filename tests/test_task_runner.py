"""Tests for Pilot's local task runner."""

import asyncio

import pytest

from backend.agent.runner import TaskRunner
from backend.db.database import database, resolve_path
from backend.config import get_config


@pytest.fixture(autouse=True)
async def cleanup_browser_pool():
    from backend.browser.pool import browser_pool
    yield
    await browser_pool.shutdown()


@pytest.fixture(autouse=True)
async def cleanup_database():
    await database.close()
    default_path = get_config().db_path
    database.path = resolve_path(default_path)
    yield
    await database.close()
    database.path = resolve_path(default_path)


@pytest.fixture(autouse=True)
def mock_llm():
    from unittest.mock import patch
    from backend.llm.parser import ParsedIntent, PlannedAction
    
    async def mock_complete(self, system, user, schema, image_bytes=None):
        if schema.__name__ == "ParsedIntent":
            if "Twitter" in user:
                print("DEBUG MOCK: returning Twitter intent")
                return ParsedIntent(action="post", risk_level="high", site="https://twitter.com", reasoning="Mock reasoning")
            print("DEBUG MOCK: returning Search intent")
            return ParsedIntent(action="search", risk_level="low", site="https://google.com/search?q=playwright+python", reasoning="Mock reasoning")
        elif schema.__name__ == "PlannedAction":
            print("DEBUG MOCK: returning PlannedAction complete")
            return PlannedAction(action_type="complete", reasoning="Done")
            
    with patch("backend.llm.gateway.OllamaGateway.complete_structured", new=mock_complete):
        yield


@pytest.mark.asyncio
async def test_low_risk_search_completes(tmp_path) -> None:
    """Low-risk search tasks should complete without approval."""

    await database.close()
    database.path = resolve_path(str(tmp_path / "pilot.db"))
    await database.connect()
    print(f"DEBUG TEST: test_low_risk_search_completes database id: {id(database)} path: {database.path}")
    runner = TaskRunner(database)
    await runner.start()
    try:
        task_id = await runner.submit("Search Google for playwright python")
        task = await wait_for_status(database, task_id, {"completed"})
        assert task.result is not None
        assert "google.com/search" in str(task.result["url"])
    finally:
        await runner.shutdown()
        await database.close()


@pytest.mark.asyncio
async def test_high_risk_post_waits_for_approval(tmp_path) -> None:
    """High-risk social posts should pause until approved."""

    await database.close()
    database.path = resolve_path(str(tmp_path / "pilot.db"))
    await database.connect()
    runner = TaskRunner(database)
    await runner.start()
    try:
        task_id = await runner.submit("Post this to Twitter: Hello from Pilot")
        task = await wait_for_status(database, task_id, {"waiting_approval"})
        assert task.approval_id is not None
        await runner.approve(task.approval_id, "approved")
        completed = await wait_for_status(database, task_id, {"completed"})
        assert completed.result is not None
        assert completed.result["plugin_id"] == "twitter"
    finally:
        await runner.shutdown()
        await database.close()


async def wait_for_status(db: Database, task_id: str, statuses: set[str]):
    """Poll a task until it reaches one of the requested statuses."""

    for _ in range(300):
        task = await db.get_task(task_id)
        if task is not None:
            if task.status in statuses:
                return task
            if task.status == "failed" and "failed" not in statuses:
                raise AssertionError(f"Task failed unexpectedly: {task.error}")
        await asyncio.sleep(1.0)
    raise AssertionError("Task did not reach expected status")
