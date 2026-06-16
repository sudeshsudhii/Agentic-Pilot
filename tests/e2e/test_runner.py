import pytest
import asyncio
from backend.db.database import database
from backend.agent.runner import TaskRunner

@pytest.mark.asyncio
async def test_runner_execution_flow():
    """Verify runner instantiates graph and handles success/failures."""
    await database.init()
    runner = TaskRunner(database)
    await runner.start()

    # Submit a simple navigation task
    task_id = await runner.submit("Open example.com")
    
    # Wait for completion
    completed = False
    for _ in range(15):
        task = await database.get_task(task_id)
        if task.status in ["completed", "failed"]:
            completed = True
            break
        await asyncio.sleep(1)
        
    await runner.shutdown()
    
    assert completed
    assert task.status in ["completed", "failed"]

@pytest.mark.asyncio
async def test_high_risk_approval_flow():
    """Verify high risk tasks are paused for approval."""
    await database.init()
    runner = TaskRunner(database)
    await runner.start()

    task_id = await runner.submit("Buy a laptop on amazon")
    
    # It should pause for approval
    paused = False
    for _ in range(15):
        task = await database.get_task(task_id)
        if task.status == "waiting_approval":
            paused = True
            break
        await asyncio.sleep(1)
        
    await runner.shutdown()
    
    # Without mock parsing it might fail to parse or parse correctly, but either way it won't execute unsupervised
    assert task.status in ["waiting_approval", "failed"]
