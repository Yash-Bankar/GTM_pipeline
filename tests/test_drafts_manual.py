"""V2-07: manual draft editor, revisions and manual outreach logging.

Covers the PRD acceptance scenarios:

* **V22** - AI disabled: manual writing works, an AI request is rejected
  without leaving an orphan revision or job behind.
* **V23** - generate/regenerate (including retry): a new linked revision
  completes once; earlier edits and reviewed versions are preserved.
* **V24** - copy/export/mark reviewed versus Log sent: only an explicit
  manual log creates a Sent event, with an accurate actor/channel/time.
* **V25** - a sent log corrected / a reply logged: visible history, correct
  latest summary, no external message dispatched.
"""

from __future__ import annotations

import pytest

from app.ai import AIService
from app.ai.schemas import OutreachDraft
from app.config import get_settings
from app.db.repository import Repository
from app.db.schemas import Dossier
from app.worker.pipeline import AIOutreachStage
from fakes import FakeAIProvider


# -- helpers ----------------------------------------------------------------


def _lead(repo: Repository, username: str):
    lead, _ = repo.create_or_get_lead(username)
    repo.update_lead(
        lead.lead_id,
        {
            "bio": "Finance educator.",
            "fit_status": "shortlisted",
            "decision_currency": "current",
        },
    )
    return repo.get_lead(lead.lead_id)


def _dossier(repo: Repository, lead) -> None:
    repo.upsert_dossier(
        Dossier(
            lead_id=lead.lead_id,
            username=lead.username,
            status="NEEDS_REVIEW",
            summary="Finance educator.",
        )
    )


def _ai_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()


def _ai_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()


def _create_lead(api_client, username: str) -> str:
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": username,
            "source": "extension",
            "request_id": f"v207-{username}",
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
        f"/api/v1/leads/{lead_id}/fit",
        json={"action": "shortlist", "note": "good fit"},
    )
    assert response.status_code == 200


# -- V22: AI disabled -------------------------------------------------------


def test_v22_manual_draft_works_without_ai_key(api_client, monkeypatch) -> None:
    """Manual writing is available without an AI key (V22)."""
    _ai_disabled(monkeypatch)
    lead_id = _create_lead(api_client, "v207.manual")

    response = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Partnership", "body": "Hi there", "channel": "email"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["subject"] == "Partnership"
    assert body["body"] == "Hi there"
    assert body["method"] == "manual"
    assert body["status"] == "needs_review"


def test_v22_ai_request_rejected_without_orphan_revision_or_job(
    api_client, repo: Repository, monkeypatch
) -> None:
    """An AI request without a key creates no revision and no job (V22)."""
    _ai_disabled(monkeypatch)
    lead_id = _create_lead(api_client, "v207.noai")
    _shortlist(api_client, lead_id)

    response = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts/generate",
        json={"channel": "email"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "AI_UNAVAILABLE"
    # No orphan revision, request or job.
    assert repo.list_draft_revisions(lead_id) == []
    assert repo.list_outreach_revisions(lead_id) == []
    assert repo.find_job("ai_outreach", lead_id) is None


def test_v22_manual_draft_survives_ai_disabled_mid_flight(
    api_client, repo: Repository, monkeypatch
) -> None:
    """A manual draft is untouched when AI is unavailable (V22)."""
    _ai_disabled(monkeypatch)
    lead_id = _create_lead(api_client, "v207.mixed")
    _shortlist(api_client, lead_id)
    api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Kept", "body": "Manual content"},
    )

    rejected = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts/generate", json={"channel": "email"}
    )

    assert rejected.status_code == 409
    revisions = repo.list_draft_revisions(lead_id)
    assert len(revisions) == 1
    assert revisions[0].subject == "Kept"
    assert revisions[0].body == "Manual content"


# -- V23: revisions, generation and preservation ----------------------------


