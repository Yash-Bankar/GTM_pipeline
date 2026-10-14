from __future__ import annotations

import pytest

from app import constants
from app.db.errors import DuplicateLeadError
from app.db.models import PipelineJob as JobORM
from app.db.repository import Repository
from app.db.schemas import Dossier, LeadPost, OutreachEntry, WebsitePage


def test_create_or_get_lead_dedupes(repo: Repository) -> None:
    created, lead = repo.create_or_get_lead("@Some.Creator", source="test")
    assert created is True
    assert lead.lead_id.startswith("ld_")
    assert lead.username == "Some.Creator"
    assert lead.username_normalized == "some.creator"

    for variant in ("Some.Creator", "https://instagram.com/some.creator/", "some.creator"):
        again_created, again = repo.create_or_get_lead(variant)
        assert again_created is False
        assert again.lead_id == lead.lead_id

    assert len(repo.list_leads()) == 1


def test_create_lead_duplicate_raises(repo: Repository) -> None:
    repo.create_lead("creator.one")
    with pytest.raises(DuplicateLeadError):
        repo.create_lead("creator.one")


def test_update_lead_coerces_counts(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("update.me")
    repo.update_lead(lead.lead_id, {"status": "enriched", "follower_count": "5000", "bio": "hi"})
    updated = repo.get_lead(lead.lead_id)
    assert updated is not None
    assert updated.status == "enriched"
    assert updated.follower_count == 5000
    assert updated.bio == "hi"


def test_posts_upsert_and_dedupe(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("posts.me")
    repo.upsert_post(LeadPost(post_id="p1", lead_id=lead.lead_id, caption="first"))
    repo.upsert_post(LeadPost(post_id="p1", lead_id=lead.lead_id, caption="updated"))
    repo.upsert_post(LeadPost(post_id="p2", lead_id=lead.lead_id, caption="second"))
    posts = repo.list_posts(lead.lead_id)
    assert len(posts) == 2
    assert {p.post_id for p in posts} == {"p1", "p2"}


def test_website_page_upsert_preserves_created_at(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("web.me")
    repo.upsert_website_page(
        WebsitePage(page_id="pg1", lead_id=lead.lead_id, url="https://x.test", status="done", created_at="2026-01-01T00:00:00+00:00")
    )
    first = repo.get_website_page("pg1")
    assert first is not None and first.created_at == "2026-01-01T00:00:00+00:00"
    repo.upsert_website_page(
        WebsitePage(page_id="pg1", lead_id=lead.lead_id, url="https://x.test", status="done", text="updated", created_at="2026-01-01T00:00:00+00:00")
    )
    again = repo.get_website_page("pg1")
    assert again is not None
    assert again.created_at == "2026-01-01T00:00:00+00:00"
    assert again.text == "updated"
    assert len(repo.list_website_pages(lead.lead_id)) == 1


def test_dossier_upsert_and_list(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("dossier.me")
    repo.upsert_dossier(Dossier(lead_id=lead.lead_id, username=lead.username, summary="s", status=constants.AI_STATUS_NEEDS_REVIEW))
    assert repo.get_dossier(lead.lead_id).summary == "s"
    assert len(repo.list_dossiers()) == 1


def test_outreach_upsert_and_update(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("outreach.me")
    repo.upsert_outreach(OutreachEntry(lead_id=lead.lead_id, username=lead.username, status=constants.AI_STATUS_NEEDS_REVIEW, subject="Hi", body="b", dm_body="d"))
    updated = repo.update_outreach(lead.lead_id, {"status": "APPROVED", "body": "edited"})
    assert updated is not None
    assert updated.status == "APPROVED"
    assert updated.body == "edited"
    assert len(repo.list_outreach()) == 1


def test_enqueue_is_idempotent(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("jobs.me")
    created, job = repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    assert created is True
    again_created, again = repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    assert again_created is False
    assert again.job_id == job.job_id


def test_claim_complete_and_fail(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("jobs.flow")
    repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized, max_attempts=2)

    claimed = repo.claim_next(worker_id="w1")
    assert claimed is not None
    assert claimed.status == constants.JOB_RUNNING
    assert claimed.attempt_count == 1
    assert repo.claim_next(worker_id="w1") is None  # nothing else eligible

    status = repo.fail(claimed, "boom", retryable=True, backoff_base=0.0)
    assert status == constants.JOB_RETRY

    claimed2 = repo.claim_next(worker_id="w1")
    assert claimed2 is not None
    status2 = repo.fail(claimed2, "boom again", retryable=True, backoff_base=0.0)
    assert status2 == constants.JOB_ERROR
    assert repo.find_job("profile_fetch", lead.lead_id).status == constants.JOB_ERROR


def test_complete_marks_done(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("jobs.done")
    repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    claimed = repo.claim_next(worker_id="w1")
    repo.complete(claimed, "result")
    assert repo.find_job("profile_fetch", lead.lead_id).status == constants.JOB_DONE


def test_recover_stale_jobs(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("jobs.stale")
    repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    claimed = repo.claim_next(worker_id="w1")
    row = repo.session.get(JobORM, claimed.job_id)
    row.locked_at = "2000-01-01T00:00:00+00:00"
    repo.session.commit()

    assert repo.recover_stale_jobs(stale_after_minutes=30) == 1
    assert repo.find_job("profile_fetch", lead.lead_id).status == constants.JOB_RETRY


def test_reenqueue_resets_finished_job(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("jobs.retry")
    _, job = repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    claimed = repo.claim_next(worker_id="w1")
    repo.complete(claimed, "done")
    _, requeued = repo.enqueue(
        "profile_fetch", lead.lead_id, lead.username, lead.username_normalized, on_duplicate="reenqueue"
    )
    assert requeued.job_id == job.job_id
    assert requeued.status == constants.JOB_QUEUED
    assert requeued.attempt_count == 0


def test_stats(repo: Repository) -> None:
    repo.create_or_get_lead("s1", status="enriched")
    repo.create_or_get_lead("s2", status="queued")
    stats = repo.stats()
    assert stats["leads_total"] == 2
    assert stats["leads_by_status"]["enriched"] == 1
