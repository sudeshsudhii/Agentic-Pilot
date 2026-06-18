import pytest
import asyncio

from backend.db.database import database, resolve_path
from backend.agent.runner import TaskRunner

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
async def setup_db(tmp_path_factory):
    """Setup a temporary database for the certification tests."""
    db_path = tmp_path_factory.mktemp("data") / "cert.db"
    database.path = resolve_path(str(db_path))
    await database.connect()
    yield database
    await database.close()

@pytest.fixture(scope="function")
async def runner(setup_db):
    """Setup the task runner."""
    r = TaskRunner(setup_db)
    await r.start()
    yield r
    await r.shutdown()

async def wait_for_completion(db, task_id: str, timeout: int = 120):
    for _ in range(timeout):
        task = await db.get_task(task_id)
        if task and task.status in {"completed", "failed"}:
            return task
        await asyncio.sleep(1.0)
    raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

@pytest.mark.asyncio
async def test_certification_suite(runner, setup_db):
    # 1. Navigation
    task_id1 = await runner.submit("Navigate to example.com")
    task1 = await wait_for_completion(setup_db, task_id1)
    assert task1.status == "completed", f"Navigation failed: {task1.error}"

    # 2. Search
    task_id2 = await runner.submit("Search for LangGraph on wikipedia.org")
    task2 = await wait_for_completion(setup_db, task_id2)
    assert task2.status == "completed", f"Search failed: {task2.error}"

    # 3. Extraction
    task_id3 = await runner.submit("Extract the title of example.com")
    task3 = await wait_for_completion(setup_db, task_id3)
    assert task3.status == "completed", f"Extraction failed: {task3.error}"
    assert task3.result is not None

    # 4. Failure
    task_id4 = await runner.submit("Navigate to http://this-domain-will-never-exist-12345.com")
    task4 = await wait_for_completion(setup_db, task_id4)
    assert task4.status == "failed"

    # 5. Recovery
    task_id5 = await runner.submit("Go to example.com and click on a non-existent button called 'Magic Button'")
    task5 = await wait_for_completion(setup_db, task_id5)
    assert task5.status in ["failed", "completed"]
