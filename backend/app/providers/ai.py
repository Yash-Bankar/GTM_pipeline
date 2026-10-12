"""AI provider abstraction + Gemini implementation.

Server-side only. The provider turns a prompt into a validated Pydantic object
using structured output. Credentials and model come from environment variables;
the key is never logged.
"""

from __future__ import annotations

import json
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.common.retry import call_with_retry
from app.config import Settings

from .errors import (
    AIConfigError,
    AIModelError,
    AINetworkError,
    AIRateLimitError,
    AIResponseError,
)

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_TRANSPORT_NAMES = ("TimeoutError", "ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError")


def _status_code(exc: BaseException) -> int:
    for attr in ("code", "status_code", "status"):
        value = getattr(exc, attr, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def is_retryable_ai_error(exc: BaseException) -> bool:
    if _status_code(exc) in _RETRYABLE_STATUSES:
        return True
    name = type(exc).__name__
    return any(marker in name for marker in _TRANSPORT_NAMES)


class AIProvider(ABC):
    """Generates structured content from a prompt."""

    @abstractmethod
    def generate_structured(
        self, *, prompt: str, system: str, schema: type[SchemaT]
    ) -> SchemaT:
        ...


class GeminiProvider(AIProvider):
    """Gemini via the official ``google-genai`` SDK."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        temperature: float = 0.4,
        max_output_tokens: int = 2048,
        timeout: float = 60.0,
        max_attempts: int = 3,
        client: Any | None = None,
        sleeper: Callable[[float], None] | None = None,
        rand: Callable[[], float] | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise AIConfigError("GEMINI_API_KEY is not set")
        if not model or not model.strip():
            raise AIConfigError("GEMINI_MODEL is not set")
        self._model = model.strip()
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._timeout = timeout
        self._max_attempts = max(1, int(max_attempts))
        self._sleeper = sleeper or time.sleep
        self._rand = rand or random.random
        self._client = client if client is not None else self._build_client(api_key.strip())

    @staticmethod
    def _build_client(api_key: str) -> Any:
        from google import genai

        return genai.Client(api_key=api_key)

    @classmethod
    def from_settings(cls, settings: Settings) -> "GeminiProvider":
        return cls(
            settings.gemini_api_key,
            settings.gemini_model,
            temperature=settings.ai_temperature,
            max_output_tokens=settings.ai_max_output_tokens,
            timeout=settings.ai_timeout_seconds,
            max_attempts=settings.ai_max_attempts,
        )

    def generate_structured(
        self, *, prompt: str, system: str, schema: type[SchemaT]
    ) -> SchemaT:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=self._temperature,
            max_output_tokens=self._max_output_tokens,
        )

        def _call() -> Any:
            return self._client.models.generate_content(
                model=self._model, contents=prompt, config=config
            )

        def _on_retry(attempt: int, delay: float, exc: BaseException) -> None:
            logger.warning(
                "Gemini request failed (attempt %s/%s), retrying in %.2fs: %s",
                attempt,
                self._max_attempts,
                delay,
                type(exc).__name__,
            )

        try:
            response = call_with_retry(
                _call,
                max_attempts=self._max_attempts,
                sleeper=self._sleeper,
                rand=self._rand,
                retryable=is_retryable_ai_error,
                on_retry=_on_retry,
            )
        except Exception as exc:  # noqa: BLE001 - mapped below
            raise _map_ai_error(exc) from exc

        return self._parse_response(response, schema)

    @staticmethod
    def _parse_response(response: Any, schema: type[SchemaT]) -> SchemaT:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        if parsed is not None:
            try:
                return schema.model_validate(parsed)
            except ValidationError as exc:
                raise AIResponseError(f"model output failed schema validation: {exc}") from exc

        text = getattr(response, "text", None)
        if not text:
            raise AIResponseError("model returned no content")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise AIResponseError("model did not return valid JSON") from exc
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise AIResponseError(f"model output failed schema validation: {exc}") from exc


def _map_ai_error(exc: BaseException) -> Exception:
    status = _status_code(exc)
    preview = str(exc).replace("\n", " ").strip()[:300]
    if status == 429:
        return AIRateLimitError("Gemini rate limit exceeded after retries.")
    if status in (401, 403):
        return AIConfigError("Gemini rejected the API key (HTTP %s)." % status)
    if status == 404:
        return AIModelError("Gemini model not found (HTTP 404). Check GEMINI_MODEL.")
    if status and 400 <= status < 500:
        return AIModelError(f"Gemini rejected the request (HTTP {status}): {preview}")
    if is_retryable_ai_error(exc):
        return AIModelError(f"Gemini server/transport error after retries: {preview}")
    if isinstance(exc, AINetworkError):
        return exc
    return AIModelError(f"Gemini call failed: {type(exc).__name__}: {preview}")
