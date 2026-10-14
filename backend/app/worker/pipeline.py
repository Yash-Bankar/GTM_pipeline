"""Pipeline stages executed by the worker.

Each stage is idempotent and returns a :class:`StageOutcome`. Stages never send
external messages; they read/write PostgreSQL through the repository and call the
HikerAPI / website providers.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app import constants
from app.ai import AIService, Evidence, build_evidence
from app.ai.service import DossierResult
from app.db.repository import Repository
from app.db.schemas import Dossier, Lead, LeadPost, OutreachEntry, PipelineJob, WebsitePage
from app.db.util import utc_now_iso
from app.leads.validation import InvalidLeadInput
from app.providers.errors import (
    AIConfigError,
    AIError,
    AINetworkError,
    AIRateLimitError,
    AIResponseError,
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

logger = logging.getLogger(__name__)

_RETRYABLE_HIKER_ERRORS = (
    HikerAPIRateLimitError,
    HikerAPIQuotaError,
    HikerAPINetworkError,
    HikerAPIResponseError,
)


@dataclass
class StageOutcome:
    ok: bool
    result: str = ""
    error: str = ""
    retryable: bool = False


class ProfileFetcher(Protocol):
    def fetch_profile(self, username: str) -> HikerProfile: ...


class MediaFetcher(Protocol):
    def fetch_recent_posts(
        self, user_id: str, *, limit: int, max_pages: int
    ) -> list[HikerPost]: ...


class PageCrawler(Protocol):
    def crawl(self, start_urls: list[str]) -> tuple[list[FetchedPage], list[str]]: ...


class Stage(Protocol):
    name: str

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome: ...


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:1000]


def _job_force(job: PipelineJob) -> bool:
    """True when the job payload asks the stage to bypass its idempotency guard.

    Used by manual AI re-processing (`{"force": true}`) so an existing dossier /
    outreach is regenerated rather than skipped.
    """
    try:
        payload = json.loads(job.payload or "{}")
    except ValueError:
        return False
    return bool(isinstance(payload, dict) and payload.get("force"))


def _page_id(lead_id: str, url: str) -> str:
    digest = hashlib.sha1(f"{lead_id}|{url}".encode("utf-8")).hexdigest()
    return f"pg_{digest[:20]}"


def _external_urls(lead: Lead) -> list[str]:
    urls: list[str] = []
    for raw in (lead.all_external_urls, lead.external_url):
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


def _build_evidence(
    repo: Repository,
    lead: Lead,
    *,
    max_posts: int,
    max_pages: int,
    text_chars: int,
) -> Evidence:
    posts = repo.list_posts(lead.lead_id)
    pages = repo.list_website_pages(lead.lead_id)
    return build_evidence(
        lead_values=lead.model_dump(),
        post_rows=[post.model_dump() for post in posts],
        page_rows=[page.model_dump() for page in pages],
        max_posts=max_posts,
        max_pages=max_pages,
        text_chars=text_chars,
    )


class ProfileFetchStage:
    """Fetch a public Instagram profile and persist it on the lead (idempotent)."""

    name = constants.STAGE_PROFILE_FETCH

    def __init__(
        self,
        client: ProfileFetcher,
        *,
        followup_max_attempts: int = 3,
        enable_ai: bool = False,
    ) -> None:
        self._client = client
        self._followup_max_attempts = followup_max_attempts
        self._enable_ai = enable_ai

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        username = job.username_normalized or job.username
        try:
            profile = self._client.fetch_profile(username)
        except HikerAPINotFoundError as exc:
            repo.update_lead(job.lead_id, {"status": constants.LEAD_STATUS_NOT_FOUND, "last_error": str(exc)})
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except (HikerAPIAuthError, HikerAPIConfigError) as exc:
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except InvalidLeadInput as exc:
            repo.update_lead(job.lead_id, {"status": constants.LEAD_STATUS_ERROR, "last_error": str(exc)})
            return StageOutcome(ok=False, error=str(exc), retryable=False)
        except HikerAPIError as exc:
            retryable = isinstance(exc, _RETRYABLE_HIKER_ERRORS)
            return StageOutcome(ok=False, error=_error_text(exc), retryable=retryable)

        fields = to_lead_fields(profile, scraped_at=utc_now_iso())
        repo.update_lead(job.lead_id, {**fields, "status": constants.LEAD_STATUS_ENRICHED, "last_error": ""})
        self._enqueue_followups(repo, job, profile)
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

    def _enqueue_followups(self, repo: Repository, job: PipelineJob, profile: HikerProfile) -> None:
        normalized = job.username_normalized or profile.username
        if profile.instagram_id:
            repo.enqueue(
                constants.STAGE_PROFILE_MEDIA,
                job.lead_id,
                profile.username,
                normalized,
                max_attempts=self._followup_max_attempts,
            )
        if profile.external_url or profile.bio_links:
            repo.enqueue(
                constants.STAGE_WEBSITE_ENRICH,
                job.lead_id,
                profile.username,
                normalized,
                max_attempts=self._followup_max_attempts,
            )
        if self._enable_ai:
            repo.enqueue(
                constants.STAGE_AI_DOSSIER,
                job.lead_id,
                profile.username,
                normalized,
                max_attempts=self._followup_max_attempts,
                priority=-1,
            )


class ProfileMediaStage:
    """Fetch a bounded number of recent posts/reels (optional stage)."""

    name = constants.STAGE_PROFILE_MEDIA

    def __init__(self, client: MediaFetcher, *, max_posts: int = 12, max_pages: int = 2) -> None:
        self._client = client
        self._max_posts = max_posts
        self._max_pages = max_pages

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        lead = repo.get_lead(job.lead_id)
        if lead is None:
            return StageOutcome(ok=False, error=f"lead {job.lead_id} not found", retryable=False)

        instagram_id = (lead.instagram_id or "").strip()
        if not instagram_id:
            repo.update_lead(job.lead_id, {"media_status": constants.STAGE_STATUS_NONE, "last_error": ""})
            return StageOutcome(ok=True, result="no instagram id; media skipped")

        try:
            posts = self._client.fetch_recent_posts(
                instagram_id, limit=self._max_posts, max_pages=self._max_pages
            )
        except HikerAPINotFoundError as exc:
            repo.update_lead(job.lead_id, {"media_status": constants.STAGE_STATUS_ERROR, "last_error": str(exc)})
            return StageOutcome(ok=True, result="media unavailable (not found)")
        except HikerAPIError as exc:
            retryable = isinstance(exc, _RETRYABLE_HIKER_ERRORS)
            repo.update_lead(job.lead_id, {"media_status": constants.STAGE_STATUS_ERROR, "last_error": str(exc)})
            return StageOutcome(ok=False, error=_error_text(exc), retryable=retryable)

        if not posts:
            repo.update_lead(job.lead_id, {"media_status": constants.STAGE_STATUS_NONE, "last_error": ""})
            return StageOutcome(ok=True, result="no recent posts")

        now = utc_now_iso()
        for post in posts:
            repo.upsert_post(
                LeadPost(
                    post_id=post.post_id,
                    lead_id=job.lead_id,
                    username=lead.username,
                    username_normalized=lead.username_normalized,
                    media_type=post.media_type,
                    product_type=post.product_type,
                    short_code=post.short_code,
                    url=post.url,
                    caption=post.caption[:2000],
                    like_count=post.like_count,
                    comment_count=post.comment_count,
                    play_count=post.play_count,
                    taken_at=post.taken_at,
                    fetched_at=now,
                    status="done",
                    created_at=now,
                    updated_at=now,
                )
            )
        repo.update_lead(job.lead_id, {"media_status": constants.STAGE_STATUS_DONE, "last_error": ""})
        return StageOutcome(ok=True, result=f"stored {len(posts)} post(s)")


class WebsiteEnrichStage:
    """Crawl the lead's external links (optional stage)."""

    name = constants.STAGE_WEBSITE_ENRICH

    def __init__(self, crawler: PageCrawler) -> None:
        self._crawler = crawler

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        lead = repo.get_lead(job.lead_id)
        if lead is None:
            return StageOutcome(ok=False, error=f"lead {job.lead_id} not found", retryable=False)

        urls = _external_urls(lead)
        if not urls:
            repo.update_lead(job.lead_id, {"website_status": constants.STAGE_STATUS_NONE})
            return StageOutcome(ok=True, result="no website; skipped")

        pages, emails = self._crawler.crawl(urls)
        now = utc_now_iso()
        done = blocked = errored = 0

        for page in pages:
            page_id = _page_id(job.lead_id, page.url)
            existing = repo.get_website_page(page_id)
            created_at = existing.created_at if existing is not None else ""
            repo.upsert_website_page(
                WebsitePage(
                    page_id=page_id,
                    lead_id=job.lead_id,
                    username=lead.username,
                    url=page.url,
                    resolved_url=page.resolved_url,
                    domain=page.domain,
                    title=page.title,
                    text=page.text,
                    links=_serialize_links(page.links),
                    http_status=page.http_status,
                    status=page.status,
                    error=page.error[:500],
                    fetched_at=now,
                    created_at=created_at or now,
                    updated_at=now,
                )
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
        repo.update_lead(job.lead_id, {"website_status": status})
        return StageOutcome(
            ok=True,
            result=json.dumps(
                {"pages": len(pages), "done": done, "blocked": blocked, "error": errored, "emails": len(emails)}
            ),
        )


class AIDossierStage:
    """Generate a validated creator dossier (Phase 6)."""

    name = constants.STAGE_AI_DOSSIER

    def __init__(
        self,
        service: AIService,
        *,
        model_name: str = "",
        followup_max_attempts: int = 3,
        max_posts: int = 10,
        max_pages: int = 5,
        text_chars: int = 1500,
    ) -> None:
        self._service = service
        self._model_name = model_name
        self._followup_max_attempts = followup_max_attempts
        self._max_posts = max_posts
        self._max_pages = max_pages
        self._text_chars = text_chars

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        lead = repo.get_lead(job.lead_id)
        if lead is None:
            return StageOutcome(ok=False, error=f"lead {job.lead_id} not found", retryable=False)

        existing = repo.get_dossier(job.lead_id)
        if (
            not _job_force(job)
            and existing is not None
            and existing.status in (constants.AI_STATUS_NEEDS_REVIEW, "generated")
        ):
            return StageOutcome(ok=True, result="dossier already generated")

        evidence = _build_evidence(
            repo, lead, max_posts=self._max_posts, max_pages=self._max_pages, text_chars=self._text_chars
        )
        if not evidence.has_content():
            self._store_dossier(repo, job, lead, evidence, None, status=constants.AI_STATUS_INSUFFICIENT, error="insufficient evidence")
            return StageOutcome(ok=True, result="insufficient evidence")

        try:
            result = self._service.generate_dossier(evidence)
        except AIResponseError as exc:
            self._store_dossier(repo, job, lead, evidence, None, status=constants.AI_STATUS_ERROR, error=str(exc))
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except (AIRateLimitError, AINetworkError) as exc:
            return StageOutcome(ok=False, error=_error_text(exc), retryable=True)
        except (AIConfigError, AIError) as exc:
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)

        self._store_dossier(repo, job, lead, evidence, result, status=constants.AI_STATUS_NEEDS_REVIEW, error="")
        repo.enqueue(
            constants.STAGE_AI_OUTREACH,
            job.lead_id,
            lead.username,
            lead.username_normalized,
            max_attempts=self._followup_max_attempts,
        )
        return StageOutcome(
            ok=True,
            result=json.dumps({"score": result.score, "tier": result.tier, "status": constants.AI_STATUS_NEEDS_REVIEW}),
        )

    def _store_dossier(
        self,
        repo: Repository,
        job: PipelineJob,
        lead: Lead,
        evidence: Evidence,
        result: DossierResult | None,
        *,
        status: str,
        error: str,
    ) -> None:
        existing = repo.get_dossier(job.lead_id)
        created_at = existing.created_at if existing is not None else ""
        now = utc_now_iso()
        repo.upsert_dossier(
            Dossier(
                lead_id=job.lead_id,
                username=evidence.username or lead.username,
                username_normalized=job.username_normalized or lead.username_normalized,
                summary=result.summary if result else "",
                topics=", ".join(result.topics) if result else "",
                audience=result.audience if result else "",
                evidence_urls="\n".join(result.evidence_urls) if result else "\n".join(evidence.source_urls()),
                qualification_score=result.score if result else 0,
                qualification_tier=result.tier if result else "",
                rubric=f"{self._service.rubric.name}@{self._service.rubric.version}",
                criterion_scores=json.dumps(result.criterion_scores) if result else "",
                uncertainty=result.uncertainty if result else "",
                model=self._model_name,
                status=status,
                last_error=error[:500],
                generated_at=now if result else "",
                created_at=created_at or now,
                updated_at=now,
            )
        )


