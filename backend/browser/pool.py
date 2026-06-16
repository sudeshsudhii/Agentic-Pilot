"""Playwright browser context pool for task execution."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from backend.config import get_config


class BrowserPool:
    """Manage a bounded pool of isolated Playwright contexts."""

    def __init__(self, max_contexts: int | None = None) -> None:
        """Create a browser pool with a configured maximum size."""

        self.max_contexts = max_contexts or get_config().browser_pool_size
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._available: asyncio.Queue[BrowserContext] = asyncio.Queue()
        self._active = 0
        self._lock = asyncio.Lock()
        self._task_contexts: dict[str, BrowserContext] = {}

    async def start(self) -> None:
        """Start Playwright and launch the Chromium browser if needed."""

        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=get_config().headless_browser)

    @asynccontextmanager
    async def context(self) -> AsyncIterator[BrowserContext]:
        """Yield a browser context and return it to the pool afterward."""

        context = await self.acquire()
        try:
            yield context
        finally:
            await self.release(context)

    async def acquire(self) -> BrowserContext:
        """Acquire an isolated context from the pool."""

        await self.start()
        async with self._lock:
            if not self._available.empty():
                context = await self._available.get()
                self._active += 1
                return context
            if self._active < self.max_contexts:
                self._active += 1
                return await self._browser.new_context()  # type: ignore[union-attr]
        context = await self._available.get()
        async with self._lock:
            self._active += 1
        return context

    async def release(self, context: BrowserContext) -> None:
        """Clear pages and return a context to the available pool."""

        for page in context.pages:
            await page.close()
        async with self._lock:
            self._active = max(0, self._active - 1)
            await self._available.put(context)

    async def get_task_context(self, task_id: str) -> BrowserContext:
        """Return the context associated with a task, acquiring one if needed."""
        
        async with self._lock:
            if task_id in self._task_contexts:
                return self._task_contexts[task_id]
                
        context = await self.acquire()
        async with self._lock:
            self._task_contexts[task_id] = context
        return context

    async def release_task_context(self, task_id: str) -> None:
        """Release a task's context back to the pool."""
        
        async with self._lock:
            context = self._task_contexts.pop(task_id, None)
        if context is not None:
            await self.release(context)

    async def shutdown(self) -> None:
        """Close all browser resources gracefully."""

        while not self._available.empty():
            context = await self._available.get()
            await context.close()
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    @property
    def active_sessions(self) -> int:
        """Return the number of checked-out browser contexts."""

        return self._active


browser_pool = BrowserPool()
