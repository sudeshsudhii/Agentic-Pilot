"""Five-level desktop grounding strategy.

Resolves a target element using an escalation chain:
1. Semantic UIA grounding (name, role, automationId)
2. Alternate UIA pattern interaction
3. Deterministic keyboard navigation
4. Local VLM screenshot grounding
5. Coordinate fallback from fresh observation
"""

from __future__ import annotations

import asyncio
import logging
import time

from backend.desktop.models import DesktopAction, DesktopActionType, DesktopElement, DesktopObservation
from backend.desktop.uia import uia_manager

logger = logging.getLogger("pilot.desktop.grounding")


class GroundingResult:
    """Result of attempting to ground a target element."""

    def __init__(
        self,
        success: bool,
        level: str,
        uia_control: object | None = None,
        element: DesktopElement | None = None,
        coordinates: tuple[int, int] | None = None,
        error: str | None = None,
    ):
        self.success = success
        self.level = level
        self.uia_control = uia_control
        self.element = element
        self.coordinates = coordinates
        self.error = error


class DesktopGrounding:
    """Multi-level element grounding strategy."""

    async def ground_target(
        self,
        action: DesktopAction,
        observation: DesktopObservation,
        window_title: str | None = None,
    ) -> GroundingResult:
        """Attempt to ground the action's target using the escalation chain.

        Returns a GroundingResult with the UIA control, coordinates, or error.
        """

        # Level 1: Semantic UIA grounding
        result = await self._ground_semantic(action, observation, window_title)
        if result.success:
            return result

        # Level 2: Alternate UIA patterns
        result = await self._ground_alternate_uia(action, observation, window_title)
        if result.success:
            return result

        # Level 3: Coordinate from element bounding box (if element found in observation)
        result = await self._ground_from_observation(action, observation)
        if result.success:
            return result

        # Level 4: VLM grounding (placeholder — returns failure, triggering REQUEST_VISUAL_GROUNDING)
        # Not invoked here — the planner will request it explicitly

        # Level 5: Direct coordinate (if provided in the action)
        if action.x is not None and action.y is not None:
            return GroundingResult(
                success=True,
                level="coordinate",
                coordinates=(action.x, action.y),
            )

        return GroundingResult(
            success=False,
            level="failed",
            error=f"Could not ground target: {action.target_id or action.application or 'unknown'}",
        )

    async def _ground_semantic(
        self,
        action: DesktopAction,
        observation: DesktopObservation,
        window_title: str | None,
    ) -> GroundingResult:
        """Level 1: Find element by name, automationId, or control type."""
        target_id = action.target_id
        if not target_id:
            return GroundingResult(success=False, level="semantic", error="No target_id specified")

        # Find the element in the observation
        target_element = None
        for el in observation.elements:
            if el.id == target_id:
                target_element = el
                break

        if target_element is None:
            return GroundingResult(success=False, level="semantic", error=f"Element {target_id} not in observation")

        # Find the actual UIA control
        win_ctrl = None
        if window_title:
            win_ctrl = await uia_manager.find_window(window_title)

        uia_control = await uia_manager.find_element(
            window_control=win_ctrl,
            name=target_element.name or None,
            automation_id=target_element.automation_id or None,
            control_type=target_element.control_type or None,
        )

        if uia_control is not None:
            logger.info(
                "GROUNDING level=semantic target=%s name=%s found=True",
                target_id, target_element.name,
            )
            return GroundingResult(
                success=True,
                level="semantic",
                uia_control=uia_control,
                element=target_element,
            )

        return GroundingResult(success=False, level="semantic", error="UIA control not found for element")

    async def _ground_alternate_uia(
        self,
        action: DesktopAction,
        observation: DesktopObservation,
        window_title: str | None,
    ) -> GroundingResult:
        """Level 2: Try broader search criteria."""
        target_id = action.target_id
        if not target_id:
            return GroundingResult(success=False, level="pattern", error="No target_id")

        target_element = None
        for el in observation.elements:
            if el.id == target_id:
                target_element = el
                break

        if target_element is None:
            return GroundingResult(success=False, level="pattern", error="Element not in observation")

        win_ctrl = None
        if window_title:
            win_ctrl = await uia_manager.find_window(window_title)

        # Try just by name (broader)
        if target_element.name:
            uia_control = await uia_manager.find_element(
                window_control=win_ctrl,
                name=target_element.name,
            )
            if uia_control:
                logger.info("GROUNDING level=pattern target=%s name=%s found=True", target_id, target_element.name)
                return GroundingResult(
                    success=True,
                    level="pattern",
                    uia_control=uia_control,
                    element=target_element,
                )

        # Try just by automationId
        if target_element.automation_id:
            uia_control = await uia_manager.find_element(
                window_control=win_ctrl,
                automation_id=target_element.automation_id,
            )
            if uia_control:
                logger.info("GROUNDING level=pattern target=%s aid=%s found=True", target_id, target_element.automation_id)
                return GroundingResult(
                    success=True,
                    level="pattern",
                    uia_control=uia_control,
                    element=target_element,
                )

        return GroundingResult(success=False, level="pattern", error="Alternate UIA search failed")

    async def _ground_from_observation(
        self,
        action: DesktopAction,
        observation: DesktopObservation,
    ) -> GroundingResult:
        """Level 3: Use bounding box from the fresh observation as coordinates."""
        target_id = action.target_id
        if not target_id:
            return GroundingResult(success=False, level="observation_bbox", error="No target_id")

        target_element = None
        for el in observation.elements:
            if el.id == target_id:
                target_element = el
                break

        if target_element is None or not target_element.bbox or len(target_element.bbox) < 4:
            return GroundingResult(success=False, level="observation_bbox", error="No bounding box")

        # Calculate center of bounding box
        x, y, w, h = target_element.bbox
        cx = x + w // 2
        cy = y + h // 2

        logger.info(
            "GROUNDING level=observation_bbox target=%s coords=(%d,%d)",
            target_id, cx, cy,
        )
        return GroundingResult(
            success=True,
            level="observation_bbox",
            element=target_element,
            coordinates=(cx, cy),
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

desktop_grounding = DesktopGrounding()
