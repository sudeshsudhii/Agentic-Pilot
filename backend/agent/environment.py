"""Environment resolver — classifies tasks as browser, desktop, or mixed.

Uses keyword analysis and LLM-assisted classification to determine
which execution environment a user task requires BEFORE environment-specific
nodes are invoked.
"""

from __future__ import annotations

import logging
import re

from backend.desktop.models import EnvironmentType

logger = logging.getLogger("pilot.agent.environment")

# ---------------------------------------------------------------------------
# Keyword-based heuristic classification
# ---------------------------------------------------------------------------

# Strong desktop indicators
_DESKTOP_KEYWORDS = frozenset({
    "settings", "bluetooth", "wifi", "wi-fi", "display", "sound", "volume",
    "brightness", "notepad", "calculator", "file explorer", "explorer",
    "task manager", "control panel", "powershell", "cmd", "terminal",
    "paint", "wordpad", "snipping", "desktop", "wallpaper", "screen",
    "mouse", "keyboard settings", "notification", "privacy", "update",
    "windows update", "device manager", "disk", "defrag", "regedit",
    "registry", "system info", "about this pc", "rename file", "move file",
    "copy file", "delete file", "create folder", "outlook", "teams",
    "excel", "word", "powerpoint", "vscode", "visual studio",
    "open application", "open app", "launch", "close window",
    "minimize", "maximize", "taskbar", "start menu",
    "uninstall", "install", "system tray", "recycle bin",
})

# Strong browser indicators
_BROWSER_KEYWORDS = frozenset({
    "browse", "website", "webpage", "web page", "http", "https",
    "url", "search google", "search bing", "search duckduckgo",
    "open chrome", "open firefox", "open edge", "open browser",
    "download from web", "bookmark", "tab", "web search",
    "navigate to", "go to site", "go to website",
    ".com", ".org", ".net", ".io", ".edu",
})

# Mixed task indicators (both environments)
_MIXED_KEYWORDS = frozenset({
    "download and move", "download and copy", "download then",
    "save from web", "from browser to", "from chrome to",
    "copy from web", "web to desktop", "browser to folder",
})


def classify_environment(input_text: str) -> EnvironmentType:
    """Classify the execution environment from user input text.

    Uses a keyword-scoring approach. Falls back to browser for ambiguous tasks.
    """
    text_lower = input_text.lower().strip()

    # Check for explicit mixed indicators first
    for kw in _MIXED_KEYWORDS:
        if kw in text_lower:
            logger.info("ENV_CLASSIFY result=mixed keyword=%s", kw)
            return EnvironmentType.MIXED

    # Score desktop vs browser
    desktop_score = 0
    browser_score = 0

    for kw in _DESKTOP_KEYWORDS:
        if kw in text_lower:
            desktop_score += 1

    for kw in _BROWSER_KEYWORDS:
        if kw in text_lower:
            browser_score += 1

    # URL pattern detection
    if re.search(r'https?://\S+', text_lower):
        browser_score += 3
    if re.search(r'\b\w+\.(com|org|net|io|edu|gov)\b', text_lower):
        browser_score += 2

    # "open X" disambiguation
    open_match = re.search(r'open\s+(\w+(?:\s+\w+)?)', text_lower)
    if open_match:
        app_name = open_match.group(1).strip()
        if app_name in ("chrome", "firefox", "edge", "browser", "safari"):
            browser_score += 3
        elif app_name in ("settings", "notepad", "calculator", "explorer",
                          "terminal", "paint", "word", "excel", "outlook",
                          "teams", "vscode"):
            desktop_score += 3

    # "search for" inside settings → desktop
    if "settings" in text_lower and "search" in text_lower:
        desktop_score += 2

    # Determine result
    if desktop_score > 0 and browser_score > 0:
        if desktop_score > browser_score:
            result = EnvironmentType.DESKTOP
        elif browser_score > desktop_score:
            result = EnvironmentType.BROWSER
        else:
            result = EnvironmentType.MIXED
    elif desktop_score > 0:
        result = EnvironmentType.DESKTOP
    elif browser_score > 0:
        result = EnvironmentType.BROWSER
    else:
        # Default to browser (backward compatible)
        result = EnvironmentType.BROWSER

    logger.info(
        "ENV_CLASSIFY result=%s desktop_score=%d browser_score=%d input=%s",
        result.value, desktop_score, browser_score, text_lower[:80],
    )
    return result
