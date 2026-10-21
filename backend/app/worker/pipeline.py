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
from app.db.schemas import (
    Contact,
    Dossier,
    DraftRevision,
    Lead,
    LeadPost,
    OutreachEntry,
    OutreachRevision,
    PipelineJob,
    WebsitePage,
)
from app.db.util import contact_id, new_job_id, utc_now_iso
from app.leads.validation import InvalidLeadInput
from app.worker.snapshot import parse_snapshot, snapshot_has_data, snapshot_to_lead_fields
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
    # When set, the job is re-queued without counting an attempt (dependency wait).
    deferred: bool = False
    defer_seconds: float = 30.0


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

    Used by manual AI re-processing (`{"force": true}`) so an existing **dossier**
    is regenerated. Drafts are always preserved regardless of this flag (T00).
    """
    try:
        payload = json.loads(job.payload or "{}")
    except ValueError:
        return False
    return bool(isinstance(payload, dict) and payload.get("force"))


def _job_request_id(job: PipelineJob) -> str:
    """Read the explicit contact-request id from a discovery job payload."""
    try:
        payload = json.loads(job.payload or "{}")
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("request_id") or "").strip()


def _is_existing_draft(entry: OutreachEntry | None) -> bool:
    """True when an outreach row already holds reviewed or authored content.

    V2-07: generation no longer overwrites in place. A draft that already
    exists is superseded by a **new** revision, so this guard is only used for
    the legacy "never silently replace" check on the current pointer.
    """
    if entry is None:
        return False
    if (entry.status or "").upper() in constants.DRAFT_REVIEW_STATUSES:
        return True
    return bool(
        (entry.subject or "").strip()
        or (entry.body or "").strip()
        or (entry.dm_body or "").strip()
    )


def _fail_generation(
    repo: Repository, request: OutreachRevision | None, error: str
) -> None:
    """Record a failed generation request so no orphan revision is left."""
    if request is None:
        return
    repo.update_outreach_revision(
        request.revision_id,
        {"status": constants.DRAFT_GENERATION_FAILED, "error": error[:4000]},
    )


def _evidence_scope(evidence: Evidence) -> str:
    """A short, human-readable description of the evidence a draft used."""
    return f"posts={len(evidence.posts or [])} pages={len(evidence.pages or [])}"


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


# Evidence stages whose terminal state must be reached before AI runs (T06).
_AI_EVIDENCE_DEPENDENCIES = (
    constants.STAGE_PROFILE_MEDIA,
    constants.STAGE_WEBSITE_ENRICH,
)
_OUTREACH_DEPENDENCIES = _AI_EVIDENCE_DEPENDENCIES + (constants.STAGE_AI_DOSSIER,)
_TERMINAL_JOB_STATUSES = (constants.JOB_DONE, constants.JOB_ERROR)
_DEPENDENCY_DEFER_SECONDS = 15.0


def _pending_dependencies(repo: Repository, lead_id: str, stages: tuple[str, ...]) -> list[str]:
    """Stages with a non-terminal job that must finish before proceeding.

    A retry is not terminal, so it is treated as pending (PRD §5.4). An absent
    job means the stage is not applicable and is not a dependency.
    """
    pending: list[str] = []
    for stage in stages:
        job = repo.find_job(stage, lead_id)
        if job is not None and job.status not in _TERMINAL_JOB_STATUSES:
            pending.append(stage)
    return pending


class ProfileFetchStage:
    """Populate the lead from a captured snapshot, else fall back to HikerAPI.

    A valid ``profile_snapshot`` fully bypasses HikerAPI (PRD T06). HikerAPI is
    only called when no snapshot exists *and* credentials are configured; a
    handle-only lead with no provider stays ``needs_data`` instead of silently
    spending HikerAPI credits.
    """

    name = constants.STAGE_PROFILE_FETCH

    def __init__(
        self,
        client: ProfileFetcher | None,
        *,
        followup_max_attempts: int = 3,
        enable_ai: bool = False,
        hiker_enabled: bool = True,
    ) -> None:
        self._client = client
        self._followup_max_attempts = followup_max_attempts
        self._enable_ai = enable_ai
        self._hiker_enabled = bool(hiker_enabled and client is not None)

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        lead = repo.get_lead(job.lead_id)
        if lead is None:
            return StageOutcome(ok=False, error=f"lead {job.lead_id} not found", retryable=False)

        snapshot = parse_snapshot(lead.profile_snapshot)
        if snapshot_has_data(snapshot):
            return self._apply_snapshot(repo, job, lead, snapshot)

        if not self._hiker_enabled:
            # No snapshot and no configured provider: do not call HikerAPI.
            return StageOutcome(ok=True, result="no snapshot and no profile provider; needs data")

        return self._fetch_with_hiker(repo, job)

    def _apply_snapshot(
        self, repo: Repository, job: PipelineJob, lead: Lead, snapshot: dict
    ) -> StageOutcome:
        fields = snapshot_to_lead_fields(snapshot)
        fields["status"] = constants.LEAD_STATUS_ENRICHED
        fields["last_error"] = ""
        updated = repo.update_lead(job.lead_id, fields) or lead
        self._enqueue_snapshot_followups(repo, job, updated)
        urls = snapshot.get("external_urls") or []
        logger.info(
            "Enriched lead %s (@%s) from snapshot: followers=%s urls=%s",
            job.lead_id,
            updated.username,
            fields.get("follower_count", ""),
            len(urls),
        )
        return StageOutcome(
            ok=True,
            result=json.dumps(
                {
                    "source": "snapshot",
                    "followers": fields.get("follower_count", 0),
                    "externalUrls": len(urls),
                }
            ),
        )

    def _fetch_with_hiker(self, repo: Repository, job: PipelineJob) -> StageOutcome:
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

    def _enqueue_snapshot_followups(
        self, repo: Repository, job: PipelineJob, lead: Lead
    ) -> None:
        normalized = job.username_normalized or lead.username_normalized
        if lead.external_url or lead.all_external_urls:
            repo.enqueue(
                constants.STAGE_WEBSITE_ENRICH,
                job.lead_id,
                lead.username,
                normalized,
                max_attempts=self._followup_max_attempts,
            )
        if self._enable_ai:
            repo.enqueue(
                constants.STAGE_AI_DOSSIER,
                job.lead_id,
                lead.username,
                normalized,
                max_attempts=self._followup_max_attempts,
                priority=-1,
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

    def __init__(self, client: MediaFetcher | None, *, max_posts: int = 12, max_pages: int = 2) -> None:
        self._client = client
        self._max_posts = max_posts
        self._max_pages = max_pages

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        lead = repo.get_lead(job.lead_id)
        if lead is None:
            return StageOutcome(ok=False, error=f"lead {job.lead_id} not found", retryable=False)

        instagram_id = (lead.instagram_id or "").strip()
        if not instagram_id or self._client is None:
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
        stored_emails: set[str] = set()

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
            stored_emails.update(email.lower() for email in page.emails)
            self._store_page_contacts(
                repo, job.lead_id, page.emails, page.phones, page.resolved_url or page.url, now
            )
            if page.status == "done":
                done += 1
            elif page.status == "blocked":
                blocked += 1
            else:
                errored += 1

        # The crawler also returns an aggregate email list (some providers only
        # expose it there). Attribute those to the first supplied URL.
        fallback_source = urls[0] if urls else ""
        for email in emails:
            if email.lower() in stored_emails:
                continue
            self._store_contact(repo, job.lead_id, "email", email, fallback_source, now)

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

    def _store_page_contacts(
        self,
        repo: Repository,
        lead_id: str,
        emails: list[str],
        phones: list[str],
        source_url: str,
        observed_at: str,
    ) -> None:
        for email in emails or []:
            self._store_contact(repo, lead_id, "email", email, source_url, observed_at)
        for phone in phones or []:
            self._store_contact(repo, lead_id, "phone", phone, source_url, observed_at)

    @staticmethod
    def _store_contact(
        repo: Repository,
        lead_id: str,
        kind: str,
        value: str,
        source_url: str,
        observed_at: str,
    ) -> None:
        text = str(value or "").strip()
        if not text:
            return
        repo.upsert_contact(
            Contact(
                contact_id=contact_id(lead_id, kind, text, source_url),
                lead_id=lead_id,
                type=kind,
                value=text,
                source_url=source_url,
                observed_at=observed_at,
                method="website_crawl",
                validation_state="unverified",
            )
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

        pending = _pending_dependencies(repo, job.lead_id, _AI_EVIDENCE_DEPENDENCIES)
        if pending:
            return StageOutcome(
                ok=False,
                deferred=True,
                defer_seconds=_DEPENDENCY_DEFER_SECONDS,
                result=f"waiting for evidence: {', '.join(pending)}",
            )

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
        # V2-01: dossier completion must never schedule outreach/draft work.
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
    """Generate a personalized draft as a NEW revision (Phase 6 / V2-07).

    V2-07: generation never overwrites. A successful run appends a new
    ``draft_revisions`` row and supersedes the previous one, so an approved or
    manually authored draft stays visible as history (V23). The legacy
    ``outreach_drafts`` row is kept in sync as the "current" pointer.
    """

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

        request_id = _job_request_id(job)
        request = repo.get_outreach_revision(request_id) if request_id else None

        if request is not None:
            # V23: a request completes once. A retry (or a crash and restart)
            # must not produce a second revision for the same request.
            if request.result_revision_id or request.status == constants.DRAFT_GENERATION_SUCCEEDED:
                return StageOutcome(ok=True, result="revision already generated")
        else:
            # Legacy path: a job without an explicit request never replaces an
            # existing draft.
            existing = repo.get_outreach(job.lead_id)
            if _is_existing_draft(existing):
                if _job_force(job):
                    logger.warning(
                        "Outreach regeneration requested for lead %s without a "
                        "draft request; preserving the existing draft.",
                        job.lead_id,
                    )
                return StageOutcome(ok=True, result="existing draft preserved")

        pending = _pending_dependencies(repo, job.lead_id, _OUTREACH_DEPENDENCIES)
        if pending:
            return StageOutcome(
                ok=False,
                deferred=True,
                defer_seconds=_DEPENDENCY_DEFER_SECONDS,
                result=f"waiting for evidence: {', '.join(pending)}",
            )

        dossier = repo.get_dossier(job.lead_id)
        if dossier is None or dossier.status in (constants.AI_STATUS_INSUFFICIENT, constants.AI_STATUS_ERROR):
            if request is not None:
                repo.update_outreach_revision(
                    request.revision_id,
                    {
                        "status": constants.DRAFT_GENERATION_FAILED,
                        "error": "no usable dossier; outreach skipped",
                    },
                )
            return StageOutcome(ok=True, result="no usable dossier; outreach skipped")

        evidence = _build_evidence(
            repo, lead, max_posts=self._max_posts, max_pages=self._max_pages, text_chars=self._text_chars
        )
        try:
            draft = self._service.generate_outreach(evidence, dossier.summary)
        except AIResponseError as exc:
            _fail_generation(repo, request, _error_text(exc))
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except (AIRateLimitError, AINetworkError) as exc:
            _fail_generation(repo, request, _error_text(exc))
            return StageOutcome(ok=False, error=_error_text(exc), retryable=True)
        except (AIConfigError, AIError) as exc:
            _fail_generation(repo, request, _error_text(exc))
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)

        now = utc_now_iso()
        parent_revision_id = request.parent_revision_id if request is not None else ""
        if not parent_revision_id:
            current = repo.get_latest_draft_revision(job.lead_id)
            parent_revision_id = current.revision_id if current is not None else ""
        if parent_revision_id:
            repo.supersede_draft_revision(parent_revision_id)

        revision = repo.create_draft_revision(
            DraftRevision(
                revision_id=new_job_id("dr"),
                lead_id=job.lead_id,
                username=lead.username,
                username_normalized=lead.username_normalized,
                channel=request.channel if request is not None else "email+dm",
                subject=draft.emailSubject.strip(),
                body=draft.emailBody.strip(),
                dm_body=draft.dmBody.strip(),
                status=constants.DRAFT_REVISION_NEEDS_REVIEW,
                method=constants.DRAFT_METHOD_AI,
                model=self._model_name,
                parent_revision_id=parent_revision_id,
                contact_id="",
                request_id=request.revision_id if request is not None else "",
                evidence_scope=_evidence_scope(evidence),
                note="",
                edited_at=now,
            )
        )
        if request is not None:
            repo.update_outreach_revision(
                request.revision_id,
                {
                    "status": constants.DRAFT_GENERATION_SUCCEEDED,
                    "result_revision_id": revision.revision_id,
                    "parent_revision_id": parent_revision_id,
                    "job_id": job.job_id,
                    "error": "",
                },
            )

        # Keep the legacy single-row draft in sync as the "current" pointer.
        existing = repo.get_outreach(job.lead_id)
        created_at = existing.created_at if existing is not None else ""
        repo.upsert_outreach(
            OutreachEntry(
                lead_id=job.lead_id,
                username=lead.username,
                username_normalized=lead.username_normalized,
                channel=revision.channel,
                status=constants.AI_STATUS_NEEDS_REVIEW,
                subject=revision.subject,
                body=revision.body,
                dm_body=revision.dm_body,
                model=self._model_name,
                generated_at=now,
                created_at=created_at or now,
                updated_at=now,
            )
        )
        return StageOutcome(ok=True, result=constants.AI_STATUS_NEEDS_REVIEW)


class AIDisabledStage:
    """Completes a queued AI job without a provider call when AI is disabled.

    V2-01: a queued AI job that encounters a capability change (AI disabled) must
    not fail as an unregistered stage. Research, the creator brief, and the manual
    workflow remain fully usable.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        logger.info("AI stage %s skipped for lead %s: AI disabled", job.stage, job.lead_id)
        return StageOutcome(ok=True, result="AI disabled; no provider call")


