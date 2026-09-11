"""Desktop automation package for Agentic Pilot (Phase 4 / R06).

Provides native OS desktop interaction capabilities including mouse control,
keyboard input, screen capture, and process inspection.
"""

from backend.desktop.executor import DesktopExecutor, desktop_executor

__all__ = ["DesktopExecutor", "desktop_executor"]
