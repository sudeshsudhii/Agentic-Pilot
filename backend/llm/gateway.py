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

        model_name = self.config.ollama_model if image_bytes is None else self.config.ollama_vision_model
        last_error: Exception | None = None
        for attempt in range(self.config.max_retry_count + 1):
            started = time.perf_counter()
            try:
                request = {
                    "model": model_name,
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
                logger.info(
                    "OLLAMA_CALL model=%s latency_ms=%d tokens_in~=%d tokens_out~=%d",
                    model_name, latency_ms,
                    len(system.split()) + len(user.split()), len(content.split()),
                )
                from backend.telemetry.tracer import tracer
                tracer.record_llm_call(
                    task_id="global",
                    prompt=system + "\n" + user,
                    response=content,
                    latency_ms=latency_ms,
                    model=model_name,
                )
                return content
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                last_error = exc
                # Determine if error is retryable
                is_retryable = isinstance(exc, (ConnectionError, OSError, TimeoutError))
                if not is_retryable:
                    exc_type = type(exc).__name__
                    exc_str = str(exc).lower()
                    # httpx exceptions (used by ollama client internally)
                    is_retryable = any(kw in exc_type.lower() for kw in (
                        "connect", "timeout", "read", "pool",
                    )) or any(kw in exc_str for kw in (
                        "connect", "refused", "timeout", "unreachable",
                    ))
                backoff = 0.25 * (2 ** attempt)
                logger.warning(
                    "OLLAMA_RETRY attempt=%d/%d model=%s retryable=%s backoff=%.2fs error_type=%s error=%s latency_ms=%d",
                    attempt + 1, self.config.max_retry_count + 1, model_name,
                    is_retryable, backoff, type(exc).__name__, exc, latency_ms,
                )
                if not is_retryable:
                    break
                await asyncio.sleep(backoff)

        logger.critical(
            "OLLAMA_EXHAUSTED model=%s retries=%d last_error=%s",
            model_name, self.config.max_retry_count + 1, last_error,
        )
        raise RuntimeError(f"Ollama completion failed after {self.config.max_retry_count + 1} attempts: {last_error}") from last_error

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
                result = parse_model_response(raw, schema)
                logger.info("OLLAMA_STRUCTURED schema=%s attempt=%d success=True", schema.__name__, attempt + 1)
                return result
            except ValueError as exc:
                last_error = exc
                logger.warning(
                    "OLLAMA_STRUCTURED_RETRY schema=%s attempt=%d/%d error=%s",
                    schema.__name__, attempt + 1, self.config.max_retry_count + 1, exc,
                )
                prompt = (
                    user
                    + f"\n\nYour previous response was not valid JSON or did not match the schema:\n{exc}\n"
                    + "Respond with only one JSON object matching the schema."
                )
                await asyncio.sleep(0.1 * (attempt + 1))

        logger.error("OLLAMA_STRUCTURED_EXHAUSTED schema=%s retries=%d", schema.__name__, self.config.max_retry_count + 1)
        raise RuntimeError("Structured LLM response could not be parsed") from last_error

    async def health_check(self) -> bool:
        """Return True when the local Ollama service can list models."""

        try:
            await self._client_instance().list()
            return True
        except Exception:
            return False