def test_v23_generation_creates_a_new_linked_revision(
    api_client, repo: Repository, monkeypatch
) -> None:
    """A generation request produces a NEW revision and supersedes the old one."""
    _ai_enabled(monkeypatch)
    lead_id = _create_lead(api_client, "v207.gen")
    _shortlist(api_client, lead_id)
    manual = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Manual subject", "body": "Manual body"},
    ).json()

    accepted = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts/generate", json={"channel": "email"}
    )
    assert accepted.status_code == 202
    request_id = accepted.json()["revision_id"]

    # The worker produces the revision.
    lead = repo.get_lead(lead_id)
    _dossier(repo, lead)
    job = repo.find_job("ai_outreach", lead_id)
    assert job is not None
    provider = FakeAIProvider(
        outreach=OutreachDraft(emailSubject="AI subject", emailBody="AI body", dmBody="AI dm")
    )
    outcome = AIOutreachStage(AIService(provider), model_name="gemini-test").run(job, repo)
    assert outcome.ok

    revisions = repo.list_draft_revisions(lead_id)
    assert len(revisions) == 2
    ai_revision = revisions[-1]
    assert ai_revision.subject == "AI subject"
    assert ai_revision.method == "ai"
    assert ai_revision.request_id == request_id
    assert ai_revision.parent_revision_id == manual["revision_id"]
    # The earlier manual version is preserved as history, not replaced.
    assert revisions[0].revision_id == manual["revision_id"]
    assert revisions[0].subject == "Manual subject"
    assert revisions[0].status == "superseded"


def test_v23_retry_completes_once_and_preserves_earlier_edits(
    api_client, repo: Repository, monkeypatch
) -> None:
    """A retry (or a crash) must not produce a second revision (V23)."""
    _ai_enabled(monkeypatch)
    lead_id = _create_lead(api_client, "v207.retry")
    _shortlist(api_client, lead_id)
    manual = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Edited subject", "body": "Edited body"},
    ).json()
    api_client.post(f"/api/v1/leads/{lead_id}/drafts/generate", json={"channel": "email"})

    lead = repo.get_lead(lead_id)
    _dossier(repo, lead)
    job = repo.find_job("ai_outreach", lead_id)
    provider = FakeAIProvider(
        outreach=OutreachDraft(emailSubject="AI subject", emailBody="AI body", dmBody="dm")
    )
    stage = AIOutreachStage(AIService(provider), model_name="gemini-test")
    stage.run(job, repo)
    stage.run(job, repo)  # retry / restart

    assert provider.calls == 1
    revisions = repo.list_draft_revisions(lead_id)
    assert len(revisions) == 2
    # The manual edit is intact.
    assert revisions[0].revision_id == manual["revision_id"]
    assert revisions[0].body == "Edited body"


def test_v23_reviewed_draft_is_never_silently_replaced(
    api_client, repo: Repository, monkeypatch
) -> None:
    """Regeneration must not overwrite an approved/reviewed draft (V23)."""
    _ai_enabled(monkeypatch)
    lead_id = _create_lead(api_client, "v207.approved")
    _shortlist(api_client, lead_id)
    created = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Approved subject", "body": "Approved body"},
    ).json()
    api_client.post(f"/api/v1/leads/{lead_id}/drafts/{created['revision_id']}/review")

    api_client.post(f"/api/v1/leads/{lead_id}/drafts/generate", json={"channel": "email"})
    lead = repo.get_lead(lead_id)
    _dossier(repo, lead)
    job = repo.find_job("ai_outreach", lead_id)
    provider = FakeAIProvider(
        outreach=OutreachDraft(emailSubject="NEW", emailBody="NEW", dmBody="NEW")
    )
    AIOutreachStage(AIService(provider), model_name="gemini-test").run(job, repo)

    revisions = repo.list_draft_revisions(lead_id)
    approved = [row for row in revisions if row.revision_id == created["revision_id"]]
    assert len(approved) == 1
    assert approved[0].subject == "Approved subject"
    assert approved[0].body == "Approved body"
    # The approved version is superseded, not deleted, and the new one is separate.
    assert approved[0].status == "superseded"
    assert revisions[-1].subject == "NEW"


def test_v23_manual_edit_returns_reviewed_draft_to_needs_review(
    api_client, repo: Repository
) -> None:
    """Editing reviewed content returns that revision to Needs review (PRD 4.5)."""
    lead_id = _create_lead(api_client, "v207.edit")
    first = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "First", "body": "First body"},
    ).json()
    api_client.post(f"/api/v1/leads/{lead_id}/drafts/{first['revision_id']}/review")
    assert repo.get_draft_revision(first["revision_id"]).status == "reviewed"

    second = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={
            "subject": "Second",
            "body": "Second body",
            "parent_revision_id": first["revision_id"],
        },
    ).json()

    assert second["status"] == "needs_review"
    assert second["parent_revision_id"] == first["revision_id"]
    assert repo.get_draft_revision(first["revision_id"]).status == "superseded"


