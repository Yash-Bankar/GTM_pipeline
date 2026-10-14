"""Contract tests mirroring the Chrome extension's requests to the API."""

from __future__ import annotations

from app.config import get_settings


def test_extension_payload_creates_then_reports_duplicate(api_client) -> None:
    body = {"username": "creator.one", "source": "extension"}
    first = api_client.post("/api/v1/leads", json=body)
    assert first.status_code == 201
    assert first.json()["created"] is True
    lead_id = first.json()["lead"]["lead_id"]

    second = api_client.post("/api/v1/leads", json=body)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["lead"]["lead_id"] == lead_id


def test_extension_invalid_profile_url_is_rejected(api_client) -> None:
    response = api_client.post(
        "/api/v1/leads", json={"username": "https://example.com/not-a-profile", "source": "extension"}
    )
    assert response.status_code == 422


def test_extension_cors_preflight_is_allowed(api_client) -> None:
    response = api_client.options(
        "/api/v1/leads",
        headers={
            "Origin": "chrome-extension://abcdefghijklmnop",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in {k.lower() for k in response.headers}


def test_extension_authentication(api_client, monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "ext-secret")
    get_settings.cache_clear()
    try:
        payload = {"username": "auth.creator", "source": "extension"}
        assert api_client.post("/api/v1/leads", json=payload).status_code == 401
        assert api_client.post("/api/v1/leads", json=payload, headers={"x-api-key": "nope"}).status_code == 401
        assert api_client.post("/api/v1/leads", json=payload, headers={"x-api-key": "ext-secret"}).status_code == 201
    finally:
        monkeypatch.delenv("API_KEY", raising=False)
        get_settings.cache_clear()
