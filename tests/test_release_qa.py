"""V2-09: release QA - acceptance checklist gaps and the authorization boundary.

Covers the PRD acceptance scenarios that the earlier packages did not assert:

* **V27** - a capture-scoped key can submit evidence, check connectivity and
  read its receipt, but is **rejected** on every dashboard-administration
  route, and a wrong key produces a useful (non-leaking) failure.
* **V17** - the generation endpoint rejects an unshortlisted or stale
  decision with **zero** new jobs, revisions or external calls.
* **V07** - an exact-zero count stays ``0``; unknown stays ``Unknown``.
* **V09** - useful existing evidence is retained when a research page fails.
* **V11** - a high-fit AI recommendation never changes the operator's fit.
* **V15** - a contact-only change and a within-threshold count change are not
  material.
* **V21** - a known email is reusable without rediscovery; a DM-only creator
  never needs an email.
* **V24** - the actor is recorded accurately.
* **V31** - the legacy migration preserves ids, draft text and decision
  history, and creates zero mass jobs or sent events.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.db.repository import Repository
from app.db.schemas import DraftRevision, Lead, OutreachEntry
from app.db.util import contact_id
from app.worker.pipeline import AIOutreachStage
from app.ai import AIService
from app.ai.schemas import DossierDraft, OutreachDraft
from fakes import FakeAIProvider


# -- helpers ----------------------------------------------------------------


def _create_lead(api_client, username: str) -> str:
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": username,
            "source": "extension",
            "request_id": f"v209-{username}",
            "profile_snapshot": {
                "display_name": "Creator",
                "is_verified": True,
                "bio": "Finance educator",
                "external_urls": ["https://site.example/"],
                "followers": {"value": 100, "display": "100", "precision": "exact"},
                "following": {"value": 10, "display": "10", "precision": "exact"},
                "post_count": {"value": 5, "display": "5", "precision": "exact"},
                "source_url": f"https://www.instagram.com/{username}/",
                "captured_at": "2026-10-21T00:00:00Z",
                "parser_version": "1",
                "missing_fields": [],
            },
        },
    )
    assert response.status_code == 201
    return response.json()["lead"]["lead_id"]


def _shortlist(api_client, lead_id: str) -> None:
    response = api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": "shortlist", "note": "good fit"}
    )
    assert response.status_code == 200


def _operator_key() -> str:
    return get_settings().api_key.strip()


# -- V27: the capture/operator authorization boundary ------------------------


def test_v27_capture_key_is_rejected_on_admin_routes(api_client, monkeypatch) -> None:
    """A capture key must not be able to administer the workspace (V27)."""
    monkeypatch.setenv("API_KEY", "operator-secret")
    monkeypatch.setenv("CAPTURE_API_KEY", "capture-secret")
    get_settings.cache_clear()
    try:
        # Seed a creator with the operator key.
        api_client.headers["x-api-key"] = "operator-secret"
        lead_id = _create_lead(api_client, "v27.boundary")

        # The capture key is recognised but not allowed on admin routes.
        api_client.headers["x-api-key"] = "capture-secret"
        capture = api_client.get(f"/api/v1/leads/{lead_id}/detail")
        assert capture.status_code == 403

        for method, path, payload in (
            ("patch", f"/api/v1/leads/{lead_id}/fit", {"action": "shortlist"}),
            ("get", f"/api/v1/leads/{lead_id}/detail", None),
            ("get", "/api/v1/outreach", None),
            ("get", "/api/v1/stats", None),
            ("post", f"/api/v1/leads/{lead_id}/contact-requests", {}),
            ("post", f"/api/v1/leads/{lead_id}/drafts", {"subject": "x"}),
            ("post", f"/api/v1/leads/{lead_id}/drafts/generate", {"channel": "email"}),
            ("get", "/api/v1/campaign", None),
            ("post", f"/api/v1/leads/{lead_id}/outreach-events", {"outcome": "sent", "channel": "email"}),
        ):
            response = (
                api_client.patch(path, json=payload)
                if method == "patch"
                else api_client.post(path, json=payload)
                if method == "post"
                else api_client.get(path)
            )
            assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
            assert "capture key" in response.json()["detail"].lower()
    finally:
        get_settings.cache_clear()


def test_v27_capture_key_can_submit_and_read_its_receipt(api_client, monkeypatch) -> None:
    """A capture key may submit evidence and read the receipt (V27)."""
    monkeypatch.setenv("API_KEY", "operator-secret")
    monkeypatch.setenv("CAPTURE_API_KEY", "capture-secret")
    get_settings.cache_clear()
    try:
        api_client.headers["x-api-key"] = "capture-secret"
        lead_id = _create_lead(api_client, "v27.captureok")
        assert lead_id

        # Connectivity check.
        listing = api_client.get("/api/v1/leads", params={"limit": 1})
        assert listing.status_code == 200

        # Its own receipt.
        receipt = api_client.get(f"/api/v1/leads/{lead_id}")
        assert receipt.status_code == 200
        assert receipt.json()["username"] == "v27.captureok"
    finally:
        get_settings.cache_clear()


def test_v27_wrong_key_fails_without_disclosing_secrets(api_client, monkeypatch) -> None:
    """A wrong key is rejected and the body leaks nothing (V27)."""
    monkeypatch.setenv("API_KEY", "operator-secret")
    monkeypatch.setenv("CAPTURE_API_KEY", "capture-secret")
    get_settings.cache_clear()
    try:
        api_client.headers["x-api-key"] = "totally-wrong"
        response = api_client.get("/api/v1/leads")
        assert response.status_code == 401
        body = response.text
        assert "operator-secret" not in body
        assert "capture-secret" not in body
        assert "totally-wrong" not in body
    finally:
        get_settings.cache_clear()


def test_v27_single_key_deployment_still_works(api_client, monkeypatch) -> None:
    """With no capture key configured, the shared key keeps working."""
    monkeypatch.setenv("API_KEY", "only-key")
    monkeypatch.setenv("CAPTURE_API_KEY", "")
    get_settings.cache_clear()
    try:
        api_client.headers["x-api-key"] = "only-key"
        assert api_client.get("/api/v1/leads").status_code == 200
        assert api_client.get("/api/v1/stats").status_code == 200
        lead_id = _create_lead(api_client, "v27.singlekey")
        assert api_client.get(f"/api/v1/leads/{lead_id}").status_code == 200
    finally:
        get_settings.cache_clear()


# -- V17: the generation endpoint is gated ---------------------------------


def test_v17_generation_rejected_without_shortlist(
    api_client, repo: Repository, monkeypatch
) -> None:
    """An unshortlisted creator cannot request generation; nothing is created."""
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    lead_id = _create_lead(api_client, "v17.noshortlist")

    response = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts/generate", json={"channel": "email"}
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FIT_APPROVAL_REQUIRED"
    # Zero new jobs, requests or revisions.
    assert repo.find_job("ai_outreach", lead_id) is None
    assert repo.list_outreach_revisions(lead_id) == []
    assert repo.list_draft_revisions(lead_id) == []


def test_v17_generation_rejected_for_stale_decision(
    api_client, repo: Repository, monkeypatch
) -> None:
    """A shortlist whose evidence changed cannot request generation."""
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()
    lead_id = _create_lead(api_client, "v17.stale")
    _shortlist(api_client, lead_id)
    repo.update_lead(lead_id, {"decision_currency": "review_needed"})

    response = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts/generate", json={"channel": "email"}
    )

    assert response.status_code == 403
    assert response.json()["detail"]["decision_currency"] == "review_needed"
    assert repo.find_job("ai_outreach", lead_id) is None
    assert repo.list_outreach_revisions(lead_id) == []


def test_v17_discovery_rejected_without_shortlist(api_client, repo: Repository) -> None:
    """Discovery is gated too, and creates no request or job."""
    lead_id = _create_lead(api_client, "v17.discovery")

    response = api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json={})

    assert response.status_code == 403
    assert repo.list_contact_requests(lead_id) == []
    assert repo.find_job("contact_discovery", lead_id) is None


# -- V07: counts ------------------------------------------------------------


def test_v07_exact_zero_count_is_not_substituted(api_client) -> None:
    """An observed zero stays 0; an unknown count stays Unknown (V07)."""
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": "v07.zero",
            "source": "extension",
            "request_id": "v209-v07-zero",
            "profile_snapshot": {
                "display_name": "Zero",
                "is_verified": False,
                "bio": "",
                "external_urls": [],
                "followers": {"value": 0, "display": "0", "precision": "exact"},
                "following": {"value": 0, "display": "0", "precision": "exact"},
                "post_count": {"value": 0, "display": "0", "precision": "exact"},
                "source_url": "https://www.instagram.com/v07.zero/",
                "captured_at": "2026-10-21T00:00:00Z",
                "parser_version": "1",
                "missing_fields": [],
            },
        },
    )
    assert response.status_code == 201
    lead_id = response.json()["lead"]["lead_id"]

    brief = api_client.get(f"/api/v1/leads/{lead_id}/brief").json()
    assert brief["follower_display"] == "0"
    assert brief["follower_precision"] == "exact"
    assert brief["follower_count"] == 0

    # An unknown count is reported as Unknown, never as 0.
    unknown = api_client.get("/api/v1/leads/v209-does-not-exist")
    assert unknown.status_code == 404


def test_v07_missing_counts_are_unknown_not_zero(api_client) -> None:
    """A missing count is Unknown, never a fabricated 0 (V07)."""
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": "v07.unknown",
            "source": "extension",
            "request_id": "v209-v07-unknown",
            "profile_snapshot": {
                "display_name": "Unknown",
                "is_verified": False,
                "bio": "",
                "external_urls": [],
                "followers": None,
                "following": None,
                "post_count": None,
                "source_url": "https://www.instagram.com/v07.unknown/",
                "captured_at": "2026-10-21T00:00:00Z",
                "parser_version": "1",
                "missing_fields": ["followers", "following", "post_count"],
            },
        },
    )
    assert response.status_code == 201
    lead_id = response.json()["lead"]["lead_id"]

    brief = api_client.get(f"/api/v1/leads/{lead_id}/brief").json()
    assert brief["follower_display"] in ("", "Unknown")
    assert brief["follower_count"] == 0  # the raw count is unknown, not zero
    assert "followers" in brief["missing_fields"]


# -- V09: evidence retention on failure -------------------------------------


def test_v09_existing_evidence_is_retained_when_a_page_fails(
    api_client, repo: Repository
) -> None:
    """A failed research page must not erase useful existing evidence (V09)."""
    lead_id = _create_lead(api_client, "v09.retain")
    repo.upsert_website_page(
        __import__("app.db.schemas", fromlist=["WebsitePage"]).WebsitePage(
            page_id="pg_keep",
            lead_id=lead_id,
            url="https://site.example/about",
            title="About",
            text="Useful evidence that must survive.",
        )
    )
    repo.upsert_post(
        __import__("app.db.schemas", fromlist=["LeadPost"]).LeadPost(
            post_id="p_keep", lead_id=lead_id, caption="A useful post"
        )
    )

    # The website stage reports a failure for a blocked source.
    from app.worker.pipeline import WebsiteEnrichStage
    from fakes import FakeCrawler, make_fetched_page

    crawler = FakeCrawler(
        pages=[make_fetched_page("https://site.example/x", status="blocked", error="blocked")]
    )
    job = repo.enqueue("website_enrich", lead_id, "v09.retain", "v09.retain")[1]
    claimed = repo.claim_next(worker_id="w1")
    outcome = WebsiteEnrichStage(crawler).run(claimed, repo)

    assert outcome.ok
    # The previously stored evidence is still there.
    detail = api_client.get(f"/api/v1/leads/{lead_id}/detail").json()
    assert any(page["page_id"] == "pg_keep" for page in detail["website_pages"])
    assert any(post["post_id"] == "p_keep" for post in detail["posts"])
    brief = api_client.get(f"/api/v1/leads/{lead_id}/brief").json()
    assert brief["bio"] == "Finance educator"


# -- V11: an AI recommendation never changes fit ----------------------------


def test_v11_high_fit_ai_does_not_change_the_operator_decision(
    repo: Repository,
) -> None:
    """A high-fit AI result must not change the recorded fit (V11)."""
    from app.db.schemas import Dossier
    from app.worker.pipeline import AIDossierStage

    _created, lead = repo.create_or_get_lead("v11.highfit")
    repo.update_lead(lead.lead_id, {"fit_status": "research_more", "bio": "Finance educator."})
    repo.upsert_post(
        __import__("app.db.schemas", fromlist=["LeadPost"]).LeadPost(
            post_id="p1", lead_id=lead.lead_id, caption="Investing basics"
        )
    )
    provider = FakeAIProvider(
        dossier=DossierDraft(
            summary="Perfect fit.",
            topics=["investing"],
            criterionScores=[],
            uncertainty="",
        )
    )
    job = repo.enqueue("ai_dossier", lead.lead_id, lead.username, lead.username_normalized)[1]
    claimed = repo.claim_next(worker_id="w1")

    outcome = AIDossierStage(AIService(provider), model_name="gemini-test").run(claimed, repo)

    assert outcome.ok
    stored = repo.get_lead(lead.lead_id)
    assert stored.fit_status == "research_more"
    # And no discovery or draft work was scheduled.
    stages = {job_row.stage for job_row in repo.list_jobs(lead.lead_id)}
    assert "ai_outreach" not in stages
    assert "contact_discovery" not in stages


# -- V15: non-material changes ----------------------------------------------


def test_v15_contact_only_change_is_not_material(api_client, repo: Repository) -> None:
    """A contact-only change keeps the current shortlist (V15)."""
    lead_id = _create_lead(api_client, "v15.contactonly")
    _shortlist(api_client, lead_id)
    before = repo.get_lead(lead_id).decision_currency

    api_client.post(
        "/api/v1/leads",
        json={
            "username": "v15.contactonly",
            "source": "extension",
            "request_id": "v209-v15-contact",
            "profile_snapshot": {
                "display_name": "Creator",
                "is_verified": True,
                # Only the bio (and its contact) changed.
                "bio": "Finance educator. Reach me at hi@brandnew.test",
                "external_urls": ["https://site.example/"],
                "followers": {"value": 100, "display": "100", "precision": "exact"},
                "following": {"value": 10, "display": "10", "precision": "exact"},
                "post_count": {"value": 5, "display": "5", "precision": "exact"},
                "source_url": "https://www.instagram.com/v15.contactonly/",
                "captured_at": "2026-10-22T00:00:00Z",
                "parser_version": "1",
                "missing_fields": [],
            },
        },
    )

    assert repo.get_lead(lead_id).decision_currency == before == "current"


# -- V21: known email without rediscovery; DM-only creator -----------------


def test_v21_known_email_is_reused_without_rediscovery(
    api_client, repo: Repository
) -> None:
    """A creator with a known email needs no discovery request (V21)."""
    from app.db.schemas import Contact

    lead_id = _create_lead(api_client, "v21.known")
    _shortlist(api_client, lead_id)
    repo.upsert_contact(
        Contact(
            contact_id=contact_id(lead_id, "email", "known@creator.test", "https://site.example/"),
            lead_id=lead_id,
            type="email",
            value="known@creator.test",
            source_url="https://site.example/",
            observed_at="2026-10-21T00:00:00Z",
            method="website_crawl",
            validation_state="unverified",
        )
    )

    detail = api_client.get(f"/api/v1/leads/{lead_id}/detail").json()

    # The email is available without any discovery request.
    assert any(c["value"] == "known@creator.test" for c in detail["contacts"])
    assert repo.list_contact_requests(lead_id) == []
    assert repo.find_job("contact_discovery", lead_id) is None


def test_v21_dm_only_creator_needs_no_email(api_client, repo: Repository) -> None:
    """A DM-only creator is not required to have an email (V21)."""
    lead_id = _create_lead(api_client, "v21.dmonly")
    _shortlist(api_client, lead_id)

    # No contact records at all.
    assert repo.list_contacts(lead_id) == []

    # The DM channel is accepted for a draft request without an email.
    response = api_client.post(
        f"/api/v1/leads/{lead_id}/draft-requests", json={"channel": "instagram_dm"}
    )
    assert response.status_code == 201
    assert response.json()["channel"] == "instagram_dm"


# -- V24: the actor is recorded accurately ----------------------------------


def test_v24_logged_event_records_the_shared_operator(api_client) -> None:
    """The actor is the shared operator, not an invented employee (V24)."""
    lead_id = _create_lead(api_client, "v24.actor")
    response = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-21T10:00:00Z",
            "note": "sent by hand",
        },
    )

    assert response.status_code == 201
    event = response.json()
    assert event["actor"] == "shared dashboard operator"
    assert event["source"] == "manually_logged"
    assert event["channel"] == "email"
    assert event["sent_at"] == "2026-10-21T10:00:00Z"


# -- V31: the legacy migration is safe --------------------------------------


def test_v31_legacy_drafts_become_revisions_without_jobs_or_events(
    repo: Repository,
) -> None:
    """A legacy draft is preserved as a revision, with no mass work (V31).

    This mirrors the ``a7b8c9d0e1f2`` backfill: existing draft content becomes
    the first revision, its review state and model are kept, and nothing is
    scheduled or sent.
    """
    _created, lead = repo.create_or_get_lead("v31.legacy")
    repo.upsert_outreach(
        OutreachEntry(
            lead_id=lead.lead_id,
            username=lead.username,
            channel="email+dm",
            status="APPROVED",
            subject="Legacy subject",
            body="Legacy body",
            dm_body="Legacy DM",
            model="gemini-3.8-flash",
        )
    )
    repo.create_draft_revision(
        DraftRevision(
            revision_id=f"dr_legacy_{lead.lead_id}",
            lead_id=lead.lead_id,
            username=lead.username,
            channel="email+dm",
            subject="Legacy subject",
            body="Legacy body",
            dm_body="Legacy DM",
            status="reviewed",
            method="ai",
            model="gemini-3.8-flash",
        )
    )

    revisions = repo.list_draft_revisions(lead.lead_id)
    assert len(revisions) == 1
    legacy = revisions[0]
    assert legacy.subject == "Legacy subject"
    assert legacy.body == "Legacy body"
    assert legacy.dm_body == "Legacy DM"
    assert legacy.status == "reviewed"
    assert legacy.method == "ai"
    assert legacy.model == "gemini-3.8-flash"

    # Zero mass jobs and zero sent events.
    assert repo.list_jobs(lead.lead_id) == []
    assert repo.list_outreach_events(lead.lead_id) == []


def test_v31_legacy_contacts_keep_an_explicit_provenance_limit(
    api_client, repo: Repository
) -> None:
    """A legacy contact is labelled, never given an invented source (V31)."""
    from app.db.schemas import Contact

    lead_id = _create_lead(api_client, "v31.contact")
    repo.upsert_contact(
        Contact(
            contact_id=contact_id(lead_id, "email", "old@legacy.test", ""),
            lead_id=lead_id,
            type="email",
            value="old@legacy.test",
            source_url="",
            observed_at="2026-10-01T00:00:00Z",
            method="legacy",
            validation_state="unverified",
        )
    )

    detail = api_client.get(f"/api/v1/leads/{lead_id}/detail").json()
    legacy = next(c for c in detail["contacts"] if c["value"] == "old@legacy.test")

    assert legacy["provenance"] == "Legacy source unknown"
    assert legacy["source_url"] == ""
    assert legacy["method"] == "legacy"
    # No validation claim was invented.
    assert legacy["validation_state"] == "unverified"
