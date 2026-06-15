"""Settings and setup API routes for Pilot."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse

from backend.api.schemas import ModelPullRequest, SettingsResponse, SettingsUpdateRequest
from backend.config import get_config

router = APIRouter(tags=["settings"])


@router.get("/api/settings", response_model=SettingsResponse)
async def get_settings(request: Request) -> SettingsResponse:
    """Return frontend-visible settings."""

    config = get_config()
    setup_complete = await request.app.state.database.get_setting("setup_complete", "false")
    return SettingsResponse(
        setup_complete=setup_complete == "true",
        ollama_base_url=config.ollama_base_url,
        ollama_model=await request.app.state.database.get_setting("ollama_model", config.ollama_model),
        debug_mode=config.debug_mode,
        auto_approve_low_risk=config.auto_approve_low_risk,
    )


@router.put("/api/settings", response_model=SettingsResponse)
async def update_settings(request_body: SettingsUpdateRequest, request: Request) -> SettingsResponse:
    """Persist mutable frontend settings."""

    if request_body.setup_complete is not None:
        await request.app.state.database.set_setting("setup_complete", str(request_body.setup_complete).lower())
    if request_body.ollama_model is not None:
        await request.app.state.database.set_setting("ollama_model", request_body.ollama_model)
    if request_body.debug_mode is not None:
        await request.app.state.database.set_setting("debug_mode", str(request_body.debug_mode).lower())
    if request_body.auto_approve_low_risk is not None:
        await request.app.state.database.set_setting(
            "auto_approve_low_risk",
            str(request_body.auto_approve_low_risk).lower(),
        )
    return await get_settings(request)


@router.post("/api/setup/pull-model")
async def pull_model(request_body: ModelPullRequest) -> StreamingResponse:
    """Stream `ollama pull` output as Server-Sent Events."""

    async def event_generator():
        try:
            process = await asyncio.create_subprocess_exec(
                "ollama",
                "pull",
                request_body.model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            yield _sse({"type": "error", "message": "Ollama executable was not found."})
            return

        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            yield _sse({"type": "progress", "percent": _progress_hint(text), "status": text})

        code = await process.wait()
        if code == 0:
            yield _sse({"type": "complete", "model": request_body.model})
        else:
            yield _sse({"type": "error", "message": "ollama pull exited with code " + str(code)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _sse(data: dict) -> str:
    """Serialize one Server-Sent Event data payload."""

    return "data: " + json.dumps(data) + "\n\n"


def _progress_hint(text: str) -> int:
    """Extract a rough percent from Ollama output."""

    for token in text.split():
        if token.endswith("%") and token[:-1].isdigit():
            return int(token[:-1])
    return 0


def db_size_mb() -> float:
    """Return the configured SQLite database size in megabytes."""

    path = Path(get_config().db_path).expanduser()
    if not path.exists():
        return 0.0
    return round(path.stat().st_size / (1024 * 1024), 2)
