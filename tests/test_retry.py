from __future__ import annotations

import pytest

from app.sheets.retry import (
    call_with_retry,
    http_status,
    is_quota_error,
    is_retryable,
    make_delay_for,
    quota_backoff,
)
from fakes import make_http_error


def test_succeeds_after_transient_failures() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("slow")
        return "ok"

    result = call_with_retry(
        fn,
        max_attempts=5,
        backoff_base=1.0,
        backoff_max=10.0,
        sleeper=sleeps.append,
        rand=lambda: 1.0,
    )

    assert result == "ok"
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]  # exponential, full jitter resolved to 1.0


def test_exhausts_attempts_then_raises() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise TimeoutError("always")

    with pytest.raises(TimeoutError):
        call_with_retry(fn, max_attempts=3, sleeper=lambda _: None, rand=lambda: 0.5)
    assert calls["n"] == 3


def test_non_retryable_raises_immediately() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        call_with_retry(fn, max_attempts=5, sleeper=lambda _: None)
    assert calls["n"] == 1


def test_backoff_is_capped() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 5:
            raise TimeoutError()
        return "ok"

    call_with_retry(
        fn,
        max_attempts=6,
        backoff_base=1.0,
        backoff_max=3.0,
        sleeper=sleeps.append,
        rand=lambda: 1.0,
    )
    assert sleeps == [1.0, 2.0, 3.0, 3.0]


@pytest.mark.parametrize(
    ("status", "expected"),
    [(429, True), (500, True), (502, True), (503, True), (504, True),
     (400, False), (401, False), (403, False), (404, False)],
)
def test_is_retryable_http_statuses(status: int, expected: bool) -> None:
    assert is_retryable(make_http_error(status)) is expected


def test_is_retryable_quota_403() -> None:
    assert is_retryable(make_http_error(403, "Quota exceeded for quota metric")) is True


def test_is_retryable_transport_errors() -> None:
    assert is_retryable(TimeoutError()) is True
    assert is_retryable(ConnectionError()) is True
    assert is_retryable(ValueError()) is False


def test_http_status_extraction() -> None:
    assert http_status(make_http_error(429)) == 429
    assert http_status(ValueError()) == 0

def test_quota_backoff_curve() -> None:
    assert quota_backoff(1) == 10.0
    assert quota_backoff(2) == 20.0
    assert quota_backoff(3) == 40.0
    assert quota_backoff(4) == 60.0
    assert quota_backoff(5) == 60.0


def test_is_quota_error() -> None:
    assert is_quota_error(make_http_error(429)) is True
    assert is_quota_error(make_http_error(403, "Quota exceeded")) is True
    assert is_quota_error(make_http_error(500)) is False
    assert is_quota_error(ValueError()) is False


def test_call_with_retry_uses_long_quota_backoff() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise make_http_error(429)
        return "ok"

    result = call_with_retry(
        fn,
        max_attempts=4,
        sleeper=sleeps.append,
        rand=lambda: 0.0,
        delay_for=make_delay_for(quota_base=10.0, quota_maximum=60.0),
    )
    assert result == "ok"
    assert sleeps == [10.0, 20.0]  # deterministic long backoff, no jitter


def test_call_with_retry_falls_back_when_delay_for_returns_none() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError()
        return "ok"

    call_with_retry(
        fn,
        max_attempts=3,
        backoff_base=1.0,
        backoff_max=10.0,
        sleeper=sleeps.append,
        rand=lambda: 1.0,
        delay_for=make_delay_for(),
    )
    assert sleeps == [1.0]  # non-quota error uses the default curve
