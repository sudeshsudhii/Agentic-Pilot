"""Plugin API routes."""

from fastapi import APIRouter

from backend.api.schemas import PluginListResponse
from backend.plugins.runtime import plugin_registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("", response_model=PluginListResponse)
async def list_plugins() -> PluginListResponse:
    """Return all registered plugin manifests."""

    return PluginListResponse(
        plugins=[manifest.model_dump() for manifest in plugin_registry.list_manifests()]
    )
