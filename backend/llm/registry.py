"""Model capability registry for Agentic Pilot multi-model routing."""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from backend.config import get_config

logger = logging.getLogger("pilot.llm.registry")


class ModelCapability(str, Enum):
    """Specific capabilities a local model can provide."""

    REASONING = "reasoning"
    PLANNING = "planning"
    GENERAL = "general"
    VISION = "vision"
    GUI_UNDERSTANDING = "gui_understanding"
    CODING = "coding"
    DEBUGGING = "debugging"
    LIGHTWEIGHT = "lightweight"
    FAST = "fast"
    LONG_CONTEXT = "long_context"
    RECOVERY = "recovery"
    FALLBACK = "fallback"
    TOOL_CALLING = "tool_calling"


class ModelRole(str, Enum):
    """Operational roles assigned to local models in the agent workflow."""

    PLANNER = "planner"
    EXECUTOR = "executor"
    VISION = "vision"
    CODER = "coder"
    RECOVERY = "recovery"
    LIGHTWEIGHT = "lightweight"
    GENERAL = "general"



class ModelMetadata(BaseModel):
    """Metadata and capabilities for an Ollama model."""

    model_name: str
    provider: str = "ollama"
    capabilities: list[ModelCapability] = Field(default_factory=list)
    priority: int = Field(default=1, description="Higher number indicates higher priority")
    context_window: int = Field(default=4096, ge=512)
    latency_tier: str = Field(default="medium", description="'low', 'medium', or 'high'")
    enabled: bool = True
    installed: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)

    def has_capability(self, cap: ModelCapability | str) -> bool:
        """Check if model possesses the specified capability."""
        cap_val = cap.value if isinstance(cap, ModelCapability) else str(cap).lower()
        return any(c.value == cap_val for c in self.capabilities)

    def has_all_capabilities(self, caps: list[ModelCapability | str]) -> bool:
        """Check if model possesses all required capabilities."""
        return all(self.has_capability(c) for c in caps)


# Standard profile mapping for well-known local models
DEFAULT_KNOWN_MODELS: list[ModelMetadata] = [
    ModelMetadata(
        model_name="qwen2.5:7b",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.PLANNING,
            ModelCapability.GENERAL,
            ModelCapability.TOOL_CALLING,
            ModelCapability.RECOVERY,
        ],
        priority=10,
        context_window=8192,
        latency_tier="medium",
    ),
    ModelMetadata(
        model_name="qwen3.5:2b",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.PLANNING,
            ModelCapability.GENERAL,
            ModelCapability.LIGHTWEIGHT,
            ModelCapability.FAST,
            ModelCapability.TOOL_CALLING,
        ],
        priority=9,
        context_window=8192,
        latency_tier="low",
    ),

    ModelMetadata(
        model_name="qwen2.5:1.5b",
        capabilities=[
            ModelCapability.GENERAL,
            ModelCapability.REASONING,
            ModelCapability.LIGHTWEIGHT,
            ModelCapability.FAST,
            ModelCapability.FALLBACK,
        ],
        priority=5,
        context_window=4096,
        latency_tier="low",
    ),
    ModelMetadata(
        model_name="deepseek-r1:1.5b",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.LIGHTWEIGHT,
            ModelCapability.FAST,
            ModelCapability.PLANNING,
        ],
        priority=9,
        context_window=4096,
        latency_tier="low",
    ),
    ModelMetadata(
        model_name="moondream",
        capabilities=[
            ModelCapability.VISION,
            ModelCapability.GUI_UNDERSTANDING,
            ModelCapability.FAST,
        ],
        priority=8,
        context_window=2048,
        latency_tier="low",
    ),
    ModelMetadata(
        model_name="qwen3-vl:2b",
        capabilities=[
            ModelCapability.VISION,
            ModelCapability.GUI_UNDERSTANDING,
            ModelCapability.REASONING,
            ModelCapability.TOOL_CALLING,
        ],
        priority=10,
        context_window=8192,
        latency_tier="medium",
    ),
    ModelMetadata(
        model_name="qwen2.5-coder:3b",
        capabilities=[
            ModelCapability.CODING,
            ModelCapability.DEBUGGING,
            ModelCapability.REASONING,
            ModelCapability.TOOL_CALLING,
        ],
        priority=10,
        context_window=8192,
        latency_tier="medium",
    ),
    ModelMetadata(
        model_name="qwen2.5-coder:1.5b",
        capabilities=[
            ModelCapability.CODING,
            ModelCapability.DEBUGGING,
            ModelCapability.LIGHTWEIGHT,
            ModelCapability.FAST,
        ],
        priority=8,
        context_window=4096,
        latency_tier="low",
    ),
]


