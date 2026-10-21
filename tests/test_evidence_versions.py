"""V2-02: capture receipts, immutable evidence versions, safe merge, recovery.

Covers QA scenarios V01, V02, V03, V04, and V06.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.db.repository import Repository


def _snapshot(**overrides):
    base = {
        "display_name": "Evidence Creator",
        "is_verified": True,
        "bio": "Finance educator. hi@evidence.org",
        "external_urls": ["https://evidence.example/"],
        "followers": {"value": 12300, "display": "12.3K", "precision": "approximate"},
        "following": {"value": 120, "display": "120", "precision": "exact"},
        "post_count": {"value": 42, "display": "42", "precision": "exact"},
        "source_url": "https://www.instagram.com/evidence.creator/",
        "captured_at": "2026-10-19T04:50:00Z",
        "parser_version": "1",
        "missing_fields": [],
    }
    base.update(overrides)
    return base


def _post(api_client, username: str, request_id: str, snapshot: dict | None = None):
    body: dict = {"username": username, "source": "extension", "request_id": request_id}
    if snapshot is not None:
        body["profile_snapshot"] = snapshot
    return api_client.post("/api/v1/leads", json=body)


# -- V01: identity + concurrency ------------------------------------------


def test_v01_handle_url_uppercase_resolve_to_one_lead(api_client, repo: Repository) -> None:
    first = _post(api_client, "@Same.Creator", "v01-a")
    assert first.status_code == 201
    lead_id = first.json()["lead"]["lead_id"]

    for index, variant in enumerate(
        ["same.creator", "https://www.instagram.com/same.creator/", "@SAME.CREATOR"]
    ):
        response = _post(api_client, variant, f"v01-{index + 1}")
        assert response.status_code == 200
        assert response.json()["created"] is False
        assert response.json()["lead"]["lead_id"] == lead_id

    assert len(repo.list_leads()) == 1


def test_v01_concurrent_insert_race_returns_existing(repo: Repository, monkeypatch) -> None:
    existing = repo.create_or_get_lead("race.creator")[1]

    calls = {"n": 0}
    original = repo.find_lead_by_username

    def flaky(username):
        calls["n"] += 1
        # Simulate two requests passing the pre-check before either inserts.
        return None if calls["n"] == 1 else original(username)

    monkeypatch.setattr(repo, "find_lead_by_username", flaky)

    created, lead = repo.create_or_get_lead("RACE.creator")

    assert created is False
    assert lead.lead_id == existing.lead_id


# -- V02: A/B/A replay -----------------------------------------------------


def test_v02_aba_replay_returns_original_without_rollback(api_client, repo: Repository) -> None:
    a = _post(api_client, "aba.creator", "v02-a", _snapshot(bio="A bio"))
    assert a.status_code == 201
    lead_id = a.json()["lead"]["lead_id"]
    versions_after_a = len(repo.list_evidence_versions(lead_id))
    jobs_after_a = len(repo.list_jobs(lead_id))

    b = _post(
        api_client,
        "aba.creator",
        "v02-b",
        _snapshot(
            bio="B bio",
            followers={"value": 200, "display": "200", "precision": "exact"},
        ),
    )
    assert b.status_code == 200
    assert b.json()["outcome"] == "updated"
    assert b.json()["lead"]["bio"] == "B bio"
    assert b.json()["lead"]["follower_count"] == 200
    versions_after_b = len(repo.list_evidence_versions(lead_id))
    assert versions_after_b == versions_after_a + 1

    replay = _post(api_client, "aba.creator", "v02-a", _snapshot(bio="A bio"))
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "unchanged"
    assert replay.json()["lead"]["lead_id"] == lead_id
    # B is not rolled back and no extra version/job is created.
    assert replay.json()["lead"]["bio"] == "B bio"
    assert replay.json()["lead"]["follower_count"] == 200
    assert len(repo.list_evidence_versions(lead_id)) == versions_after_b
    assert len(repo.list_jobs(lead_id)) == jobs_after_a

    receipt = repo.find_capture_receipt("v02-a")
    assert receipt is not None
    assert receipt.outcome == "new"  # the original receipt is retained


# -- V03: request-id conflict ----------------------------------------------


def test_v03_request_id_reused_with_different_payload_is_conflict(
    api_client, repo: Repository
) -> None:
    first = _post(api_client, "conflict.creator", "v03-a", _snapshot(bio="One"))
    assert first.status_code == 201
    lead_id = first.json()["lead"]["lead_id"]
    versions_before = len(repo.list_evidence_versions(lead_id))

    conflict = _post(api_client, "conflict.creator", "v03-a", _snapshot(bio="Two"))

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "REQUEST_ID_CONFLICT"
    lead = repo.get_lead(lead_id)
    assert lead is not None
    assert lead.bio == "One"
    assert len(repo.list_evidence_versions(lead_id)) == versions_before


# -- V04: stale evidence + clock safety ------------------------------------


def test_v04_future_clock_and_stale_snapshot_preserve_newer_evidence(
    api_client, repo: Repository
) -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=365)).replace(microsecond=0).isoformat()
    first = _post(
        api_client,
        "clock.creator",
        "v04-a",
        _snapshot(bio="Future bio", captured_at=future),
    )
    assert first.status_code == 201
    lead_id = first.json()["lead"]["lead_id"]

    # A later capture with no/now clock is still newer than the clamped future.
    second = _post(
        api_client,
        "clock.creator",
        "v04-b",
        _snapshot(bio="Later bio", captured_at=""),
    )
    assert second.status_code == 200
    assert second.json()["outcome"] == "updated"
    assert second.json()["lead"]["bio"] == "Later bio"

    # An older snapshot is retained as history but never overwrites or mutates
    # the current evidence.
    stale = _post(
        api_client,
        "clock.creator",
        "v04-c",
        _snapshot(
            bio="Old bio",
            display_name="Old Name",
            captured_at="2026-10-01T00:00:00Z",
            external_urls=["https://extra.example/"],
        ),
    )
    assert stale.status_code == 200
    body = stale.json()
    assert body["outcome"] == "unchanged"
    assert body["lead"]["bio"] == "Later bio"
    assert body["lead"]["full_name"] != "Old Name"
    assert "https://extra.example/" not in body["lead"]["all_external_urls"]
    # The stale capture is still retained as immutable history.
    assert len(repo.list_evidence_versions(lead_id)) == 3


# -- V06: needs-data then recapture ----------------------------------------


def test_v06_handle_only_needs_data_then_recapture_queues_research(
    api_client, repo: Repository, monkeypatch
) -> None:
    monkeypatch.setenv("HIKERAPI_KEY", "")
    get_settings.cache_clear()
    try:
        first = _post(api_client, "recover.creator", "v06-a")
        assert first.status_code == 201
        body = first.json()
        assert body["lead"]["status"] == "needs_data"
        assert body["research_queued"] is False
        lead_id = body["lead"]["lead_id"]
        assert repo.find_job("profile_fetch", lead_id) is None

        second = _post(
            api_client,
            "recover.creator",
            "v06-b",
            _snapshot(bio="Recovered evidence"),
        )
        assert second.status_code == 200
        assert second.json()["outcome"] == "updated"
        assert second.json()["research_queued"] is True
        job = repo.find_job("profile_fetch", lead_id)
        assert job is not None
        assert job.status == "queued"
        assert repo.get_lead(lead_id).bio == "Recovered evidence"
    finally:
        get_settings.cache_clear()


# -- receipts + evidence metadata ------------------------------------------


def test_receipt_and_immutable_evidence_version_are_recorded(
    api_client, repo: Repository
) -> None:
    response = _post(api_client, "meta.creator", "meta-1", _snapshot())
    assert response.status_code == 201
    lead_id = response.json()["lead"]["lead_id"]

    receipt = repo.find_capture_receipt("meta-1")
    assert receipt is not None
    assert receipt.lead_id == lead_id
    assert receipt.payload_hash
    assert receipt.received_at

    versions = repo.list_evidence_versions(lead_id)
    assert len(versions) == 1
    version = versions[0]
    assert version.version == 1
    assert version.request_id == "meta-1"
    assert version.parser_version == "1"
    assert version.captured_at == "2026-10-19T04:50:00Z"
    assert version.received_at
    assert json.loads(version.field_provenance)["bio"] == "snapshot"
    assert json.loads(version.changed_fields)

    lead = repo.get_lead(lead_id)
    assert lead is not None
    assert lead.evidence_version == 1
    assert lead.evidence_version_id == version.evidence_version_id


def test_identical_new_request_creates_no_duplicate_version(
    api_client, repo: Repository
) -> None:
    first = _post(api_client, "same.evidence", "same-1", _snapshot())
    assert first.status_code == 201
    lead_id = first.json()["lead"]["lead_id"]

    second = _post(api_client, "same.evidence", "same-2", _snapshot())

    assert second.status_code == 200
    assert second.json()["outcome"] == "unchanged"
    assert len(repo.list_evidence_versions(lead_id)) == 1
