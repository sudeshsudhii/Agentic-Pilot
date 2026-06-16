"""Vision-Language fallback strategies for DOM extraction failures."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.llm.gateway import OllamaGateway


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


class VisionFallback:
    """Uses a vision model to plan actions when the DOM is insufficient."""

    async def plan_action(self, screenshot_bytes: bytes, goal: str, target: str | None) -> VisionAction:
        """Analyze the screenshot and return the next action."""
        gateway = OllamaGateway()
        prompt = f"Goal: {goal}\nTarget: {target or ''}\nWhat is the next action?"
        
        try:
            return await gateway.complete_structured(
                VISION_PLANNING_SYSTEM_PROMPT,
                prompt,
                VisionAction,
                image_bytes=screenshot_bytes
            )
        except Exception as e:
            return VisionAction(
                action_type="need_help",
                reasoning=f"Vision model failure: {e}"
            )
