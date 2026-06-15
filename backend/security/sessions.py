"""Session state helpers for browser authentication checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.config import get_config


class SessionRegistry:
    """In-memory session registry used until cookie persistence is configured."""

    def __init__(self) -> None:
        """Create an empty registry."""

        self._sessions: dict[str, datetime] = {}

    async def has_valid_session(self, site: str) -> bool:
        """Return True when the site has a non-expired local session marker."""

        expires = self._sessions.get(site)
        return expires is not None and expires > datetime.now(UTC)

    async def mark_authenticated(self, site: str) -> None:
        """Mark a site as authenticated for the configured session TTL."""

        ttl = timedelta(hours=get_config().session_ttl_hours)
        self._sessions[site] = datetime.now(UTC) + ttl

    async def clear(self, site: str) -> None:
        """Remove a site session marker."""

        self._sessions.pop(site, None)


session_registry = SessionRegistry()
