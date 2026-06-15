"""FastAPI entrypoint for the Pilot local backend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import sys
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agent.runner import TaskRunner
from backend.api import approvals, health, plugins, sessions, settings, tasks
from backend.browser.pool import browser_pool
from backend.config import get_config
from backend.db.database import database


config = get_config()
logging.basicConfig(
    level=logging.DEBUG if config.debug_mode else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pilot.backend")


class HealthResponse(BaseModel):
    """Response model for the basic health check."""

    status: str
    model: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize shared services and shut them down cleanly."""

    app.state.started_at = time.time()
    app.state.database = database
    app.state.browser_pool = browser_pool
    await database.connect()
    app.state.task_runner = TaskRunner(database, config)
    await app.state.task_runner.start()
    logger.info("Starting Pilot backend with config: %s", config.model_dump())
    try:
        yield
    finally:
        await app.state.task_runner.shutdown()
        await browser_pool.shutdown()
        await database.close()


app = FastAPI(title="Pilot API", version=config.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://127.0.0.1:1420"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(tasks.router)
app.include_router(approvals.router)
app.include_router(sessions.router)
app.include_router(plugins.router)
app.include_router(settings.router)
app.include_router(health.router)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Log every request with duration and status code."""

    started = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "status_code": response.status_code,
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return structured validation errors."""

    return JSONResponse(status_code=422, content={"detail": json.loads(exc.json())})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Return structured errors for unexpected API exceptions."""

    logger.exception("Unhandled API exception")
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return a lightweight backend health status."""

    return HealthResponse(status="ok", model=config.ollama_model)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.server_port, log_level="info")
