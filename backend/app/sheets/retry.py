"""Retry / exponential backoff helpers.

Kept dependency-free and injectable (sleeper, random) so retry behaviour can be
unit tested deterministically without real waits.
"""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

from googleapiclient.errors import HttpError

import httplib2

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


def call_with_retry(
    func: Callable[[], T],
    *,
    max_attempts: int = 5,
    backoff_base: float = 0.5,
    backoff_max: float = 30.0,
    sleeper: Callable[[float], None] = time.sleep,
    rand: Callable[[], float] = random.random,
    retryable: Callable[[BaseException], bool] = is_retryable,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
) -> T:
    """Call ``func`` with exponential backoff on transient failures.

    :param max_attempts: total attempts (>= 1).
    :param backoff_base: base delay in seconds.
    :param backoff_max: maximum delay in seconds.
    :param sleeper: sleep function (injected for tests).
    :param rand: random source in [0, 1) used for full jitter.
    :param retryable: predicate deciding whether an exception is transient.
    :param on_retry: optional callback ``(attempt, delay, exc)`` before sleeping.
    """
    attempts = max(1, int(max_attempts))
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - re-raised below
            if attempt >= attempts or not retryable(exc):
                raise
            ceiling = min(backoff_max, backoff_base * (2 ** (attempt - 1)))
            delay = ceiling * rand()
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            sleeper(delay)
