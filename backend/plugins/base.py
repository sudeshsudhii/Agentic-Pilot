"""Plugin SDK primitives for Pilot site automations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from backend.llm.parser import ParsedIntent


class PluginResult(BaseModel):
    """Result returned by a plugin execution."""

    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False


class PluginManifest(BaseModel):
    """Metadata advertised by a Pilot plugin."""

    plugin_id: str
    name: str
    sites: list[str]
    actions: list[str]
    risk_levels: dict[str, str]
    network_permission: bool = False


class PluginBase(ABC):
    """Base class every built-in and external plugin must implement."""

    plugin_id: str
    name: str
    sites: list[str]
    actions: list[str]
    risk_levels: dict[str, str]
    network_permission = False

    def manifest(self) -> PluginManifest:
        """Return this plugin's manifest."""

        return PluginManifest(
            plugin_id=self.plugin_id,
            name=self.name,
            sites=self.sites,
            actions=self.actions,
            risk_levels=self.risk_levels,
            network_permission=self.network_permission,
        )

    @abstractmethod
    def validate_params(self, intent: ParsedIntent) -> list[str]:
        """Return validation error messages for a parsed intent."""

    @abstractmethod
    def get_selector_hints(self, action: str) -> dict[str, list[str]]:
        """Return site-specific selector hints grouped by field name."""

    def get_risk_level(self, action: str) -> str:
        """Return the risk level for a plugin action."""

        return self.risk_levels.get(action, "medium")

    @abstractmethod
    async def execute(self, intent: ParsedIntent) -> PluginResult:
        """Execute a plugin action with already-approved parameters."""