def test_v23_mark_reviewed_sets_state_without_new_revision(
    api_client, repo: Repository
) -> None:
    """Mark reviewed changes the review state, it does not fork a version."""
    lead_id = _create_lead(api_client, "v207.review")
    created = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Review me", "body": "b"},
    ).json()

    reviewed = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts/{created['revision_id']}/review"
    )

    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"
    assert len(repo.list_draft_revisions(lead_id)) == 1


# -- V24: manual logging ----------------------------------------------------


def test_v24_log_sent_requires_channel_time_and_revision_or_note(
    api_client, repo: Repository
) -> None:
    """A sent log needs a channel, a sent time and a revision or a note (V24)."""
    lead_id = _create_lead(api_client, "v207.log")
    revision = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Subject", "body": "Body"},
    ).json()

    missing_revision = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={"outcome": "sent", "channel": "email", "sent_at": "2026-10-21T10:00:00Z"},
    )
    assert missing_revision.status_code == 422
    assert repo.list_outreach_events(lead_id) == []

    ok = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-21T10:00:00Z",
            "revision_id": revision["revision_id"],
        },
    )
    assert ok.status_code == 201
    event = ok.json()
    assert event["outcome"] == "sent"
    assert event["channel"] == "email"
    assert event["sent_at"] == "2026-10-21T10:00:00Z"
    assert event["revision_id"] == revision["revision_id"]
    assert event["source"] == "manually_logged"


def test_v24_log_sent_accepts_a_manual_note_instead_of_a_revision(
    api_client, repo: Repository
) -> None:
    """A manual note satisfies the evidence requirement for a sent log."""
    lead_id = _create_lead(api_client, "v207.note")
    response = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "instagram_dm",
            "sent_at": "2026-10-21T10:00:00Z",
            "note": "Sent by DM from the creator's inbox",
        },
    )
    assert response.status_code == 201
    assert response.json()["revision_id"] == ""
    assert response.json()["note"]


def test_v24_copy_and_export_never_mark_sent(api_client, repo: Repository) -> None:
    """Only an explicit manual log creates a Sent event (V24)."""
    lead_id = _create_lead(api_client, "v207.copy")
    revision = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Subject", "body": "Body", "dm_body": "DM"},
    ).json()

    text = api_client.get(
        f"/api/v1/leads/{lead_id}/drafts/{revision['revision_id']}/text"
    )
    assert text.status_code == 200
    assert "Subject" in text.json()["text"]
    assert "DM" in text.json()["text"]

    api_client.post(f"/api/v1/leads/{lead_id}/drafts/{revision['revision_id']}/review")

    assert repo.list_outreach_events(lead_id) == []


def test_v24_mark_reviewed_never_marks_sent(api_client, repo: Repository) -> None:
    """Marking reviewed is not sending (V24)."""
    lead_id = _create_lead(api_client, "v207.reviewnotsent")
    revision = api_client.post(
        f"/api/v1/leads/{lead_id}/drafts",
        json={"subject": "Subject", "body": "Body"},
    ).json()
    api_client.post(f"/api/v1/leads/{lead_id}/drafts/{revision['revision_id']}/review")
    assert repo.list_outreach_events(lead_id) == []


@pytest.mark.parametrize(
    "outcome", ["replied", "interested", "not_interested", "follow_up"]
)
def test_v24_outcome_events_are_logged_manually(api_client, repo: Repository, outcome: str) -> None:
    """Replies and outcomes are manually logged with their own label (V24)."""
    lead_id = _create_lead(api_client, f"v207.outcome.{outcome}")
    response = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": outcome,
            "channel": "email",
            "sent_at": "2026-10-21T12:00:00Z",
            "note": "manual note",
        },
    )
    assert response.status_code == 201
    assert response.json()["outcome"] == outcome
    assert response.json()["source"] == "manually_logged"
    assert repo.list_outreach_events(lead_id)[0].outcome == outcome


