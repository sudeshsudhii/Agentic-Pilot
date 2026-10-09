"""Strongly-typed models for Windows desktop automation.

Defines the core schema for desktop elements, observations, actions,
verification predicates, and goal conditions used throughout the
desktop environment pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Desktop Element (normalized UI Automation control)
# ---------------------------------------------------------------------------

class DesktopElement(BaseModel):
    """Normalized representation of a single Windows UI Automation control.

    The LLM reasons over these objects — never raw UIA COM objects.
    """

    id: str = Field(description="Stable internal element ID (e.g. desktop-el-001)")
    role: str = Field(description="Semantic role: button, toggle, checkbox, text, menu, etc.")
    name: str = Field(default="", description="Accessible name / label")
    automation_id: str = Field(default="", description="UIA AutomationId property")
    control_type: str = Field(default="", description="Raw UIA ControlType name")
    value: str = Field(default="", description="Current text/value content")
    enabled: bool = Field(default=True)
    visible: bool = Field(default=True)
    focused: bool = Field(default=False)
    bbox: list[int] = Field(default_factory=list, description="Bounding rect [x, y, w, h]")
    window: str = Field(default="", description="Parent window title")
    application: str = Field(default="", description="Owning application name")
    children_count: int = Field(default=0, description="Number of direct children")
    depth: int = Field(default=0, description="Depth in the UI tree from window root")
    toggle_state: str | None = Field(default=None, description="On/Off/Indeterminate for toggles")
    is_keyboard_focusable: bool = Field(default=False)
    patterns: list[str] = Field(default_factory=list, description="Supported UIA patterns")


# ---------------------------------------------------------------------------
# Desktop Observation (compact manifest sent to planner)
# ---------------------------------------------------------------------------

class WindowInfo(BaseModel):
    """Summary of a visible window."""

    title: str
    process_name: str = ""
    pid: int = 0
    is_focused: bool = False
    is_minimized: bool = False
    bbox: list[int] = Field(default_factory=list)


class DesktopObservation(BaseModel):
    """Bounded snapshot of the current Windows desktop state.

    Filtered and relevance-ranked before being sent to the planner.
    """

    active_window: WindowInfo | None = None
    visible_windows: list[WindowInfo] = Field(default_factory=list)
    screen_width: int = 1920
    screen_height: int = 1080
    dpi_scale: float = 1.0
    elements: list[DesktopElement] = Field(default_factory=list, description="Actionable UI controls")
    element_count_total: int = Field(default=0, description="Total elements before filtering")
    element_count_visible: int = Field(default=0, description="Visible elements before ranking")
    focused_element: DesktopElement | None = None
    screenshot_available: bool = False
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Desktop Action (typed executor input)
# ---------------------------------------------------------------------------

class DesktopActionType(str, Enum):
    """Supported desktop action types."""

    LAUNCH_APPLICATION = "launch_application"
    FOCUS_WINDOW = "focus_window"
    SWITCH_WINDOW = "switch_window"
    MOVE_MOUSE = "move_mouse"
    CLICK_ELEMENT = "click_element"
    CLICK_COORDINATE = "click_coordinate"
    DOUBLE_CLICK = "double_click"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    DRAG = "drag"
    WAIT = "wait"
    CLOSE_WINDOW = "close_window"
    CLIPBOARD_COPY = "clipboard_copy"
    CLIPBOARD_PASTE = "clipboard_paste"
    REQUEST_VISUAL_GROUNDING = "request_visual_grounding"
    REQUEST_REOBSERVATION = "request_reobservation"


class ExpectedEffect(BaseModel):
    """Structured expectation for post-action verification."""

    predicate: str = Field(description="Verification predicate name")
    target: str = Field(default="", description="Target element name or identifier")
    expected_value: Any = Field(default=None, description="Expected value after action")
    target_window: str = Field(default="", description="Expected window context")


class DesktopAction(BaseModel):
    """Single typed desktop action selected by the planner.

    All physical desktop actions flow through this model.
    The LLM CANNOT return arbitrary shell commands.
    """

    action_type: DesktopActionType
    target_id: str | None = Field(default=None, description="DesktopElement.id to interact with")
    application: str | None = Field(default=None, description="Application name for launch/focus")
    window_title: str | None = Field(default=None, description="Window title for focus/switch")
    text: str | None = Field(default=None, description="Text to type")
    key: str | None = Field(default=None, description="Key name for press_key")
    keys: list[str] | None = Field(default=None, description="Key combination for hotkey")
    x: int | None = Field(default=None, description="Screen X coordinate")
    y: int | None = Field(default=None, description="Screen Y coordinate")
    direction: str | None = Field(default=None, description="Scroll direction: up/down")
    clicks: int = Field(default=1, description="Number of clicks")
    button: str = Field(default="left", description="Mouse button: left/right/middle")
    expected_effect: ExpectedEffect | None = None
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    reasoning: str = Field(default="")


class DesktopActionResult(BaseModel):
    """Result of a single desktop action execution."""

    success: bool
    action_type: str
    target_id: str | None = None
    error: str | None = None
    duration_ms: int = 0
    grounding_level: str = Field(default="semantic", description="Level used: semantic/pattern/keyboard/vlm/coordinate")
    observed_state: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Goal Conditions (structured task completion criteria)
# ---------------------------------------------------------------------------

class GoalPredicate(str, Enum):
    """Supported verification predicates for goal conditions."""

    WINDOW_EXISTS = "window_exists"
    WINDOW_FOCUSED = "window_focused"
    APPLICATION_RUNNING = "application_running"
    PROCESS_RUNNING = "process_running"
    ELEMENT_EXISTS = "element_exists"
    ELEMENT_VISIBLE = "element_visible"
    ELEMENT_ENABLED = "element_enabled"
    TEXT_EQUALS = "text_equals"
    TEXT_CONTAINS = "text_contains"
    TOGGLE_EQUALS = "toggle_equals"
    CHECKBOX_EQUALS = "checkbox_equals"
    RADIO_SELECTED = "radio_selected"
    VALUE_EQUALS = "value_equals"
    ACTIVE_WINDOW_EQUALS = "active_window_equals"


class GoalTarget(BaseModel):
    """Target specification for a goal condition."""

    role: str | None = None
    name: str | None = None
    automation_id: str | None = None
    control_type: str | None = None
    window: str | None = None
    application: str | None = None
    process_name: str | None = None


class GoalCondition(BaseModel):
    """First-class representation of a task completion condition.

    Evaluated deterministically against desktop state — not by LLM opinion.
    """

    predicate: GoalPredicate
    target: GoalTarget
    expected_value: Any = Field(default=True)
    description: str = Field(default="")


# ---------------------------------------------------------------------------
# Environment Types
# ---------------------------------------------------------------------------

class EnvironmentType(str, Enum):
    """Task execution environment."""

    BROWSER = "browser"
    DESKTOP = "desktop"
    MIXED = "mixed"


# ---------------------------------------------------------------------------
# Desktop Risk Classification
# ---------------------------------------------------------------------------

class DesktopRiskLevel(str, Enum):
    """Risk levels for desktop actions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


DESKTOP_ACTION_RISK: dict[str, DesktopRiskLevel] = {
    "launch_application": DesktopRiskLevel.LOW,
    "focus_window": DesktopRiskLevel.LOW,
    "switch_window": DesktopRiskLevel.LOW,
    "move_mouse": DesktopRiskLevel.LOW,
    "click_element": DesktopRiskLevel.LOW,
    "click_coordinate": DesktopRiskLevel.LOW,
    "double_click": DesktopRiskLevel.LOW,
    "type_text": DesktopRiskLevel.LOW,
    "press_key": DesktopRiskLevel.LOW,
    "hotkey": DesktopRiskLevel.LOW,
    "scroll": DesktopRiskLevel.LOW,
    "drag": DesktopRiskLevel.MEDIUM,
    "wait": DesktopRiskLevel.LOW,
    "close_window": DesktopRiskLevel.MEDIUM,
    "clipboard_copy": DesktopRiskLevel.LOW,
    "clipboard_paste": DesktopRiskLevel.LOW,
    "request_visual_grounding": DesktopRiskLevel.LOW,
    "request_reobservation": DesktopRiskLevel.LOW,
}