class ContactDiscoveryStage:
    """Explicit, contact-focused pass over public sources (V2-06).

    Idempotent: a repeated click for the same evidence version reuses the request.
    If the shortlist is revoked (rejected / review needed) before or during the
    pass, the request is cancelled and no contacts are published.
    """

    name = constants.STAGE_CONTACT_DISCOVERY

    def __init__(self, crawler: PageCrawler) -> None:
        self._crawler = crawler

    def run(self, job: PipelineJob, repo: Repository) -> StageOutcome:
        request_id = _job_request_id(job)
        request = repo.get_contact_request(request_id)
        if request is None:
            return StageOutcome(ok=True, result="contact request not found; skipped")

        terminal = (
            constants.CONTACT_REQUEST_FOUND,
            constants.CONTACT_REQUEST_NOT_FOUND,
            constants.CONTACT_REQUEST_FAILED,
            constants.CONTACT_REQUEST_CANCELLED,
        )
        if request.status in terminal:
            return StageOutcome(ok=True, result=f"request already {request.status}")

        lead = repo.get_lead(request.lead_id)
        if lead is None:
            repo.update_contact_request(
                request_id,
                {
                    "status": constants.CONTACT_REQUEST_FAILED,
                    "error": "lead not found",
                    "completed_at": utc_now_iso(),
                },
            )
            return StageOutcome(ok=True, result="lead not found")

        if not _contact_gate(lead):
            return _cancel_request(repo, request_id, "Fit approval revoked")

        now = utc_now_iso()
        repo.update_contact_request(
            request_id,
            {"status": constants.CONTACT_REQUEST_RUNNING, "started_at": now, "error": ""},
        )

        urls = _discovery_urls(repo, lead)
        if not urls:
            repo.update_contact_request(
                request_id,
                {
                    "status": constants.CONTACT_REQUEST_FAILED,
                    "error": "No public sources to search",
                    "searched_scope": "0 sources",
                    "completed_at": utc_now_iso(),
                },
            )
            return StageOutcome(ok=True, result="no public sources")

        try:
            pages, _emails = self._crawler.crawl(urls)
        except Exception as exc:  # noqa: BLE001 - recorded as a request failure
            repo.update_contact_request(
                request_id,
                {
                    "status": constants.CONTACT_REQUEST_FAILED,
                    "error": _error_text(exc),
                    "searched_scope": f"{len(urls)} source(s)",
                    "completed_at": utc_now_iso(),
                },
            )
            return StageOutcome(ok=True, result="contact discovery failed")

        # Re-check after the external work: never publish after a revocation.
        lead = repo.get_lead(request.lead_id)
        if lead is None or not _contact_gate(lead):
            return _cancel_request(repo, request_id, "Fit approval revoked during search")

        done = blocked = errored = 0
        contact_ids: set[str] = set()
        for page in pages:
            if page.status == "done":
                done += 1
            elif page.status == "blocked":
                blocked += 1
            else:
                errored += 1
            source = page.resolved_url or page.url
            for email in page.emails or []:
                contact_ids.add(_store_discovery_contact(repo, request.lead_id, "email", email, source, now))
            for phone in page.phones or []:
                contact_ids.add(_store_discovery_contact(repo, request.lead_id, "phone", phone, source, now))
        contact_ids.discard("")

        scope = f"{len(urls)} source(s), {len(pages)} page(s) searched"
        if contact_ids:
            status = constants.CONTACT_REQUEST_FOUND
            error = ""
        elif pages and done == 0:
            status = constants.CONTACT_REQUEST_FAILED
            error = "All sources were blocked or unreachable"
        else:
            status = constants.CONTACT_REQUEST_NOT_FOUND
            error = ""

        repo.update_contact_request(
            request_id,
            {
                "status": status,
                "result_count": len(contact_ids),
                "searched_scope": scope,
                "completed_at": utc_now_iso(),
                "error": error,
            },
        )
        return StageOutcome(
            ok=True,
            result=json.dumps(
                {
                    "status": status,
                    "contacts": len(contact_ids),
                    "pages": len(pages),
                    "done": done,
                    "blocked": blocked,
                    "error": errored,
                }
            ),
        )


