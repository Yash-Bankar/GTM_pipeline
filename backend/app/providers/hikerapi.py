"""HikerAPI client: profile fetching only.

Ported selectively from the legacy reference implementation
(``user/by/username`` + ``to_lead_row``) and rebuilt on this repo's conventions:
typed output, validation, timeouts, bounded retries and typed errors. No recent-
media research, no website crawling and no Gemini calls live here.

Endpoint and auth follow the current HikerAPI docs:
``GET https://api.hikerapi.com/v2/user/by/username`` with header
``x-access-key``.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable

import httpx

from app.common.retry import call_with_retry
from app.config import Settings
from app.leads.validation import InvalidLeadInput, parse_lead_input

from .errors import (
    HikerAPIAuthError,
    HikerAPIConfigError,
    HikerAPIError,
    HikerAPINetworkError,
    HikerAPINotFoundError,
    HikerAPIQuotaError,
    HikerAPIRateLimitError,
    HikerAPIResponseError,
)
from .models import (
    HikerPost,
    HikerProfile,
    parse_media_payload,
    parse_profile_payload,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.hikerapi.com/v2"
USER_BY_USERNAME_PATH = "/user/by/username"
USER_MEDIAS_PATH = "/user/medias"
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class _RetryableStatus(Exception):
    """Internal marker for a transient HTTP status worth retrying."""

    def __init__(self, status: int) -> None:
        super().__init__(f"retryable status {status}")
        self.status = status


class HikerAPIClient:
    """Minimal, typed HikerAPI client for Instagram profile lookups."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        max_attempts: int = 4,
        backoff_base: float = 0.5,
        backoff_max: float = 10.0,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
        rand: Callable[[], float] | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise HikerAPIConfigError("HIKERAPI_KEY is not set")
        self._api_key = api_key.strip()
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._max_attempts = max(1, int(max_attempts))
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._sleeper = sleeper or time.sleep
        self._rand = rand or random.random
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client(
            base_url=self._base_url, timeout=timeout
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "HikerAPIClient":
        return cls(
            settings.hikerapi_key,
            base_url=settings.hikerapi_base_url,
            timeout=settings.hikerapi_timeout_seconds,
            max_attempts=settings.hikerapi_max_attempts,
            backoff_base=settings.hikerapi_backoff_base_seconds,
            backoff_max=settings.hikerapi_backoff_max_seconds,
        )

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "HikerAPIClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- public API ---------------------------------------------------------

    def fetch_profile(self, username: str) -> HikerProfile:
        """Fetch and normalize a public profile.

        Raises ``InvalidLeadInput`` for a bad username/URL and a ``HikerAPI*``
        error for provider failures.
        """
        parsed = parse_lead_input(username)
        payload = self._request_profile(parsed.normalized)
        return parse_profile_payload(payload)

    def fetch_profile_or_none(self, username: str) -> HikerProfile | None:
        try:
            return self.fetch_profile(username)
        except HikerAPINotFoundError:
            return None

    def validate_key(self) -> bool:
        """Return True when the API key can fetch a known public profile."""
        try:
            self.fetch_profile("instagram")
            return True
        except (HikerAPIError, InvalidLeadInput):
            return False

    # -- internals ----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"accept": "application/json", "x-access-key": self._api_key}

    def _get(self, path: str, params: dict[str, Any], *, context: str) -> Any:
        def _do_request() -> httpx.Response:
            response = self._http.get(path, params=params, headers=self._headers())
            if response.status_code in _RETRYABLE_STATUSES:
                raise _RetryableStatus(response.status_code)
            return response

        def _retryable(exc: BaseException) -> bool:
            return isinstance(exc, (_RetryableStatus, httpx.TransportError))

        def _on_retry(attempt: int, delay: float, exc: BaseException) -> None:
            logger.warning(
                "HikerAPI request (%s) failed (attempt %s/%s), retrying in %.2fs: %s",
                context,
                attempt,
                self._max_attempts,
                delay,
                type(exc).__name__,
            )

        try:
            response = call_with_retry(
                _do_request,
                max_attempts=self._max_attempts,
                backoff_base=self._backoff_base,
                backoff_max=self._backoff_max,
                sleeper=self._sleeper,
                rand=self._rand,
                retryable=_retryable,
                on_retry=_on_retry,
            )
        except _RetryableStatus as exc:
            if exc.status == 429:
                raise HikerAPIRateLimitError(
                    "HikerAPI rate limit exceeded after retries."
                ) from exc
            raise HikerAPIError(
                f"HikerAPI server error (HTTP {exc.status}) after retries."
            ) from exc
        except httpx.TransportError as exc:
            raise HikerAPINetworkError(
                f"HikerAPI request failed: {type(exc).__name__}: {exc}"
            ) from exc

        return self._parse_response(response)

    def _request_profile(self, username: str) -> dict[str, Any]:
        payload = self._get(
            USER_BY_USERNAME_PATH, {"username": username}, context=f"@{username}"
        )
        if not isinstance(payload, dict) or not (
            isinstance(payload.get("user"), dict) or payload.get("username")
        ):
            raise HikerAPIResponseError(
                "HikerAPI response did not contain a user object."
            )
        return payload

    def fetch_recent_posts(
        self, user_id: str, *, limit: int = 12, max_pages: int = 2
    ) -> list[HikerPost]:
        """Fetch up to ``limit`` recent media items for a user id (bounded pages)."""
        if not user_id or not str(user_id).strip():
            raise InvalidLeadInput("A user id is required to fetch media.")

        posts: list[HikerPost] = []
        page_id = ""
        for _page in range(max(1, int(max_pages))):
            params: dict[str, Any] = {"user_id": str(user_id)}
            if page_id:
                params["page_id"] = page_id
            payload = self._get(USER_MEDIAS_PATH, params, context=f"user_id={user_id}")
            page_posts, page_id = parse_media_payload(payload)
            posts.extend(page_posts)
            if len(posts) >= limit or not page_id:
                break
        return posts[:limit]

    @staticmethod
    def _parse_response(response: httpx.Response) -> Any:
        status = response.status_code
        if status == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise HikerAPIResponseError(
                    "HikerAPI returned a non-JSON response."
                ) from exc
        if status in (401, 403):
            raise HikerAPIAuthError("HikerAPI rejected the API key (HTTP %s)." % status)
        if status == 404:
            raise HikerAPINotFoundError("HikerAPI resource was not found (HTTP 404).")
        if status == 402:
            raise HikerAPIQuotaError("HikerAPI balance/quota exhausted (HTTP 402).")
        raise HikerAPIResponseError(f"HikerAPI returned unexpected HTTP {status}.")
