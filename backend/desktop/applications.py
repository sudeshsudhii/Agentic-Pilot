"""Controlled application launcher for desktop automation.

Maps semantic application names to safe launch mechanisms.
The LLM never provides arbitrary shell commands — only application names
from this controlled resolver.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from typing import Any

from backend.desktop.models import DesktopActionResult

logger = logging.getLogger("pilot.desktop.applications")


# ---------------------------------------------------------------------------
# Known safe application mappings (Windows)
# ---------------------------------------------------------------------------

_KNOWN_APPLICATIONS: dict[str, dict[str, Any]] = {
    # Windows built-in
    "settings": {"cmd": "start", "args": ["ms-settings:"], "shell": True, "process": "SystemSettings.exe"},
    "bluetooth": {"cmd": "start", "args": ["ms-settings:bluetooth"], "shell": True, "process": "SystemSettings.exe"},
    "bluetooth settings": {"cmd": "start", "args": ["ms-settings:bluetooth"], "shell": True, "process": "SystemSettings.exe"},
    "wifi": {"cmd": "start", "args": ["ms-settings:network-wifi"], "shell": True, "process": "SystemSettings.exe"},
    "display": {"cmd": "start", "args": ["ms-settings:display"], "shell": True, "process": "SystemSettings.exe"},
    "sound": {"cmd": "start", "args": ["ms-settings:sound"], "shell": True, "process": "SystemSettings.exe"},
    "notepad": {"cmd": "notepad.exe", "args": [], "process": "notepad.exe"},
    "calculator": {"cmd": "calc.exe", "args": [], "process": "CalculatorApp.exe"},
    "file explorer": {"cmd": "explorer.exe", "args": [], "process": "explorer.exe"},
    "explorer": {"cmd": "explorer.exe", "args": [], "process": "explorer.exe"},
    "task manager": {"cmd": "taskmgr.exe", "args": [], "process": "Taskmgr.exe"},
    "command prompt": {"cmd": "cmd.exe", "args": [], "process": "cmd.exe"},
    "powershell": {"cmd": "powershell.exe", "args": [], "process": "powershell.exe"},
    "paint": {"cmd": "mspaint.exe", "args": [], "process": "mspaint.exe"},
    "wordpad": {"cmd": "wordpad.exe", "args": [], "process": "wordpad.exe"},
    "snipping tool": {"cmd": "snippingtool.exe", "args": [], "process": "SnippingTool.exe"},
    "control panel": {"cmd": "control.exe", "args": [], "process": "control.exe"},

    # Common third-party
    "chrome": {"cmd": "start", "args": ["chrome"], "shell": True, "process": "chrome.exe"},
    "firefox": {"cmd": "start", "args": ["firefox"], "shell": True, "process": "firefox.exe"},
    "edge": {"cmd": "start", "args": ["msedge"], "shell": True, "process": "msedge.exe"},
    "microsoft edge": {"cmd": "start", "args": ["msedge"], "shell": True, "process": "msedge.exe"},
    "outlook": {"cmd": "start", "args": ["outlook"], "shell": True, "process": "OUTLOOK.EXE"},
    "word": {"cmd": "start", "args": ["winword"], "shell": True, "process": "WINWORD.EXE"},
    "excel": {"cmd": "start", "args": ["excel"], "shell": True, "process": "EXCEL.EXE"},
    "vscode": {"cmd": "code", "args": [], "process": "Code.exe"},
    "visual studio code": {"cmd": "code", "args": [], "process": "Code.exe"},
    "spotify": {"cmd": "start", "args": ["spotify:"], "shell": True, "process": "Spotify.exe"},
    "teams": {"cmd": "start", "args": ["msteams:"], "shell": True, "process": "ms-teams.exe"},
    "terminal": {"cmd": "wt.exe", "args": [], "process": "WindowsTerminal.exe"},
    "windows terminal": {"cmd": "wt.exe", "args": [], "process": "WindowsTerminal.exe"},
}


def _normalize_app_name(name: str) -> str:
    """Normalize an application name for lookup."""
    return name.strip().lower().replace("_", " ").replace("-", " ")


def resolve_application(name: str) -> dict[str, Any] | None:
    """Resolve a semantic application name to launch configuration.

    Returns None if the application is unknown.
    """
    norm = _normalize_app_name(name)
    # Exact match
    if norm in _KNOWN_APPLICATIONS:
        return _KNOWN_APPLICATIONS[norm]
    # Partial / fuzzy match
    for key, cfg in _KNOWN_APPLICATIONS.items():
        if norm in key or key in norm:
            return cfg
    return None


class ApplicationLauncher:
    """Safely launches applications through controlled resolution.

    The LLM requests:  {"action_type": "launch_application", "application": "Settings"}
    This class resolves and launches safely.
    """

    async def launch(self, application_name: str) -> DesktopActionResult:
        """Launch an application by semantic name.

        Post-launch observation must confirm the window exists.
        """
        started = time.perf_counter()
        norm = _normalize_app_name(application_name)
        config = resolve_application(norm)

        if config is None:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("APP_LAUNCH unknown application: %s", application_name)
            return DesktopActionResult(
                success=False,
                action_type="launch_application",
                error=f"Unknown application: '{application_name}'. Only known safe applications can be launched.",
                duration_ms=duration_ms,
                grounding_level="semantic",
            )

        def _launch() -> tuple[bool, str | None]:
            try:
                use_shell = config.get("shell", False)
                cmd = config["cmd"]
                args = config.get("args", [])
                if use_shell:
                    full_cmd = f"{cmd} {' '.join(args)}" if args else cmd
                    subprocess.Popen(full_cmd, shell=True)
                else:
                    subprocess.Popen([cmd] + args)
                return True, None
            except FileNotFoundError:
                return False, f"Application executable not found: {cmd}"
            except Exception as e:
                return False, str(e)

        success, error = await asyncio.to_thread(_launch)

        # Wait for application startup and UI rendering
        if success:
            await asyncio.sleep(2.5)

        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "APP_LAUNCH app=%s resolved=%s success=%s duration_ms=%d",
            application_name, config["cmd"], success, duration_ms,
        )

        return DesktopActionResult(
            success=success,
            action_type="launch_application",
            target_id=application_name,
            error=error,
            duration_ms=duration_ms,
            grounding_level="semantic",
        )

    async def is_running(self, process_name: str) -> bool:
        """Check if a process is currently running."""
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

    async def get_expected_process(self, application_name: str) -> str | None:
        """Return expected process name for a known application."""
        config = resolve_application(_normalize_app_name(application_name))
        return config.get("process") if config else None

    async def terminate_app(self, application_name: str) -> bool:
        """Terminate running processes matching a known application name."""
        proc_name = await self.get_expected_process(application_name)
        target = (proc_name or application_name).lower()

        def _term() -> bool:
            terminated = False
            try:
                import psutil
                for proc in psutil.process_iter(["name"]):
                    try:
                        name = (proc.info["name"] or "").lower()
                        if target in name or name in target:
                            proc.terminate()
                            terminated = True
                    except Exception:
                        continue
            except Exception as e:
                logger.warning("terminate_app failed for %s: %s", application_name, e)
            return terminated

        return await asyncio.to_thread(_term)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

app_launcher = ApplicationLauncher()
