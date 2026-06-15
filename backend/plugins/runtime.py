"""Plugin registry and lookup helpers for Pilot."""

from __future__ import annotations

from backend.llm.parser import ParsedIntent
from backend.plugins.base import PluginBase, PluginManifest
from backend.plugins.builtin.gmail import GmailPlugin
from backend.plugins.builtin.google_forms import GoogleFormsPlugin
from backend.plugins.builtin.twitter import TwitterPlugin


class PluginRegistry:
    """Runtime registry for built-in and external plugins."""

    def __init__(self) -> None:
        """Create a registry with Pilot's built-in plugins."""

        self._plugins: dict[str, PluginBase] = {}
        for plugin in (TwitterPlugin(), GmailPlugin(), GoogleFormsPlugin()):
            self.register(plugin)

    def register(self, plugin: PluginBase) -> None:
        """Register a plugin by id."""

        self._plugins[plugin.plugin_id] = plugin

    def list_manifests(self) -> list[PluginManifest]:
        """Return manifests for all registered plugins."""

        return [plugin.manifest() for plugin in self._plugins.values()]

    def find_for_intent(self, intent: ParsedIntent) -> PluginBase | None:
        """Return the best plugin for a parsed intent, if one exists."""

        site = intent.site.lower()
        for plugin in self._plugins.values():
            if intent.action in plugin.actions and any(candidate in site for candidate in plugin.sites):
                return plugin
        return None

    def get(self, plugin_id: str) -> PluginBase | None:
        """Return a plugin by id."""

        return self._plugins.get(plugin_id)


plugin_registry = PluginRegistry()
