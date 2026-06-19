"""Playwright browser context pool for task execution."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from backend.config import get_config

logger = logging.getLogger("pilot.browser.pool")


@dataclass
class RetainedContext:
    """A browser context kept alive after task completion for user inspection."""

    context: BrowserContext
    task_id: str
    retained_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))


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
        self._retained_contexts: dict[str, RetainedContext] = {}
        self._idle_watchdog: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start Playwright and launch the Chromium browser if needed."""

        if self._browser is not None:
            return
        headless = get_config().headless_browser
        logger.info("BROWSER_POOL starting_playwright headless=%s", headless)
        self._playwright = await async_playwright().start()
        logger.info("BROWSER_POOL playwright_started, launching_chromium")
        self._browser = await self._playwright.chromium.launch(headless=headless)
        logger.info(
            "BROWSER_CREATED pid=%s headless=%s",
            getattr(self._browser, "process", None),
            headless,
        )
        # Start idle timeout watchdog
        if self._idle_watchdog is None:
            self._idle_watchdog = asyncio.create_task(self._idle_timeout_watchdog())

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
                logger.info("BROWSER_REUSED active=%d", self._active)
                return context
            if self._active < self.max_contexts:
                self._active += 1
                ctx = await self._browser.new_context()  # type: ignore[union-attr]
                logger.info(
                    "BROWSER_CREATED context active=%d max=%d",
                    self._active,
                    self.max_contexts,
                )
                return ctx
        context = await self._available.get()
        async with self._lock:
            self._active += 1
        logger.info("BROWSER_POOL context_waited active=%d", self._active)
        return context

    async def release(self, context: BrowserContext) -> None:
        """Clear pages and return a context to the available pool."""

        if self._browser is None:
            return

        for page in context.pages:
            await page.close()
        async with self._lock:
            self._active = max(0, self._active - 1)
            await self._available.put(context)

    async def get_task_context(
        self, task_id: str, session_id: str | None = None
    ) -> BrowserContext:
        """Return the context associated with a task or session, acquiring one if needed."""

        key = session_id or task_id
        async with self._lock:
            if key in self._task_contexts:
                return self._task_contexts[key]
            # Check if there's a retained context for this task we can reuse
            if key in self._retained_contexts:
                retained = self._retained_contexts.pop(key)
                self._task_contexts[key] = retained.context
                retained.last_activity = datetime.now(UTC)
                logger.info("BROWSER_REUSED retained_context task_id=%s", key)
                return retained.context

        context = await self.acquire()
        async with self._lock:
            self._task_contexts[key] = context
        return context

    async def release_task_context(
        self, task_id: str, session_id: str | None = None
    ) -> None:
        """Release a task's context back to the pool, unless it belongs to a persistent session."""

        if session_id:
            # Persistent sessions remain open for future tasks
            return

        async with self._lock:
            context = self._task_contexts.pop(task_id, None)
        if context is not None:
            await self.release(context)

    async def retain_task_context(
        self, task_id: str, session_id: str | None = None
    ) -> None:
        """Keep a task's browser context alive for user inspection instead of releasing it.

        The context stays open until explicitly closed, a new task starts, or the idle timeout fires.
        """

        if session_id:
            # Persistent sessions are already kept alive
            return

        async with self._lock:
            context = self._task_contexts.pop(task_id, None)
            if context is None:
                logger.warning(
                    "BROWSER_RETAIN_SKIP task_id=%s reason=no_context", task_id
                )
                return
            self._retained_contexts[task_id] = RetainedContext(
                context=context,
                task_id=task_id,
            )
        logger.info("BROWSER_RETAINED task_id=%s", task_id)

    async def close_task_browser(self, task_id: str, reason: str = "user") -> bool:
        """Explicitly close a retained browser context.

        Returns True if a context was found and closed, False otherwise.
        """

        async with self._lock:
            retained = self._retained_contexts.pop(task_id, None)
        if retained is None:
            return False

        for page in retained.context.pages:
            await page.close()
        async with self._lock:
            self._active = max(0, self._active - 1)
            await self._available.put(retained.context)

        event_name = {
            "user": "BROWSER_CLOSED_BY_USER",
            "timeout": "BROWSER_TIMEOUT",
            "new_task": "BROWSER_CLOSED_BY_USER",
            "exit": "BROWSER_CLOSED_ON_EXIT",
        }.get(reason, "BROWSER_CLOSED_BY_USER")

        logger.info(
            "%s task_id=%s idle_seconds=%d",
            event_name,
            task_id,
            (datetime.now(UTC) - retained.retained_at).total_seconds(),
        )
        return True

    async def close_all_retained(self, reason: str = "exit") -> None:
        """Close all retained browser contexts (used during shutdown or before new tasks)."""

        async with self._lock:
            task_ids = list(self._retained_contexts.keys())

        for task_id in task_ids:
            await self.close_task_browser(task_id, reason=reason)

    def get_browser_status(self) -> dict:
        """Return status information about retained browser contexts for the frontend."""

        if not self._retained_contexts:
            return {
                "open": False,
                "task_id": None,
                "idle_seconds": 0,
                "timeout_minutes": get_config().browser_idle_timeout_minutes,
            }

        # Return the most recent retained context
        latest_key = max(
            self._retained_contexts,
            key=lambda k: self._retained_contexts[k].retained_at,
        )
        retained = self._retained_contexts[latest_key]
        idle_seconds = int(
            (datetime.now(UTC) - retained.last_activity).total_seconds()
        )

        # Try to get the current URL from the first page
        current_url = None
        if retained.context.pages:
            current_url = retained.context.pages[0].url

        return {
            "open": True,
            "task_id": retained.task_id,
            "url": current_url,
            "idle_seconds": idle_seconds,
            "timeout_minutes": get_config().browser_idle_timeout_minutes,
        }

    async def _idle_timeout_watchdog(self) -> None:
        """Periodically check retained contexts and auto-close those that exceed the idle timeout."""

        while True:
            await asyncio.sleep(30)
            timeout_minutes = get_config().browser_idle_timeout_minutes

            async with self._lock:
                expired_ids = []
                now = datetime.now(UTC)
                for task_id, retained in self._retained_contexts.items():
                    idle_seconds = (now - retained.last_activity).total_seconds()
                    if idle_seconds >= timeout_minutes * 60:
                        expired_ids.append(task_id)

            for task_id in expired_ids:
                logger.info(
                    "BROWSER_TIMEOUT task_id=%s timeout_minutes=%d",
                    task_id,
                    timeout_minutes,
                )
                # Log the timeout event to the database
                try:
                    from backend.db.database import database

                    await database.add_event(
                        task_id,
                        "BROWSER_TIMEOUT",
                        f"Browser auto-closed after {timeout_minutes}min idle",
                    )
                except Exception:
                    pass  # Don't crash the watchdog if DB logging fails
                await self.close_task_browser(task_id, reason="timeout")

    async def shutdown(self) -> None:
        """Close all browser resources gracefully."""

        logger.info(
            "BROWSER_POOL shutting_down active=%d queued=%d retained=%d",
            self._active,
            self._available.qsize(),
            len(self._retained_contexts),
        )
        # Stop idle watchdog
        if self._idle_watchdog is not None:
            self._idle_watchdog.cancel()
            self._idle_watchdog = None
        # Close all retained contexts first
        await self.close_all_retained(reason="exit")
        # Then close pooled contexts
        while not self._available.empty():
            context = await self._available.get()
            await context.close()
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        logger.info("BROWSER_CLOSED_ON_EXIT shutdown_complete")

    @property
    def active_sessions(self) -> int:
        """Return the number of checked-out browser contexts."""

        return self._active

    @property
    def retained_count(self) -> int:
        """Return the number of retained (post-task) browser contexts."""

        return len(self._retained_contexts)


browser_pool = BrowserPool()
