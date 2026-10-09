"""Desktop observer — produces bounded, compact DesktopObservation snapshots.

Collects raw UIA tree data, normalises it into DesktopElement objects,
applies visibility / actionability / relevance filters, and returns
a bounded manifest suitable for LLM planner context.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from backend.desktop.models import DesktopElement, DesktopObservation, WindowInfo
from backend.desktop.uia import uia_manager

logger = logging.getLogger("pilot.desktop.observer")


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------

# Roles that are rarely actionable on their own
_NOISE_ROLES = frozenset({
    "pane", "group", "titlebar", "thumb", "scrollbar",
    "header", "headeritem", "statusbar", "toolbar",
    "semanticzoom", "separator", "appbar",
})

# Control types to skip entirely
_SKIP_CONTROL_TYPES = frozenset({
    "SeparatorControl", "ThumbControl", "ScrollBarControl",
})


def _is_actionable(el: DesktopElement) -> bool:
    """Return True if the element is worth surfacing to the planner."""
    if not el.visible or not el.enabled:
        return False
    if el.control_type in _SKIP_CONTROL_TYPES:
        return False
    # Skip very deep unnamed controls
    if el.depth > 6 and not el.name and not el.automation_id:
        return False
    # Keep elements with names, automation IDs, patterns, or meaningful roles
    if el.name or el.automation_id or el.patterns or el.toggle_state is not None:
        return True
    if el.role not in _NOISE_ROLES:
        return True
    return False


def _relevance_score(el: DesktopElement, goal_keywords: list[str] | None = None) -> float:
    """Score an element's relevance for ranking (higher = more relevant)."""
    score = 0.0
    # Named elements are more useful
    if el.name:
        score += 3.0
    if el.automation_id:
        score += 1.0
    # Interactive patterns
    if el.patterns:
        score += 2.0 * len(el.patterns)
    # Toggles / checkboxes are high-value targets
    if el.toggle_state is not None:
        score += 5.0
    # Focused element is critically important
    if el.focused:
        score += 10.0
    # Keyboard focusable
    if el.is_keyboard_focusable:
        score += 1.0
    # Penalise noise roles
    if el.role in _NOISE_ROLES:
        score -= 2.0
    # Goal-keyword boosting
    if goal_keywords:
        name_lower = el.name.lower()
        aid_lower = el.automation_id.lower()
        for kw in goal_keywords:
            if kw in name_lower or kw in aid_lower:
                score += 8.0
    return score


class DesktopObserver:
    """Produces bounded desktop observation snapshots."""

    def __init__(self, max_elements: int = 60, max_uia_elements: int = 200) -> None:
        self.max_elements = max_elements
        self.max_uia_elements = max_uia_elements

    async def observe(
        self,
        goal_keywords: list[str] | None = None,
        target_window: str | None = None,
    ) -> DesktopObservation:
        """Capture current desktop state as a compact observation.

        Steps:
        1. Get active window + visible windows
        2. Walk UIA tree (bounded)
        3. Filter invisible / disabled / noise
        4. Rank by relevance
        5. Truncate to max_elements
        """
        started = time.perf_counter()

        # 1. Windows
        active_win = await uia_manager.get_active_window()
        visible_windows = await uia_manager.list_windows()

        # Mark the active window in the list
        if active_win:
            for w in visible_windows:
                if w.pid == active_win.pid and w.title == active_win.title:
                    w.is_focused = True

        # 2. Get screen info
        screen_w, screen_h, dpi_scale = await self._get_screen_info()

        # 3. Find target window control for UIA tree walk
        window_ctrl = None
        if target_window:
            window_ctrl = await uia_manager.find_window(target_window)
        elif active_win:
            window_ctrl = await uia_manager.find_window(active_win.title)

        # 4. Extract elements
        all_elements = await uia_manager.get_elements(
            window_control=window_ctrl,
            max_elements=self.max_uia_elements,
        )
        total_count = len(all_elements)

        # 5. Filter actionable
        actionable = [el for el in all_elements if _is_actionable(el)]
        visible_count = len(actionable)

        # 6. Rank by relevance
        scored = [(el, _relevance_score(el, goal_keywords)) for el in actionable]
        scored.sort(key=lambda x: x[1], reverse=True)

        # 7. Truncate
        bounded = [el for el, _ in scored[: self.max_elements]]

        # 8. Find focused element
        focused = None
        for el in bounded:
            if el.focused:
                focused = el
                break

        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "DESKTOP_OBSERVE total=%d visible=%d bounded=%d duration_ms=%d",
            total_count, visible_count, len(bounded), duration_ms,
        )

        return DesktopObservation(
            active_window=active_win,
            visible_windows=visible_windows[:10],
            screen_width=screen_w,
            screen_height=screen_h,
            dpi_scale=dpi_scale,
            elements=bounded,
            element_count_total=total_count,
            element_count_visible=visible_count,
            focused_element=focused,
            timestamp=datetime.now(UTC).isoformat(),
        )

    async def _get_screen_info(self) -> tuple[int, int, float]:
        """Return (width, height, dpi_scale) for the primary monitor."""

        def _info() -> tuple[int, int, float]:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetProcessDPIAware()
                w = user32.GetSystemMetrics(0)
                h = user32.GetSystemMetrics(1)
                # DPI scale
                try:
                    dc = ctypes.windll.user32.GetDC(0)
                    dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
                    ctypes.windll.user32.ReleaseDC(0, dc)
                    scale = dpi / 96.0
                except Exception:
                    scale = 1.0
                return (w, h, scale)
            except Exception:
                return (1920, 1080, 1.0)

        return await asyncio.to_thread(_info)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

desktop_observer = DesktopObserver()
