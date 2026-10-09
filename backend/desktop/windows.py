"""Window management and DPI-aware coordinate handling.

Provides window operations (focus, switch, close) and correct
coordinate transformations for multi-monitor, DPI-scaled environments.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.desktop.uia import uia_manager

logger = logging.getLogger("pilot.desktop.windows")


class WindowManager:
    """Manages window focus, switching, and coordinate transformations."""

    async def focus_window(self, title_substring: str) -> bool:
        """Bring a window to the foreground by title match."""
        return await uia_manager.focus_window(title_substring)

    async def close_window(self, title_substring: str) -> bool:
        """Close a window by sending Alt+F4 after focusing it."""
        focused = await uia_manager.focus_window(title_substring)
        if not focused:
            return False

        def _close() -> bool:
            try:
                import pyautogui
                pyautogui.hotkey("alt", "F4")
                return True
            except Exception as e:
                logger.warning("close_window failed: %s", e)
                return False

        await asyncio.sleep(0.3)
        return await asyncio.to_thread(_close)

    async def get_dpi_scale(self) -> float:
        """Return the DPI scaling factor for the primary monitor."""

        def _dpi() -> float:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetProcessDPIAware()
                dc = user32.GetDC(0)
                dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)
                user32.ReleaseDC(0, dc)
                return dpi / 96.0
            except Exception:
                return 1.0

        return await asyncio.to_thread(_dpi)

    async def transform_coordinates(
        self,
        x: int,
        y: int,
        from_space: str = "screen",
        to_space: str = "pyautogui",
    ) -> tuple[int, int]:
        """Transform coordinates between coordinate spaces.

        Handles DPI scaling for correct PyAutoGUI targeting.

        Spaces:
            - screen: raw Windows screen coordinates (DPI-aware)
            - pyautogui: PyAutoGUI coordinate space
            - screenshot: pixel coordinates from a screenshot image
        """
        if from_space == to_space:
            return (x, y)

        dpi_scale = await self.get_dpi_scale()

        if from_space == "screenshot" and to_space == "pyautogui":
            # Screenshot pixels → PyAutoGUI (account for DPI)
            return (int(x / dpi_scale), int(y / dpi_scale))

        if from_space == "screen" and to_space == "pyautogui":
            # On Windows, PyAutoGUI uses logical coordinates when DPI-aware
            return (x, y)

        if from_space == "pyautogui" and to_space == "screen":
            return (x, y)

        logger.warning(
            "Unknown coordinate transform: %s -> %s, returning identity",
            from_space, to_space,
        )
        return (x, y)

    async def detect_security_boundary(self) -> tuple[bool, str]:
        """Detect if the current foreground is a security boundary.

        Checks for UAC prompts, credential dialogs, lock screen, etc.
        """

        def _detect() -> tuple[bool, str]:
            try:
                import ctypes
                import psutil

                # Check foreground window process
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd == 0:
                    return True, "No foreground window — possible secure desktop or lock screen"

                # Get process ID
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                try:
                    proc = psutil.Process(pid.value)
                    proc_name = proc.name().lower()

                    # Known security boundary processes
                    if proc_name in ("consent.exe",):
                        return True, "UAC elevation prompt detected (consent.exe)"
                    if proc_name in ("logonui.exe",):
                        return True, "Windows login/lock screen detected (LogonUI.exe)"
                    if proc_name in ("credentialproviderhost.exe",):
                        return True, "Credential dialog detected"
                except Exception:
                    pass

                # Check window title for credential patterns
                title_buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 256)
                title = title_buf.value.lower()

                security_titles = [
                    "user account control",
                    "windows security",
                    "credential",
                    "sign in",
                ]
                for pattern in security_titles:
                    if pattern in title:
                        return True, f"Security boundary detected: {title}"

            except Exception as e:
                logger.warning("Security boundary detection failed: %s", e)

            return False, ""

        return await asyncio.to_thread(_detect)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

window_manager = WindowManager()