class AIOutreachStage:
    """Generate personalized email/DM drafts marked NEEDS_REVIEW (Phase 6)."""

    name = constants.STAGE_AI_OUTREACH

    def __init__(
        self,
        service: AIService,
        *,
        model_name: str = "",
        max_posts: int = 10,
        max_pages: int = 5,
        text_chars: int = 1500,
    ) -> None:
        self._service = service
        self._model_name = model_name
        self._max_posts = max_posts
        self._max_pages = max_pages
        self._text_chars = text_chars

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        lead = repo.get_lead(job.lead_id)
        if lead is None:
            return StageOutcome(ok=False, error=f"lead {job.lead_id} not found", retryable=False)

        existing = repo.get_outreach(job.lead_id)
        if (
            not _job_force(job)
            and existing is not None
            and existing.status == constants.AI_STATUS_NEEDS_REVIEW
        ):
            return StageOutcome(ok=True, result="outreach already generated")

        dossier = repo.get_dossier(job.lead_id)
        if dossier is None or dossier.status in (constants.AI_STATUS_INSUFFICIENT, constants.AI_STATUS_ERROR):
            return StageOutcome(ok=True, result="no usable dossier; outreach skipped")

        evidence = _build_evidence(
            repo, lead, max_posts=self._max_posts, max_pages=self._max_pages, text_chars=self._text_chars
        )
        try:
            draft = self._service.generate_outreach(evidence, dossier.summary)
        except AIResponseError as exc:
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except (AIRateLimitError, AINetworkError) as exc:
            return StageOutcome(ok=False, error=_error_text(exc), retryable=True)
        except (AIConfigError, AIError) as exc:
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)

        created_at = existing.created_at if existing is not None else ""
        now = utc_now_iso()
        repo.upsert_outreach(
            OutreachEntry(
                lead_id=job.lead_id,
                username=lead.username,
                username_normalized=lead.username_normalized,
                channel="email+dm",
                status=constants.AI_STATUS_NEEDS_REVIEW,
                subject=draft.emailSubject.strip(),
                body=draft.emailBody.strip(),
                dm_body=draft.dmBody.strip(),
                model=self._model_name,
                generated_at=now,
                created_at=created_at or now,
                updated_at=now,
            )
        )
        return StageOutcome(ok=True, result=constants.AI_STATUS_NEEDS_REVIEW)
