"""Vision provider abstractions for Agentic Pilot."""

from __future__ import annotations
from abc import ABC, abstractmethod
from backend.vision.fallback import VisionAction, VisionFallback

class VisionProvider(ABC):
    """Base class for vision model providers."""
    
    @abstractmethod
    async def plan_action(self, screenshot_bytes: bytes, goal: str, target: str | None) -> VisionAction:
        pass

class OllamaVisionProvider(VisionProvider):
    """Ollama vision implementation."""
    
    def __init__(self):
        self.fallback = VisionFallback()
        
    async def plan_action(self, screenshot_bytes: bytes, goal: str, target: str | None) -> VisionAction:
        return await self.fallback.plan_action(screenshot_bytes, goal, target)

# Factory instance
vision_provider: VisionProvider = OllamaVisionProvider()
