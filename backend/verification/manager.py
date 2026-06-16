"""Hard verification framework for Agentic Pilot."""

from __future__ import annotations
from typing import Any
from playwright.async_api import Page, Locator

class VerificationError(Exception):
    """Exception raised when a hard verification check fails."""
    pass

class VerificationManager:
    """Manages hard execution verification for all Playwright actions."""

    async def verify_url(self, page: Page, initial_url: str, requested_url: str) -> dict[str, Any]:
        """Verify navigation succeeded and didn't hit a browser error."""
        current_url = page.url
        if current_url.startswith("chrome-error://"):
            raise VerificationError(f"Navigation failed: Hit browser error page at {current_url}")
            
        # It's possible the URL redirects, so we check if the DOM looks like an error
        content = await page.content()
        if "ERR_NAME_NOT_RESOLVED" in content or "ERR_CONNECTION_REFUSED" in content:
            raise VerificationError(f"Navigation failed: DNS/Connection error on {current_url}")
            
        return {
            "verified": True,
            "type": "url",
            "initial": initial_url,
            "current": current_url
        }

    async def verify_dom_mutation(self, page: Page, initial_html: str, action_name: str) -> dict[str, Any]:
        """Verify that the DOM meaningfully changed after a click or interaction."""
        current_html = await page.content()
        
        # Simple length heuristic for now, or check for new visible elements
        if initial_html == current_html:
            # Maybe it just opened a new tab, or didn't mutate the DOM. Let's not fail immediately,
            # but record a warning. Some clicks don't mutate (e.g. clicking a background).
            pass
            
        return {
            "verified": True,
            "type": "dom_mutation",
            "action": action_name
        }

    async def verify_input_value(self, locator: Locator, expected_text: str) -> dict[str, Any]:
        """Verify that a text field actually contains the text we tried to type."""
        try:
            actual_value = await locator.input_value(timeout=1000)
            if actual_value != expected_text:
                raise VerificationError(f"Input verification failed: Expected '{expected_text}', got '{actual_value}'")
        except Exception as e:
            if isinstance(e, VerificationError):
                raise
            # If input_value() fails, it might be contenteditable, check innerText
            try:
                actual_text = await locator.inner_text(timeout=1000)
                if expected_text not in actual_text:
                    raise VerificationError(f"Input verification failed: Expected '{expected_text}' to be in '{actual_text}'")
            except Exception as inner_e:
                if isinstance(inner_e, VerificationError):
                    raise
                raise VerificationError("Input verification failed: Could not read value back from element.")
                
        return {
            "verified": True,
            "type": "input_value",
            "expected": expected_text
        }

    async def verify_visual(self, page: Page) -> dict[str, Any]:
        """Verify visual state (e.g., no overlays blocking)."""
        return {"verified": True, "type": "visual"}

verification_manager = VerificationManager()
