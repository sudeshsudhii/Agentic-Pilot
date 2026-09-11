"""Capability-aware multi-model router for Agentic Pilot."""

from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field

from backend.config import get_config
from backend.llm.registry import ModelCapability, ModelMetadata, ModelRegistry, model_registry

logger = logging.getLogger("pilot.llm.router")


class RoutingDecision(BaseModel):
    """Detailed record of a model routing determination."""

    selected_model: str
    role: str  # "reasoning", "vision", "coding", "lightweight", "recovery", "general"
    required_capabilities: list[str] = Field(default_factory=list)
    reason: str
    fallback_used: bool = False
    model_switch: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRouter:
    """Dynamic, capability-aware router selecting local Ollama models per subtask.

    Implements a 4-stage routing pipeline:
    1. Capability Matching (task requirements -> capability set)
    2. Availability Checking (filters installed/healthy models)
    3. Preference & Anti-Thrashing (re-uses active model when capable to minimize model loading)
    4. Fallback Hierarchy (specialized -> secondary -> general -> fallback)
    """

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or model_registry
        self._last_selected_model: str | None = None
        self._step_counter: int = 0

    def route(
        self,
        task_type: str = "general",
        input_text: str = "",
        action_type: str | None = None,
        has_image: bool = False,
        complexity: str = "medium",  # "low", "medium", "high"
        is_recovery: bool = False,
        active_model: str | None = None,
        forced_capabilities: list[ModelCapability | str] | None = None,
    ) -> RoutingDecision:
        """Select the optimal local model for the given subtask requirements."""
        config = get_config()
        self._step_counter += 1

        # 0. Check Single-Model or Multi-Model Disabled Mode
        if not config.enable_multi_model or config.model_routing_strategy == "single":
            chosen = config.ollama_vision_model if has_image else config.ollama_model
            return RoutingDecision(
                selected_model=chosen,
                role="vision" if has_image else "general",
                required_capabilities=["vision"] if has_image else ["general"],
                reason="Single model ablation mode enforced by configuration",
                fallback_used=False,
                model_switch=(self._last_selected_model is not None and self._last_selected_model != chosen),
            )

        # Check single installed model bypass (Section 12: Installed Models = 1 -> Router bypass)
        has_probed_installed = bool(self.registry._installed_cache)
        installed_models = self.registry.list_installed_models()
        if has_probed_installed and len(installed_models) == 1:
            single_m = installed_models[0].model_name
            return RoutingDecision(
                selected_model=single_m,
                role="vision" if has_image else "general",
                required_capabilities=["vision"] if has_image else ["general"],
                reason=f"Single installed model bypass ({single_m} is the only local model)",
                fallback_used=False,
                model_switch=(self._last_selected_model is not None and self._last_selected_model != single_m),
            )

        # 1. Stage 1: Capability Analysis via CapabilityAnalyzer
        from backend.llm.analyzer import capability_analyzer
        reqs = capability_analyzer.analyze(
            task_text=input_text or task_type,
            action_type=action_type,
            task_type=task_type,
            complexity=complexity,
            has_image=has_image,
            is_recovery=is_recovery,
            forced_capabilities=forced_capabilities,
        )
        req_caps = reqs.required_capabilities

        # Map ModelRole enum to role string
        role_map = {
            "coder": "coding",
            "planner": "reasoning",
            "executor": "general",
        }
        role_raw = reqs.target_role.value
        target_role = role_map.get(role_raw, role_raw)

        # 2. Stage 2: Candidate Resolution (Role Candidates -> Capabilities -> Installed filter)
        candidates = self.registry.get_candidates_for_role(
            reqs.target_role,
            installed_only=has_probed_installed,
        )

        # If role candidates returned no match, query by capability
        if not candidates:
            candidates = self.registry.find_by_capabilities(req_caps, installed_only=has_probed_installed)

        # If strict capability matching returned no candidates, try finding with primary capability
        if not candidates and len(req_caps) > 1:
            candidates = self.registry.find_by_capabilities([req_caps[0]], installed_only=has_probed_installed)

        # 3. Stage 3: Model Stickiness (Anti-Thrashing)
        # If active model already satisfies the required capabilities and this is not recovery escalation, retain it
        current_active = active_model or self._last_selected_model
        if current_active and not is_recovery:
            active_meta = self.registry.get_model(current_active)
            if active_meta and (not has_probed_installed or active_meta.installed):
                if active_meta.has_all_capabilities(req_caps):
                    self._last_selected_model = current_active
                    return RoutingDecision(
                        selected_model=current_active,
                        role=target_role,
                        required_capabilities=[c.value for c in req_caps],
                        reason=f"Active model '{current_active}' retained (stickiness: satisfies requirements)",
                        fallback_used=False,
                        model_switch=False,
                        metadata={"stickiness": True},
                    )

        # 4. Stage 4: Fallback Hierarchy
        fallback_used = False
        selected_model = None
        reason = ""

        # Check configured role overrides if static routing is requested
        if config.model_routing_strategy == "static":
            if target_role == "vision" and config.model_vision:
                selected_model = config.model_vision
                reason = "Static mapping: model_vision"
            elif target_role == "coding" and config.model_coding:
                selected_model = config.model_coding
                reason = "Static mapping: model_coding"
            elif target_role == "lightweight" and config.model_lightweight:
                selected_model = config.model_lightweight
                reason = "Static mapping: model_lightweight"
            elif target_role in ("reasoning", "recovery") and config.model_reasoning:
                selected_model = config.model_reasoning
                reason = f"Static mapping: model_{target_role}"

        if not selected_model:
            if candidates:
                # Select top ranked candidate by priority
                selected_model = candidates[0].model_name
                reason = f"Dynamic capability match: {target_role} -> {selected_model}"
            else:
                # Specialized model unavailable -> Fallback Escalation
                fallback_used = True
                # Priority 1: Configured fallback model
                fallback_candidate = self.registry.get_model(config.model_fallback)
                if fallback_candidate and (not has_probed_installed or fallback_candidate.installed):
                    selected_model = config.model_fallback
                    reason = f"Fallback to configured model_fallback '{config.model_fallback}' ({target_role} model unavailable)"
                # Priority 2: Base ollama_model
                elif self.registry.get_model(config.ollama_model):
                    selected_model = config.ollama_model
                    reason = f"Fallback to default ollama_model '{config.ollama_model}' ({target_role} model unavailable)"
                # Priority 3: Any enabled model in registry
                else:
                    enabled_models = self.registry.list_models(enabled_only=True)
                    if enabled_models:
                        selected_model = enabled_models[0].model_name
                        reason = f"Fallback to first enabled model '{selected_model}'"
                    else:
                        selected_model = config.ollama_model
                        reason = "Fallback to base config.ollama_model"

        model_switch = bool(self._last_selected_model and self._last_selected_model != selected_model)
        self._last_selected_model = selected_model

        logger.info(
            "MODEL_ROUTER decision model=%s role=%s capabilities=%s fallback=%s switch=%s reason=%s",
            selected_model, target_role, [c.value for c in req_caps], fallback_used, model_switch, reason,
        )

        return RoutingDecision(
            selected_model=selected_model,
            role=target_role,
            required_capabilities=[c.value for c in req_caps],
            reason=reason,
            fallback_used=fallback_used,
            model_switch=model_switch,
        )


# Global router singleton
model_router = ModelRouter()
