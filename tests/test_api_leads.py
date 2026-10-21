from __future__ import annotations

import json

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
    # Complete alpha's research so its derived progress becomes "ready".
    repo.complete(repo.find_job("profile_fetch", alpha["lead_id"]), "ok")
    repo.update_lead(alpha["lead_id"], {"bio": "crypto educator", "status": "enriched"})

    found = api_client.get("/api/v1/leads", params={"q": "crypto"}).json()
    assert found["total"] == 1
    assert found["items"][0]["username"] == "alpha.one"

    # The status filter matches the derived progress, not the raw lead status.
    ready = api_client.get("/api/v1/leads", params={"status": "complete"}).json()
    assert ready["total"] == 1
    assert ready["items"][0]["username"] == "alpha.one"

    queued = api_client.get("/api/v1/leads", params={"status": "queued"}).json()
    assert queued["total"] == 1
    assert queued["items"][0]["username"] == "bravo.two"


def test_terminal_profile_error_is_blocked_everywhere(api_client, repo: Repository) -> None:
    """A HikerAPI 401 surfaces as a consistent `blocked` state (PRD A09/A26)."""
    lead_id = api_client.post("/api/v1/leads", json={"username": "auth.fail"}).json()["lead"]["lead_id"]
    repo.fail(
        repo.claim_next(worker_id="w1"),
        "HikerAPIAuthError: HikerAPI rejected the API key (HTTP 401).",
        retryable=False,
    )

    listing = api_client.get("/api/v1/leads", params={"status": "blocked"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["progress"] == "blocked"
    assert "HIKERAPI_KEY" in listing["items"][0]["progress_remedy"]

    detail = api_client.get(f"/api/v1/leads/{lead_id}").json()
    assert detail["progress"] == "blocked"
    assert "HIKERAPI_KEY" in detail["progress_remedy"]

    stats = api_client.get("/api/v1/stats").json()
    assert stats["leads_by_progress"]["blocked"] == 1


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


def _snapshot(**overrides) -> dict:
    base = {
        "display_name": "Example Creator",
        "is_verified": True,
        "bio": "Personal finance education.",
        "external_urls": ["https://example.com/?utm_source=ig&utm_medium=bio"],
        "followers": {"value": 12300, "display": "12.3K", "precision": "approximate"},
        "following": {"value": None, "display": "", "precision": "unknown"},
        "post_count": None,
        "source_url": "https://www.instagram.com/example.creator/",
        "captured_at": "2026-10-19T04:50:00Z",
        "parser_version": "1",
        "missing_fields": [],
    }
    base.update(overrides)
    return base


def test_submit_with_snapshot_fills_lead_and_persists(api_client, repo: Repository) -> None:
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": "example.creator",
            "source": "extension",
            "request_id": "req-1",
            "profile_snapshot": _snapshot(),
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["outcome"] == "new"
    assert set(body["missing_fields"]) == {"following", "post_count"}

    lead = body["lead"]
    assert lead["full_name"] == "Example Creator"
    assert lead["bio"] == "Personal finance education."
    assert lead["follower_count"] == 12300
    # Tracking parameters are stripped from stored external URLs.
    assert lead["external_url"] == "https://example.com/"

    stored = repo.get_lead(lead["lead_id"])
    assert stored is not None
    persisted = json.loads(stored.profile_snapshot)
    assert persisted["is_verified"] is True
    assert persisted["followers"]["precision"] == "approximate"
    assert persisted["following"]["value"] is None
    assert stored.request_id == "req-1"


def test_repeat_request_id_returns_original_without_new_job(api_client, repo: Repository) -> None:
    payload = {
        "username": "repeat.creator",
        "request_id": "req-dup",
        "profile_snapshot": _snapshot(source_url="https://www.instagram.com/repeat.creator/"),
    }
    first = api_client.post("/api/v1/leads", json=payload)
    assert first.status_code == 201
    lead_id = first.json()["lead"]["lead_id"]
    jobs_after_first = len(repo.list_jobs(lead_id))

    second = api_client.post("/api/v1/leads", json=payload)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["lead"]["lead_id"] == lead_id
    assert len(repo.list_jobs(lead_id)) == jobs_after_first


def test_newer_snapshot_updates_and_stale_never_erases(api_client) -> None:
    first = api_client.post(
        "/api/v1/leads",
        json={"username": "keep.creator", "request_id": "req-a", "profile_snapshot": _snapshot()},
    )
    assert first.status_code == 201

    second = api_client.post(
        "/api/v1/leads",
        json={
            "username": "keep.creator",
            "request_id": "req-b",
            "profile_snapshot": _snapshot(display_name="Changed Name", bio="Changed bio"),
        },
    )
    assert second.status_code == 200
    # Newer evidence may update known fields (V2-02).
    assert second.json()["outcome"] == "updated"
    assert second.json()["lead"]["full_name"] == "Changed Name"
    assert second.json()["lead"]["bio"] == "Changed bio"

    # An older snapshot is retained as history but must not mutate the lead.
    stale = api_client.post(
        "/api/v1/leads",
        json={
            "username": "keep.creator",
            "request_id": "req-c",
            "profile_snapshot": _snapshot(
                display_name="Stale Name",
                bio="Stale bio",
                captured_at="2026-10-18T00:00:00Z",
                external_urls=["https://extra.example/"],
            ),
        },
    )
    assert stale.status_code == 200
    body = stale.json()
    assert body["outcome"] == "unchanged"
    assert body["lead"]["full_name"] == "Changed Name"
    assert body["lead"]["bio"] == "Changed bio"
    assert "https://extra.example/" not in body["lead"]["all_external_urls"]


def test_malformed_optional_snapshot_fields_become_missing(api_client) -> None:
    long_bio = "x" * 2500
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": "malformed.creator",
            "profile_snapshot": _snapshot(
                bio=long_bio,
                external_urls=["javascript:alert(1)", "https://ok.example/path?utm_campaign=x"],
                followers={"value": 500, "display": "500", "precision": "weird"},
            ),
        },
    )
    assert response.status_code == 201
    body = response.json()
    lead = body["lead"]
    assert len(lead["bio"]) == 2200
    assert lead["external_url"] == "https://ok.example/path"
    # An unrecognized precision is treated as unknown, not a fabricated exact value.
    assert "followers" in body["missing_fields"]
    assert lead["follower_count"] == 0


