from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_lead_service
from app.leads.service import LeadService
from app.main import app
from app.sheets.errors import (
    SheetsAuthError,
    SheetsConfigError,
    SheetsNetworkError,
    SheetsNotFoundError,
    SheetsQuotaError,
)
from app.sheets.repository import LeadStore
from app.sheets.schemas import KEY_JOBS
from fakes import RaisingSheetsClient


def test_health(api_client) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_submit_new_lead(api_client) -> None:
    response = api_client.post("/api/v1/leads", json={"username": "@Some.Creator"})
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    lead = body["lead"]
    assert lead["username"] == "Some.Creator"
    assert lead["username_normalized"] == "some.creator"
    assert lead["status"] == "queued"
    assert lead["lead_id"].startswith("ld_")
    assert lead["profile_url"] == "https://www.instagram.com/some.creator/"


def test_duplicate_submission_returns_existing(api_client) -> None:
    first = api_client.post("/api/v1/leads", json={"username": "creator.one"})
    assert first.status_code == 201
    lead_id = first.json()["lead"]["lead_id"]

    # Same username in different forms must not create a second row.
    for variant in ("Creator.One", "@creator.one", "https://instagram.com/creator.one/"):
        duplicate = api_client.post("/api/v1/leads", json={"username": variant})
        assert duplicate.status_code == 200
        assert duplicate.json()["created"] is False
        assert duplicate.json()["lead"]["lead_id"] == lead_id

    listing = api_client.get("/api/v1/leads").json()
    assert listing["total"] == 1


@pytest.mark.parametrize(
    "username",
    [
        "",
        "https://example.com/foo",
        "https://www.instagram.com/p/ABC123",
        "bad handle!",
        "a" * 31,
        ".leading",
        "dou..ble",
    ],
)
def test_invalid_username_is_rejected(api_client, username: str) -> None:
    response = api_client.post("/api/v1/leads", json={"username": username})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_unknown_field_is_rejected(api_client) -> None:
    response = api_client.post(
        "/api/v1/leads", json={"username": "ok.name", "unexpected": 1}
    )
    assert response.status_code == 422


def test_get_lead_by_id(api_client) -> None:
    lead_id = api_client.post("/api/v1/leads", json={"username": "fetch.me"}).json()["lead"]["lead_id"]
    response = api_client.get(f"/api/v1/leads/{lead_id}")
    assert response.status_code == 200
    assert response.json()["lead_id"] == lead_id


def test_get_missing_lead_returns_404(api_client) -> None:
    response = api_client.get("/api/v1/leads/ld_does_not_exist")
    assert response.status_code == 404


def test_submit_enqueues_profile_fetch_job(api_client, job_store) -> None:
    response = api_client.post("/api/v1/leads", json={"username": "job.creator"})
    assert response.status_code == 201
    lead_id = response.json()["lead"]["lead_id"]

    jobs = job_store.read_rows(KEY_JOBS)
    assert len(jobs) == 1
    assert jobs[0].values["stage"] == "profile_fetch"
    assert jobs[0].values["leadId"] == lead_id
    assert jobs[0].values["status"] == "queued"


def test_duplicate_submission_does_not_duplicate_job(api_client, job_store) -> None:
    api_client.post("/api/v1/leads", json={"username": "dup.job"})
    api_client.post("/api/v1/leads", json={"username": "@Dup.Job"})
    assert len(job_store.read_rows(KEY_JOBS)) == 1


def test_list_pagination(api_client) -> None:
    for index in range(5):
        api_client.post("/api/v1/leads", json={"username": f"page.creator.{index}"})

    page1 = api_client.get("/api/v1/leads", params={"limit": 2, "offset": 0}).json()
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert page1["limit"] == 2 and page1["offset"] == 0

    page3 = api_client.get("/api/v1/leads", params={"limit": 2, "offset": 4}).json()
    assert len(page3["items"]) == 1


def test_list_search_and_status_filter(api_client, api_store: LeadStore) -> None:
    alpha = api_client.post("/api/v1/leads", json={"username": "alpha.one"}).json()["lead"]
    api_client.post("/api/v1/leads", json={"username": "bravo.two"})
    api_store.update_by_key("ig_leads", alpha["lead_id"], {"bio": "crypto educator"})
    api_store.update_by_key("ig_leads", alpha["lead_id"], {"status": "done"})

    found = api_client.get("/api/v1/leads", params={"q": "crypto"}).json()
    assert found["total"] == 1
    assert found["items"][0]["username"] == "alpha.one"

    done = api_client.get("/api/v1/leads", params={"status": "done"}).json()
    assert done["total"] == 1
    assert done["items"][0]["status"] == "done"

    queued = api_client.get("/api/v1/leads", params={"status": "queued"}).json()
    assert queued["total"] == 1


def test_limit_is_validated(api_client) -> None:
    assert api_client.get("/api/v1/leads", params={"limit": 0}).status_code == 422
    assert api_client.get("/api/v1/leads", params={"limit": 501}).status_code == 422


def test_missing_configuration_returns_503() -> None:
    def _raise_not_configured() -> LeadService:
        raise SheetsConfigError("GOOGLE_SHEETS_SPREADSHEET_ID is not set")

    app.dependency_overrides[get_lead_service] = _raise_not_configured
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/leads")
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (SheetsQuotaError("quota"), 503),
        (SheetsNetworkError("timeout"), 502),
        (SheetsNotFoundError("missing"), 502),
        (SheetsAuthError("bad credentials"), 502),
    ],
)
def test_sheets_errors_are_mapped(exc: Exception, expected_status: int) -> None:
    store = LeadStore(RaisingSheetsClient(exc), tab_names={"ig_leads": "IG Leads"})
    service = LeadService(store)
    app.dependency_overrides[get_lead_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/leads")
        assert response.status_code == expected_status
        assert "detail" in response.json()
    finally:
        app.dependency_overrides.clear()
