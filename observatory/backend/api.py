"""API router for Pilot Agent Observatory."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

from observatory.backend.event_stream import event_stream_manager
from observatory.backend.models import PerformanceMetrics, RunSummary, SystemStatus
from observatory.backend.storage import storage

logger = logging.getLogger("observatory.api")

router = APIRouter(prefix="/api")


@router.get("/status", response_model=SystemStatus)
async def get_status() -> SystemStatus:
    """Return the current connection status of the Observatory."""
    return event_stream_manager.get_status()


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(limit: int = 50) -> list[RunSummary]:
    """List historical agent runs."""
    return await storage.list_runs(limit=limit)


@router.get("/runs/{run_id}")
async def get_run_details(run_id: str) -> dict[str, Any]:
    """Get all events and summary for a specific run."""
    events = await storage.get_run_events(run_id)
    # Check if there are also buffered live events for this run
    buffered = event_stream_manager.get_buffered_events(run_id=run_id)
    known_event_ids = {e.event_id for e in events}
    for b in buffered:
        eid = str(b.get("event_id", ""))
        if eid and eid not in known_event_ids:
            from observatory.backend.models import ObservatoryEventModel
            events.append(ObservatoryEventModel(**b))
            known_event_ids.add(eid)

    state = await storage.get_run_state(run_id)
    perf = await storage.get_performance(run_id)
    return {
        "run_id": run_id,
        "events": [e.model_dump() for e in events],
        "state": state,
        "performance": perf.model_dump(),
    }


@router.get("/runs/{run_id}/state")
async def get_run_state(run_id: str) -> dict[str, Any]:
    """Get the latest LangGraph state for a run."""
    state = await storage.get_run_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run state not found")
    return state


@router.get("/runs/{run_id}/performance", response_model=PerformanceMetrics)
async def get_run_performance(run_id: str) -> PerformanceMetrics:
    """Get calculated latency metrics for a run."""
    return await storage.get_performance(run_id)


@router.get("/experiences")
async def list_experiences(limit: int = 50) -> list[dict[str, Any]]:
    """List captured experiences from Pilot memories table."""
    return await storage.list_experiences(limit=limit)


@router.get("/evidence/{task_id}/{filename}")
async def get_evidence_file(task_id: str, filename: str) -> FileResponse:
    """Serve screenshot and evidence files from the evidence directory."""
    evidence_base = Path("~/.pilot/logs/evidence").expanduser().resolve()
    target = (evidence_base / task_id / filename).resolve()
    if not target.is_relative_to(evidence_base) or not target.exists():
        raise HTTPException(status_code=404, detail="Evidence file not found")

    content_type = "image/png"
    if filename.endswith(".json"):
        content_type = "application/json"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        content_type = "image/jpeg"
    elif filename.endswith(".webp"):
        content_type = "image/webp"

    return FileResponse(target, media_type=content_type)


@router.get("/stream")
async def local_event_stream() -> StreamingResponse:
    """SSE event stream for local Observatory frontend clients."""
    queue = event_stream_manager.subscribe()

    async def event_generator():
        try:
            # Send initial sync of buffered events
            buffered = event_stream_manager.get_buffered_events(limit=50)
            for event in buffered:
                yield f"data: {json.dumps(event)}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            event_stream_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def handle_dashboard_websocket(websocket: WebSocket) -> None:
    """WebSocket handler for Observatory frontend."""
    await websocket.accept()
    queue = event_stream_manager.subscribe()
    logger.info("Observatory frontend WebSocket client connected")

    try:
        # Send initial sync of recent buffered events
        buffered = event_stream_manager.get_buffered_events(limit=50)
        for ev in buffered:
            await websocket.send_text(json.dumps(ev))

        # Forward live incoming events
        while True:
            # Wait for event or ping from client
            event_future = asyncio.create_task(queue.get())
            recv_future = asyncio.create_task(websocket.receive_text())
            done, pending = await asyncio.wait(
                [event_future, recv_future],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            if event_future in done:
                event = event_future.result()
                await websocket.send_text(json.dumps(event))
            elif recv_future in done:
                client_msg = recv_future.result()
                if client_msg == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        logger.info("Observatory frontend WebSocket disconnected")
    except Exception as exc:
        logger.warning("Observatory frontend WebSocket error: %s", exc)
    finally:
        event_stream_manager.unsubscribe(queue)
