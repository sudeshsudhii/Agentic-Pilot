"""Tests for Pilot's SQLite database wrapper."""

import pytest

from backend.db.database import Database


@pytest.mark.asyncio
async def test_database_task_event_roundtrip(tmp_path) -> None:
    """Tasks and events should persist and read back as typed records."""

    db = Database(str(tmp_path / "pilot.db"))
    await db.connect()
    try:
        task = await db.create_task("task-1", "Search Google for Pilot")
        assert task.status == "queued"
        event = await db.add_event(task.task_id, "queued", "Task queued")
        events = await db.list_events(task.task_id)
        assert events == [event]
        updated = await db.update_task(task.task_id, status="completed")
        assert updated.status == "completed"
    finally:
        await db.close()
