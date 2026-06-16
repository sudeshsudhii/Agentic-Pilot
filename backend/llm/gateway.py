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

    async def complete(self, system: str, user: str, json_mode: bool = False, image_bytes: bytes | None = None) -> str:
        """Return raw text completion content from the configured local model."""

        last_error: Exception | None = None
        for attempt in range(self.config.max_retry_count + 1):
            started = time.perf_counter()
            try:
                request = {
                    "model": self.config.ollama_model if image_bytes is None else self.config.ollama_vision_model,
                    "messages": [
                        {"role": "system", "content": system},
                    ],
                }
                user_msg = {"role": "user", "content": user}
                if image_bytes:
                    import base64
                    user_msg["images"] = [base64.b64encode(image_bytes).decode("utf-8")]
                request["messages"].append(user_msg)
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
                from backend.telemetry.tracer import tracer
                tracer.record_llm_call(
                    task_id="global", # Can be improved by passing via context
                    prompt=system + "\n" + user,
                    response=content,
                    latency_ms=latency_ms,
                    model=self.config.ollama_model if image_bytes is None else self.config.ollama_vision_model
                )
                return content
            except (ConnectionError, OSError, TimeoutError) as exc:
                last_error = exc
                await asyncio.sleep(0.25 * (2**attempt))

        raise RuntimeError("Ollama completion failed") from last_error

    async def complete_structured(self, system: str, user: str, schema: type[BaseModel], image_bytes: bytes | None = None) -> BaseModel:
        """Return a Pydantic model parsed from an Ollama JSON-mode response."""

        fields = []
        for name, field in schema.model_fields.items():
            type_info = "string"
            if "int" in str(field.annotation):
                type_info = "integer"
            elif "float" in str(field.annotation) or "num" in str(field.annotation):
                type_info = "number"
            elif "bool" in str(field.annotation):
                type_info = "boolean"
            
            is_optional = "None" in str(field.annotation) or "Optional" in str(field.annotation)
            req_str = "optional" if is_optional else "REQUIRED"
            desc = f" ({field.description})" if field.description else ""
            fields.append(f'  "{name}": {type_info} - {req_str}{desc}')
        
        fields_str = "{\n" + ",\n".join(fields) + "\n}"
        system_with_schema = system + f"\n\nYou MUST respond with a single JSON object containing exactly these fields:\n{fields_str}"

        prompt = user
        last_error: Exception | None = None
        for attempt in range(self.config.max_retry_count + 1):
            try:
                raw = await self.complete(system_with_schema, prompt, json_mode=True, image_bytes=image_bytes)
                return parse_model_response(raw, schema)
            except ValueError as exc:
                last_error = exc
                prompt = (
                    user
                    + f"\n\nYour previous response was not valid JSON or did not match the schema:\n{exc}\n"
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
