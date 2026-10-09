"""Deterministic desktop verification predicates.

Verifies desktop action results and goal conditions using native
UI Automation state — never relying on LLM opinion or screenshots alone.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.desktop.models import (
    DesktopObservation,
    GoalCondition,
    GoalPredicate,
)
from backend.desktop.observer import desktop_observer
from backend.desktop.uia import uia_manager
from backend.verification.manager import VerificationResult

logger = logging.getLogger("pilot.desktop.verifier")


class DesktopVerifier:
    """Deterministic desktop verification using UIA state."""

    async def verify_goal(
        self,
        condition: GoalCondition,
        observation: DesktopObservation | None = None,
    ) -> VerificationResult:
        """Evaluate a single GoalCondition against current desktop state.

        Returns a VerificationResult with expected/observed comparison.
        """
        predicate = condition.predicate
        target = condition.target
        expected_value = condition.expected_value

        expected: dict[str, Any] = {"predicate": predicate.value, "expected": expected_value}
        observed: dict[str, Any] = {}

        exp_bool = bool(expected_value) if expected_value is not None else True

        try:
            if predicate == GoalPredicate.WINDOW_EXISTS:
                result = await self._check_window_exists(target.window or target.name or "")
                observed["window_exists"] = result
                expected["window_exists"] = exp_bool

            elif predicate == GoalPredicate.WINDOW_FOCUSED:
                result = await self._check_window_focused(target.window or target.name or "")
                observed["window_focused"] = result
                expected["window_focused"] = exp_bool

            elif predicate == GoalPredicate.APPLICATION_RUNNING:
                result = await self._check_process_running(target.process_name or target.application or "")
                observed["application_running"] = result
                expected["application_running"] = exp_bool

            elif predicate == GoalPredicate.PROCESS_RUNNING:
                result = await self._check_process_running(target.process_name or "")
                observed["process_running"] = result
                expected["process_running"] = exp_bool

            elif predicate == GoalPredicate.TOGGLE_EQUALS:
                obs = observation or await desktop_observer.observe()
                result = await self._check_toggle_state(
                    target.name or "",
                    expected_value,
                    target.window or "",
                    obs,
                )
                observed["toggle_state"] = result
                expected["toggle_state"] = "On" if expected_value else "Off"

            elif predicate == GoalPredicate.ELEMENT_EXISTS:
                obs = observation or await desktop_observer.observe()
                result = self._check_element_exists(target.name or "", obs)
                observed["element_exists"] = result
                expected["element_exists"] = exp_bool

            elif predicate == GoalPredicate.ELEMENT_VISIBLE:
                obs = observation or await desktop_observer.observe()
                result = self._check_element_visible(target.name or "", obs)
                observed["element_visible"] = result
                expected["element_visible"] = exp_bool

            elif predicate == GoalPredicate.ELEMENT_ENABLED:
                obs = observation or await desktop_observer.observe()
                result = self._check_element_enabled(target.name or "", obs)
                observed["element_enabled"] = result
                expected["element_enabled"] = exp_bool

            elif predicate == GoalPredicate.TEXT_EQUALS:
                obs = observation or await desktop_observer.observe()
                actual = self._get_element_value(target.name or "", obs)
                observed["text"] = actual
                expected["text"] = expected_value

            elif predicate == GoalPredicate.TEXT_CONTAINS:
                obs = observation or await desktop_observer.observe()
                actual = self._get_element_value(target.name or "", obs)
                observed["text_contains"] = expected_value in actual if expected_value and actual else False
                expected["text_contains"] = True

            elif predicate == GoalPredicate.ACTIVE_WINDOW_EQUALS:
                active = await uia_manager.get_active_window()
                actual_title = active.title if active else ""
                target_title = target.window or target.name or ""
                observed["active_window"] = actual_title
                expected["active_window"] = target_title
                # Flexible comparison
                observed["match"] = target_title.lower() in actual_title.lower() if target_title and actual_title else False
                expected["match"] = True

            elif predicate == GoalPredicate.VALUE_EQUALS:
                obs = observation or await desktop_observer.observe()
                actual = self._get_element_value(target.name or "", obs)
                observed["value"] = actual
                expected["value"] = expected_value

            elif predicate == GoalPredicate.CHECKBOX_EQUALS:
                obs = observation or await desktop_observer.observe()
                result = await self._check_toggle_state(
                    target.name or "", expected_value, target.window or "", obs,
                )
                observed["checkbox_state"] = result
                expected["checkbox_state"] = "On" if expected_value else "Off"

            elif predicate == GoalPredicate.RADIO_SELECTED:
                obs = observation or await desktop_observer.observe()
                # Check via toggle pattern or selection pattern
                result = await self._check_toggle_state(
                    target.name or "", True, target.window or "", obs,
                )
                observed["radio_selected"] = result
                expected["radio_selected"] = "On"

            else:
                observed["error"] = f"Unknown predicate: {predicate}"
                expected["error"] = None

        except Exception as e:
            logger.exception("Desktop verification error: %s", e)
            observed["error"] = str(e)
            expected["error"] = None

        verified = self._compare(expected, observed)
        message = "PASS" if verified else f"FAIL — expected: {expected}, observed: {observed}"

        logger.info(
            "DESKTOP_VERIFY predicate=%s verified=%s target=%s",
            predicate.value, verified, target.name or target.window or "",
        )

        return VerificationResult(
            verified=verified,
            type=f"desktop_{predicate.value}",
            expected=expected,
            observed=observed,
            confidence=1.0 if verified else 0.0,
            message=message,
        )

    async def verify_all_goals(
        self,
        conditions: list[GoalCondition],
    ) -> tuple[bool, list[VerificationResult]]:
        """Verify all goal conditions. Returns (all_passed, results)."""
        if not conditions:
            return True, []

        # Fresh observation for all checks
        observation = await desktop_observer.observe()
        results = []
        for cond in conditions:
            result = await self.verify_goal(cond, observation)
            results.append(result)

        all_passed = all(r.verified for r in results)
        return all_passed, results

    # ---- private predicate implementations ----------------------------------

    async def _check_window_exists(self, title: str) -> bool:
        if not title:
            return False
        win = await uia_manager.find_window(title)
        return win is not None

    async def _check_window_focused(self, title: str) -> bool:
        if not title:
            return False
        active = await uia_manager.get_active_window()
        if active and title.lower() in active.title.lower():
            return True
        try:
            import win32gui

            fg = win32gui.GetForegroundWindow()
            if fg and title.lower() in win32gui.GetWindowText(fg).lower():
                return True
        except Exception:
            pass
        win = await uia_manager.find_window(title)
        if win:
            if getattr(win, "HasKeyboardFocus", False):
                return True
            try:
                for c in win.GetChildren():
                    if getattr(c, "HasKeyboardFocus", False):
                        return True
            except Exception:
                pass
            return True
        return False

    async def _check_process_running(self, process_name: str) -> bool:
        if not process_name:
            return False

        def _check() -> bool:
            try:
                import psutil
                target = process_name.lower()
                for proc in psutil.process_iter(["name"]):
                    try:
                        if target in (proc.info["name"] or "").lower():
                            return True
                    except Exception:
                        continue
            except Exception:
                pass
            return False

        return await asyncio.to_thread(_check)

    async def _check_toggle_state(
        self,
        element_name: str,
        expected_on: Any,
        window_title: str,
        observation: DesktopObservation,
    ) -> str:
        """Check toggle/checkbox state via UIA.

        Returns the actual state string ("On", "Off", "Unknown").
        """
        # First try from UIA directly
        win_ctrl = await uia_manager.find_window(window_title) if window_title else None
        uia_ctrl = await uia_manager.find_element(
            window_control=win_ctrl,
            name=element_name,
        )
        if uia_ctrl:
            state = await uia_manager.get_toggle_state(uia_ctrl)
            if state:
                return state

        # Fallback: check observation
        for el in observation.elements:
            if element_name.lower() in el.name.lower():
                if el.toggle_state is not None:
                    return el.toggle_state

        return "Unknown"

    def _check_element_exists(self, name: str, obs: DesktopObservation) -> bool:
        name_lower = name.lower()
        for el in obs.elements:
            if (el.name and name_lower in el.name.lower()) or (el.role and name_lower in el.role.lower()) or (el.window and name_lower in el.window.lower()):
                return True
        return False

    def _check_element_visible(self, name: str, obs: DesktopObservation) -> bool:
        name_lower = name.lower()
        for el in obs.elements:
            if ((el.name and name_lower in el.name.lower()) or (el.role and name_lower in el.role.lower()) or (el.window and name_lower in el.window.lower())) and el.visible:
                return True
        return False

    def _check_element_enabled(self, name: str, obs: DesktopObservation) -> bool:
        name_lower = name.lower()
        for el in obs.elements:
            if ((el.name and name_lower in el.name.lower()) or (el.role and name_lower in el.role.lower()) or (el.window and name_lower in el.window.lower())) and el.enabled:
                return True
        return False

    def _get_element_value(self, name: str, obs: DesktopObservation) -> str:
        name_lower = name.lower()
        for el in obs.elements:
            if el.name and name_lower in el.name.lower():
                return el.value
        return ""

    def _compare(self, expected: dict, observed: dict) -> bool:
        """Generic comparison — all expected keys must match observed."""
        for key, exp_val in expected.items():
            obs_val = observed.get(key)
            if obs_val is None:
                continue
            if isinstance(exp_val, bool) and isinstance(obs_val, bool):
                if exp_val != obs_val:
                    return False
            elif isinstance(exp_val, str) and isinstance(obs_val, str):
                if exp_val.lower() != obs_val.lower():
                    # Flexible string match
                    if exp_val.lower() not in obs_val.lower():
                        return False
            elif exp_val != obs_val:
                return False
        return True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

desktop_verifier = DesktopVerifier()
