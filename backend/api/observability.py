"""Observability API and WebSocket endpoints for real-time developer dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse

from backend.telemetry.broadcaster import broadcaster, ObservatoryEvent

logger = logging.getLogger("pilot.api.observability")
router = APIRouter(tags=["observability"])


@router.get("/api/observability/status")
async def get_observability_status() -> dict[str, Any]:
    """Return live status of the observability subsystem."""
    return {
        "status": "active",
        "subscribers_count": len(broadcaster._subscribers),
        "buffered_events_count": len(broadcaster._history),
    }


@router.get("/api/observability/stream")
async def stream_observability_events(request: Request, task_id: str | None = None) -> StreamingResponse:
    """Server-Sent Events (SSE) stream for real-time observability events."""
    queue = broadcaster.subscribe()

    async def event_generator():
        try:
            # Emit recent buffered events first to synchronize new connection
            recent = broadcaster.get_recent_events(task_id=task_id, limit=50)
            for ev in recent:
                yield f"id: {ev.event_id}\nevent: {ev.event_type}\ndata: {ev.model_dump_json()}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    if task_id and event.task_id != task_id and event.run_id != task_id:
                        continue
                    yield f"id: {event.event_id}\nevent: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws/observability")
async def websocket_observability(websocket: WebSocket, task_id: str | None = None) -> None:
    """Real-time bidirectional WebSocket stream for the Pilot Agent Observatory."""
    await websocket.accept()
    queue = broadcaster.subscribe()
    logger.info("Observability WebSocket client connected (task_id=%s)", task_id)

    try:
        # Push recent buffered events to populate immediate state
        recent = broadcaster.get_recent_events(task_id=task_id, limit=50)
        for ev in recent:
            await websocket.send_text(ev.model_dump_json())

        while True:
            # Listen for new events from broadcaster
            fetch_task = asyncio.create_task(queue.get())
            recv_task = asyncio.create_task(websocket.receive_text())

            done, pending = await asyncio.wait(
                [fetch_task, recv_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            if recv_task in done:
                # Handle any client commands (e.g. ping, switch task_id)
                msg = recv_task.result()
                try:
                    payload = json.loads(msg)
                    if payload.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif payload.get("type") == "subscribe_task":
                        task_id = payload.get("task_id")
                except Exception:
                    pass

            if fetch_task in done:
                event = fetch_task.result()
                if not task_id or event.task_id == task_id or event.run_id == task_id:
                    await websocket.send_text(event.model_dump_json())

    except WebSocketDisconnect:
        logger.info("Observability WebSocket client disconnected")
    except Exception as exc:
        logger.debug("Observability WebSocket error: %s", exc)
    finally:
        broadcaster.unsubscribe(queue)
