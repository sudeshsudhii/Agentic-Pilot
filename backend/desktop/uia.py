"""Windows UI Automation abstraction layer.

Provides a clean Python interface to the Windows UIA tree using the
``uiautomation`` library. Falls back gracefully when running on
non-Windows platforms or headless CI.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from backend.desktop.models import DesktopElement, WindowInfo

logger = logging.getLogger("pilot.desktop.uia")

# ---------------------------------------------------------------------------
# Optional import — graceful degradation on non-Windows / CI
# ---------------------------------------------------------------------------

try:
    import uiautomation as auto

    UIA_AVAILABLE = True
except Exception as exc:
    auto = None  # type: ignore[assignment]
    UIA_AVAILABLE = False
    logger.warning("uiautomation not available (non-Windows or missing dependency): %s", exc)

# ---------------------------------------------------------------------------
# Control-type → semantic role mapping
# ---------------------------------------------------------------------------

_CONTROL_TYPE_ROLE_MAP: dict[str, str] = {
    "ButtonControl": "button",
    "CheckBoxControl": "checkbox",
    "ComboBoxControl": "combobox",
    "EditControl": "textbox",
    "HyperlinkControl": "link",
    "ImageControl": "image",
    "ListControl": "list",
    "ListItemControl": "listitem",
    "MenuControl": "menu",
    "MenuItemControl": "menuitem",
    "PaneControl": "pane",
    "RadioButtonControl": "radio",
    "ScrollBarControl": "scrollbar",
    "SliderControl": "slider",
    "TabControl": "tab",
    "TabItemControl": "tabitem",
    "TextControl": "text",
    "ToolTipControl": "tooltip",
    "TreeControl": "tree",
    "TreeItemControl": "treeitem",
    "WindowControl": "window",
    "GroupControl": "group",
    "HeaderControl": "header",
    "HeaderItemControl": "headeritem",
    "ProgressBarControl": "progressbar",
    "StatusBarControl": "statusbar",
    "ToolBarControl": "toolbar",
    "DataGridControl": "datagrid",
    "DataItemControl": "dataitem",
    "DocumentControl": "document",
    "SplitButtonControl": "splitbutton",
    "ThumbControl": "thumb",
    "TitleBarControl": "titlebar",
    "AppBarControl": "appbar",
    "SemanticZoomControl": "semanticzoom",
    "CustomControl": "custom",
}

# Patterns we query on elements
_PATTERN_NAMES = [
    "TogglePattern",
    "InvokePattern",
    "SelectionItemPattern",
    "ValuePattern",
    "ExpandCollapsePattern",
    "ScrollPattern",
    "RangeValuePattern",
]


@contextlib.contextmanager
def _thread_com_context():
    """Context manager for COM access in worker threads."""
    if auto and hasattr(auto, "UIAutomationInitializerInThread"):
        with auto.UIAutomationInitializerInThread():
            yield
    else:
        yield


class UIAutomationManager:
    """Thin abstraction over Windows UI Automation.

    All public methods run blocking COM work on a thread-pool so the
    async event loop is never blocked.
    """

    def __init__(self) -> None:
        self.available = UIA_AVAILABLE

    # ---- window enumeration ------------------------------------------------

    async def get_active_window(self) -> WindowInfo | None:
        """Return the currently focused / foreground window."""
        if not self.available:
            return None

        def _get() -> WindowInfo | None:
            with _thread_com_context():
                try:
                    ctrl = auto.GetForegroundControl()
                    if ctrl is None:
                        try:
                            import win32gui

                            fg = win32gui.GetForegroundWindow()
                            if fg:
                                ctrl = auto.ControlFromHandle(fg)
                        except Exception:
                            pass

                    if ctrl is None:
                        return None

                    rect = ctrl.BoundingRectangle
                    bbox = [rect.left, rect.top, rect.width(), rect.height()] if rect else []
                    pid = ctrl.ProcessId
                    proc_name = ""
                    try:
                        import psutil

                        proc_name = psutil.Process(pid).name()
                    except Exception:
                        pass
                    return WindowInfo(
                        title=ctrl.Name or "",
                        process_name=proc_name,
                        pid=pid,
                        is_focused=True,
                        is_minimized=False,
                        bbox=bbox,
                    )
                except Exception as e:
                    logger.warning("UIA get_active_window failed: %s", e)
                    return None

        return await asyncio.to_thread(_get)

    async def list_windows(self) -> list[WindowInfo]:
        """Return all visible top-level windows."""
        if not self.available:
            return []

        def _list() -> list[WindowInfo]:
            wins: list[WindowInfo] = []
            with _thread_com_context():
                try:
                    desktop = auto.GetRootControl()
                    for child in desktop.GetChildren():
                        try:
                            ct = child.ControlTypeName
                            if ct != "WindowControl":
                                continue
                            name = child.Name or ""
                            if not name:
                                continue
                            rect = child.BoundingRectangle
                            bbox = [rect.left, rect.top, rect.width(), rect.height()] if rect else []
                            pid = child.ProcessId
                            proc_name = ""
                            try:
                                import psutil

                                proc_name = psutil.Process(pid).name()
                            except Exception:
                                pass
                            wins.append(
                                WindowInfo(
                                    title=name,
                                    process_name=proc_name,
                                    pid=pid,
                                    is_focused=False,
                                    bbox=bbox,
                                )
                            )
                        except Exception:
                            continue

                    # If GetChildren returned empty, fallback to EnumWindows
                    if not wins:
                        try:
                            import win32gui

                            hwnds: list[int] = []

                            def _cb(h: int, _: Any) -> bool:
                                if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h):
                                    hwnds.append(h)
                                return True

                            win32gui.EnumWindows(_cb, None)
                            for h in hwnds[:30]:
                                try:
                                    c = auto.ControlFromHandle(h)
                                    if c and c.Name:
                                        rect = c.BoundingRectangle
                                        bbox = [rect.left, rect.top, rect.width(), rect.height()] if rect else []
                                        pid = c.ProcessId
                                        proc_name = ""
                                        try:
                                            import psutil

                                            proc_name = psutil.Process(pid).name()
                                        except Exception:
                                            pass
                                        wins.append(
                                            WindowInfo(
                                                title=c.Name,
                                                process_name=proc_name,
                                                pid=pid,
                                                is_focused=False,
                                                bbox=bbox,
                                            )
                                        )
                                except Exception:
                                    continue
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("UIA list_windows failed: %s", e)
            return wins[:30]  # bounded

        return await asyncio.to_thread(_list)

    # ---- find specific window -----------------------------------------------

    async def find_window(self, title_substring: str) -> Any | None:
        """Find a top-level window whose title contains *title_substring*.

        Returns the raw UIA control (for further inspection) or None.
        """
        if not self.available:
            return None

        def _find():
            with _thread_com_context():
                try:
                    target = title_substring.lower()
                    desktop = auto.GetRootControl()
                    for child in desktop.GetChildren():
                        try:
                            if child.ControlTypeName != "WindowControl":
                                continue
                            if target in (child.Name or "").lower():
                                return child
                        except Exception:
                            continue

                    # Fallback via EnumWindows
                    try:
                        import win32gui

                        found_hwnds: list[int] = []

                        def _cb(h: int, _: Any) -> bool:
                            if win32gui.IsWindowVisible(h) and target in win32gui.GetWindowText(h).lower():
                                found_hwnds.append(h)
                            return True

                        win32gui.EnumWindows(_cb, None)
                        if found_hwnds:
                            return auto.ControlFromHandle(found_hwnds[0])
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning("UIA find_window failed: %s", e)
                return None

        return await asyncio.to_thread(_find)

    # ---- focus / activate window -------------------------------------------

    async def focus_window(self, title_substring: str) -> bool:
        """Bring a window to the foreground by title substring."""
        if not self.available:
            return False

        def _focus() -> bool:
            with _thread_com_context():
                try:
                    target = title_substring.lower()
                    desktop = auto.GetRootControl()
                    for child in desktop.GetChildren():
                        try:
                            if child.ControlTypeName != "WindowControl":
                                continue
                            if target in (child.Name or "").lower():
                                try:
                                    child.SetFocus()
                                except Exception:
                                    pass
                                try:
                                    import ctypes

                                    ctypes.windll.user32.ShowWindow(child.NativeWindowHandle, 9)
                                    ctypes.windll.user32.SetForegroundWindow(child.NativeWindowHandle)
                                except Exception:
                                    pass
                                return True
                        except Exception:
                            continue

                    # Fallback via EnumWindows
                    try:
                        import ctypes
                        import win32gui

                        found_hwnds: list[int] = []

                        def _cb(h: int, _: Any) -> bool:
                            if win32gui.IsWindowVisible(h) and target in win32gui.GetWindowText(h).lower():
                                found_hwnds.append(h)
                            return True

                        win32gui.EnumWindows(_cb, None)
                        if found_hwnds:
                            hwnd = found_hwnds[0]
                            ctypes.windll.user32.ShowWindow(hwnd, 9)
                            win32gui.SetForegroundWindow(hwnd)
                            return True
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning("UIA focus_window failed: %s", e)
                return False

        return await asyncio.to_thread(_focus)

    # ---- element tree extraction -------------------------------------------

    async def get_elements(
        self,
        window_control: Any | None = None,
        max_depth: int = 8,
        max_elements: int = 200,
    ) -> list[DesktopElement]:
        """Walk the UIA tree from *window_control* and return normalized elements.

        If *window_control* is None, uses the foreground window.
        """
        if not self.available:
            return []

        def _walk() -> list[DesktopElement]:
            with _thread_com_context():
                root = window_control
                if root is None:
                    root = auto.GetForegroundControl()
                    if root is None:
                        try:
                            import win32gui

                            fg = win32gui.GetForegroundWindow()
                            if fg:
                                root = auto.ControlFromHandle(fg)
                        except Exception:
                            pass
                if root is None:
                    return []

                elements: list[DesktopElement] = []
                counter = [0]  # mutable counter
                win_title = root.Name or ""
                proc_name = ""
                try:
                    import psutil

                    proc_name = psutil.Process(root.ProcessId).name()
                except Exception:
                    pass

                def _recurse(ctrl: Any, depth: int) -> None:
                    if counter[0] >= max_elements or depth > max_depth:
                        return
                    try:
                        ct = ctrl.ControlTypeName or ""
                        name = ctrl.Name or ""
                        aid = ctrl.AutomationId or ""

                        # Skip invisible / tiny controls
                        rect = ctrl.BoundingRectangle
                        if rect:
                            w = rect.width()
                            h = rect.height()
                            if w < 2 or h < 2:
                                return
                            bbox = [rect.left, rect.top, w, h]
                        else:
                            bbox = []

                        role = _CONTROL_TYPE_ROLE_MAP.get(ct, ct.replace("Control", "").lower() or "unknown")

                        # Value / toggle state
                        value = ""
                        toggle_state = None
                        patterns: list[str] = []

                        try:
                            vp = ctrl.GetValuePattern()
                            if vp:
                                patterns.append("ValuePattern")
                                value = vp.Value or ""
                        except Exception:
                            pass
                        try:
                            tp = ctrl.GetTogglePattern()
                            if tp:
                                patterns.append("TogglePattern")
                                ts = tp.ToggleState
                                toggle_state = {0: "Off", 1: "On", 2: "Indeterminate"}.get(ts, str(ts))
                        except Exception:
                            pass
                        try:
                            ip = ctrl.GetInvokePattern()
                            if ip:
                                patterns.append("InvokePattern")
                        except Exception:
                            pass
                        try:
                            sip = ctrl.GetSelectionItemPattern()
                            if sip:
                                patterns.append("SelectionItemPattern")
                        except Exception:
                            pass
                        try:
                            ecp = ctrl.GetExpandCollapsePattern()
                            if ecp:
                                patterns.append("ExpandCollapsePattern")
                        except Exception:
                            pass

                        enabled = ctrl.IsEnabled if hasattr(ctrl, "IsEnabled") else True
                        focused = False
                        try:
                            focused = ctrl.HasKeyboardFocus
                        except Exception:
                            pass
                        is_kf = False
                        try:
                            is_kf = ctrl.IsKeyboardFocusable
                        except Exception:
                            pass

                        children_count = 0
                        try:
                            children_count = len(ctrl.GetChildren())
                        except Exception:
                            pass

                        counter[0] += 1
                        elem = DesktopElement(
                            id=f"desktop-el-{counter[0]:03d}",
                            role=role,
                            name=name,
                            automation_id=aid,
                            control_type=ct,
                            value=value,
                            enabled=enabled,
                            visible=True,  # passed rect filter
                            focused=focused,
                            bbox=bbox,
                            window=win_title,
                            application=proc_name,
                            children_count=children_count,
                            depth=depth,
                            toggle_state=toggle_state,
                            is_keyboard_focusable=is_kf,
                            patterns=patterns,
                        )
                        elements.append(elem)

                        # Recurse into children
                        for child in ctrl.GetChildren():
                            _recurse(child, depth + 1)

                    except Exception:
                        pass

                # Walk children of root
                for child in root.GetChildren():
                    _recurse(child, 1)

                return elements

        return await asyncio.to_thread(_walk)

    # ---- find single element by criteria -----------------------------------

    async def find_element(
        self,
        window_control: Any | None = None,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        role: str | None = None,
    ) -> Any | None:
        """Search for a specific UIA control matching the given criteria.

        Returns the raw UIA control for pattern invocation.
        """
        if not self.available:
            return None

        def _find():
            with _thread_com_context():
                root = window_control
                if root is None:
                    root = auto.GetForegroundControl()
                    if root is None:
                        try:
                            import win32gui

                            fg = win32gui.GetForegroundWindow()
                            if fg:
                                root = auto.ControlFromHandle(fg)
                        except Exception:
                            pass
                if root is None:
                    return None

                name_lower = (name or "").lower()
                aid_lower = (automation_id or "").lower()
                ct_match = control_type or ""

                def _search(ctrl: Any, depth: int) -> Any | None:
                    if depth > 10:
                        return None
                    try:
                        ctrl_name = (ctrl.Name or "").lower()
                        ctrl_aid = (ctrl.AutomationId or "").lower()
                        ctrl_ct = ctrl.ControlTypeName or ""

                        match = True
                        if name_lower and name_lower not in ctrl_name:
                            match = False
                        if aid_lower and aid_lower not in ctrl_aid:
                            match = False
                        if ct_match and ct_match not in ctrl_ct:
                            match = False

                        if match and (name_lower or aid_lower or ct_match):
                            return ctrl

                        for child in ctrl.GetChildren():
                            result = _search(child, depth + 1)
                            if result:
                                return result
                    except Exception:
                        pass
                    return None

                return _search(root, 0)

        return await asyncio.to_thread(_find)

    # ---- UIA pattern invocations ------------------------------------------

    async def invoke_element(self, uia_control: Any) -> bool:
        """Invoke the InvokePattern on a UIA control."""
        if not self.available or uia_control is None:
            return False

        def _invoke() -> bool:
            with _thread_com_context():
                try:
                    ip = uia_control.GetInvokePattern()
                    if ip:
                        ip.Invoke()
                        return True
                    # Fallback: try Click()
                    try:
                        uia_control.Click()
                        return True
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning("UIA invoke failed: %s", e)
                return False

        return await asyncio.to_thread(_invoke)

    async def toggle_element(self, uia_control: Any) -> str | None:
        """Toggle via TogglePattern. Returns new state string or None."""
        if not self.available or uia_control is None:
            return None

        def _toggle() -> str | None:
            with _thread_com_context():
                try:
                    tp = uia_control.GetTogglePattern()
                    if tp:
                        tp.Toggle()
                        time.sleep(0.3)
                        new_state = tp.ToggleState
                        return {0: "Off", 1: "On", 2: "Indeterminate"}.get(new_state, str(new_state))
                except Exception as e:
                    logger.warning("UIA toggle failed: %s", e)
                return None

        return await asyncio.to_thread(_toggle)

    async def get_toggle_state(self, uia_control: Any) -> str | None:
        """Read current toggle state without changing it."""
        if not self.available or uia_control is None:
            return None

        def _read() -> str | None:
            with _thread_com_context():
                try:
                    tp = uia_control.GetTogglePattern()
                    if tp:
                        ts = tp.ToggleState
                        return {0: "Off", 1: "On", 2: "Indeterminate"}.get(ts, str(ts))
                except Exception as e:
                    logger.warning("UIA get_toggle_state failed: %s", e)
                return None

        return await asyncio.to_thread(_read)

    async def set_value(self, uia_control: Any, value: str) -> bool:
        """Set text via ValuePattern."""
        if not self.available or uia_control is None:
            return False

        def _set() -> bool:
            with _thread_com_context():
                try:
                    vp = uia_control.GetValuePattern()
                    if vp:
                        vp.SetValue(value)
                        return True
                except Exception as e:
                    logger.warning("UIA set_value failed: %s", e)
                return False

        return await asyncio.to_thread(_set)

    async def get_value(self, uia_control: Any) -> str:
        """Read text via ValuePattern."""
        if not self.available or uia_control is None:
            return ""

        def _get() -> str:
            with _thread_com_context():
                try:
                    vp = uia_control.GetValuePattern()
                    if vp:
                        return vp.Value or ""
                except Exception as e:
                    logger.warning("UIA get_value failed: %s", e)
                return ""

        return await asyncio.to_thread(_get)

    async def click_element_center(self, uia_control: Any) -> bool:
        """Click the center of a UIA control's bounding rectangle."""
        if not self.available or uia_control is None:
            return False

        def _click() -> bool:
            with _thread_com_context():
                try:
                    rect = uia_control.BoundingRectangle
                    if rect:
                        cx = rect.left + rect.width() // 2
                        cy = rect.top + rect.height() // 2
                        try:
                            import pyautogui

                            pyautogui.click(cx, cy)
                            return True
                        except Exception:
                            uia_control.Click()
                            return True
                except Exception as e:
                    logger.warning("UIA click_element_center failed: %s", e)
                return False

        return await asyncio.to_thread(_click)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

uia_manager = UIAutomationManager()
