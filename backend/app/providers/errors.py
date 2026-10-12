"""Error types for external data providers (HikerAPI, later Gemini, ...)."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for external provider failures."""


class HikerAPIError(ProviderError):
    """Base class for HikerAPI failures."""


class HikerAPIConfigError(HikerAPIError):
    """Missing or invalid client configuration (e.g. no API key)."""


class HikerAPIAuthError(HikerAPIError):
    """The API key is missing, invalid, or unauthorized (HTTP 401/403)."""


class HikerAPINotFoundError(HikerAPIError):
    """The requested profile does not exist (HTTP 404)."""


class HikerAPIQuotaError(HikerAPIError):
    """Insufficient balance / quota (HTTP 402)."""


class HikerAPIRateLimitError(HikerAPIError):
    """Rate limited after exhausting retries (HTTP 429)."""


class HikerAPINetworkError(HikerAPIError):
    """Transport failure (timeout, connection error) after retries."""


class HikerAPIResponseError(HikerAPIError):
    """The provider returned a non-JSON or unexpected payload."""


class AIError(ProviderError):
    """Base class for AI provider failures."""


class AIConfigError(AIError):
    """Missing or invalid AI configuration (e.g. no API key)."""


class AIRateLimitError(AIError):
    """The AI provider rate-limited the request after retries."""


class AIModelError(AIError):
    """The AI provider rejected the request (bad model/params) or failed."""


class AIResponseError(AIError):
    """The model returned malformed output that failed schema validation."""


class AINetworkError(AIError):
    """Transport failure talking to the AI provider."""
