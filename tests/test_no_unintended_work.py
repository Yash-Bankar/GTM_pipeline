"""V2-01: no unintended work.

These tests prove that AI summary/dossier completion, the "retry AI" action, and
shortlisting never schedule outreach/draft generation or contact discovery, and
that the manual workflow + evidence brief work with AI disabled.
"""

from __future__ import annotations

from app.ai import AIService, DEFAULT_RUBRIC
from app.ai.schemas import CriterionScore, DossierDraft
from app.config import Settings, get_settings
from app.constants import AI_STATUS_NEEDS_REVIEW
from app.db.repository import Repository
from app.worker.main import build_stages
from app.worker.pipeline import AIDossierStage
from fakes import FakeAIProvider


def _full_score_draft() -> DossierDraft:
    return DossierDraft(
        summary="Finance educator.",
        topics=["investing"],
        criterionScores=[CriterionScore(name=c.name, score=100) for c in DEFAULT_RUBRIC.criteria],
        uncertainty="",
    )


def _create_lead(api_client, username: str) -> str:
    response = api_client.post("/api/v1/leads", json={"username": username})
    assert response.status_code == 201
    return response.json()["lead"]["lead_id"]


def _dossier_job(repo: Repository, name: str):
    lead = repo.create_or_get_lead(name)[1]
    repo.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)
    return lead, repo.claim_next(worker_id="w1")


def _seed_evidence(repo: Repository, lead) -> None:
    from app.db.schemas import LeadPost, WebsitePage

    repo.update_lead(lead.lead_id, {"bio": "Finance educator. hi@creator.org"})
    repo.upsert_post(LeadPost(post_id="p1", lead_id=lead.lead_id, caption="Investing basics"))
    repo.upsert_website_page(
        WebsitePage(page_id="pg1", lead_id=lead.lead_id, url="https://x.test", title="About", text="Coaching")
    )


def test_dossier_completion_does_not_enqueue_outreach(repo: Repository) -> None:
    """Direct execution path: a dossier run schedules no outreach/draft work."""
    lead, job = _dossier_job(repo, "v201.direct")
    _seed_evidence(repo, lead)
    provider = FakeAIProvider(dossier=_full_score_draft())

    outcome = AIDossierStage(AIService(provider), model_name="test").run(job, repo)

    assert outcome.ok is True
    assert repo.get_dossier(lead.lead_id).status == AI_STATUS_NEEDS_REVIEW
    assert repo.find_job("ai_outreach", lead.lead_id) is None
    assert repo.list_outreach_revisions(lead.lead_id) == []
    assert provider.calls == 1  # only the dossier call


def test_retry_ai_enqueues_only_the_dossier(api_client, repo: Repository, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        lead_id = _create_lead(api_client, "v201.retry")

        response = api_client.post(f"/api/v1/leads/{lead_id}/retry-ai")

        assert response.status_code == 200
        assert {job["stage"] for job in response.json()["jobs"]} == {"ai_dossier"}
        assert repo.find_job("ai_dossier", lead_id) is not None
        assert repo.find_job("ai_outreach", lead_id) is None
        assert repo.list_outreach_revisions(lead_id) == []
    finally:
        get_settings.cache_clear()


def test_shortlist_does_not_schedule_contact_or_draft(api_client, repo: Repository) -> None:
    lead_id = _create_lead(api_client, "v201.shortlist")
    before = {job.job_id for job in repo.list_jobs(lead_id)}

    response = api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": "shortlist", "note": "Good fit"}
    )

    assert response.status_code == 200
    assert response.json()["fit_status"] == "shortlisted"
    # No new jobs, no discovery request, no draft revision.
    assert {job.job_id for job in repo.list_jobs(lead_id)} == before
    assert repo.list_contact_requests(lead_id) == []
    assert repo.list_outreach_revisions(lead_id) == []


def test_ai_disabled_stages_complete_without_a_provider(repo: Repository) -> None:
    stages = build_stages(Settings(hikerapi_key="", ai_enabled=False))
    assert "ai_dossier" in stages
    assert "ai_outreach" in stages

    lead = repo.create_or_get_lead("v201.aioff")[1]
    repo.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)
    job = repo.claim_next(worker_id="w1")

    outcome = stages["ai_dossier"].run(job, repo)

    assert outcome.ok is True
    assert "disabled" in outcome.result.lower()


def test_manual_workflow_works_with_ai_disabled(api_client, repo: Repository, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("AI_ENABLED", "false")
    get_settings.cache_clear()
    try:
        lead_id = _create_lead(api_client, "v201.manual")
        approve = api_client.patch(
            f"/api/v1/leads/{lead_id}/fit", json={"action": "shortlist", "note": "Manual"}
        )
        assert approve.status_code == 200

        contact = api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json={})
        draft = api_client.post(
            f"/api/v1/leads/{lead_id}/draft-requests", json={"channel": "email"}
        )

        assert contact.status_code == 201
        assert draft.status_code == 201
        assert repo.find_job("ai_outreach", lead_id) is None
    finally:
        get_settings.cache_clear()


def test_brief_renders_from_raw_evidence_without_ai(api_client, repo: Repository) -> None:
    lead_id = _create_lead(api_client, "v201.brief")
    repo.update_lead(
        lead_id,
        {
            "bio": "Finance educator. Email hi@brief.org",
            "external_url": "https://brief.org",
            "business_category_name": "Education",
        },
    )
    before = {job.job_id for job in repo.list_jobs(lead_id)}

    response = api_client.get(f"/api/v1/leads/{lead_id}/brief")

    assert response.status_code == 200
    brief = response.json()
    assert "hi@brief.org" in brief["bio"]
    assert brief["external_urls"] == ["https://brief.org"]
    assert brief["has_dossier"] is False
    assert brief["ai_status"] == "not_generated"
    assert {job.job_id for job in repo.list_jobs(lead_id)} == before
