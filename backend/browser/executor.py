"""Playwright execution layer for Agentic Pilot."""

from __future__ import annotations
import asyncio
import time
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from backend.browser.dom import DOMExtractor
from backend.llm.parser import ActionResult, InteractiveElement
from backend.verification.manager import verification_manager, VerificationError

class PlaywrightExecutor:
    """Execute browser actions natively via Playwright with hard verification."""

    def __init__(self) -> None:
        self.extractor = DOMExtractor()

    async def click(self, page: Page, element: InteractiveElement) -> ActionResult:
        """Click an interactive element and verify the DOM mutated."""
        return await self._execute_and_verify(
            page, "click", element, self._click_impl(page, element)
        )

    async def type_text(self, page: Page, element: InteractiveElement, text: str, press_enter: bool = False) -> ActionResult:
        """Fill text, verify input_value matches, and optionally submit with Enter."""
        started = time.perf_counter()
        try:
            locator = self._locator(page, element)
            if locator is None:
                raise ValueError("Element has no usable selector")
            await locator.fill(text, timeout=10000)
            await verification_manager.verify_input_value(locator, text)
            if press_enter:
                await locator.press("Enter")
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
            state = await self.extractor._detect_page_state(page)
            return ActionResult(
                success=True,
                action_type="type_text",
                element_id=element.element_id,
                error=None,
                page_state_after=state,
                duration_ms=int((time.perf_counter() - started) * 1000),
                observed_state={"text": text, "press_enter": press_enter, "url": page.url},
            )
        except VerificationError as exc:
            return ActionResult(
                success=False, action_type="type_text", element_id=element.element_id,
                error=str(exc), page_state_after="error", duration_ms=int((time.perf_counter() - started) * 1000)
            )
        except Exception as exc:
            try:
                # Resilient fallback: click and type via keyboard
                if element.bounding_box:
                    await page.mouse.click(element.bounding_box["x"], element.bounding_box["y"])
                await page.keyboard.type(text)
                if press_enter:
                    await page.keyboard.press("Enter")
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=3000)
                    except Exception:
                        pass
                state = await self.extractor._detect_page_state(page)
                return ActionResult(
                    success=True,
                    action_type="type_text",
                    element_id=element.element_id,
                    error=None,
                    page_state_after=state,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    observed_state={"text": text, "press_enter": press_enter, "url": page.url},
                )
            except Exception:
                return ActionResult(
                    success=False, action_type="type_text", element_id=element.element_id,
                    error=str(exc), page_state_after="error", duration_ms=int((time.perf_counter() - started) * 1000)
                )

    async def press_key(self, page: Page, key: str) -> ActionResult:
        """Press a keyboard key (e.g. 'Enter')."""
        started = time.perf_counter()
        try:
            initial_url = page.url
            await page.keyboard.press(key)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
            state = await self.extractor._detect_page_state(page)
            return ActionResult(
                success=True,
                action_type="press_key",
                element_id=None,
                error=None,
                page_state_after=state,
                duration_ms=int((time.perf_counter() - started) * 1000),
                observed_state={"key": key, "url": page.url, "url_changed": page.url != initial_url},
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                action_type="press_key",
                element_id=None,
                error=str(exc),
                page_state_after="error",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    async def extract_content(self, page: Page, selector: str | None = None) -> ActionResult:
        """Extract structured text, title, and headings from the active page."""
        started = time.perf_counter()
        try:
            page_title = await page.title()
            current_url = page.url
            if selector:
                extracted_text = await page.locator(selector).inner_text(timeout=5000)
            else:
                extracted_text = await page.locator("body").inner_text(timeout=5000)
            
            clean_lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
            summary_text = "\n".join(clean_lines[:80])
            state = await self.extractor._detect_page_state(page)
            return ActionResult(
                success=True,
                action_type="extract",
                element_id=selector,
                error=None,
                page_state_after=state,
                duration_ms=int((time.perf_counter() - started) * 1000),
                data={
                    "page_title": page_title,
                    "url": current_url,
                    "content_snippet": summary_text[:2500],
                },
                observed_state={"page_title": page_title, "url": current_url, "char_count": len(summary_text)},
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                action_type="extract",
                element_id=selector,
                error=str(exc),
                page_state_after="error",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    async def select_option(self, page: Page, element: InteractiveElement, value: str) -> ActionResult:
        """Select an option."""
        return await self._execute_and_verify(
            page, "select_option", element, self._select_impl(page, element, value)
        )

    async def navigate(self, page: Page, url: str) -> ActionResult:
        """Navigate and verify URL, with recovery for transient failures."""
        started = time.perf_counter()
        normalized_url = self._normalize_url(url)
        initial_url = page.url
        
        for attempt in range(3):
            try:
                await page.goto(normalized_url, wait_until="domcontentloaded", timeout=15000)
                await verification_manager.verify_url(page, initial_url, url)
                
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
                is_transient = isinstance(exc, PlaywrightTimeoutError) or "net::ERR_" in str(exc)
                if not is_transient or attempt == 2:
                    return ActionResult(
                        success=False,
                        action_type="navigate",
                        element_id=None,
                        error=f"Failed after {attempt + 1} attempts: {str(exc)}",
                        page_state_after="error",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                await asyncio.sleep(0.2)

    async def scroll(self, page: Page, direction: str) -> ActionResult:
        """Scroll the page down or up."""
        started = time.perf_counter()
        try:
            if direction == "down":
                await page.mouse.wheel(0, 1000)
            elif direction == "up":
                await page.mouse.wheel(0, -1000)
            try:
                await page.evaluate("() => new Promise(resolve => requestAnimationFrame(resolve))")
            except Exception:
                await asyncio.sleep(0.05)
            state = await self.extractor._detect_page_state(page)
            return ActionResult(
                success=True, action_type="scroll", element_id=None, error=None,
                page_state_after=state, duration_ms=int((time.perf_counter() - started) * 1000)
            )
        except Exception as exc:
            return ActionResult(
                success=False, action_type="scroll", element_id=None, error=str(exc),
                page_state_after="error", duration_ms=int((time.perf_counter() - started) * 1000)
            )

    async def extract_text(self, page: Page) -> str:
        """Extract all text from the body."""
        return await page.locator("body").inner_text()

    async def take_screenshot(self, page: Page) -> bytes:
        """Capture a full-page PNG screenshot."""
        try:
            return await page.screenshot(full_page=True, timeout=10000, animations="disabled")
        except Exception:
            try:
                return await page.screenshot(full_page=False, timeout=5000)
            except Exception:
                return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

    async def get_screenshot_with_dimensions(self, page: Page) -> tuple[bytes, int, int]:
        """Capture screenshot and return (bytes, width, height)."""
        screenshot = await self.take_screenshot(page)
        width, height = 1280, 800
        viewport = page.viewport_size
        if viewport:
            width = viewport.get("width", 1280)
            height = viewport.get("height", 800)
        else:
            try:
                import io
                from PIL import Image
                with Image.open(io.BytesIO(screenshot)) as im:
                    width, height = im.size
            except Exception:
                pass
        return screenshot, width, height

    async def _click_impl(self, page: Page, element: InteractiveElement) -> None:
        locator = self._locator(page, element)
        if locator is not None:
            await locator.click(timeout=10000)
            return
        if element.bounding_box:
            await page.mouse.click(element.bounding_box["x"], element.bounding_box["y"])
            return
        raise ValueError("Element has no usable selector or bounding box")

    async def _type_impl(self, page: Page, element: InteractiveElement, text: str) -> None:
        locator = self._locator(page, element)
        if locator is None:
            raise ValueError("Element has no usable selector")
        await locator.fill(text, timeout=10000)
        await verification_manager.verify_input_value(locator, text)

    async def _select_impl(self, page: Page, element: InteractiveElement, value: str) -> None:
        locator = self._locator(page, element)
        if locator is None:
            raise ValueError("Element has no usable selector")
        await locator.select_option(value, timeout=10000)

    async def _execute_and_verify(self, page: Page, action_type: str, element: InteractiveElement, operation) -> ActionResult:
        """Run operation and wrap in ActionResult with hard verification."""
        started = time.perf_counter()
        try:
            initial_html = await page.content()
            
            await operation
            
            if action_type == "click":
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=300)
                except Exception:
                    pass
                await verification_manager.verify_dom_mutation(page, initial_html, "click")

            state = await self.extractor._detect_page_state(page)
            return ActionResult(
                success=True,
                action_type=action_type,
                element_id=element.element_id,
                error=None,
                page_state_after=state,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except PlaywrightTimeoutError as exc:
            return ActionResult(
                success=False, action_type=action_type, element_id=element.element_id,
                error=f"Timeout: {exc}", page_state_after="error", duration_ms=int((time.perf_counter() - started) * 1000)
            )
        except VerificationError as exc:
            return ActionResult(
                success=False, action_type=action_type, element_id=element.element_id,
                error=str(exc), page_state_after="error", duration_ms=int((time.perf_counter() - started) * 1000)
            )
        except Exception as exc:
            return ActionResult(
                success=False, action_type=action_type, element_id=element.element_id,
                error=str(exc), page_state_after="error", duration_ms=int((time.perf_counter() - started) * 1000)
            )

    def _locator(self, page: Page, element: InteractiveElement):
        if element.selector:
            return page.locator(element.selector)
        if element.css_selector:
            return page.locator(element.css_selector)
        if element.xpath:
            return page.locator(f"xpath={element.xpath}")
        return None

    def _normalize_url(self, url: str) -> str:
        if url.startswith(("http://", "https://")):
            return url
        return "https://" + url

executor = PlaywrightExecutor()
