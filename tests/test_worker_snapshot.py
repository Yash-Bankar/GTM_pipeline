from __future__ import annotations

import json

from app import constants
from app.ai import AIService, DEFAULT_RUBRIC, build_evidence
from app.ai.masking import normalize_bio
from app.ai.schemas import CriterionScore, DossierDraft
from app.db.repository import Repository
from app.worker.pipeline import AIDossierStage, ProfileFetchStage, WebsiteEnrichStage
from app.worker.snapshot import snapshot_has_data, snapshot_to_lead_fields
from fakes import FakeAIProvider, FakeCrawler, FakeHikerClient, make_fetched_page, make_profile

SNAPSHOT = {
    "display_name": "Snapshot Creator",
    "is_verified": True,
    "bio": "Finance educator. Reach me at hello@example.org or +1 415 555 0199",
    "external_urls": ["https://example.org", "https://www.threads.net/@snap"],
    "followers": {"value": 12300, "display": "12.3K", "precision": "approximate"},
    "following": {"value": 120, "display": "120", "precision": "exact"},
    "post_count": None,
    "source_url": "https://www.instagram.com/snap.creator/",
    "captured_at": "2026-10-19T00:00:00Z",
    "parser_version": "1",
    "missing_fields": ["post_count"],
}


def _lead_with_snapshot(repo: Repository, name: str, **overrides: object):
    lead = repo.create_or_get_lead(name, status="queued")[1]
    snapshot = {**SNAPSHOT, **overrides}
    repo.update_lead(lead.lead_id, {"profile_snapshot": json.dumps(snapshot)})
    return lead


def _claim(repo: Repository, name: str, *, snapshot: dict | None = None):
    lead = repo.create_or_get_lead(name, status="queued")[1]
    if snapshot is not None:
        repo.update_lead(lead.lead_id, {"profile_snapshot": json.dumps(snapshot)})
    repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    return lead, repo.claim_next(worker_id="w1")


def _full_score_draft() -> DossierDraft:
    return DossierDraft(
        summary="Finance educator.",
        topics=["investing"],
        criterionScores=[CriterionScore(name=c.name, score=100) for c in DEFAULT_RUBRIC.criteria],
        uncertainty="",
    )


def test_snapshot_bypasses_hikerapi_and_completes(repo: Repository) -> None:
    lead, job = _claim(repo, "snap.creator", snapshot=SNAPSHOT)
    hiker = FakeHikerClient(lambda _u: (_ for _ in ()).throw(AssertionError("HikerAPI must not be called")))

    outcome = ProfileFetchStage(hiker, hiker_enabled=True).run(job, repo)

    assert outcome.ok is True
    assert hiker.calls == 0
    updated = repo.get_lead(lead.lead_id)
    assert updated.status == constants.LEAD_STATUS_ENRICHED
    assert updated.full_name == "Snapshot Creator"
    assert updated.follower_count == 12300
    assert updated.follows_count == 120
    assert updated.external_url == "https://example.org"
    assert "threads.net/@snap" in updated.all_external_urls
    assert updated.scraped_at == "2026-10-19T00:00:00Z"


def test_v08_public_business_contacts_saved_and_visible(repo: Repository) -> None:
    """V2-01 V08: public contacts are retained and visible, unmasked."""
    lead, job = _claim(repo, "contacts.creator", snapshot=SNAPSHOT)

    ProfileFetchStage(FakeHikerClient(lambda _u: make_profile("x")), hiker_enabled=False).run(job, repo)

    updated = repo.get_lead(lead.lead_id)
    assert "hello@example.org" in updated.bio
    assert "+1 415 555 0199" in updated.bio
    assert "hidden" not in updated.bio
    # Ordinary research does not create a discovery request.
    assert repo.list_contact_requests(lead.lead_id) == []

    # The dashboard-facing serialization exposes the public contact.
    from app.leads.schemas import LeadResponse

    payload = LeadResponse.from_lead(updated).model_dump()
    assert "hello@example.org" in payload["bio"]


def test_snapshot_enqueues_website_and_ai_followups(repo: Repository) -> None:
    lead, job = _claim(repo, "follow.creator", snapshot=SNAPSHOT)

    ProfileFetchStage(
        FakeHikerClient(lambda _u: make_profile("x")), enable_ai=True, hiker_enabled=False
    ).run(job, repo)

    assert repo.find_job("website_enrich", lead.lead_id) is not None
    assert repo.find_job("ai_dossier", lead.lead_id) is not None


def test_no_snapshot_falls_back_to_hikerapi(repo: Repository) -> None:
    lead, job = _claim(repo, "no.snapshot")
    hiker = FakeHikerClient(lambda _u: make_profile("no.snapshot"))

    outcome = ProfileFetchStage(hiker, hiker_enabled=True).run(job, repo)

    assert outcome.ok is True
    assert hiker.calls == 1
    assert repo.get_lead(lead.lead_id).status == constants.LEAD_STATUS_ENRICHED


