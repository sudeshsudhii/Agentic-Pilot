"""Main application entry point for Pilot Agent Observatory backend."""

from __future__ import annotations

import contextlib
import logging
from typing import AsyncIterator
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from observatory.backend.api import handle_dashboard_websocket, router
from observatory.backend.event_stream import event_stream_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("observatory.backend")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage lifecycle of background event stream consumer."""
    logger.info("Starting Observatory event stream consumer...")
    await event_stream_manager.start()
    yield
    logger.info("Stopping Observatory event stream consumer...")
    await event_stream_manager.stop()


app = FastAPI(
    title="Pilot Agent Observatory Backend",
    description="Real-time developer observatory for monitoring Pilot browser agent execution.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:1420",
        "http://127.0.0.1:1420",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Dashboard real-time WebSocket connection."""
    await handle_dashboard_websocket(websocket)


@app.get("/")
async def root() -> dict[str, str]:
    """Root status check."""
    return {"name": "Pilot Agent Observatory Backend", "port": "8766", "status": "running"}


def run(host: str = "127.0.0.1", port: int = 8766) -> None:
    """Run Observatory backend using uvicorn."""
    uvicorn.run("observatory.backend.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
