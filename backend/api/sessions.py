"""Session API routes for future authenticated browser sessions."""

from fastapi import APIRouter

from backend.api.schemas import SessionListResponse

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions() -> SessionListResponse:
    """Return configured session markers."""

    return SessionListResponse(sessions=[])
