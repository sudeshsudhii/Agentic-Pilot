"""Credential storage helpers backed by the operating system keychain."""

from __future__ import annotations

import keyring


SERVICE_NAME = "Pilot"


class CredentialStore:
    """Small wrapper around Python keyring for local-only secrets."""

    async def set_secret(self, account: str, secret: str) -> None:
        """Store a secret in the OS keychain."""

        keyring.set_password(SERVICE_NAME, account, secret)

    async def get_secret(self, account: str) -> str | None:
        """Return a secret from the OS keychain when present."""

        return keyring.get_password(SERVICE_NAME, account)

    async def delete_secret(self, account: str) -> None:
        """Delete a secret from the OS keychain when present."""

        keyring.delete_password(SERVICE_NAME, account)
