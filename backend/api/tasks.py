"""Task API routes for creating, streaming, reading, and cancelling work."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from backend.api.schemas import TaskCreateRequest, TaskCreateResponse, TaskEventResponse, TaskListResponse, TaskResponse
from backend.db.models import EventRecord, TaskRecord

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskCreateResponse)
async def create_task(request_body: TaskCreateRequest, request: Request) -> TaskCreateResponse:
    """Create a background task and return stream metadata."""

    task_id = await request.app.state.task_runner.submit(request_body.input_text)
    return TaskCreateResponse(task_id=task_id, status="queued", stream_url="/api/tasks/" + task_id + "/stream")


@router.get("", response_model=TaskListResponse)
async def list_tasks(request: Request, limit: int = 50) -> TaskListResponse:
    """Return recent task history."""

    tasks = await request.app.state.database.list_tasks(limit)
    return TaskListResponse(tasks=[_task_response(task) for task in tasks])


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request) -> TaskResponse:
    """Return a single task by id."""

    task = await request.app.state.database.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_response(task)


@router.delete("/{task_id}", response_model=TaskResponse)
async def cancel_task(task_id: str, request: Request) -> TaskResponse:
    """Cancel a task and return the updated task state."""

    if await request.app.state.database.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await request.app.state.task_runner.cancel(task_id)
    task = await request.app.state.database.get_task(task_id)
    return _task_response(task)


@router.get("/{task_id}/events", response_model=list[TaskEventResponse])
async def list_events(task_id: str, request: Request, after_id: int = 0) -> list[TaskEventResponse]:
    """Return task events after a cursor id."""

    events = await request.app.state.database.list_events(task_id, after_id)
    return [_event_response(event) for event in events]


@router.get("/{task_id}/stream")
async def stream_task(task_id: str, request: Request) -> StreamingResponse:
    """Stream task events with Server-Sent Events."""

    async def event_generator():
        last_id = 0
        while True:
            if await request.is_disconnected():
                break
            events = await request.app.state.database.list_events(task_id, last_id)
            for event in events:
                last_id = event.id
                yield "id: " + str(event.id) + "\n"
                yield "event: " + event.type + "\n"
                yield "data: " + json.dumps(_event_response(event).model_dump()) + "\n\n"
            task = await request.app.state.database.get_task(task_id)
            if task is not None and task.status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _task_response(task: TaskRecord | None) -> TaskResponse:
    """Convert a database task into an API response."""

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**task.model_dump())


def _event_response(event: EventRecord) -> TaskEventResponse:
    """Convert a database event into an API response."""

    return TaskEventResponse(**event.model_dump())
