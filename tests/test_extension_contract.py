"""Contract tests mirroring the Chrome extension's requests to the API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.dependencies import get_lead_service
from app.leads.service import LeadService
from app.main import app


@pytest.fixture
def client(worker_stores):
    service = LeadService(worker_stores.lead, job_store=worker_stores.jobs)
    app.dependency_overrides[get_lead_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_extension_payload_creates_then_reports_duplicate(client) -> None:
    body = {"username": "creator.one", "source": "extension"}

    first = client.post("/api/v1/leads", json=body)
    assert first.status_code == 201
    assert first.json()["created"] is True
    lead_id = first.json()["lead"]["lead_id"]

    second = client.post("/api/v1/leads", json=body)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["lead"]["lead_id"] == lead_id


def test_extension_invalid_profile_url_is_rejected(client) -> None:
    response = client.post(
        "/api/v1/leads",
        json={"username": "https://example.com/not-a-profile", "source": "extension"},
    )
    assert response.status_code == 422
    assert "detail" in response.json()


def test_extension_cors_preflight_is_allowed(client) -> None:
    response = client.options(
        "/api/v1/leads",
        headers={
            "Origin": "chrome-extension://abcdefghijklmnop",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-api-key",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in {k.lower() for k in response.headers}


def test_extension_authentication(worker_stores, monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "ext-secret")
    get_settings.cache_clear()
    service = LeadService(worker_stores.lead, job_store=worker_stores.jobs)
    app.dependency_overrides[get_lead_service] = lambda: service
    try:
        with TestClient(app) as test_client:
            payload = {"username": "auth.creator", "source": "extension"}

            missing = test_client.post("/api/v1/leads", json=payload)
            assert missing.status_code == 401

            wrong = test_client.post(
                "/api/v1/leads", json=payload, headers={"x-api-key": "nope"}
            )
            assert wrong.status_code == 401

            ok = test_client.post(
                "/api/v1/leads", json=payload, headers={"x-api-key": "ext-secret"}
            )
            assert ok.status_code == 201
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("API_KEY", raising=False)
        get_settings.cache_clear()
