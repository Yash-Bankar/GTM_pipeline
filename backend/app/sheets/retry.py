"""Google Sheets retry helpers.

The generic ``call_with_retry`` lives in ``app.common.retry`` and is re-exported
here for backwards compatibility. This module adds Google-specific transient
detection (``HttpError`` statuses, httplib2 transport errors).
"""

from __future__ import annotations

from typing import Callable, TypeVar

from googleapiclient.errors import HttpError

import httplib2

from app.common.retry import call_with_retry as _call_with_retry

T = TypeVar("T")

# HTTP statuses that are worth retrying.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
# Transport-level exceptions that are worth retrying.
TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    httplib2.HttpLib2Error,
    TimeoutError,
    ConnectionError,
    OSError,
)


def http_status(exc: BaseException) -> int:
    """Best-effort extraction of an HTTP status code from an HttpError."""
    if not isinstance(exc, HttpError):
        return 0
    resp = getattr(exc, "resp", None)
    candidates = [
        getattr(resp, "status", None),
        resp.get("status") if hasattr(resp, "get") else None,
        getattr(exc, "status_code", None),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return 0


def _looks_like_quota(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "quota",
            "rate limit",
            "ratelimit",
            "userratelimitexceeded",
            "too many requests",
        )
    )


def is_retryable(exc: BaseException) -> bool:
    """Return True when an exception represents a transient failure."""
    if isinstance(exc, HttpError):
        status = http_status(exc)
        if status in RETRYABLE_STATUSES:
            return True
        if status == 403 and _looks_like_quota(str(exc)):
            return True
        return False
    return isinstance(exc, TRANSPORT_ERRORS)


def is_quota_error(exc: BaseException) -> bool:
    """Return True for HTTP 429 (or 403 quota) rate-limit errors.

    These need a much longer backoff than ordinary 5xx errors so the client does
    not immediately burn the 60 requests/minute Sheets quota again.
    """
    if not isinstance(exc, HttpError):
        return False
    status = http_status(exc)
    if status == 429:
        return True
    return status == 403 and _looks_like_quota(str(exc))


def quota_backoff(attempt: int, *, base: float = 10.0, maximum: float = 60.0) -> float:
    """Dedicated exponential backoff for quota errors: base, 2x, 4x... capped.

    With the defaults this yields 10s, 20s, 40s, 60s, 60s, ...
    """
    return min(maximum, base * (2 ** (max(1, attempt) - 1)))


def make_delay_for(
    *, quota_base: float = 10.0, quota_maximum: float = 60.0
) -> Callable[[BaseException, int], float | None]:
    """Build a ``delay_for`` hook that applies the long quota backoff for 429s.

    Returns ``None`` for non-quota errors so ``call_with_retry`` falls back to its
    normal (jittered) curve.
    """

    def delay_for(exc: BaseException, attempt: int) -> float | None:
        if is_quota_error(exc):
            return quota_backoff(attempt, base=quota_base, maximum=quota_maximum)
        return None

    return delay_for


def call_with_retry(
    func: Callable[[], T],
    *,
    retryable: Callable[[BaseException], bool] = is_retryable,
    **kwargs: object,
) -> T:
    """Sheets wrapper: defaults to Google transient-error detection."""
    return _call_with_retry(func, retryable=retryable, **kwargs)  # type: ignore[arg-type]

