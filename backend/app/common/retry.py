"""Shared retry helper (provider-agnostic).

Kept free of any Google/HTTP-library imports so it can be reused by the Sheets
client and external API providers alike.
"""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def call_with_retry(
    func: Callable[[], T],
    *,
    max_attempts: int = 5,
    backoff_base: float = 0.5,
    backoff_max: float = 30.0,
    sleeper: Callable[[float], None] = time.sleep,
    rand: Callable[[], float] = random.random,
    retryable: Callable[[BaseException], bool] | None = None,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
    delay_for: Callable[[BaseException, int], float | None] | None = None,
) -> T:
    """Call ``func`` with exponential backoff on transient failures.

    :param max_attempts: total attempts (>= 1).
    :param backoff_base: base delay in seconds.
    :param backoff_max: maximum delay in seconds.
    :param sleeper: sleep function (injected for tests).
    :param rand: random source in [0, 1) used for full jitter.
    :param retryable: predicate deciding whether an exception is transient;
        defaults to "never retry".
    :param on_retry: optional callback ``(attempt, delay, exc)`` before sleeping.
    :param delay_for: optional ``(exc, attempt) -> seconds | None`` override.
        When it returns a number that exact delay is used (no jitter), which lets
        callers apply a dedicated, longer backoff for specific errors (e.g. HTTP
        429 quota) while everything else uses the default curve.
    """
    if retryable is None:
        def retryable(_exc: BaseException) -> bool:
            return False

    attempts = max(1, int(max_attempts))
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - re-raised below
            if attempt >= attempts or not retryable(exc):
                raise
            override = delay_for(exc, attempt) if delay_for is not None else None
            if override is not None:
                delay = max(0.0, float(override))
            else:
                ceiling = min(backoff_max, backoff_base * (2 ** (attempt - 1)))
                delay = ceiling * rand()
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            sleeper(delay)
