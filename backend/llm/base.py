"""Abstract base interface and exceptions for LLM providers in Agentic Pilot."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("pilot.llm.base")


class LLMProviderError(Exception):
    """Base exception for all LLM provider failures."""
    pass


class MissingGeminiApiKeyError(LLMProviderError):
    """Raised when Gemini provider is selected but GEMINI_API_KEY is not set."""
    pass


class GeminiAuthenticationError(LLMProviderError):
    """Raised when Gemini API key is invalid or unauthorized."""
    pass


class GeminiRateLimitError(LLMProviderError):
    """Raised when Gemini returns HTTP 429 Resource Exhausted / Rate Limit."""
    pass


class GeminiTimeoutError(LLMProviderError):
    """Raised when a Gemini API request times out."""
    pass


class GeminiResponseError(LLMProviderError):
    """Raised when Gemini returns an empty or unparsable response."""
    pass


class BaseLLMProvider(ABC):
    """Abstract base provider interface implemented by GeminiGateway and OllamaGateway.
    
    Provides uniform text generation, structured parsing, and health probing.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'gemini', 'ollama', 'hybrid')."""
        ...

    @abstractmethod
    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        image_bytes: bytes | None = None,
        model_override: str | None = None,
    ) -> str:
        """Return raw completion text from the active model."""
        ...

    @abstractmethod
    async def complete_structured(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        image_bytes: bytes | None = None,
        model_override: str | None = None,
    ) -> BaseModel:
        """Return a validated Pydantic model parsed from the active model's response."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Probe the liveness and readiness of the provider."""
        ...

    # Common aliases matching Requirement 2:
    # generate(...)
    # generate_structured(...)
    async def generate(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        image_bytes: bytes | None = None,
        model_override: str | None = None,
    ) -> str:
        """Alias for complete(...)."""
        return await self.complete(
            system=system,
            user=user,
            json_mode=json_mode,
            image_bytes=image_bytes,
            model_override=model_override,
        )

    async def generate_structured(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        image_bytes: bytes | None = None,
        model_override: str | None = None,
    ) -> BaseModel:
        """Alias for complete_structured(...)."""
        return await self.complete_structured(
            system=system,
            user=user,
            schema=schema,
            image_bytes=image_bytes,
            model_override=model_override,
        )
