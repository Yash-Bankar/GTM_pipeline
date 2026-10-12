from __future__ import annotations

from app.constants import (
    STAGE_PROFILE_MEDIA,
    STAGE_WEBSITE_ENRICH,
    STAGE_STATUS_BLOCKED,
    STAGE_STATUS_DONE,
    STAGE_STATUS_NONE,
    STAGE_STATUS_PARTIAL,
)
from app.providers.errors import HikerAPIQuotaError
from app.sheets.models import EnrichedLead
from app.sheets.schemas import KEY_ENRICHED, KEY_IG_LEADS, KEY_POSTS, KEY_WEBSITE_PAGES
from app.worker.pipeline import ProfileFetchStage, ProfileMediaStage, WebsiteEnrichStage
from fakes import FakeCrawler, FakeHikerClient, FakeMediaClient, make_fetched_page, make_post, make_profile


def _lead_with_id(store, username: str, *, instagram_id: str = "787132", external_url: str = ""):
    lead = store.lead.create_lead(username)
    fields = {"instagramId": instagram_id}
    if external_url:
        fields["externalUrl"] = external_url
    store.lead.update_by_key(KEY_IG_LEADS, lead.lead_id, fields)
    return lead


def _claim(store, stage: str, lead):
    store.jobs.enqueue(stage, lead.lead_id, lead.username, lead.username_normalized)
    return store.jobs.claim_next(worker_id="w1")


# --- media ---------------------------------------------------------------

def test_media_stage_stores_posts(worker_stores) -> None:
    lead = _lead_with_id(worker_stores, "media.one")
    job = _claim(worker_stores, STAGE_PROFILE_MEDIA, lead)
    stage = ProfileMediaStage(
        FakeMediaClient([make_post("1"), make_post("2")]), worker_stores.lead, worker_stores.posts
    )

    outcome = stage.run(job)

    assert outcome.ok
    rows = worker_stores.posts.read_rows(KEY_POSTS)
    assert len(rows) == 2
    assert {r.values["postId"] for r in rows} == {"1", "2"}
    assert rows[0].values["leadId"] == lead.lead_id
    assert worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id).values["mediaStatus"] == STAGE_STATUS_DONE


def test_media_stage_deduplicates_posts(worker_stores) -> None:
    lead = _lead_with_id(worker_stores, "media.dup")
    job = _claim(worker_stores, STAGE_PROFILE_MEDIA, lead)
    stage = ProfileMediaStage(
        FakeMediaClient([make_post("1"), make_post("1")]), worker_stores.lead, worker_stores.posts
    )

    stage.run(job)
    rows = worker_stores.posts.read_rows(KEY_POSTS)
    assert len(rows) == 1


def test_media_stage_missing_instagram_id_is_skipped(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("media.noid")
    job = _claim(worker_stores, STAGE_PROFILE_MEDIA, lead)
    stage = ProfileMediaStage(FakeMediaClient([make_post("1")]), worker_stores.lead, worker_stores.posts)

    outcome = stage.run(job)
    assert outcome.ok
    assert "skipped" in outcome.result
    assert worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id).values["mediaStatus"] == STAGE_STATUS_NONE
    assert worker_stores.posts.read_rows(KEY_POSTS) == []


def test_media_stage_no_posts(worker_stores) -> None:
    lead = _lead_with_id(worker_stores, "media.empty")
    job = _claim(worker_stores, STAGE_PROFILE_MEDIA, lead)
    stage = ProfileMediaStage(FakeMediaClient([]), worker_stores.lead, worker_stores.posts)

    outcome = stage.run(job)
    assert outcome.ok
    assert worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id).values["mediaStatus"] == STAGE_STATUS_NONE


def test_media_stage_provider_error_is_retryable(worker_stores) -> None:
    lead = _lead_with_id(worker_stores, "media.err")
    job = _claim(worker_stores, STAGE_PROFILE_MEDIA, lead)
    stage = ProfileMediaStage(
        FakeMediaClient(error=HikerAPIQuotaError("no balance")), worker_stores.lead, worker_stores.posts
    )

    outcome = stage.run(job)
    assert outcome.ok is False
    assert outcome.retryable is True
    assert worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id).values["mediaStatus"] == "error"