def test_snapshot_external_urls_are_capped(api_client) -> None:
    urls = [f"https://site{index}.example/" for index in range(15)]
    response = api_client.post(
        "/api/v1/leads",
        json={"username": "many.urls", "profile_snapshot": _snapshot(external_urls=urls)},
    )
    assert response.status_code == 201
    stored_urls = response.json()["lead"]["all_external_urls"].split(",")
    assert len(stored_urls) == 10


def test_handle_only_submission_still_works(api_client) -> None:
    response = api_client.post("/api/v1/leads", json={"username": "plain.handle"})
    assert response.status_code == 201
    assert response.json()["outcome"] == "new"
    assert response.json()["missing_fields"] == []


def test_lead_response_exposes_snapshot(api_client) -> None:
    api_client.post(
        "/api/v1/leads",
        json={"username": "expose.snap", "profile_snapshot": _snapshot()},
    )

    listing = api_client.get("/api/v1/leads", params={"q": "expose.snap"}).json()
    lead = listing["items"][0]
    assert lead["snapshot"]["is_verified"] is True
    assert lead["snapshot"]["followers"]["display"] == "12.3K"
    assert lead["snapshot"]["followers"]["precision"] == "approximate"
    assert lead["snapshot"]["external_urls"] == ["https://example.com/"]
    assert set(lead["snapshot"]["missing_fields"]) == {"following", "post_count"}
    # `snapshot.bio` is redundant; the lead row carries the canonical bio (V2-01
    # withdrew blanket contact masking).
    assert "bio" not in lead["snapshot"]

    detail = api_client.get(f"/api/v1/leads/{lead['lead_id']}/detail").json()
    assert detail["lead"]["snapshot"]["is_verified"] is True
    assert detail["lead"]["snapshot"]["source_url"] == "https://www.instagram.com/example.creator/"


def test_lead_response_without_snapshot_is_null(api_client) -> None:
    api_client.post("/api/v1/leads", json={"username": "no.snap"})
    listing = api_client.get("/api/v1/leads", params={"q": "no.snap"}).json()
    assert listing["items"][0]["snapshot"] is None
