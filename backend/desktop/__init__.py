"""Desktop automation package for Agentic Pilot (Phase 4 / R06).

Provides native OS desktop interaction capabilities including mouse control,
keyboard input, screen capture, process inspection, Windows UI Automation
abstraction, element grounding, application launching, window management,
and deterministic verification.
"""

from backend.desktop.executor import DesktopExecutor, desktop_executor
from backend.desktop.models import (
    DesktopAction,
    DesktopActionResult,
    DesktopActionType,
    DesktopElement,
    DesktopObservation,
    DesktopRiskLevel,
    EnvironmentType,
    GoalCondition,
    GoalPredicate,
    GoalTarget,
    WindowInfo,
)

__all__ = [
    "DesktopExecutor",
    "desktop_executor",
    "DesktopAction",
    "DesktopActionResult",
    "DesktopActionType",
    "DesktopElement",
    "DesktopObservation",
    "DesktopRiskLevel",
    "EnvironmentType",
    "GoalCondition",
    "GoalPredicate",
    "GoalTarget",
    "WindowInfo",
]
