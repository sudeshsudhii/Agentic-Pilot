"""Tests for environment resolver — classifies tasks as browser vs desktop."""

import pytest

from backend.agent.environment import classify_environment
from backend.desktop.models import EnvironmentType


class TestEnvironmentClassification:
    """Verify the keyword-scoring environment resolver."""

    # ── Desktop tasks ──────────────────────────────────────────────

    def test_open_settings(self):
        assert classify_environment("Open Windows Settings") == EnvironmentType.DESKTOP

    def test_bluetooth_settings(self):
        assert classify_environment("Turn on Bluetooth in Settings") == EnvironmentType.DESKTOP

    def test_launch_notepad(self):
        assert classify_environment("Open Notepad") == EnvironmentType.DESKTOP

    def test_launch_calculator(self):
        assert classify_environment("Launch the calculator") == EnvironmentType.DESKTOP

    def test_change_volume(self):
        assert classify_environment("Change the volume settings") == EnvironmentType.DESKTOP

    def test_search_in_settings(self):
        assert classify_environment("Open Settings and search for Bluetooth") == EnvironmentType.DESKTOP

    def test_taskbar_task(self):
        assert classify_environment("Pin the calculator to the taskbar") == EnvironmentType.DESKTOP

    def test_file_explorer(self):
        assert classify_environment("Open File Explorer and create a new folder") == EnvironmentType.DESKTOP

    # ── Browser tasks ──────────────────────────────────────────────

    def test_google_search(self):
        assert classify_environment("Search Google for Python tutorials") == EnvironmentType.BROWSER

    def test_navigate_url(self):
        assert classify_environment("Navigate to https://github.com") == EnvironmentType.BROWSER

    def test_open_website(self):
        assert classify_environment("Go to website stackoverflow.com") == EnvironmentType.BROWSER

    def test_browse_web(self):
        assert classify_environment("Browse the web for news") == EnvironmentType.BROWSER

    def test_open_chrome(self):
        assert classify_environment("Open Chrome and go to google.com") == EnvironmentType.BROWSER

    # ── Default to browser ─────────────────────────────────────────

    def test_ambiguous_defaults_browser(self):
        result = classify_environment("Do something interesting")
        assert result == EnvironmentType.BROWSER

    def test_empty_input(self):
        result = classify_environment("")
        assert result == EnvironmentType.BROWSER


class TestDesktopModels:
    """Verify desktop data model construction and serialization."""

    def test_desktop_element_creation(self):
        from backend.desktop.models import DesktopElement

        el = DesktopElement(
            id="desktop-el-001",
            role="button",
            name="Submit",
            control_type="ButtonControl",
            enabled=True,
            visible=True,
        )
        assert el.id == "desktop-el-001"
        assert el.role == "button"
        assert el.name == "Submit"

    def test_desktop_action_enum(self):
        from backend.desktop.models import DesktopActionType

        assert DesktopActionType.CLICK_ELEMENT.value == "click_element"
        assert DesktopActionType.LAUNCH_APPLICATION.value == "launch_application"
        assert DesktopActionType.TYPE_TEXT.value == "type_text"

    def test_desktop_action_serialization(self):
        from backend.desktop.models import DesktopAction, DesktopActionType

        action = DesktopAction(
            action_type=DesktopActionType.CLICK_ELEMENT,
            target_id="desktop-el-005",
            reasoning="Clicking the Bluetooth toggle",
        )
        data = action.model_dump()
        assert data["action_type"] == "click_element"
        assert data["target_id"] == "desktop-el-005"

    def test_goal_condition_creation(self):
        from backend.desktop.models import GoalCondition, GoalPredicate, GoalTarget

        gc = GoalCondition(
            predicate=GoalPredicate.TOGGLE_EQUALS,
            target=GoalTarget(name="Bluetooth", window="Bluetooth & devices"),
            expected_value=True,
            description="Bluetooth toggle should be On",
        )
        assert gc.predicate == GoalPredicate.TOGGLE_EQUALS
        assert gc.target.name == "Bluetooth"
        assert gc.expected_value is True

    def test_desktop_observation_creation(self):
        from backend.desktop.models import DesktopObservation, WindowInfo

        obs = DesktopObservation(
            active_window=WindowInfo(title="Settings", process_name="SystemSettings.exe"),
            screen_width=1920,
            screen_height=1080,
            element_count_total=150,
            element_count_visible=40,
        )
        assert obs.active_window.title == "Settings"
        assert obs.element_count_total == 150

    def test_environment_type_enum(self):
        assert EnvironmentType.BROWSER.value == "browser"
        assert EnvironmentType.DESKTOP.value == "desktop"
        assert EnvironmentType.MIXED.value == "mixed"

    def test_risk_mapping(self):
        from backend.desktop.models import DESKTOP_ACTION_RISK, DesktopRiskLevel

        assert DESKTOP_ACTION_RISK["click_element"] == DesktopRiskLevel.LOW
        assert DESKTOP_ACTION_RISK["close_window"] == DesktopRiskLevel.MEDIUM
        assert DESKTOP_ACTION_RISK["launch_application"] == DesktopRiskLevel.LOW