class ModelRegistry:
    """Manages model profiles, capabilities, and availability."""

    def __init__(self, probe_ttl_seconds: int = 300) -> None:
        self._models: dict[str, ModelMetadata] = {}
        self._installed_cache: set[str] = set()
        self._last_probe_time: float = 0.0
        self.probe_ttl_seconds = probe_ttl_seconds

        # Register default models
        for m in DEFAULT_KNOWN_MODELS:
            self.register_model(m)

        # Synchronize configured models from config
        self._sync_with_config()

    def _sync_with_config(self) -> None:
        """Ensure all models specified in PilotConfig are registered."""
        cfg = get_config()
        configured_models = {
            cfg.model_reasoning: [ModelCapability.REASONING, ModelCapability.PLANNING, ModelCapability.GENERAL],
            cfg.model_vision: [ModelCapability.VISION, ModelCapability.GUI_UNDERSTANDING],
            cfg.model_coding: [ModelCapability.CODING, ModelCapability.DEBUGGING],
            cfg.model_lightweight: [ModelCapability.LIGHTWEIGHT, ModelCapability.FAST, ModelCapability.REASONING],
            cfg.model_fallback: [ModelCapability.FALLBACK, ModelCapability.GENERAL, ModelCapability.LIGHTWEIGHT],
            cfg.ollama_model: [ModelCapability.GENERAL, ModelCapability.REASONING, ModelCapability.FALLBACK],
        }

        for model_name, default_caps in configured_models.items():
            if model_name not in self._models:
                self.register_model(
                    ModelMetadata(
                        model_name=model_name,
                        capabilities=default_caps,
                        priority=5,
                    )
                )

    def register_model(self, metadata: ModelMetadata) -> None:
        """Register or update a model profile in the registry."""
        self._models[metadata.model_name] = metadata
        logger.debug("Registered model profile: %s capabilities=%s", metadata.model_name, [c.value for c in metadata.capabilities])

    def get_model(self, model_name: str) -> ModelMetadata | None:
        """Get profile for a specific model."""
        return self._models.get(model_name)

    def list_models(self, enabled_only: bool = True) -> list[ModelMetadata]:
        """Return list of all registered models."""
        models = list(self._models.values())
        if enabled_only:
            models = [m for m in models if m.enabled]
        return sorted(models, key=lambda m: m.priority, reverse=True)

    def mark_installed(self, model_names: list[str]) -> None:
        """Update installed status for the specified model names."""
        installed_set = {n.strip().lower() for n in model_names}
        # Also include without :latest tag (e.g., 'moondream:latest' -> 'moondream')
        installed_normalized = set(installed_set)
        for name in installed_set:
            if name.endswith(":latest"):
                installed_normalized.add(name[:-7])

        self._installed_cache = installed_normalized
        self._last_probe_time = time.time()

        for name, meta in self._models.items():
            norm_name = name.lower()
            is_installed = (norm_name in installed_normalized)
            if not is_installed and ":" not in norm_name:
                is_installed = f"{norm_name}:latest" in installed_set
            meta.installed = is_installed

    async def probe_installed(self, gateway: Any | None = None, force_refresh: bool = False) -> set[str]:
        """Query local Ollama daemon to refresh installed models cache."""
        now = time.time()
        if not force_refresh and (now - self._last_probe_time < self.probe_ttl_seconds) and self._installed_cache:
            return self._installed_cache

        try:
            if gateway is None:
                from backend.llm.gateway import OllamaGateway
                gateway = OllamaGateway()

            names = await gateway.list_model_names()
            if names:
                self.mark_installed(names)
                logger.info("Probed local Ollama daemon: %d models installed", len(names))
            else:
                logger.debug("Ollama daemon returned no models (service may be starting or empty)")
        except Exception as exc:
            logger.warning("Failed to probe installed models from Ollama daemon: %s", exc)

        return self._installed_cache

    def unregister_model(self, model_name: str) -> bool:
        """Remove a model profile from the registry."""
        return self._models.pop(model_name, None) is not None

    def list_registered_models(self) -> list[ModelMetadata]:
        """Return list of all registered models (including disabled)."""
        return self.list_models(enabled_only=False)

    def list_installed_models(self) -> list[ModelMetadata]:
        """Return list of models currently marked as installed."""
        return [m for m in self._models.values() if m.installed]

    def get_models_with_capability(self, cap: ModelCapability | str) -> list[ModelMetadata]:
        """Find all registered models with a specific capability sorted by priority."""
        return self.find_by_capabilities([cap])

    def get_preferred_model(self, cap: ModelCapability | str, fallback: str = "qwen2.5:1.5b") -> str:
        """Get the highest priority model possessing the given capability."""
        models = self.find_by_capabilities([cap])
        return models[0].model_name if models else fallback

    def get_candidates_for_role(
        self,
        role: ModelRole | str,
        installed_only: bool = False,
    ) -> list[ModelMetadata]:
        """Return candidate models configured for a specific role, ordered by preference."""
        cfg = get_config()
        role_str = role.value if isinstance(role, ModelRole) else str(role).lower()
        candidate_names = cfg.model_candidates_by_role.get(role_str, [])

        resolved: list[ModelMetadata] = []
        for name in candidate_names:
            meta = self.get_model(name)
            if not meta:
                continue
            if not meta.enabled:
                continue
            if installed_only and not meta.installed:
                continue
            resolved.append(meta)

        # If no configured candidates are available, fall back to capability search
        if not resolved:
            role_to_cap = {
                "planner": [ModelCapability.PLANNING, ModelCapability.REASONING],
                "executor": [ModelCapability.GENERAL],
                "vision": [ModelCapability.VISION],
                "coder": [ModelCapability.CODING],
                "recovery": [ModelCapability.RECOVERY, ModelCapability.REASONING],
                "lightweight": [ModelCapability.LIGHTWEIGHT],
                "general": [ModelCapability.GENERAL],
            }
            caps = role_to_cap.get(role_str, [ModelCapability.GENERAL])
            resolved = self.find_by_capabilities(caps, installed_only=installed_only)

        return resolved

    def find_by_capabilities(
        self,
        required_capabilities: list[ModelCapability | str],
        installed_only: bool = False,
    ) -> list[ModelMetadata]:
        """Find models possessing all required capabilities sorted by priority."""
        candidates: list[ModelMetadata] = []
        for meta in self._models.values():
            if not meta.enabled:
                continue
            if installed_only and not meta.installed:
                continue
            if meta.has_all_capabilities(required_capabilities):
                candidates.append(meta)

        return sorted(candidates, key=lambda m: m.priority, reverse=True)


# Global registry singleton
model_registry = ModelRegistry()
