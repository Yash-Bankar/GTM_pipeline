"""Pipeline stages executed by the worker.

Each stage is idempotent and returns a :class:`StageOutcome`. Stages never send
external messages; they only read/write Google Sheets and call the HikerAPI /
website providers.

Phase 4 implemented ``profile_fetch``. Phase 5 adds ``profile_media`` (recent
posts/reels) and ``website_enrich`` (SSRF-safe crawl + email extraction). The
optional stages keep the pipeline moving when data is genuinely unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app import constants
from app.leads.validation import InvalidLeadInput
from app.providers.errors import (
    HikerAPIAuthError,
    HikerAPIConfigError,
    HikerAPIError,
    HikerAPINetworkError,
    HikerAPINotFoundError,
    HikerAPIQuotaError,
    HikerAPIRateLimitError,
    HikerAPIResponseError,
)
from app.providers.models import HikerPost, HikerProfile, to_lead_fields
from app.providers.website import FetchedPage
from app.sheets.models import EnrichedLead, LeadPost, PipelineJob, WebsitePage
from app.sheets.repository import JobStore, LeadStore, SheetStore
from app.sheets.schemas import (
    KEY_ENRICHED,
    KEY_IG_LEADS,
    KEY_POSTS,
    KEY_WEBSITE_PAGES,
    normalize_username,
)
from app.sheets.util import utc_now_iso

logger = logging.getLogger(__name__)

# Provider failures that are worth retrying with backoff.
_RETRYABLE_HIKER_ERRORS = (
    HikerAPIRateLimitError,
    HikerAPIQuotaError,
    HikerAPINetworkError,
    HikerAPIResponseError,
)


@dataclass
class StageOutcome:
    """Result of running one stage for one job."""

    ok: bool
    result: str = ""
    error: str = ""
    retryable: bool = False


class ProfileFetcher(Protocol):
    def fetch_profile(self, username: str) -> HikerProfile:
        ...


class MediaFetcher(Protocol):
    def fetch_recent_posts(
        self, user_id: str, *, limit: int, max_pages: int
    ) -> list[HikerPost]:
        ...


class PageCrawler(Protocol):
    def crawl(self, start_urls: list[str]) -> tuple[list[FetchedPage], list[str]]:
        ...


class Stage(Protocol):
    name: str

    def run(self, job: PipelineJob) -> StageOutcome:
        ...


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:1000]


def _page_id(lead_id: str, url: str) -> str:
    digest = hashlib.sha1(f"{lead_id}|{url}".encode("utf-8")).hexdigest()
    return f"pg_{digest[:20]}"


class ProfileFetchStage:
    """Fetch a public Instagram profile and persist it (idempotent)."""

    name = constants.STAGE_PROFILE_FETCH

    def __init__(
        self,
        client: ProfileFetcher,
        lead_store: LeadStore,
        enriched_store: SheetStore,
        *,
        job_store: JobStore | None = None,
        followup_max_attempts: int = 3,
    ) -> None:
        self._client = client
        self._lead_store = lead_store
        self._enriched_store = enriched_store
        self._job_store = job_store
        self._followup_max_attempts = followup_max_attempts

    def run(self, job: PipelineJob) -> StageOutcome:
        username = job.username_normalized or job.username
        try:
            profile = self._client.fetch_profile(username)
        except HikerAPINotFoundError as exc:
            self._mark_lead(job, constants.LEAD_STATUS_NOT_FOUND, str(exc))
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except (HikerAPIAuthError, HikerAPIConfigError) as exc:
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except InvalidLeadInput as exc:
            self._mark_lead(job, constants.LEAD_STATUS_ERROR, str(exc))
            return StageOutcome(ok=False, error=str(exc), retryable=False)
        except HikerAPIError as exc:
            retryable = isinstance(exc, _RETRYABLE_HIKER_ERRORS)
            return StageOutcome(ok=False, error=_error_text(exc), retryable=retryable)

        created_at = self._existing_enriched_created_at(job.lead_id)
        self._write_enriched(job, profile, created_at)
        self._update_lead(job, profile)
        self._enqueue_followups(job, profile)
        logger.info(
            "Enriched lead %s (@%s): followers=%s emails=%s",
            job.lead_id,
            profile.username,
            profile.follower_count,
            len(profile.emails),
        )
        return StageOutcome(
            ok=True,
            result=json.dumps(
                {
                    "username": profile.username,
                    "followers": profile.follower_count,
                    "emails": len(profile.emails),
                    "externalUrl": profile.external_url,
                }
            ),
        )

    def _enqueue_followups(self, job: PipelineJob, profile: HikerProfile) -> None:
        if self._job_store is None:
            return
        if profile.instagram_id:
            self._job_store.enqueue(
                constants.STAGE_PROFILE_MEDIA,
                job.lead_id,
                profile.username,
                job.username_normalized or profile.username,
                max_attempts=self._followup_max_attempts,
            )
        has_website = bool(profile.external_url) or bool(profile.bio_links)
        if has_website:
            self._job_store.enqueue(
                constants.STAGE_WEBSITE_ENRICH,
                job.lead_id,
                profile.username,
                job.username_normalized or profile.username,
                max_attempts=self._followup_max_attempts,
            )

    # -- persistence --------------------------------------------------------

    def _existing_enriched_created_at(self, lead_id: str) -> str:
        record = self._enriched_store.find_row(KEY_ENRICHED, lead_id, key_header="leadId")
        return record.values.get("createdAt", "") if record is not None else ""

    def _write_enriched(self, job: PipelineJob, profile: HikerProfile, created_at: str) -> None:
        now = utc_now_iso()
        fields = to_lead_fields(profile, scraped_at=now)
        enriched = EnrichedLead(
            leadId=job.lead_id,
            username=profile.username,
            usernameNormalized=normalize_username(profile.username) or job.username_normalized,
            fullName=fields["fullName"],
            instagramId=fields["instagramId"],
            followerCount=int(fields["followerCount"] or 0),
            followsCount=int(fields["followsCount"] or 0),
            businessCategoryName=fields["businessCategoryName"],
            bio=fields["bio"],
            businessEmail=fields["businessEmail"],
            businessPhoneNumber=fields["businessPhoneNumber"],
            profileUrl=fields["profileUrl"],
            externalUrl=fields["externalUrl"],
            allExternalUrls=fields["allExternalUrls"],
            profileStatus="done",
            profileScrapedAt=now,
            createdAt=created_at or now,
            updatedAt=now,
        )
        self._enriched_store.upsert_model(KEY_ENRICHED, enriched)

    def _update_lead(self, job: PipelineJob, profile: HikerProfile) -> None:
        fields = to_lead_fields(profile)
        self._lead_store.update_by_key(
            KEY_IG_LEADS,
            job.lead_id,
            {**fields, "status": constants.LEAD_STATUS_ENRICHED, "lastError": ""},
        )

    def _mark_lead(self, job: PipelineJob, status: str, error: str) -> None:
        self._lead_store.update_by_key(
            KEY_IG_LEADS,
            job.lead_id,
            {"status": status, "lastError": error[:500]},
        )


class ProfileMediaStage:
    """Fetch a bounded number of recent posts/reels (optional stage)."""

    name = constants.STAGE_PROFILE_MEDIA

    def __init__(
        self,
        client: MediaFetcher,
        lead_store: LeadStore,
        post_store: SheetStore,
        *,
        max_posts: int = 12,
        max_pages: int = 2,
    ) -> None:
        self._client = client
        self._lead_store = lead_store
        self._post_store = post_store
        self._max_posts = max_posts
        self._max_pages = max_pages

    def run(self, job: PipelineJob) -> StageOutcome:
        lead = self._lead_store.find_row(KEY_IG_LEADS, job.lead_id)
        if lead is None:
            return StageOutcome(ok=False, error=f"lead {job.lead_id} not found", retryable=False)

        instagram_id = lead.values.get("instagramId", "").strip()
        if not instagram_id:
            self._set_media_status(job, constants.STAGE_STATUS_NONE, "")
            return StageOutcome(ok=True, result="no instagram id; media skipped")

        try:
            posts = self._client.fetch_recent_posts(
                instagram_id, limit=self._max_posts, max_pages=self._max_pages
            )
        except HikerAPINotFoundError as exc:
            self._set_media_status(job, constants.STAGE_STATUS_ERROR, str(exc))
            return StageOutcome(ok=True, result="media unavailable (not found)")
        except HikerAPIError as exc:
            retryable = isinstance(exc, _RETRYABLE_HIKER_ERRORS)
            self._set_media_status(job, constants.STAGE_STATUS_ERROR, str(exc))
            return StageOutcome(ok=False, error=_error_text(exc), retryable=retryable)

        if not posts:
            self._set_media_status(job, constants.STAGE_STATUS_NONE, "")
            return StageOutcome(ok=True, result="no recent posts")

        now = utc_now_iso()
        username = lead.values.get("username", "") or job.username
        normalized = lead.values.get("usernameNormalized", "") or job.username_normalized
        for post in posts:
            self._post_store.upsert_model(
                KEY_POSTS,
                LeadPost(
                    postId=post.post_id,
                    leadId=job.lead_id,
                    username=username,
                    usernameNormalized=normalized,
                    mediaType=post.media_type,
                    productType=post.product_type,
                    shortCode=post.short_code,
                    url=post.url,
                    caption=post.caption[:2000],
                    likeCount=post.like_count,
                    commentCount=post.comment_count,
                    playCount=post.play_count,
                    takenAt=post.taken_at,
                    fetchedAt=now,
                    status="done",
                    createdAt=now,
                    updatedAt=now,
                ),
            )
        self._set_media_status(job, constants.STAGE_STATUS_DONE, "")
        return StageOutcome(ok=True, result=f"stored {len(posts)} post(s)")

    def _set_media_status(self, job: PipelineJob, status: str, error: str) -> None:
        self._lead_store.update_by_key(
            KEY_IG_LEADS,
            job.lead_id,
            {"mediaStatus": status, "lastError": error[:500] if error else ""},
        )


class WebsiteEnrichStage:
    """Crawl the lead's external links (optional stage)."""

    name = constants.STAGE_WEBSITE_ENRICH

    def __init__(
        self,
        crawler: PageCrawler,
        lead_store: LeadStore,
        website_store: SheetStore,
        enriched_store: SheetStore | None = None,
    ) -> None:
        self._crawler = crawler
        self._lead_store = lead_store
        self._website_store = website_store
        self._enriched_store = enriched_store

    def run(self, job: PipelineJob) -> StageOutcome:
        lead = self._lead_store.find_row(KEY_IG_LEADS, job.lead_id)
        if lead is None:
            return StageOutcome(ok=False, error=f"lead {job.lead_id} not found", retryable=False)

        urls = _external_urls(lead.values)
        if not urls:
            self._set_website_status(job, constants.STAGE_STATUS_NONE, "")
            return StageOutcome(ok=True, result="no website; skipped")

        pages, emails = self._crawler.crawl(urls)
        now = utc_now_iso()
        username = lead.values.get("username", "") or job.username
        done = 0
        blocked = 0
        errored = 0

        for page in pages:
            page_id = _page_id(job.lead_id, page.url)
            created_at = self._existing_page_created_at(page_id)
            self._website_store.upsert_model(
                KEY_WEBSITE_PAGES,
                WebsitePage(
                    pageId=page_id,
                    leadId=job.lead_id,
                    username=username,
                    url=page.url,
                    resolvedUrl=page.resolved_url,
                    domain=page.domain,
                    title=page.title,
                    text=page.text,
                    links=_serialize_links(page.links),
                    httpStatus=page.http_status,
                    status=page.status,
                    error=page.error[:500],
                    fetchedAt=now,
                    createdAt=created_at or now,
                    updatedAt=now,
                ),
            )
            if page.status == "done":
                done += 1
            elif page.status == "blocked":
                blocked += 1
            else:
                errored += 1

        if done and (blocked or errored):
            status = constants.STAGE_STATUS_PARTIAL
        elif done:
            status = constants.STAGE_STATUS_DONE
        elif blocked and not errored:
            status = constants.STAGE_STATUS_BLOCKED
        else:
            status = constants.STAGE_STATUS_ERROR
        self._set_website_status(job, status, "")
        return StageOutcome(
            ok=True,
            result=json.dumps(
                {"pages": len(pages), "done": done, "blocked": blocked, "error": errored, "emails": len(emails)}
            ),
        )

    def _existing_page_created_at(self, page_id: str) -> str:
        record = self._website_store.find_row(KEY_WEBSITE_PAGES, page_id, key_header="pageId")
        return record.values.get("createdAt", "") if record is not None else ""

    def _set_website_status(self, job: PipelineJob, status: str, error: str) -> None:
        self._lead_store.update_by_key(
            KEY_IG_LEADS, job.lead_id, {"websiteStatus": status}
        )
        if self._enriched_store is not None:
            record = self._enriched_store.find_row(KEY_ENRICHED, job.lead_id, key_header="leadId")
            if record is not None:
                self._enriched_store.update_by_key(
                    KEY_ENRICHED, job.lead_id, {"websiteStatus": status}
                )


def _external_urls(values: dict[str, str]) -> list[str]:
    urls: list[str] = []
    for raw in (values.get("allExternalUrls", ""), values.get("externalUrl", "")):
        for part in str(raw).replace("\n", ",").split(","):
            value = part.strip()
            if value and value not in urls:
                urls.append(value)
    return urls


def _serialize_links(links: list[dict]) -> str:
    lines = []
    for link in links[:50]:
        label = str(link.get("label", "")).strip()
        url = str(link.get("url", "")).strip()
        if url:
            lines.append(f"{label} | {url}".strip(" |"))
    return "\n".join(lines)
