from __future__ import annotations

import json

import pytest

from app.config import get_settings
from app.db.repository import Repository
from app.db.schemas import Dossier, LeadPost, OutreachEntry, WebsitePage


@pytest.fixture
def seeded(repo: Repository):
    _, lead = repo.create_or_get_lead("dash.one")
    repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    repo.upsert_post(LeadPost(post_id="p1", lead_id=lead.lead_id, caption="cap"))
    repo.upsert_website_page(
        WebsitePage(page_id="pg1", lead_id=lead.lead_id, url="https://x.test", title="T", text="txt", status="done")
    )
    repo.upsert_dossier(
        Dossier(
            lead_id=lead.lead_id,
            username=lead.username,
            summary="Finance educator.",
            topics="investing, money",
            qualification_score=80,
            qualification_tier="A",
            status="NEEDS_REVIEW",
            criterion_scores='{"finance_relevance": 90}',
            evidence_urls="https://x.test",
        )
    )
    repo.upsert_outreach(
        OutreachEntry(
            lead_id=lead.lead_id, username=lead.username, status="NEEDS_REVIEW",
            subject="Hi", body="Body", dm_body="DM",
        )
    )
    return lead


def test_lead_detail(api_client, seeded) -> None:
    response = api_client.get(f"/api/v1/leads/{seeded.lead_id}/detail")
    assert response.status_code == 200
    body = response.json()
    assert body["lead"]["lead_id"] == seeded.lead_id
    assert len(body["posts"]) == 1
    assert len(body["website_pages"]) == 1
    assert len(body["jobs"]) == 1


def test_lead_detail_missing_returns_404(api_client) -> None:
    assert api_client.get("/api/v1/leads/ld_nope/detail").status_code == 404


def test_retry_lead(api_client, seeded) -> None:
    response = api_client.post(f"/api/v1/leads/{seeded.lead_id}/retry")
    assert response.status_code == 200
    assert response.json()["stage"] == "profile_fetch"


def test_retry_ai_enqueues_only_ai_jobs(api_client, seeded, repo: Repository, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        response = api_client.post(f"/api/v1/leads/{seeded.lead_id}/retry-ai")
        assert response.status_code == 200
        body = response.json()
        assert body["lead_id"] == seeded.lead_id
        assert {job["stage"] for job in body["jobs"]} == {"ai_dossier", "ai_outreach"}

        # AI jobs are re-queued with a force flag...
        dossier_job = repo.find_job("ai_dossier", seeded.lead_id)
        assert dossier_job.status == "queued"
        assert json.loads(dossier_job.payload)["force"] is True

        # ...and the completed profile/media stages are left untouched.
        profile_job = repo.find_job("profile_fetch", seeded.lead_id)
        assert profile_job is not None
        assert json.loads(profile_job.payload or "{}") == {}
    finally:
        get_settings.cache_clear()


def test_retry_ai_without_ai_returns_409(api_client, seeded, repo: Repository) -> None:
    """AI disabled / key absent → 409 AI_UNAVAILABLE before any job is created."""
    before = repo.find_job("ai_dossier", seeded.lead_id)
    assert before is None

    response = api_client.post(f"/api/v1/leads/{seeded.lead_id}/retry-ai")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "AI_UNAVAILABLE"
    assert "GEMINI_API_KEY" in detail["message"]
    # No job was created for the rejected request.
    assert repo.find_job("ai_dossier", seeded.lead_id) is None


def test_retry_ai_missing_lead_returns_404(api_client, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        assert api_client.post("/api/v1/leads/ld_nope/retry-ai").status_code == 404
    finally:
        get_settings.cache_clear()


def test_list_and_get_dossier(api_client, seeded) -> None:
    listing = api_client.get("/api/v1/dossiers").json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["topics"] == ["investing", "money"]
    assert item["criterion_scores"] == {"finance_relevance": 90}
    assert item["qualification_tier"] == "A"
    single = api_client.get(f"/api/v1/dossiers/{seeded.lead_id}")
    assert single.status_code == 200
    assert single.json()["summary"] == "Finance educator."


def test_list_and_patch_outreach(api_client, seeded) -> None:
    assert api_client.get("/api/v1/outreach").json()["total"] == 1
    patched = api_client.patch(
        f"/api/v1/outreach/{seeded.lead_id}", json={"status": "APPROVED", "body": "edited body"}
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "APPROVED"
    assert patched.json()["body"] == "edited body"


def test_patch_outreach_invalid_status(api_client, seeded) -> None:
    assert api_client.patch(f"/api/v1/outreach/{seeded.lead_id}", json={"status": "nope"}).status_code == 422


def test_stats(api_client, seeded) -> None:
    stats = api_client.get("/api/v1/stats").json()
    assert stats["leads_total"] == 1
    assert stats["dossiers_total"] == 1
    assert stats["outreach_needs_review"] == 1


def test_api_key_is_enforced(api_client, monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "s3cret")
    get_settings.cache_clear()
    try:
        assert api_client.get("/api/v1/leads").status_code == 401
        assert api_client.get("/api/v1/leads", headers={"x-api-key": "s3cret"}).status_code == 200
    finally:
        monkeypatch.delenv("API_KEY", raising=False)
        get_settings.cache_clear()
