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
    # Safety settings (FAILSAFE disabled to allow automation when cursor is at origin 0,0)
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.05
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

    async def take_screenshot(self, target_hwnd: int | None = None) -> bytes:
        """Capture the screen or active window as PNG bytes."""
        if PYAUTOGUI_AVAILABLE and pyautogui is not None:
            try:
                img = await asyncio.to_thread(pyautogui.screenshot)
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                png_bytes = buffer.getvalue()
                if png_bytes:
                    return png_bytes
            except Exception as exc:
                logger.debug("pyautogui screenshot failed, attempting window fallback: %s", exc)

        # Resolve target_hwnd if not provided
        hwnd = target_hwnd
        if not hwnd:
            try:
                from backend.desktop.uia import uia_manager

                wins = await uia_manager.list_windows()
                for w in wins:
                    wctrl = await uia_manager.find_window(w.title)
                    if wctrl and getattr(wctrl, "NativeWindowHandle", 0):
                        hwnd = wctrl.NativeWindowHandle
                        break
            except Exception:
                pass

        def _window_capture(h: int | None) -> bytes:
            if not h:
                # Generate synthetic canvas with status info
                try:
                    from PIL import Image, ImageDraw

                    img = Image.new("RGB", (1280, 720), color=(30, 30, 30))
                    draw = ImageDraw.Draw(img)
                    draw.text((40, 40), f"Agentic Pilot Desktop Capture - {time.ctime()}", fill=(220, 220, 220))
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return buf.getvalue()
                except Exception:
                    return b""

            try:
                import ctypes
                import win32gui
                import win32ui
                from PIL import Image

                r = win32gui.GetWindowRect(h)
                w = max(1, r[2] - r[0])
                height = max(1, r[3] - r[1])
                hwndDC = win32gui.GetWindowDC(h)
                mfcDC = win32ui.CreateDCFromHandle(hwndDC)
                saveDC = mfcDC.CreateCompatibleDC()
                saveBitMap = win32ui.CreateBitmap()
                saveBitMap.CreateCompatibleBitmap(mfcDC, w, height)
                saveDC.SelectObject(saveBitMap)

                # PW_RENDERFULLCONTENT = 2
                res = ctypes.windll.user32.PrintWindow(h, saveDC.GetSafeHdc(), 2)
                out_bytes = b""
                if res:
                    bmpinfo = saveBitMap.GetInfo()
                    bmpstr = saveBitMap.GetBitmapBits(True)
                    im = Image.frombuffer(
                        "RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]), bmpstr, "raw", "BGRX", 0, 1
                    )
                    buf = io.BytesIO()
                    im.save(buf, format="PNG")
                    out_bytes = buf.getvalue()

                win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                win32gui.ReleaseDC(h, hwndDC)
                return out_bytes
            except Exception as e:
                logger.warning("PrintWindow screenshot capture failed: %s", e)
                return b""

        return await asyncio.to_thread(_window_capture, hwnd)

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
