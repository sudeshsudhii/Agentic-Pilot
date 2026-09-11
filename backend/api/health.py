"""Health monitoring API routes for Pilot."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from backend.api.schemas import DetailedHealthResponse
from backend.api.settings import db_size_mb
from backend.config import get_config
from backend.llm.gateway import OllamaGateway

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/detailed", response_model=DetailedHealthResponse)
async def detailed_health(request: Request) -> DetailedHealthResponse:
    """Return component health, uptime, and version details."""

    started = time.perf_counter()
    gateway = OllamaGateway()
    ollama_ok = await gateway.health_check()
    ollama_latency = int((time.perf_counter() - started) * 1000)
    installed_models = await gateway.list_models() if ollama_ok else []
    tasks_count = await request.app.state.database.count_tasks()
    browser_pool = getattr(request.app.state, "browser_pool", None)
    config = get_config()
    components = {
        "ollama": {
            "status": "connected" if ollama_ok else "disconnected",
            "model": config.ollama_model,
            "vision_model": config.ollama_vision_model,
            "latency_ms": ollama_latency,
            "installed_models": installed_models,
        },
        "database": {
            "status": "connected",
            "tasks_count": tasks_count,
            "db_size_mb": db_size_mb(),
        },
        "browser": {
            "status": "ready",
            "active_sessions": browser_pool.active_sessions if browser_pool else 0,
        },
        "features": {
            "evidence": config.enable_evidence,
            "verification": config.enable_verification,
            "recovery": config.enable_recovery,
            "memory": config.enable_memory,
        },
    }
    status = "healthy" if ollama_ok else "degraded"
    uptime = int(time.time() - request.app.state.started_at)
    return DetailedHealthResponse(
        status=status,
        components=components,
        uptime_seconds=uptime,
        version=get_config().app_version,
    )