def _contact_gate(lead: Lead) -> bool:
    return (
        lead.fit_status == constants.FIT_STATUS_SHORTLISTED
        and (lead.decision_currency or constants.DECISION_CURRENCY_CURRENT)
        == constants.DECISION_CURRENCY_CURRENT
    )


def _cancel_request(repo: Repository, request_id: str, reason: str) -> StageOutcome:
    repo.update_contact_request(
        request_id,
        {
            "status": constants.CONTACT_REQUEST_CANCELLED,
            "error": reason,
            "completed_at": utc_now_iso(),
        },
    )
    return StageOutcome(ok=True, result=f"cancelled: {reason}")


def _discovery_urls(repo: Repository, lead: Lead) -> list[str]:
    """Public sources to search: supplied links plus already-observed pages."""
    urls = _external_urls(lead)
    for page in repo.list_website_pages(lead.lead_id):
        candidate = page.resolved_url or page.url
        if candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def _store_discovery_contact(
    repo: Repository,
    lead_id: str,
    kind: str,
    value: str,
    source_url: str,
    observed_at: str,
) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    cid = contact_id(lead_id, kind, text, source_url)
    repo.upsert_contact(
        Contact(
            contact_id=cid,
            lead_id=lead_id,
            type=kind,
            value=text,
            source_url=source_url,
            observed_at=observed_at,
            method=constants.CONTACT_METHOD_DISCOVERY,
            validation_state="unverified",
        )
    )
    return cid
