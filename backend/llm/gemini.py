"""Google Gemini cloud LLM provider implementation for Agentic Pilot.

Leverages the official Google Gemini API Python SDK (google-genai) with
first-class structured outputs, multimodal vision grounding, bounded error
handling, and zero local laptop hardware overhead.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from pydantic import BaseModel

from backend.config import PilotConfig, get_config
from backend.llm.base import (
    BaseLLMProvider,
    GeminiAuthenticationError,
    GeminiRateLimitError,
    GeminiResponseError,
    GeminiTimeoutError,
    LLMProviderError,
    MissingGeminiApiKeyError,
)
from backend.llm.parser import parse_model_response

logger = logging.getLogger("pilot.llm.gemini")


class GeminiGateway(BaseLLMProvider):
    """Async client wrapper for Google Gemini cloud inference via google-genai."""

    def __init__(self, config: PilotConfig | None = None) -> None:
        self.config = config or get_config()
        self._client = None
        self._last_latency_ms: int = 0
        self._last_input_tokens: int | None = None
        self._last_output_tokens: int | None = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _get_api_key(self) -> str:
        """Resolve Gemini API key ONLY from environment, never hardcoded."""
        key = (
            self.config.gemini_api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("PILOT_GEMINI_API_KEY")
        )
        if not key or not key.strip():
            raise MissingGeminiApiKeyError(
                "GEMINI_API_KEY is missing from the environment. "
                "Set GEMINI_API_KEY in your system environment or .env file to enable Gemini cloud inference."
            )
        return key.strip()

    def _client_instance(self):
        """Return lazily-initialized Google GenAI client."""
        if self._client is None:
            from google import genai

            api_key = self._get_api_key()
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _resolve_model(self, model_override: str | None = None) -> str:
        """Resolve Gemini model name, automatically mapping local model overrides to gemini."""
        if not model_override:
            return self.config.gemini_model
        override_lower = model_override.lower()
        if any(local_tag in override_lower for local_tag in ("qwen", "moondream", "deepseek", "llama", "mistral", "phi")):
            return self.config.gemini_model
        return model_override

    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        image_bytes: bytes | None = None,
        model_override: str | None = None,
    ) -> str:
        """Return completion text from the Google Gemini API with bounded retries."""
        from google.genai import types

        model_name = self._resolve_model(model_override)
        client = self._client_instance()

        # Build contents (text + optional image Part)
        contents: list[Any] = [user]
        if image_bytes:
            part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
            contents.append(part)

        config_kwargs: dict[str, Any] = {
            "temperature": self.config.gemini_temperature,
            "system_instruction": system,
        }
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        gen_config = types.GenerateContentConfig(**config_kwargs)

        last_error: Exception | None = None
        for attempt in range(self.config.max_retry_count + 1):
            started = time.perf_counter()
            try:
                if hasattr(client, "aio") and hasattr(client.aio, "models") and hasattr(client.aio.models, "generate_content"):
                    call_res = client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=gen_config,
                    )
                    import inspect
                    if inspect.isawaitable(call_res):
                        response = await asyncio.wait_for(
                            call_res,
                            timeout=float(self.config.gemini_timeout_seconds),
                        )
                    else:
                        response = call_res
                else:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name,
                            contents=contents,
                            config=gen_config,
                        ),
                        timeout=float(self.config.gemini_timeout_seconds),
                    )
                duration_ms = int((time.perf_counter() - started) * 1000)
                self._last_latency_ms = duration_ms

                # Extract content
                content = response.text or ""
                if not content and response.candidates:
                    # Extract from parts if response.text is None
                    parts = response.candidates[0].content.parts or []
                    content = "".join([p.text or "" for p in parts])

                # Extract token usage if available
                prompt_tokens: int | None = None
                output_tokens: int | None = None
                if getattr(response, "usage_metadata", None):
                    prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
                    output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)

                self._last_input_tokens = prompt_tokens
                self._last_output_tokens = output_tokens

                tokens_in_approx = prompt_tokens if prompt_tokens is not None else (len(system.split()) + len(user.split()))
                tokens_out_approx = output_tokens if output_tokens is not None else len(content.split())

                logger.info(
                    "GEMINI_CALL model=%s latency_ms=%d tokens_in=%s tokens_out=%s attempt=%d",
                    model_name,
                    duration_ms,
                    tokens_in_approx,
                    tokens_out_approx,
                    attempt + 1,
                )

                # Telemetry recording (sanitized, zero secrets logged)
                from backend.telemetry.tracer import tracer
                tracer.record_llm_call(
                    task_id="global",
                    prompt=system + "\n" + user,
                    response=content,
                    latency_ms=duration_ms,
                    model=model_name,
                )

                # Privacy audit
                from backend.security.audit import privacy_auditor
                privacy_auditor.record_llm_call(
                    model=model_name,
                    destination="https://generativelanguage.googleapis.com",
                    prompt_bytes=len(system) + len(user),
                    response_bytes=len(content),
                    latency_ms=duration_ms,
                )

                return content

            except TimeoutError as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                last_error = GeminiTimeoutError(
                    f"Gemini API request timed out after {self.config.gemini_timeout_seconds}s"
                )
                logger.warning(
                    "GEMINI_TIMEOUT attempt=%d/%d model=%s duration_ms=%d",
                    attempt + 1,
                    self.config.max_retry_count + 1,
                    model_name,
                    duration_ms,
                )
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                err_str = str(exc).lower()
                exc_type = type(exc).__name__

                # Check for rate limit / quota exhaustion (429)
                is_rate_limit = "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str
                if is_rate_limit:
                    last_error = GeminiRateLimitError(f"Gemini quota exceeded / rate limit: {exc}")
                    if model_name != "gemini-3.1-flash-lite":
                        logger.warning(
                            "GEMINI_QUOTA_FALLBACK: %s exhausted quota, falling back to gemini-3.1-flash-lite",
                            model_name,
                        )
                        model_name = "gemini-3.1-flash-lite"
                        await asyncio.sleep(1.0)
                        continue
                elif any(k in err_str for k in ("unauthenticated", "permission_denied", "401", "403", "api_key not valid", "invalid api key")):
                    logger.error("GEMINI_AUTH_ERROR: Invalid or unauthorized Gemini API key.")
                    raise GeminiAuthenticationError(
                        "Gemini API authentication failed. Verify that your GEMINI_API_KEY is valid."
                    ) from exc
                else:
                    last_error = LLMProviderError(f"Gemini API error ({exc_type}): {exc}")

                backoff = max(5.0, 1.0 * (2**attempt)) if is_rate_limit else 0.5 * (2**attempt)
                logger.warning(
                    "GEMINI_RETRY attempt=%d/%d model=%s error_type=%s backoff=%.2fs latency_ms=%d",
                    attempt + 1,
                    self.config.max_retry_count + 1,
                    model_name,
                    exc_type,
                    backoff,
                    duration_ms,
                )
                if attempt < self.config.max_retry_count:
                    await asyncio.sleep(backoff)

        logger.critical(
            "GEMINI_EXHAUSTED model=%s retries=%d last_error=%s",
            model_name,
            self.config.max_retry_count + 1,
            last_error,
        )
        raise last_error or LLMProviderError(f"Gemini completion failed for model {model_name}")

    async def complete_structured(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        image_bytes: bytes | None = None,
        model_override: str | None = None,
    ) -> BaseModel:
        """Return a validated Pydantic model parsed from Gemini response."""
        # Build schema description prompt
        fields = []
        for name, field in schema.model_fields.items():
            type_info = "string"
            ann_str = str(field.annotation)
            if "int" in ann_str:
                type_info = "integer"
            elif "float" in ann_str or "num" in ann_str:
                type_info = "number"
            elif "bool" in ann_str:
                type_info = "boolean"
            elif "list" in ann_str or "List" in ann_str:
                type_info = "array"
            elif "dict" in ann_str or "Dict" in ann_str:
                type_info = "object"

            is_optional = "None" in ann_str or "Optional" in ann_str
            req_str = "optional" if is_optional else "REQUIRED"
            desc = f" ({field.description})" if field.description else ""
            fields.append(f'  "{name}": {type_info} - {req_str}{desc}')

        fields_str = "{\n" + ",\n".join(fields) + "\n}"
        system_with_schema = (
            f"{system}\n\n"
            f"You MUST respond with a single valid JSON object containing exactly these fields:\n"
            f"{fields_str}\n"
            f"Do not include any explanation or markdown formatting."
        )

        prompt = user
        last_error: Exception | None = None
        for attempt in range(self.config.max_retry_count + 1):
            try:
                raw = await self.complete(
                    system_with_schema,
                    prompt,
                    json_mode=True,
                    image_bytes=image_bytes,
                    model_override=model_override,
                )
                result = parse_model_response(raw, schema)
                logger.info(
                    "GEMINI_STRUCTURED schema=%s attempt=%d success=True",
                    schema.__name__,
                    attempt + 1,
                )
                return result
            except ValueError as exc:
                last_error = exc
                logger.warning(
                    "GEMINI_STRUCTURED_RETRY schema=%s attempt=%d/%d error=%s",
                    schema.__name__,
                    attempt + 1,
                    self.config.max_retry_count + 1,
                    exc,
                )
                prompt = (
                    f"{user}\n\n"
                    f"Your previous response was not valid JSON or did not match the schema:\n{exc}\n"
                    f"Respond with ONLY one JSON object matching the schema."
                )
                await asyncio.sleep(0.2 * (attempt + 1))

        logger.error(
            "GEMINI_STRUCTURED_EXHAUSTED schema=%s retries=%d",
            schema.__name__,
            self.config.max_retry_count + 1,
        )
        raise GeminiResponseError(
            f"Structured LLM response could not be parsed into {schema.__name__}: {last_error}"
        ) from last_error

    async def health_check(self) -> bool:
        """Probe Gemini API reachability without heavy token consumption."""
        try:
            key = self._get_api_key()
            if not key or len(key) < 10:
                return False
            # Verify client can be constructed and list models or ping
            client = self._client_instance()
            # Issue a minimal count_tokens or get model check to verify API key validity
            model_name = self.config.gemini_model
            await asyncio.wait_for(
                client.aio.models.count_tokens(
                    model=model_name,
                    contents="healthcheck",
                ),
                timeout=5.0,
            )
            return True
        except Exception as exc:
            logger.debug("GEMINI_HEALTH_CHECK_FAILED: %s", exc)
            return False
