"""DOM extraction utilities for compact browser action manifests."""

from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from backend.llm.parser import ActionManifest, InteractiveElement


class DOMExtractor:
    """Extract visible interactive elements from a Playwright page."""

    async def extract(self, page: Page) -> ActionManifest:
        """Extract a compact action manifest from the current page."""

        raw_elements = await self._get_interactive_elements(page)
        elements = self._compress_manifest(raw_elements)
        return ActionManifest(
            url=page.url,
            interactive_elements=elements,
            page_title=await page.title(),
            page_state=await self._detect_page_state(page),
        )

    async def _detect_page_state(self, page: Page) -> str:
        """Detect login, loading, error, CAPTCHA, or ready page states."""

        text = (await page.locator("body").inner_text(timeout=3000)).lower()
        url = page.url.lower()
        if "captcha" in text or "recaptcha" in text:
            return "captcha"
        if "login" in url or any(term in text for term in ("sign in", "log in", "password")):
            return "login_required"
        if any(term in text for term in ("404", "500", "not found", "server error")):
            return "error"
        if await page.locator("[aria-busy='true'], .loading, .spinner, [role='progressbar']").count() > 0:
            return "loading"
        return "ready"

    async def _get_interactive_elements(self, page: Page) -> list[dict[str, Any]]:
        """Extract visible buttons, links, form controls, and basic metadata."""

        return await page.evaluate(
            """
            () => {
              const selector = 'button,input,textarea,select,a,[role="button"],[role="link"],[contenteditable="true"]';
              const nodes = Array.from(document.querySelectorAll(selector));
              return nodes.map((el, index) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const visible = rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' && style.display !== 'none' && !el.disabled;
                const id = `pilot-el-${index}`;
                el.setAttribute('data-pilot-id', id);
                return {
                  element_id: id,
                  tag: el.tagName.toLowerCase(),
                  role: el.getAttribute('role'),
                  aria_label: el.getAttribute('aria-label'),
                  text_content: (el.innerText || el.value || '').trim().slice(0, 120),
                  placeholder: el.getAttribute('placeholder'),
                  input_type: el.getAttribute('type'),
                  is_visible: visible,
                  selector: `[data-pilot-id="${id}"]`,
                  bounding_box: {
                    x: rect.x + rect.width / 2,
                    y: rect.y + rect.height / 2,
                    width: rect.width,
                    height: rect.height
                  }
                };
              }).filter((item) => item.is_visible);
            }
            """
        )

    def _compress_manifest(self, elements: list[dict[str, Any]]) -> list[InteractiveElement]:
        """Reduce extracted elements to the most useful top 50 actions."""

        seen: set[tuple[str, str, str]] = set()
        ranked = sorted(elements, key=_element_rank)
        compressed: list[InteractiveElement] = []
        nav_links = 0
        for element in ranked:
            key = (
                str(element.get("role") or ""),
                str(element.get("aria_label") or ""),
                str(element.get("text_content") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            if element.get("tag") == "a":
                nav_links += 1
                if nav_links > 5:
                    continue
            label = " ".join(
                str(element.get(name) or "").lower()
                for name in ("aria_label", "text_content", "placeholder")
            )
            if any(noise in label for noise in ("cookie", "advertisement", "sponsored")):
                continue
            compressed.append(InteractiveElement.model_validate(element))
            if len(compressed) >= 50:
                break
        return compressed


def _element_rank(element: dict[str, Any]) -> int:
    """Rank elements so primary task controls fit within the manifest."""

    text = " ".join(
        str(element.get(name) or "").lower()
        for name in ("aria_label", "text_content", "placeholder", "input_type")
    )
    tag = str(element.get("tag") or "")
    if any(word in text for word in ("submit", "send", "post", "publish", "continue", "next")):
        return 0
    if tag in {"input", "textarea"}:
        return 1
    if tag == "select":
        return 2
    if tag == "a":
        return 3
    return 4
