from __future__ import annotations

import httpx
import pytest

from app.leads.validation import InvalidLeadInput
from app.providers.errors import (
    HikerAPIAuthError,
    HikerAPIConfigError,
    HikerAPIError,
    HikerAPINetworkError,
    HikerAPINotFoundError,
    HikerAPIQuotaError,
    HikerAPIRateLimitError,
    HikerAPIResponseError,
)
from app.providers.hikerapi import HikerAPIClient
from hiker_fixtures import SAMPLE_PROFILE_PAYLOAD

BASE_URL = "https://api.hikerapi.com/v2"


def build_client(handler, **overrides) -> HikerAPIClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    params = dict(sleeper=lambda _delay: None, rand=lambda: 1.0)
    params.update(overrides)
    return HikerAPIClient("test-key", http_client=http, **params)


def test_success_sends_expected_request_and_normalizes() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["username"] = request.url.params.get("username")
        seen["key"] = request.headers.get("x-access-key")
        return httpx.Response(200, json=SAMPLE_PROFILE_PAYLOAD)

    client = build_client(handler)
    profile = client.fetch_profile("NatGeo")

    assert seen["path"] == "/v2/user/by/username"
    assert seen["username"] == "natgeo"  # normalized, lowercased
    assert seen["key"] == "test-key"
    assert profile.username == "natgeo"
    assert profile.follower_count == 274988955


def test_not_found_raises_and_or_none_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"status": "fail"})

    client = build_client(handler)
    with pytest.raises(HikerAPINotFoundError):
        client.fetch_profile("ghost")
    assert client.fetch_profile_or_none("ghost") is None


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "unauthorized"})

    client = build_client(handler)
    with pytest.raises(HikerAPIAuthError):
        client.fetch_profile("someone")


def test_quota_error_402() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"message": "insufficient balance"})

    client = build_client(handler)
    with pytest.raises(HikerAPIQuotaError):
        client.fetch_profile("someone")


def test_rate_limit_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"message": "slow down"})
        return httpx.Response(200, json=SAMPLE_PROFILE_PAYLOAD)

    client = build_client(handler, max_attempts=3)
    profile = client.fetch_profile("natgeo")
    assert calls["n"] == 2
    assert profile.username == "natgeo"


def test_rate_limit_exhausts_to_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429)

    client = build_client(handler, max_attempts=3)
    with pytest.raises(HikerAPIRateLimitError):
        client.fetch_profile("natgeo")
    assert calls["n"] == 3


def test_server_error_after_retries() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client = build_client(handler, max_attempts=2)
    with pytest.raises(HikerAPIError):
        client.fetch_profile("natgeo")
    assert calls["n"] == 2


def test_timeout_becomes_network_error() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectTimeout("timed out")

    client = build_client(handler, max_attempts=2)
    with pytest.raises(HikerAPINetworkError):
        client.fetch_profile("natgeo")
    assert calls["n"] == 2


def test_invalid_json_is_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    client = build_client(handler)
    with pytest.raises(HikerAPIResponseError):
        client.fetch_profile("natgeo")


def test_missing_user_is_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    client = build_client(handler)
    with pytest.raises(HikerAPIResponseError):
        client.fetch_profile("natgeo")


def test_invalid_username_rejected_without_http_call() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=SAMPLE_PROFILE_PAYLOAD)

    client = build_client(handler)
    with pytest.raises(InvalidLeadInput):
        client.fetch_profile("not a handle!")
    assert calls["n"] == 0


def test_validate_key_true_and_false() -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SAMPLE_PROFILE_PAYLOAD)

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    assert build_client(ok).validate_key() is True
    assert build_client(unauthorized).validate_key() is False


def test_missing_key_raises_config_error() -> None:
    with pytest.raises(HikerAPIConfigError):
        HikerAPIClient("   ")