def test_no_snapshot_and_no_provider_stays_needs_data(repo: Repository) -> None:
    lead, job = _claim(repo, "handle.only")
    hiker = FakeHikerClient(lambda _u: make_profile("handle.only"))

    outcome = ProfileFetchStage(hiker, hiker_enabled=False).run(job, repo)

    assert outcome.ok is True
    assert hiker.calls == 0
    repo.complete(job, outcome.result)  # the worker completes an ok outcome
    updated = repo.get_lead(lead.lead_id)
    assert updated.status != constants.LEAD_STATUS_ENRICHED
    # Derived research state is needs_data, not a fabricated enrichment.
    assert repo.lead_progress(lead.lead_id)[0] == constants.RESEARCH_NEEDS_DATA


def test_snapshot_has_data_requires_meaningful_fields() -> None:
    assert snapshot_has_data(SNAPSHOT) is True
    assert snapshot_has_data({"followers": {"value": 100}}) is True
    assert snapshot_has_data({"external_urls": ["https://x.org"]}) is True
    assert snapshot_has_data({"display_name": "Only Name"}) is False
    assert snapshot_has_data({}) is False


def test_normalize_bio_collapses_whitespace() -> None:
    assert normalize_bio("  line one\r\n\r\n\r\nline two  ") == "line one\n\nline two"


def test_build_evidence_keeps_public_contacts() -> None:
    evidence = build_evidence(
        lead_values={"lead_id": "ld_1", "bio": "contact hi@x.org"},
        post_rows=[{"caption": "reach me at 5551234567"}],
        page_rows=[{"url": "https://x.org", "title": "T", "text": "call +1 415 555 0199"}],
    )
    assert "hi@x.org" in evidence.bio
    assert "5551234567" in evidence.posts[0]
    assert "+1 415 555 0199" in evidence.pages[0].text


def test_website_enrich_runs_from_snapshot_urls(repo: Repository) -> None:
    lead, job = _claim(repo, "site.creator", snapshot=SNAPSHOT)
    ProfileFetchStage(FakeHikerClient(lambda _u: make_profile("x")), hiker_enabled=False).run(job, repo)

    crawl_job = repo.claim_next(worker_id="w1")
    assert crawl_job.stage == "website_enrich"

    crawler = FakeCrawler(pages=[make_fetched_page("https://example.org", text="email hi@example.org")])
    outcome = WebsiteEnrichStage(crawler).run(crawl_job, repo)

    assert outcome.ok is True
    assert crawler.calls == 1
    pages = repo.list_website_pages(lead.lead_id)
    assert pages
    # V2-01: public business contacts are retained in persisted evidence.
    assert "hi@example.org" in pages[0].text


def test_ai_dossier_waits_for_evidence_terminal_states(repo: Repository) -> None:
    lead = repo.create_or_get_lead("deps.creator")[1]
    repo.update_lead(lead.lead_id, {"bio": "finance educator"})
    repo.enqueue("website_enrich", lead.lead_id, lead.username, lead.username_normalized)
    repo.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized, priority=-1)

    website_job = repo.claim_next(worker_id="w1")
    assert website_job.stage == "website_enrich"
    dossier_job = repo.claim_next(worker_id="w1")
    assert dossier_job.stage == "ai_dossier"

    provider = FakeAIProvider(dossier=_full_score_draft())
    stage = AIDossierStage(AIService(provider), model_name="test")

    deferred = stage.run(dossier_job, repo)
    assert deferred.deferred is True
    assert deferred.ok is False
    assert provider.calls == 0

    repo.complete(website_job, "ok")
    result = stage.run(dossier_job, repo)
    assert result.ok is True
    assert provider.calls == 1
    assert repo.get_dossier(lead.lead_id).status == constants.AI_STATUS_NEEDS_REVIEW


def test_deferred_dossier_is_requeued_without_burning_attempts(repo: Repository) -> None:
    lead = repo.create_or_get_lead("defer.creator")[1]
    repo.update_lead(lead.lead_id, {"bio": "finance educator"})
    repo.enqueue("website_enrich", lead.lead_id, lead.username, lead.username_normalized)
    repo.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized, priority=-1)

    repo.claim_next(worker_id="w1")  # website_enrich
    dossier_job = repo.claim_next(worker_id="w1")
    assert dossier_job.attempt_count == 1

    repo.defer(dossier_job, 15.0)

    requeued = repo.find_job("ai_dossier", lead.lead_id)
    assert requeued.status == constants.JOB_QUEUED
    assert requeued.attempt_count == 0
    assert requeued.run_after != ""


def test_snapshot_to_lead_fields_omits_contact_columns() -> None:
    fields = snapshot_to_lead_fields(SNAPSHOT)
    assert "business_email" not in fields
    assert "business_phone_number" not in fields
    assert fields["follower_count"] == 12300
    assert fields["all_external_urls"] == "https://example.org,https://www.threads.net/@snap"


def test_build_stages_without_hiker_key_does_not_require_credentials() -> None:
    from app.config import Settings
    from app.worker.main import build_stages
    from app.worker.pipeline import AIDisabledStage

    stages = build_stages(Settings(hikerapi_key="", ai_enabled=False))

    assert "profile_fetch" in stages
    assert "profile_media" in stages
    assert "website_enrich" in stages
    # V2-01: AI stages are registered as no-op guards so queued jobs complete
    # harmlessly when AI is disabled.
    assert isinstance(stages["ai_dossier"], AIDisabledStage)
    assert isinstance(stages["ai_outreach"], AIDisabledStage)
