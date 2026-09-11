"""Vision-Language fallback strategies for DOM extraction failures."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.llm.gateway import OllamaGateway
from backend.llm.router import model_router


VISION_PLANNING_SYSTEM_PROMPT = """
You are a vision-language browser automation planner. You are given a screenshot of a webpage.
The user wants to accomplish the specified goal. 
Determine the single best action to take on the page based on its visual contents.
If you need to click or type, estimate the relative x/y coordinates (0.0 to 1.0) where the element is located.
For example, x=0.5, y=0.5 is the exact center of the screen.

Respond with valid JSON only. No markdown.
"""


class VisionAction(BaseModel):
    """Action selected by the vision model."""
    action_type: str = Field(description="One of: click, type_text, navigate, complete, need_help")
    text: str | None = Field(default=None, description="Text to type if action_type is type_text")
    url: str | None = Field(default=None, description="URL to navigate to if action_type is navigate")
    x_percent: float | None = Field(default=None, description="Relative X coordinate (0.0-1.0) to click")
    y_percent: float | None = Field(default=None, description="Relative Y coordinate (0.0-1.0) to click")
    reasoning: str = Field(description="Why this action was chosen")


import hashlib
import logging
from backend.config import get_config

logger = logging.getLogger("pilot.vision.fallback")


class VisionUnavailableError(Exception):
    """Raised when visual analysis is required but no compatible vision model is available."""
    pass


class VisionFallback:
    """Uses a vision model to plan actions when the DOM is insufficient with screenshot hash caching."""

    def __init__(self, max_cache_size: int = 30) -> None:
        self.max_cache_size = max_cache_size
        self._cache: dict[str, VisionAction] = {}

    def _get_key(self, screenshot_bytes: bytes, goal: str, target: str | None) -> str:
        h = hashlib.sha256()
        h.update(screenshot_bytes)
        h.update((goal or "").encode("utf-8"))
        h.update((target or "").encode("utf-8"))
        return h.hexdigest()

    async def check_vision_availability(self) -> tuple[bool, str | None]:
        """Verify whether a true vision-capable model is installed and accessible in Ollama."""
        gateway = OllamaGateway()
        from backend.llm.registry import model_registry, ModelCapability
        installed_names = await gateway.list_model_names()
        
        # Priority order for vision models
        vision_candidates = ["qwen3-vl:2b", "moondream", "moondream:latest", "qwen2.5-vl:7b"]
        for candidate in vision_candidates:
            cand_base = candidate.lower().split(":")[0]
            for inst in installed_names:
                if cand_base == inst.lower().split(":")[0]:
                    return True, inst

        # Check any other registered model with vision capability
        vision_metas = model_registry.get_models_with_capability(ModelCapability.VISION)
        for meta in vision_metas:
            meta_base = meta.model_name.lower().split(":")[0]
            for inst in installed_names:
                if meta_base == inst.lower().split(":")[0]:
                    return True, inst

        return False, None

    async def plan_action(self, screenshot_bytes: bytes, goal: str, target: str | None) -> VisionAction:
        """Analyze the screenshot and return the next action, reusing cached inference if unchanged."""
        config = get_config()
        is_avail, selected_vision_model = await self.check_vision_availability()
        if not is_avail or not selected_vision_model:
            logger.error("[VISION]\ncalled=false\nmodel=none\nimage_attached=false\nerror=VISION_UNAVAILABLE")
            raise VisionUnavailableError("VISION_UNAVAILABLE: No compatible vision model installed in Ollama.")

        key = self._get_key(screenshot_bytes, goal, target)
        if getattr(config, "vision_cache_enabled", True) and key in self._cache:
            logger.info("VISION_FALLBACK cache_hit key=%s (screen and goal unchanged, skipping VLM inference)", key[:10])
            cached = self._cache[key]
            logger.info("[VISION]\ncalled=true\nmodel=%s\nimage_attached=%s", selected_vision_model, bool(screenshot_bytes))
            logger.info("[VISION_RESPONSE]\n%s", cached.model_dump_json(indent=2))
            return cached

        gateway = OllamaGateway()
        prompt = f"Goal: {goal}\nTarget: {target or ''}\nWhat is the single best next action to take?"
        
        logger.info("[VISION]\ncalled=true\nmodel=%s\nimage_attached=%s", selected_vision_model, bool(screenshot_bytes))
        try:
            action = await gateway.complete_structured(
                VISION_PLANNING_SYSTEM_PROMPT,
                prompt,
                VisionAction,
                image_bytes=screenshot_bytes,
                model_override=selected_vision_model,
            )
            logger.info("[VISION_RESPONSE]\n%s", action.model_dump_json(indent=2))
            if getattr(config, "vision_cache_enabled", True):
                if len(self._cache) >= self.max_cache_size:
                    first_key = next(iter(self._cache))
                    del self._cache[first_key]
                self._cache[key] = action
            return action
        except Exception as e:
            logger.warning("VISION_EXECUTION_EXCEPTION error=%s", e)
            return VisionAction(
                action_type="need_help",
                reasoning=f"Vision model failure: {e}"
            )
