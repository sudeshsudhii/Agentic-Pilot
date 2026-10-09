"""Hybrid LLM provider combining Cloud Gemini with Local Ollama fallback."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from backend.config import PilotConfig, get_config
from backend.llm.base import BaseLLMProvider
from backend.llm.gemini import GeminiGateway
from backend.llm.gateway import OllamaGateway

logger = logging.getLogger("pilot.llm.hybrid")


class HybridLLMProvider(BaseLLMProvider):
    """Hybrid provider: Primary runtime is Gemini; gracefully falls back to Ollama.
    
    Ensures maximum resilience: laptop stays cool with cloud Gemini, but execution
    can continue offline or during API disruptions via local Ollama.
    """

    def __init__(self, config: PilotConfig | None = None) -> None:
        self.config = config or get_config()
        self.gemini = GeminiGateway(self.config)
        self.ollama = OllamaGateway(self.config)

    @property
    def provider_name(self) -> str:
        return "hybrid"

    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        image_bytes: bytes | None = None,
        model_override: str | None = None,
    ) -> str:
        """Attempt Gemini first; on failure, log explicit fallback and call Ollama."""
        try:
            return await self.gemini.complete(
                system=system,
                user=user,
                json_mode=json_mode,
                image_bytes=image_bytes,
                model_override=model_override,
            )
        except Exception as exc:
            fallback_model = model_override or self.config.ollama_model
            logger.warning(
                "HYBRID_FALLBACK_TRIGGERED: Gemini error (%s). Falling back to Ollama model %s",
                exc,
                fallback_model,
            )
            from backend.telemetry.tracer import tracer
            tracer.record_trace(
                task_id="global",
                component="llm",
                event="hybrid_fallback",
                metadata={
                    "from_provider": "gemini",
                    "to_provider": "ollama",
                    "error": str(exc),
                    "fallback_model": fallback_model,
                },
            )
            return await self.ollama.complete(
                system=system,
                user=user,
                json_mode=json_mode,
                image_bytes=image_bytes,
                model_override=fallback_model,
            )

    async def complete_structured(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        image_bytes: bytes | None = None,
        model_override: str | None = None,
    ) -> BaseModel:
        """Attempt Gemini structured generation first; on failure, fall back to Ollama."""
        try:
            return await self.gemini.complete_structured(
                system=system,
                user=user,
                schema=schema,
                image_bytes=image_bytes,
                model_override=model_override,
            )
        except Exception as exc:
            fallback_model = model_override or self.config.ollama_model
            logger.warning(
                "HYBRID_FALLBACK_STRUCTURED_TRIGGERED: Gemini error (%s). Falling back to Ollama model %s",
                exc,
                fallback_model,
            )
            from backend.telemetry.tracer import tracer
            tracer.record_trace(
                task_id="global",
                component="llm",
                event="hybrid_fallback",
                metadata={
                    "from_provider": "gemini",
                    "to_provider": "ollama",
                    "error": str(exc),
                    "fallback_model": fallback_model,
                    "schema": schema.__name__,
                },
            )
            return await self.ollama.complete_structured(
                system=system,
                user=user,
                schema=schema,
                image_bytes=image_bytes,
                model_override=fallback_model,
            )

    async def health_check(self) -> bool:
        """Check if either Gemini or Ollama is healthy."""
        gemini_ok = await self.gemini.health_check()
        if gemini_ok:
            return True
        return await self.ollama.health_check()
