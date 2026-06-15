"""Unified local-first LLM gateway for Ollama and structured outputs."""

from __future__ import annotations

import asyncio
import logging
import time

from pydantic import BaseModel

from backend.config import PilotConfig, get_config
from backend.llm.parser import parse_model_response

logger = logging.getLogger("pilot.llm")


class OllamaGateway:
    """Async wrapper around the Ollama Python client."""

    def __init__(self, config: PilotConfig | None = None) -> None:
        """Create a gateway using the configured local Ollama endpoint."""

        self.config = config or get_config()
        self._client = None

    def _client_instance(self):
        """Return a lazily-created Ollama async client."""

        if self._client is None:
            import ollama

            self._client = ollama.AsyncClient(host=self.config.ollama_base_url)
        return self._client

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        """Return raw text completion content from the configured local model."""

        last_error: Exception | None = None
        for attempt in range(self.config.max_retry_count + 1):
            started = time.perf_counter()
            try:
                request = {
                    "model": self.config.ollama_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                }
                if json_mode:
                    request["format"] = "json"
                response = await self._client_instance().chat(**request)
                latency_ms = int((time.perf_counter() - started) * 1000)
                content = response.get("message", {}).get("content", "")
                if self.config.debug_mode:
                    logger.info(
                        "ollama_call",
                        extra={
                            "model": self.config.ollama_model,
                            "latency_ms": latency_ms,
                            "tokens_in": len(system.split()) + len(user.split()),
                            "tokens_out": len(content.split()),
                        },
                    )
                return content
            except (ConnectionError, OSError, TimeoutError) as exc:
                last_error = exc
                await asyncio.sleep(0.25 * (2**attempt))

        raise RuntimeError("Ollama completion failed") from last_error

    async def complete_structured(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        """Return a Pydantic model parsed from an Ollama JSON-mode response."""

        prompt = user
        last_error: Exception | None = None
        for attempt in range(self.config.max_retry_count + 1):
            try:
                raw = await self.complete(system, prompt, json_mode=True)
                return parse_model_response(raw, schema)
            except ValueError as exc:
                last_error = exc
                prompt = (
                    user
                    + "\n\nYour previous response was not valid JSON. "
                    + "Respond with only one JSON object matching the schema."
                )
                await asyncio.sleep(0.1 * (attempt + 1))

        raise RuntimeError("Structured LLM response could not be parsed") from last_error

    async def health_check(self) -> bool:
        """Return True when the local Ollama service can list models."""

        try:
            await self._client_instance().list()
            return True
        except Exception:
            return False
