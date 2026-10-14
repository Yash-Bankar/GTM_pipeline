from __future__ import annotations

from app.constants import (
    STAGE_STATUS_BLOCKED,
    STAGE_STATUS_DONE,
    STAGE_STATUS_NONE,
    STAGE_STATUS_PARTIAL,
)
from app.db.repository import Repository
from app.providers.errors import HikerAPIQuotaError
from app.worker.pipeline import ProfileMediaStage, WebsiteEnrichStage
from fakes import FakeCrawler, FakeMediaClient, make_fetched_page, make_post


def _media_job(repo: Repository, name: str, *, instagram_id: str = "787132"):
    lead = repo.create_or_get_lead(name)[1]
    if instagram_id:
        repo.update_lead(lead.lead_id, {"instagram_id": instagram_id})
    repo.enqueue("profile_media", lead.lead_id, lead.username, lead.username_normalized)
    return lead, repo.claim_next(worker_id="w1")


def _website_job(repo: Repository, name: str, *, external_url: str = "https://example.org"):
    lead = repo.create_or_get_lead(name)[1]
    if external_url:
        repo.update_lead(lead.lead_id, {"external_url": external_url})
    repo.enqueue("website_enrich", lead.lead_id, lead.username, lead.username_normalized)
    return lead, repo.claim_next(worker_id="w1")


# --- media ---------------------------------------------------------------

def test_media_stage_stores_posts(repo: Repository) -> None:
    lead, job = _media_job(repo, "media.one")
    stage = ProfileMediaStage(FakeMediaClient([make_post("1"), make_post("2")]))

    outcome = stage.run(job, repo)

    assert outcome.ok
    posts = repo.list_posts(lead.lead_id)
    assert {p.post_id for p in posts} == {"1", "2"}
    assert repo.get_lead(lead.lead_id).media_status == STAGE_STATUS_DONE


def test_media_stage_deduplicates_posts(repo: Repository) -> None:
    lead, job = _media_job(repo, "media.dup")
    ProfileMediaStage(FakeMediaClient([make_post("1"), make_post("1")])).run(job, repo)
    assert len(repo.list_posts(lead.lead_id)) == 1


def test_media_stage_missing_instagram_id_is_skipped(repo: Repository) -> None:
    lead, job = _media_job(repo, "media.noid", instagram_id="")
    outcome = ProfileMediaStage(FakeMediaClient([make_post("1")])).run(job, repo)
    assert outcome.ok
    assert repo.get_lead(lead.lead_id).media_status == STAGE_STATUS_NONE
    assert repo.list_posts(lead.lead_id) == []


def test_media_stage_no_posts(repo: Repository) -> None:
    lead, job = _media_job(repo, "media.empty")
    ProfileMediaStage(FakeMediaClient([])).run(job, repo)
    assert repo.get_lead(lead.lead_id).media_status == STAGE_STATUS_NONE


def test_media_stage_provider_error_is_retryable(repo: Repository) -> None:
    lead, job = _media_job(repo, "media.err")
    outcome = ProfileMediaStage(FakeMediaClient(error=HikerAPIQuotaError("no balance"))).run(job, repo)
    assert outcome.ok is False
    assert outcome.retryable is True
    assert repo.get_lead(lead.lead_id).media_status == "error"


# --- website -------------------------------------------------------------

def test_website_stage_partial_when_some_pages_fail(repo: Repository) -> None:
    lead, job = _website_job(repo, "web.partial")
    pages = [
        make_fetched_page("https://example.org/", status="done"),
        make_fetched_page("https://example.org/broken", status="error"),
    ]
    outcome = WebsiteEnrichStage(FakeCrawler(pages, ["hello@example.org"])).run(job, repo)
    assert outcome.ok
    assert len(repo.list_website_pages(lead.lead_id)) == 2
    assert repo.get_lead(lead.lead_id).website_status == STAGE_STATUS_PARTIAL


def test_website_stage_missing_website_is_skipped(repo: Repository) -> None:
    lead, job = _website_job(repo, "web.none", external_url="")
    outcome = WebsiteEnrichStage(FakeCrawler([], [])).run(job, repo)
    assert outcome.ok
    assert repo.get_lead(lead.lead_id).website_status == STAGE_STATUS_NONE


def test_website_stage_all_blocked(repo: Repository) -> None:
    lead, job = _website_job(repo, "web.blocked", external_url="http://internal.test")
    WebsiteEnrichStage(FakeCrawler([make_fetched_page("http://internal.test", status="blocked")])).run(job, repo)
    assert repo.get_lead(lead.lead_id).website_status == STAGE_STATUS_BLOCKED


def test_website_stage_is_idempotent(repo: Repository) -> None:
    lead, job = _website_job(repo, "web.idem")
    pages = [make_fetched_page("https://example.org/", status="done")]
    stage = WebsiteEnrichStage(FakeCrawler(pages, []))
    stage.run(job, repo)
    first = repo.list_website_pages(lead.lead_id)
    assert len(first) == 1
    created_at = first[0].created_at

    # Re-run the stage (idempotent): still one row, createdAt preserved.
    stage.run(job, repo)
    second = repo.list_website_pages(lead.lead_id)
    assert len(second) == 1
    assert second[0].created_at == created_at