def test_v24_invalid_outcome_or_channel_is_rejected(api_client) -> None:
    """Unknown outcomes and channels are rejected, not coerced."""
    lead_id = _create_lead(api_client, "v207.badoutcome")
    bad_outcome = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={"outcome": "exploded", "channel": "email", "note": "x"},
    )
    assert bad_outcome.status_code == 422

    bad_channel = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={"outcome": "sent", "channel": "carrier_pigeon", "note": "x"},
    )
    assert bad_channel.status_code == 422


# -- V25: corrections and history -------------------------------------------


def test_v25_correction_creates_a_visible_event_and_keeps_history(
    api_client, repo: Repository
) -> None:
    """A correction is a new visible event; the original is not rewritten (V25)."""
    lead_id = _create_lead(api_client, "v207.correct")
    original = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-20T09:00:00Z",
            "note": "sent yesterday",
        },
    ).json()

    correction = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-21T09:00:00Z",
            "note": "sent this morning, not yesterday",
            "corrects_event_id": original["event_id"],
        },
    )

    assert correction.status_code == 201
    assert correction.json()["corrects_event_id"] == original["event_id"]
    assert correction.json()["source"] == "manually_logged_correction"

    events = repo.list_outreach_events(lead_id)
    assert len(events) == 2
    # The original row is untouched.
    stored = repo.get_outreach_event(original["event_id"])
    assert stored.sent_at == "2026-10-20T09:00:00Z"
    assert stored.note == "sent yesterday"
    # The correction is visible in the history.
    listing = api_client.get(f"/api/v1/leads/{lead_id}/outreach-events").json()
    assert listing["total"] == 2
    assert [item["source"] for item in listing["items"]] == [
        "manually_logged",
        "manually_logged_correction",
    ]


def test_v25_latest_summary_reflects_the_correction(api_client) -> None:
    """The latest summary is correct while the history keeps both rows (V25)."""
    lead_id = _create_lead(api_client, "v207.latest")
    original = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-20T09:00:00Z",
            "note": "wrong time",
        },
    ).json()
    api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-21T09:00:00Z",
            "note": "right time",
            "corrects_event_id": original["event_id"],
        },
    )
    api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "replied",
            "channel": "email",
            "sent_at": "2026-10-22T09:00:00Z",
            "note": "they replied",
        },
    )

    listing = api_client.get(f"/api/v1/leads/{lead_id}/outreach-events").json()

    assert listing["total"] == 3
    assert listing["latest_outcome"] == "replied"


def test_v25_reply_after_sent_is_logged_without_rewriting_the_sent(
    api_client, repo: Repository
) -> None:
    """A reply is a separate event; the sent log stays as it was (V25)."""
    lead_id = _create_lead(api_client, "v207.reply")
    sent = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-20T09:00:00Z",
            "note": "sent",
        },
    ).json()
    api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "interested",
            "channel": "email",
            "sent_at": "2026-10-22T09:00:00Z",
            "note": "interested in a demo",
        },
    )

    events = repo.list_outreach_events(lead_id)
    assert [event.outcome for event in events] == ["sent", "interested"]
    assert repo.get_outreach_event(sent["event_id"]).outcome == "sent"


def test_v25_correction_of_unknown_event_is_rejected(api_client) -> None:
    """A correction must reference a real event."""
    lead_id = _create_lead(api_client, "v207.badcorrect")
    response = api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-21T09:00:00Z",
            "note": "x",
            "corrects_event_id": "oe_does_not_exist",
        },
    )
    assert response.status_code == 422


def test_v25_logging_never_dispatches_a_message(api_client, repo: Repository) -> None:
    """Manual logging creates history only - it never enqueues work (V25)."""
    lead_id = _create_lead(api_client, "v207.nodispatch")
    api_client.post(
        f"/api/v1/leads/{lead_id}/outreach-events",
        json={
            "outcome": "sent",
            "channel": "email",
            "sent_at": "2026-10-21T09:00:00Z",
            "note": "sent by hand",
        },
    )
    # No outreach or AI work is scheduled by a manual log.
    stages = {job.stage for job in repo.list_jobs(lead_id)}
    assert "ai_outreach" not in stages
    assert "outreach" not in stages
