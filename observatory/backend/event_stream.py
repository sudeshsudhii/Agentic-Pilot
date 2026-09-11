"""Real-time event stream consumer and multiplexer for Observatory."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import logging
from typing import Any
import aiohttp

from observatory.backend.models import ObservatoryEventModel, SystemStatus

logger = logging.getLogger("observatory.event_stream")


class EventStreamManager:
    """Manages connection to Pilot Core event stream and multiplexes events to Observatory frontends."""

    def __init__(self, pilot_ws_url: str = "ws://127.0.0.1:8765/ws/observability", pilot_http_url: str = "http://127.0.0.1:8765") -> None:
        self.pilot_ws_url = pilot_ws_url
        self.pilot_http_url = pilot_http_url
        self.is_running = False
        self._consumer_task: asyncio.Task[None] | None = None
        self._local_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._buffer: list[dict[str, Any]] = []
        self._max_buffer = 500
        self.pilot_backend_connected = False
        self.event_stream_connected = False
        self.last_event_time: datetime | None = None
        self.active_run_id: str | None = None

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Subscribe a local client (e.g. browser UI WebSocket) to events."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
        self._local_subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Unsubscribe a local client queue."""
        self._local_subscribers.discard(queue)

    def get_buffered_events(self, run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Return buffered events, optionally filtered by run_id."""
        if run_id:
            filtered = [e for e in self._buffer if e.get("run_id") == run_id or e.get("task_id") == run_id]
            return filtered[-limit:]
        return self._buffer[-limit:]

    def get_status(self) -> SystemStatus:
        """Return real-time connection status metrics."""
        now = datetime.now(UTC)
        age = (now - self.last_event_time).total_seconds() if self.last_event_time else None
        return SystemStatus(
            pilot_backend_connected=self.pilot_backend_connected,
            event_stream_connected=self.event_stream_connected,
            last_event_timestamp=self.last_event_time.isoformat() if self.last_event_time else None,
            last_event_age_sec=round(age, 1) if age is not None else None,
            active_run_id=self.active_run_id,
            event_buffer_size=len(self._buffer),
        )

    async def start(self) -> None:
        """Start the background consumer loop."""
        if self.is_running:
            return
        self.is_running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("Observatory EventStreamManager started connecting to %s", self.pilot_ws_url)

    async def stop(self) -> None:
        """Stop background consumer."""
        self.is_running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
        logger.info("Observatory EventStreamManager stopped")

    async def _handle_incoming_event(self, event_data: dict[str, Any]) -> None:
        """Process incoming event, update status, and broadcast to local subscribers."""
        self.last_event_time = datetime.now(UTC)
        self.event_stream_connected = True
        self.pilot_backend_connected = True

        run_id = event_data.get("run_id") or event_data.get("task_id")
        if run_id:
            self.active_run_id = run_id

        # Buffer event
        self._buffer.append(event_data)
        if len(self._buffer) > self._max_buffer:
            self._buffer.pop(0)

        # Broadcast to local UI clients
        dead = []
        for q in self._local_subscribers:
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event_data)
                except Exception:
                    dead.append(q)
            except Exception:
                dead.append(q)

        for d in dead:
            self._local_subscribers.discard(d)

    async def _consume_loop(self) -> None:
        """Continuously connect to Pilot Core via WebSocket with exponential backoff and SSE fallback."""
        backoff = 1.0
        max_backoff = 8.0

        while self.is_running:
            try:
                # 1. Check HTTP health first
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(f"{self.pilot_http_url}/api/health", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                            if resp.status == 200:
                                self.pilot_backend_connected = True
                            else:
                                self.pilot_backend_connected = False
                    except Exception:
                        self.pilot_backend_connected = False

                    # 2. Try WebSocket connection
                    try:
                        async with session.ws_connect(self.pilot_ws_url, timeout=aiohttp.ClientTimeout(total=5)) as ws:
                            logger.info("Observatory connected to Pilot WebSocket: %s", self.pilot_ws_url)
                            self.event_stream_connected = True
                            self.pilot_backend_connected = True
                            backoff = 1.0

                            async for msg in ws:
                                if not self.is_running:
                                    break
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    try:
                                        data = json.loads(msg.data)
                                        await self._handle_incoming_event(data)
                                    except Exception as exc:
                                        logger.debug("Failed to parse WS message: %s", exc)
                                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                    logger.warning("Pilot WebSocket connection closed (%s)", msg.type)
                                    break
                    except Exception as ws_err:
                        logger.debug("WebSocket connection attempt failed: %s (attempting SSE fallback)", ws_err)
                        self.event_stream_connected = False
                        
                        # 3. Fallback: SSE stream
                        try:
                            sse_url = f"{self.pilot_http_url}/api/observability/stream"
                            async with session.get(sse_url, timeout=aiohttp.ClientTimeout(total=None)) as sse_resp:
                                if sse_resp.status == 200:
                                    logger.info("Observatory connected via SSE fallback: %s", sse_url)
                                    self.event_stream_connected = True
                                    self.pilot_backend_connected = True
                                    backoff = 1.0

                                    async for line in sse_resp.content:
                                        if not self.is_running:
                                            break
                                        decoded = line.decode("utf-8").strip()
                                        if decoded.startswith("data: "):
                                            raw_json = decoded[6:].strip()
                                            try:
                                                data = json.loads(raw_json)
                                                await self._handle_incoming_event(data)
                                            except Exception:
                                                pass
                        except Exception as sse_err:
                            logger.debug("SSE fallback also failed: %s", sse_err)
                            self.event_stream_connected = False

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Event consumer loop error: %s", exc)
                self.event_stream_connected = False

            # Exponential backoff before reconnect
            await asyncio.sleep(backoff)
            backoff = min(max_backoff, backoff * 1.5)


event_stream_manager = EventStreamManager()