# --- website -------------------------------------------------------------

def test_website_stage_partial_when_some_pages_fail(worker_stores) -> None:
    lead = _lead_with_id(worker_stores, "web.partial", external_url="https://example.org")
    job = _claim(worker_stores, STAGE_WEBSITE_ENRICH, lead)
    pages = [
        make_fetched_page("https://example.org/", status="done"),
        make_fetched_page("https://example.org/broken", status="error"),
    ]
    stage = WebsiteEnrichStage(
        FakeCrawler(pages, ["hello@example.org"]), worker_stores.lead, worker_stores.website
    )

    outcome = stage.run(job)
    assert outcome.ok
    assert len(worker_stores.website.read_rows(KEY_WEBSITE_PAGES)) == 2
    assert worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id).values["websiteStatus"] == STAGE_STATUS_PARTIAL


def test_website_stage_missing_website_is_skipped(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("web.none")
    job = _claim(worker_stores, STAGE_WEBSITE_ENRICH, lead)
    stage = WebsiteEnrichStage(FakeCrawler([], []), worker_stores.lead, worker_stores.website)

    outcome = stage.run(job)
    assert outcome.ok
    assert "no website" in outcome.result
    assert worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id).values["websiteStatus"] == STAGE_STATUS_NONE


def test_website_stage_all_blocked(worker_stores) -> None:
    lead = _lead_with_id(worker_stores, "web.blocked", external_url="http://internal.test")
    job = _claim(worker_stores, STAGE_WEBSITE_ENRICH, lead)
    stage = WebsiteEnrichStage(
        FakeCrawler([make_fetched_page("http://internal.test", status="blocked")]),
        worker_stores.lead,
        worker_stores.website,
    )

    stage.run(job)
    assert worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id).values["websiteStatus"] == STAGE_STATUS_BLOCKED


def test_website_stage_updates_enriched_status_and_is_idempotent(worker_stores) -> None:
    lead = _lead_with_id(worker_stores, "web.idem", external_url="https://example.org")
    worker_stores.enriched.upsert_model(
        KEY_ENRICHED, EnrichedLead(leadId=lead.lead_id, username=lead.username, profileStatus="done")
    )
    job = _claim(worker_stores, STAGE_WEBSITE_ENRICH, lead)
    pages = [make_fetched_page("https://example.org/", status="done")]
    stage = WebsiteEnrichStage(
        FakeCrawler(pages, []), worker_stores.lead, worker_stores.website,
        enriched_store=worker_stores.enriched,
    )

    stage.run(job)
    first = worker_stores.website.read_rows(KEY_WEBSITE_PAGES)
    assert len(first) == 1
    created_at = first[0].values["createdAt"]
    assert worker_stores.enriched.find_row(KEY_ENRICHED, lead.lead_id).values["websiteStatus"] == STAGE_STATUS_DONE

    # Re-run (e.g. retry): still one row, createdAt preserved.
    worker_stores.jobs.update_by_key("pipeline_jobs", job.job_id, {"status": "queued"})
    stage.run(worker_stores.jobs.claim_next(worker_id="w1"))
    second = worker_stores.website.read_rows(KEY_WEBSITE_PAGES)
    assert len(second) == 1
    assert second[0].values["createdAt"] == created_at


# --- downstream enqueue --------------------------------------------------

def test_profile_fetch_enqueues_media_and_website(worker_stores) -> None:
    profile = make_profile("enqueue.me", instagram_id="555", external_url="https://example.org")
    stage = ProfileFetchStage(
        FakeHikerClient(lambda username: profile),
        worker_stores.lead,
        worker_stores.enriched,
        job_store=worker_stores.jobs,
    )
    lead = worker_stores.lead.create_lead("enqueue.me")
    worker_stores.jobs.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)
    job = worker_stores.jobs.claim_next(worker_id="w1")

    stage.run(job)

    assert worker_stores.jobs.find_job(STAGE_PROFILE_MEDIA, lead.lead_id) is not None
    assert worker_stores.jobs.find_job(STAGE_WEBSITE_ENRICH, lead.lead_id) is not None
    assert len(worker_stores.jobs.read_rows("pipeline_jobs")) == 3
