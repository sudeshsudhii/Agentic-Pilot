"""Native desktop interaction executor for Agentic Pilot (Phase 4 / R06).

Provides native OS interaction capabilities:
- Mouse clicks, movements, drags
- Keyboard typing, shortcuts, hotkeys
- Full-screen capture and region screenshots
- Running process inspection via psutil
- Safe failsafes and headless environment tolerance
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Any

from backend.llm.parser import ActionResult

logger = logging.getLogger("pilot.desktop.executor")

# Optional imports for native desktop control
try:
    import pyautogui
    # Safety settings
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    PYAUTOGUI_AVAILABLE = True
except Exception as exc:
    pyautogui = None  # type: ignore
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not available on this platform/environment: %s", exc)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except Exception as exc:
    psutil = None  # type: ignore
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available: %s", exc)


class DesktopExecutor:
    """Executes actions on the native OS desktop."""

    def __init__(self) -> None:
        self.enabled = PYAUTOGUI_AVAILABLE

    def is_available(self) -> bool:
        """Check if native desktop control is available."""
        return PYAUTOGUI_AVAILABLE

    async def click(
        self,
        x: int,
        y: int,
        clicks: int = 1,
        button: str = "left",
        duration: float = 0.2,
    ) -> ActionResult:
        """Click at the specified screen coordinates."""
        started = time.perf_counter()
        if not PYAUTOGUI_AVAILABLE or pyautogui is None:
            return ActionResult(
                success=False,
                action_type="desktop_click",
                element_id=f"coord_{x}_{y}",
                error="pyautogui is not available on this system",
                page_state_after="unsupported",
                duration_ms=0,
            )

        try:
            await asyncio.to_thread(
                pyautogui.click,
                x=x,
                y=y,
                clicks=clicks,
                button=button,
                duration=duration,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info("DESKTOP click x=%d y=%d button=%s duration_ms=%d", x, y, button, duration_ms)
            return ActionResult(
                success=True,
                action_type="desktop_click",
                element_id=f"coord_{x}_{y}",
                error=None,
                page_state_after="ready",
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("DESKTOP click failed: %s", exc)
            return ActionResult(
                success=False,
                action_type="desktop_click",
                element_id=f"coord_{x}_{y}",
                error=str(exc),
                page_state_after="error",
                duration_ms=duration_ms,
            )

    async def type_text(
        self,
        text: str,
        interval: float = 0.05,
    ) -> ActionResult:
        """Type text into the currently active desktop window/input."""
        started = time.perf_counter()
        if not PYAUTOGUI_AVAILABLE or pyautogui is None:
            return ActionResult(
                success=False,
                action_type="desktop_type",
                element_id="active_window",
                error="pyautogui is not available",
                page_state_after="unsupported",
                duration_ms=0,
            )

        try:
            await asyncio.to_thread(pyautogui.write, text, interval=interval)
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info("DESKTOP type_text length=%d duration_ms=%d", len(text), duration_ms)
            return ActionResult(
                success=True,
                action_type="desktop_type",
                element_id="active_window",
                error=None,
                page_state_after="ready",
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ActionResult(
                success=False,
                action_type="desktop_type",
                element_id="active_window",
                error=str(exc),
                page_state_after="error",
                duration_ms=duration_ms,
            )

    async def hotkey(self, *keys: str) -> ActionResult:
        """Send a keyboard shortcut/hotkey combination (e.g. 'ctrl', 'c')."""
        started = time.perf_counter()
        if not PYAUTOGUI_AVAILABLE or pyautogui is None:
            return ActionResult(
                success=False,
                action_type="desktop_hotkey",
                element_id="+".join(keys),
                error="pyautogui is not available",
                page_state_after="unsupported",
                duration_ms=0,
            )

        try:
            await asyncio.to_thread(pyautogui.hotkey, *keys)
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info("DESKTOP hotkey keys=%s duration_ms=%d", "+".join(keys), duration_ms)
            return ActionResult(
                success=True,
                action_type="desktop_hotkey",
                element_id="+".join(keys),
                error=None,
                page_state_after="ready",
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ActionResult(
                success=False,
                action_type="desktop_hotkey",
                element_id="+".join(keys),
                error=str(exc),
                page_state_after="error",
                duration_ms=duration_ms,
            )

    async def take_screenshot(self) -> bytes:
        """Capture the primary display screen as PNG bytes."""
        if not PYAUTOGUI_AVAILABLE or pyautogui is None:
            return b""

        try:
            img = await asyncio.to_thread(pyautogui.screenshot)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as exc:
            logger.warning("DESKTOP screenshot failed: %s", exc)
            return b""

    async def get_screen_size(self) -> tuple[int, int]:
        """Return the (width, height) of the primary display."""
        if not PYAUTOGUI_AVAILABLE or pyautogui is None:
            return (1920, 1080)
        try:
            size = await asyncio.to_thread(pyautogui.size)
            return (size.width, size.height)
        except Exception:
            return (1920, 1080)

    async def list_processes(self, filter_name: str | None = None) -> list[dict[str, Any]]:
        """List running system processes using psutil."""
        if not PSUTIL_AVAILABLE or psutil is None:
            return []

        def _get_procs() -> list[dict[str, Any]]:
            procs = []
            for p in psutil.process_iter(["pid", "name", "status"]):
                try:
                    info = p.info
                    name = info.get("name") or ""
                    if not filter_name or filter_name.lower() in name.lower():
                        procs.append({
                            "pid": info.get("pid"),
                            "name": name,
                            "status": info.get("status"),
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return procs[:50]

        try:
            return await asyncio.to_thread(_get_procs)
        except Exception as exc:
            logger.warning("DESKTOP list_processes failed: %s", exc)
            return []


desktop_executor = DesktopExecutor()
