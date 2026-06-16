"""Playwright action execution helpers for Pilot."""

from __future__ import annotations

import time

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from backend.browser.dom import DOMExtractor
from backend.llm.parser import ActionResult, InteractiveElement


class ActionExecutor:
    """Execute selected browser actions using resilient locator priority."""

    def __init__(self) -> None:
        """Create an executor with its own DOM state detector."""

        self.extractor = DOMExtractor()

    async def click(self, page: Page, element: InteractiveElement) -> ActionResult:
        """Click an interactive element and return action metadata."""

        return await self._timed_action(page, "click", element, self._click_impl(page, element))

    async def type_text(self, page: Page, element: InteractiveElement, text: str) -> ActionResult:
        """Fill text into an interactive field and return action metadata."""

        return await self._timed_action(page, "type_text", element, self._type_impl(page, element, text))

    async def select_option(self, page: Page, element: InteractiveElement, value: str) -> ActionResult:
        """Select a dropdown option and return action metadata."""

        return await self._timed_action(page, "select_option", element, self._select_impl(page, element, value))

    async def navigate(self, page: Page, url: str) -> ActionResult:
        """Navigate the page to a URL and return action metadata."""

        started = time.perf_counter()
        try:
            initial_url = page.url
            await page.goto(_normalize_url(url), wait_until="domcontentloaded", timeout=30000)
            
            # Hard verification: Verify URL loaded
            if initial_url == page.url and initial_url != "about:blank":
                if not "google.com" in url:  # Let's not be too rigid if the user navigates to the same page, but generally we want it to work. Wait, let's just check response.
                    pass
            # A better verification is to check if we hit a browser error page
            if page.url.startswith("chrome-error://"):
                raise ValueError(f"Verification failed: Could not reach {url}")

            state = await self.extractor._detect_page_state(page)
            return ActionResult(
                success=True,
                action_type="navigate",
                element_id=None,
                error=None,
                page_state_after=state,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                action_type="navigate",
                element_id=None,
                error=str(exc),
                page_state_after="error",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    async def wait_for_state(self, page: Page, state: str, timeout_ms: int = 10000) -> ActionResult:
        """Wait until the page detector reports the requested state."""

        started = time.perf_counter()
        while int((time.perf_counter() - started) * 1000) < timeout_ms:
            current = await self.extractor._detect_page_state(page)
            if current == state:
                return ActionResult(
                    success=True,
                    action_type="wait_for_state",
                    element_id=None,
                    error=None,
                    page_state_after=current,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            await page.wait_for_timeout(250)
        return ActionResult(
            success=False,
            action_type="wait_for_state",
            element_id=None,
            error="Timed out waiting for state",
            page_state_after="error",
            duration_ms=timeout_ms,
        )

    async def take_screenshot(self, page: Page) -> bytes:
        """Capture a full-page PNG screenshot."""

        return await page.screenshot(full_page=True)

    async def _click_impl(self, page: Page, element: InteractiveElement) -> None:
        """Click using role, label, text, selector, then coordinate fallback."""

        locator = self._locator(page, element)
        if locator is not None:
            await locator.click(timeout=10000)
            return
        if element.bounding_box:
            await page.mouse.click(element.bounding_box["x"], element.bounding_box["y"])
            return
        raise ValueError("Element has no usable selector or bounding box")

    async def _type_impl(self, page: Page, element: InteractiveElement, text: str) -> None:
        """Fill a field using the best available locator."""

        locator = self._locator(page, element)
        if locator is None:
            raise ValueError("Element has no usable selector")
        await locator.fill(text, timeout=10000)
        
        # Hard verification: Verify field value changed
        actual_value = await locator.input_value(timeout=2000)
        if actual_value != text:
            raise ValueError(f"Verification failed: expected '{text}', got '{actual_value}'")

    async def _select_impl(self, page: Page, element: InteractiveElement, value: str) -> None:
        """Select an option using the best available locator."""

        locator = self._locator(page, element)
        if locator is None:
            raise ValueError("Element has no usable selector")
        await locator.select_option(value, timeout=10000)

    async def _timed_action(self, page: Page, action_type: str, element: InteractiveElement, operation) -> ActionResult:
        """Run a Playwright operation and wrap it in an ActionResult."""

        started = time.perf_counter()
        try:
            initial_url = page.url
            initial_dom_len = len(await page.content())
            
            await operation
            
            # Hard verification for clicks
            if action_type == "click":
                await page.wait_for_timeout(500) # Wait for potential JS mutations
                final_url = page.url
                final_dom_len = len(await page.content())
                if initial_url == final_url and abs(initial_dom_len - final_dom_len) < 50:
                    raise ValueError("Verification failed: Click did not result in a page state change")

            success = True
            error = None
        except PlaywrightTimeoutError as exc:
            success = False
            error = "Action timeout: " + str(exc)
        except Exception as exc:
            success = False
            error = str(exc)
            
        state = await self.extractor._detect_page_state(page)
        return ActionResult(
            success=success,
            action_type=action_type,
            element_id=element.element_id,
            error=error,
            page_state_after=state,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def _locator(self, page: Page, element: InteractiveElement):
        """Return the highest-priority Playwright locator for an element."""

        if element.aria_label and element.role:
            return page.get_by_role(element.role, name=element.aria_label)
        if element.role and element.text_content:
            return page.get_by_role(element.role, name=element.text_content)
        if element.placeholder:
            return page.get_by_placeholder(element.placeholder)
        if element.text_content:
            return page.get_by_text(element.text_content, exact=True)
        if element.selector:
            return page.locator(element.selector)
        return None


def _normalize_url(url: str) -> str:
    """Ensure navigation URLs include an explicit scheme."""

    if url.startswith(("http://", "https://")):
        return url
    return "https://" + url
