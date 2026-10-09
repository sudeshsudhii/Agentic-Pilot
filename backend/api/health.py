"""Health monitoring API routes for Pilot."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from backend.api.schemas import DetailedHealthResponse
from backend.api.settings import db_size_mb
from backend.config import get_config
from backend.llm.gateway import get_llm_provider

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/detailed", response_model=DetailedHealthResponse)
async def detailed_health(request: Request) -> DetailedHealthResponse:
    """Return component health, uptime, and version details."""

    config = get_config()
    started = time.perf_counter()
    gateway = get_llm_provider()
    llm_ok = await gateway.health_check()
    llm_latency = int((time.perf_counter() - started) * 1000)
    tasks_count = await request.app.state.database.count_tasks()
    browser_pool = getattr(request.app.state, "browser_pool", None)
    
    components = {
        "llm": {
            "provider": gateway.provider_name,
            "status": "connected" if llm_ok else "disconnected",
            "model": config.gemini_model if gateway.provider_name == "gemini" else config.ollama_model,
            "latency_ms": llm_latency,
        },
        "ollama": {
            "status": "connected" if (gateway.provider_name == "ollama" and llm_ok) else "idle",
            "model": config.ollama_model,
            "vision_model": config.ollama_vision_model,
            "latency_ms": llm_latency if gateway.provider_name == "ollama" else 0,
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