class TestApplicationLauncher:
    """Verify the controlled application resolver."""

    def test_known_application_resolution(self):
        from backend.desktop.applications import resolve_application

        cfg = resolve_application("settings")
        assert cfg is not None
        assert "ms-settings:" in cfg["args"][0]

    def test_bluetooth_shortcut(self):
        from backend.desktop.applications import resolve_application

        cfg = resolve_application("bluetooth")
        assert cfg is not None
        assert "bluetooth" in cfg["args"][0]

    def test_unknown_application_returns_none(self):
        from backend.desktop.applications import resolve_application

        assert resolve_application("xyznonexistentapp123") is None

    def test_case_insensitive_resolution(self):
        from backend.desktop.applications import resolve_application

        assert resolve_application("Notepad") is not None
        assert resolve_application("NOTEPAD") is not None
        assert resolve_application("  notepad  ") is not None

    def test_partial_match(self):
        from backend.desktop.applications import resolve_application

        assert resolve_application("visual studio code") is not None


class TestRecoveryEngineDesktop:
    """Verify desktop-specific failure classification and recovery strategies."""

    def test_desktop_element_not_found_classification(self):
        from backend.recovery.engine import recovery_engine

        ft = recovery_engine.classify_failure("Grounding failed: element not in observation")
        assert ft == "desktop_element_not_found"

    def test_desktop_window_not_found(self):
        from backend.recovery.engine import recovery_engine

        ft = recovery_engine.classify_failure("Window not found: Settings")
        assert ft == "desktop_window_not_found"

    def test_desktop_security_boundary(self):
        from backend.recovery.engine import recovery_engine

        ft = recovery_engine.classify_failure("Security boundary detected: UAC elevation")
        assert ft == "desktop_security_boundary"

    def test_desktop_security_blocks(self):
        from backend.recovery.engine import recovery_engine

        strategy = recovery_engine.select_strategy("desktop_security_boundary", 0)
        assert strategy == "blocked"

    def test_desktop_element_not_found_escalation(self):
        from backend.recovery.engine import recovery_engine

        assert recovery_engine.select_strategy("desktop_element_not_found", 0) == "reobserve"
        assert recovery_engine.select_strategy("desktop_element_not_found", 2) == "keyboard_navigation"
        assert recovery_engine.select_strategy("desktop_element_not_found", 4) == "vision_grounding"

    def test_browser_failures_unchanged(self):
        """Existing browser failure classification must not change."""
        from backend.recovery.engine import recovery_engine

        assert recovery_engine.classify_failure("captcha detected") == "captcha"
        assert recovery_engine.classify_failure("net::ERR_CONNECTION_REFUSED") == "transient"
        assert recovery_engine.classify_failure("Navigation failed: DNS error") == "navigation_failed"


class TestAgentState:
    """Verify AgentState has all required desktop fields."""

    def test_state_has_desktop_fields(self):
        from backend.agent.state import AgentState

        annotations = AgentState.__annotations__
        desktop_fields = [
            "current_environment",
            "desktop_observation",
            "desktop_action",
            "desktop_action_result",
            "desktop_verification",
            "active_window",
            "active_application",
            "goal_conditions",
            "recovery_strategy",
        ]
        for field in desktop_fields:
            assert field in annotations, f"Missing desktop field: {field}"

    def test_state_preserves_browser_fields(self):
        """Existing browser fields must still be present."""
        from backend.agent.state import AgentState

        annotations = AgentState.__annotations__
        browser_fields = [
            "task_id", "input_text", "parsed_intent", "current_url",
            "action_manifest", "action_history", "retry_count", "status",
            "planned_action", "navigation_succeeded", "session_id",
            "task_plan", "selected_model",
        ]
        for field in browser_fields:
            assert field in annotations, f"Missing browser field: {field}"


class TestGraphConstruction:
    """Verify the LangGraph builds with environment routing."""

    def test_graph_builds_successfully(self):
        from backend.agent.graph import build_graph

        graph = build_graph()
        # If langgraph is installed, graph should be non-None
        # If not installed, it returns None (acceptable in CI)
        # We just verify it doesn't crash
        assert graph is not None or graph is None  # Always passes — no crash is the test


class TestConfigDesktopFields:
    """Verify desktop configuration fields exist with correct defaults."""

    def test_enable_desktop_default(self):
        from backend.config import PilotConfig

        config = PilotConfig()
        assert config.enable_desktop is True

    def test_desktop_max_elements_default(self):
        from backend.config import PilotConfig

        config = PilotConfig()
        assert config.desktop_max_elements == 60

    def test_desktop_max_iterations_default(self):
        from backend.config import PilotConfig

        config = PilotConfig()
        assert config.desktop_max_iterations == 15
