from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.dashboard.service import DashboardService
from app.dependencies import get_dashboard_service, get_lead_service
from app.leads.service import LeadService
from app.main import app
from app.sheets.models import Dossier, LeadPost, OutreachEntry, WebsitePage
from app.sheets.schemas import KEY_DOSSIERS, KEY_OUTREACH, KEY_POSTS, KEY_WEBSITE_PAGES


@pytest.fixture
def dash_service(worker_stores) -> DashboardService:
    return DashboardService(
        lead_store=worker_stores.lead,
        job_store=worker_stores.jobs,
        enriched_store=worker_stores.enriched,
        post_store=worker_stores.posts,
        website_store=worker_stores.website,
        dossier_store=worker_stores.dossiers,
        outreach_store=worker_stores.outreach,
    )


@pytest.fixture
def seeded(worker_stores):
    lead = worker_stores.lead.create_lead("dash.one")
    worker_stores.jobs.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    worker_stores.posts.append_model(
        KEY_POSTS, LeadPost(postId="p1", leadId=lead.lead_id, caption="cap")
    )
    worker_stores.website.append_model(
        KEY_WEBSITE_PAGES,
        WebsitePage(pageId="pg1", leadId=lead.lead_id, url="https://x.test", title="T", text="txt", status="done"),
    )
    worker_stores.dossiers.upsert_model(
        KEY_DOSSIERS,
        Dossier(
            leadId=lead.lead_id,
            username=lead.username,
            summary="Finance educator.",
            topics="investing, money",
            qualificationScore=80,
            qualificationTier="A",
            status="NEEDS_REVIEW",
            criterionScores='{"finance_relevance": 90}',
            evidenceUrls="https://x.test",
        ),
    )
    worker_stores.outreach.upsert_model(
        KEY_OUTREACH,
        OutreachEntry(
            leadId=lead.lead_id, username=lead.username, status="NEEDS_REVIEW",
            subject="Hi", body="Body", dmBody="DM",
        ),
    )
    return lead


@pytest.fixture
def client(dash_service):
    app.dependency_overrides[get_dashboard_service] = lambda: dash_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_lead_detail(client, seeded) -> None:
    response = client.get(f"/api/v1/leads/{seeded.lead_id}/detail")
    assert response.status_code == 200
    body = response.json()
    assert body["lead"]["lead_id"] == seeded.lead_id
    assert len(body["posts"]) == 1
    assert len(body["website_pages"]) == 1
    assert len(body["jobs"]) == 1


def test_lead_detail_missing_returns_404(client) -> None:
    assert client.get("/api/v1/leads/ld_nope/detail").status_code == 404


def test_retry_lead(client, seeded) -> None:
    response = client.post(f"/api/v1/leads/{seeded.lead_id}/retry")
    assert response.status_code == 200
    assert response.json()["stage"] == "profile_fetch"


def test_list_and_get_dossier(client, seeded) -> None:
    listing = client.get("/api/v1/dossiers").json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["topics"] == ["investing", "money"]
    assert item["criterion_scores"] == {"finance_relevance": 90}
    assert item["qualification_tier"] == "A"

    single = client.get(f"/api/v1/dossiers/{seeded.lead_id}")
    assert single.status_code == 200
    assert single.json()["summary"] == "Finance educator."


def test_list_and_patch_outreach(client, seeded) -> None:
    listing = client.get("/api/v1/outreach").json()
    assert listing["total"] == 1

    patched = client.patch(
        f"/api/v1/outreach/{seeded.lead_id}",
        json={"status": "APPROVED", "body": "edited body"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "APPROVED"
    assert patched.json()["body"] == "edited body"


def test_patch_outreach_invalid_status(client, seeded) -> None:
    response = client.patch(f"/api/v1/outreach/{seeded.lead_id}", json={"status": "nope"})
    assert response.status_code == 422


def test_stats(client, seeded) -> None:
    stats = client.get("/api/v1/stats").json()
    assert stats["leads_total"] == 1
    assert stats["dossiers_total"] == 1
    assert stats["outreach_needs_review"] == 1


def test_api_key_is_enforced(worker_stores, monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "s3cret")
    get_settings.cache_clear()
    service = LeadService(worker_stores.lead, job_store=worker_stores.jobs)
    app.dependency_overrides[get_lead_service] = lambda: service
    try:
        with TestClient(app) as test_client:
            assert test_client.get("/api/v1/leads").status_code == 401
            ok = test_client.get("/api/v1/leads", headers={"x-api-key": "s3cret"})
            assert ok.status_code == 200
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("API_KEY", raising=False)
        get_settings.cache_clear()
