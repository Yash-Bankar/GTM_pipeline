from __future__ import annotations

import pytest

from app.common.retry import call_with_retry


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
        retryable=lambda exc: isinstance(exc, TimeoutError),
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_exhausts_attempts_then_raises() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise TimeoutError("always")

    with pytest.raises(TimeoutError):
        call_with_retry(
            fn,
            max_attempts=3,
            sleeper=lambda _: None,
            rand=lambda: 0.5,
            retryable=lambda exc: isinstance(exc, TimeoutError),
        )
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
        retryable=lambda exc: isinstance(exc, TimeoutError),
    )
    assert sleeps == [1.0, 2.0, 3.0, 3.0]


def test_delay_for_override_is_used_verbatim() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError()
        return "ok"

    call_with_retry(
        fn,
        max_attempts=4,
        sleeper=sleeps.append,
        rand=lambda: 0.0,
        retryable=lambda exc: isinstance(exc, TimeoutError),
        delay_for=lambda exc, attempt: 10.0 * attempt,
    )
    assert sleeps == [10.0, 20.0]
