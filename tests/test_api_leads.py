from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.repository import Repository
from app.main import app
from app.dependencies import get_repository


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


def test_submit_enqueues_profile_fetch_job(api_client, repo: Repository) -> None:
    response = api_client.post("/api/v1/leads", json={"username": "job.creator"})
    lead_id = response.json()["lead"]["lead_id"]
    job = repo.find_job("profile_fetch", lead_id)
    assert job is not None
    assert job.status == "queued"


def test_duplicate_submission_returns_existing(api_client) -> None:
    first = api_client.post("/api/v1/leads", json={"username": "creator.one"})
    assert first.status_code == 201
    lead_id = first.json()["lead"]["lead_id"]

    for variant in ("Creator.One", "@creator.one", "https://instagram.com/creator.one/"):
        duplicate = api_client.post("/api/v1/leads", json={"username": variant})
        assert duplicate.status_code == 200
        assert duplicate.json()["created"] is False
        assert duplicate.json()["lead"]["lead_id"] == lead_id

    assert api_client.get("/api/v1/leads").json()["total"] == 1


@pytest.mark.parametrize(
    "username",
    ["", "https://example.com/foo", "https://www.instagram.com/p/ABC123", "bad handle!", "a" * 31, ".leading"],
)
def test_invalid_username_is_rejected(api_client, username: str) -> None:
    response = api_client.post("/api/v1/leads", json={"username": username})
    assert response.status_code == 422


def test_unknown_field_is_rejected(api_client) -> None:
    response = api_client.post("/api/v1/leads", json={"username": "ok.name", "unexpected": 1})
    assert response.status_code == 422


def test_get_lead_by_id(api_client) -> None:
    lead_id = api_client.post("/api/v1/leads", json={"username": "fetch.me"}).json()["lead"]["lead_id"]
    response = api_client.get(f"/api/v1/leads/{lead_id}")
    assert response.status_code == 200
    assert response.json()["lead_id"] == lead_id


def test_get_missing_lead_returns_404(api_client) -> None:
    assert api_client.get("/api/v1/leads/ld_does_not_exist").status_code == 404


def test_list_pagination(api_client) -> None:
    for index in range(5):
        api_client.post("/api/v1/leads", json={"username": f"page.creator.{index}"})
    page1 = api_client.get("/api/v1/leads", params={"limit": 2, "offset": 0}).json()
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    page3 = api_client.get("/api/v1/leads", params={"limit": 2, "offset": 4}).json()
    assert len(page3["items"]) == 1


def test_list_search_and_status_filter(api_client, repo: Repository) -> None:
    alpha = api_client.post("/api/v1/leads", json={"username": "alpha.one"}).json()["lead"]
    api_client.post("/api/v1/leads", json={"username": "bravo.two"})
    repo.update_lead(alpha["lead_id"], {"bio": "crypto educator", "status": "done"})

    found = api_client.get("/api/v1/leads", params={"q": "crypto"}).json()
    assert found["total"] == 1
    assert found["items"][0]["username"] == "alpha.one"

    done = api_client.get("/api/v1/leads", params={"status": "done"}).json()
    assert done["total"] == 1


def test_limit_is_validated(api_client) -> None:
    assert api_client.get("/api/v1/leads", params={"limit": 0}).status_code == 422
    assert api_client.get("/api/v1/leads", params={"limit": 501}).status_code == 422


def test_database_error_returns_503(session_factory) -> None:
    def _boom():
        raise OperationalError("select 1", {}, Exception("db down"))

    app.dependency_overrides[get_repository] = _boom
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/leads")
        assert response.status_code == 503
        assert "Database is unavailable" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
