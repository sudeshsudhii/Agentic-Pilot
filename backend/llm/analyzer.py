"""CapabilityAnalyzer for determining task requirements in Agentic Pilot.

Analyzes natural language tasks, parsed intents, and environment context to establish:
- Reasoning requirements
- Visual perception requirements
- Coding/diagnostic requirements
- Tool-calling requirements
- Task complexity tier
- Target model role and required capabilities
"""

from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, Field

from backend.llm.registry import ModelCapability, ModelRole

logger = logging.getLogger("pilot.llm.analyzer")

CODING_KEYWORDS = {
    "code", "python", "script", "syntax", "refactor", "bug", "debug", "unit test",
    "modify_file", "write code", "test_code", "function", "class", "ast", "lint",
    "compile", "exception", "traceback", "fix error",
}

VISION_KEYWORDS = {
    "screenshot", "screen", "visual", "gui", "button location", "visual element",
    "look at", "image", "canvas", "coord", "pixel",
}

REASONING_KEYWORDS = {
    "plan", "decompose", "analyze", "evaluate", "compare", "strategy", "reason",
    "why", "deduce", "invariant", "complex", "multi-step",
}


class TaskCapabilityRequirements(BaseModel):
    """Structured requirements produced by CapabilityAnalyzer."""

    target_role: ModelRole = ModelRole.GENERAL
    required_capabilities: list[ModelCapability] = Field(default_factory=list)
    reasoning_required: bool = False
    vision_required: bool = False
    coding_required: bool = False
    tool_use_required: bool = True
    complexity: str = "medium"  # "low", "medium", "high"
    requires_long_context: bool = False
    analysis_reason: str = ""


class CapabilityAnalyzer:
    """Analyzes task inputs to determine required model capabilities and role.

    Implements fast deterministic classification to eliminate unnecessary LLM calls
    while guaranteeing accurate capability mapping.
    """

    def analyze(
        self,
        task_text: str = "",
        action_type: str | None = None,
        task_type: str = "general",
        complexity: str = "medium",
        has_image: bool = False,
        is_recovery: bool = False,
        context_length_tokens: int = 0,
        forced_capabilities: list[ModelCapability | str] | None = None,
    ) -> TaskCapabilityRequirements:
        """Determine capabilities required for the subtask."""
        text_lower = task_text.lower()
        act_lower = (action_type or "").lower()
        type_lower = (task_type or "general").lower()

        # 0. Check Forced Capabilities Override
        if forced_capabilities:
            caps = [
                c if isinstance(c, ModelCapability) else ModelCapability(str(c).lower())
                for c in forced_capabilities
            ]
            role = ModelRole.GENERAL
            if ModelCapability.VISION in caps:
                role = ModelRole.VISION
            elif ModelCapability.CODING in caps:
                role = ModelRole.CODER
            elif ModelCapability.RECOVERY in caps:
                role = ModelRole.RECOVERY
            elif ModelCapability.PLANNING in caps or ModelCapability.REASONING in caps:
                role = ModelRole.PLANNER
            elif ModelCapability.LIGHTWEIGHT in caps:
                role = ModelRole.LIGHTWEIGHT

            return TaskCapabilityRequirements(
                target_role=role,
                required_capabilities=caps,
                reasoning_required=(ModelCapability.REASONING in caps or ModelCapability.PLANNING in caps),
                vision_required=(ModelCapability.VISION in caps),
                coding_required=(ModelCapability.CODING in caps),
                analysis_reason="Explicit forced capabilities specification",
            )

        # 1. Recovery Escalation Check
        if is_recovery or type_lower == "recovery":
            return TaskCapabilityRequirements(
                target_role=ModelRole.RECOVERY,
                required_capabilities=[ModelCapability.RECOVERY, ModelCapability.REASONING],
                reasoning_required=True,
                tool_use_required=True,
                complexity="high",
                analysis_reason="Failure recovery requires strong reasoning specialist",
            )

        # 2. Vision Perception Check
        if has_image or act_lower == "screenshot" or type_lower in ("vision", "gui_understanding", "visual_interaction") or any(kw in text_lower for kw in VISION_KEYWORDS):
            return TaskCapabilityRequirements(
                target_role=ModelRole.VISION,
                required_capabilities=[ModelCapability.VISION, ModelCapability.GUI_UNDERSTANDING],
                vision_required=True,
                tool_use_required=True,
                complexity="medium",
                analysis_reason="Visual / GUI perception requires Vision-Language specialist",
            )

        # 3. Coding & Diagnostic Check
        if (
            type_lower in ("coding", "code_generation", "debugging", "test_generation")
            or act_lower in ("code", "modify_file", "debug", "test_code", "run_script")
            or any(kw in text_lower for kw in CODING_KEYWORDS)
        ):
            return TaskCapabilityRequirements(
                target_role=ModelRole.CODER,
                required_capabilities=[ModelCapability.CODING, ModelCapability.DEBUGGING],
                coding_required=True,
                tool_use_required=True,
                complexity="high",
                analysis_reason="Code synthesis, inspection, or diagnostics requires Coding specialist",
            )

        # 4. Long Context Check
        requires_long_context = context_length_tokens > 3000

        # 5. Planning & Complex Decomposition Check
        is_complex = (
            type_lower in ("planning", "task_decomposition")
            or complexity == "high"
            or any(w in text_lower for w in [" and ", " then ", " after ", " followed by ", ",", ";"])
            or len(text_lower.split()) > 10
            or any(kw in text_lower for kw in REASONING_KEYWORDS)
        )

        # 6. Fast / Lightweight Tier for Routine Operations
        if (
            type_lower in ("intent_parsing", "fast_filter")
            or (complexity == "low" and not is_complex)
            or (act_lower in ("navigate", "open", "go", "browse") and not is_complex)
        ):
            return TaskCapabilityRequirements(
                target_role=ModelRole.LIGHTWEIGHT,
                required_capabilities=[ModelCapability.LIGHTWEIGHT, ModelCapability.FAST],
                reasoning_required=False,
                tool_use_required=True,
                complexity="low",
                analysis_reason="Routine subtask mapped to Fast/Lightweight tier to conserve compute",
            )

        if is_complex:
            caps = [ModelCapability.PLANNING, ModelCapability.REASONING]
            if requires_long_context:
                caps.append(ModelCapability.LONG_CONTEXT)
            return TaskCapabilityRequirements(
                target_role=ModelRole.PLANNER,
                required_capabilities=caps,
                reasoning_required=True,
                tool_use_required=True,
                complexity="high",
                requires_long_context=requires_long_context,
                analysis_reason="Complex multi-step task requires Planning/Reasoning specialist",
            )

        # 7. Default General Executor
        return TaskCapabilityRequirements(
            target_role=ModelRole.GENERAL,
            required_capabilities=[ModelCapability.GENERAL],
            reasoning_required=False,
            tool_use_required=True,
            complexity="medium",
            analysis_reason="Standard browser operation mapped to General executor tier",
        )


# Global singleton analyzer
capability_analyzer = CapabilityAnalyzer()
