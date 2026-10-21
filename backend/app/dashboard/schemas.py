"""Response/request schemas for the dashboard API."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.leads.schemas import LeadResponse
from app.db.schemas import (
    Dossier,
    LeadPost,
    OutreachEntry,
    PipelineJob,
    WebsitePage,
)


class PostOut(BaseModel):
    post_id: str
    media_type: str
    product_type: str
    short_code: str
    url: str
    caption: str
    like_count: int
    comment_count: int
    play_count: int
    taken_at: str
    fetched_at: str
    status: str

    @classmethod
    def from_model(cls, post: LeadPost) -> "PostOut":
        return cls(
            post_id=post.post_id,
            media_type=post.media_type,
            product_type=post.product_type,
            short_code=post.short_code,
            url=post.url,
            caption=post.caption,
            like_count=post.like_count,
            comment_count=post.comment_count,
            play_count=post.play_count,
            taken_at=post.taken_at,
            fetched_at=post.fetched_at,
            status=post.status,
        )


class WebsitePageOut(BaseModel):
    page_id: str
    url: str
    resolved_url: str
    domain: str
    title: str
    text: str
    links: str
    http_status: int
    status: str
    error: str
    fetched_at: str

    @classmethod
    def from_model(cls, page: WebsitePage) -> "WebsitePageOut":
        return cls(
            page_id=page.page_id,
            url=page.url,
            resolved_url=page.resolved_url,
            domain=page.domain,
            title=page.title,
            text=page.text,
            links=page.links,
            http_status=page.http_status,
            status=page.status,
            error=page.error,
            fetched_at=page.fetched_at,
        )


class JobOut(BaseModel):
    job_id: str
    stage: str
    status: str
    attempt_count: int
    max_attempts: int
    result: str
    last_error: str
    run_after: str
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, job: PipelineJob) -> "JobOut":
        return cls(
            job_id=job.job_id,
            stage=job.stage,
            status=job.status,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            result=job.result,
            last_error=job.last_error,
            run_after=job.run_after,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class DossierOut(BaseModel):
    lead_id: str
    username: str
    summary: str
    topics: list[str]
    audience: str
    evidence_urls: list[str]
    qualification_score: int
    qualification_tier: str
    rubric: str
    criterion_scores: dict[str, int]
    uncertainty: str
    model: str
    status: str
    generated_at: str

    @classmethod
    def from_model(cls, dossier: Dossier) -> "DossierOut":
        try:
            scores = json.loads(dossier.criterion_scores) if dossier.criterion_scores else {}
        except ValueError:
            scores = {}
        return cls(
            lead_id=dossier.lead_id,
            username=dossier.username,
            summary=dossier.summary,
            topics=[t.strip() for t in dossier.topics.split(",") if t.strip()],
            audience=dossier.audience,
            evidence_urls=[u.strip() for u in dossier.evidence_urls.replace(",", "\n").split("\n") if u.strip()],
            qualification_score=dossier.qualification_score,
            qualification_tier=dossier.qualification_tier,
            rubric=dossier.rubric,
            criterion_scores={str(k): int(v) for k, v in scores.items()},
            uncertainty=dossier.uncertainty,
            model=dossier.model,
            status=dossier.status,
            generated_at=dossier.generated_at,
        )


class OutreachOut(BaseModel):
    lead_id: str
    username: str
    channel: str
    status: str
    subject: str
    body: str
    dm_body: str
    model: str
    generated_at: str

    @classmethod
    def from_model(cls, entry: OutreachEntry) -> "OutreachOut":
        return cls(
            lead_id=entry.lead_id,
            username=entry.username,
            channel=entry.channel,
            status=entry.status,
            subject=entry.subject,
            body=entry.body,
            dm_body=entry.dm_body,
            model=entry.model,
            generated_at=entry.generated_at,
        )


class ContactOut(BaseModel):
    """A publicly listed, evidence-backed contact (V2-04)."""

    contact_id: str
    lead_id: str
    type: str
    value: str
    source_url: str
    observed_at: str
    method: str
    validation_state: str
    provenance: str = ""

    @classmethod
    def from_model(cls, contact) -> "ContactOut":
        legacy = contact.method == "legacy" or not (contact.source_url or "").strip()
        return cls(
            contact_id=contact.contact_id,
            lead_id=contact.lead_id,
            type=contact.type,
            value=contact.value,
            source_url=contact.source_url,
            observed_at=contact.observed_at,
            method=contact.method,
            validation_state=contact.validation_state,
            provenance="Legacy source unknown" if legacy else "Public website",
        )


class LeadDetailOut(BaseModel):
    lead: LeadResponse
    progress: str = "needs_data"
    progress_remedy: str = ""
    posts: list[PostOut] = Field(default_factory=list)
    website_pages: list[WebsitePageOut] = Field(default_factory=list)
    contacts: list[ContactOut] = Field(default_factory=list)
    jobs: list[JobOut] = Field(default_factory=list)


class RetryAIOut(BaseModel):
    """Result of a manual AI re-processing request."""

    lead_id: str
    jobs: list[JobOut] = Field(default_factory=list)


class DossierListOut(BaseModel):
    items: list[DossierOut]
    total: int
    limit: int
    offset: int


class OutreachListOut(BaseModel):
    items: list[OutreachOut]
    total: int
    limit: int
    offset: int


class OutreachUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    subject: str | None = None
    body: str | None = None
    dm_body: str | None = None


class StatsOut(BaseModel):
    leads_total: int
    leads_by_status: dict[str, int]
    leads_by_progress: dict[str, int]
    jobs_by_status: dict[str, int]
    dossiers_total: int
    outreach_total: int
    outreach_needs_review: int


class IntegrationsStatusOut(BaseModel):
    """Secret-free readiness snapshot (PRD T09)."""

    database: Literal["healthy", "unreachable"]
    worker: Literal["active", "stale", "stopped"]
    gemini: Literal["configured", "disabled"]
    hikerapi: Literal["configured", "disabled"]
    worker_last_beat_at: str = ""


class BriefSourceOut(BaseModel):
    url: str
    title: str
    status: str
    fetched_at: str


class BriefOut(BaseModel):
    """An evidence-only creator brief. Never requires an AI call (V2-01/V2-04)."""

    lead_id: str
    username: str
    full_name: str
    bio: str
    category: str
    follower_count: int
    follower_display: str = ""
    follower_precision: str = "unknown"
    follows_count: int
    external_urls: list[str] = Field(default_factory=list)
    captured_at: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    is_verified: bool = False
    observed_topics: list[str] = Field(default_factory=list)
    websites: list[BriefSourceOut] = Field(default_factory=list)
    sources: list[BriefSourceOut] = Field(default_factory=list)
    contacts: list[ContactOut] = Field(default_factory=list)
    evidence_version: int = 0
    has_dossier: bool = False
    ai_summary: str = ""
    ai_status: str = "not_generated"
    generated_at: str = ""
    model: str = ""


class ContactListOut(BaseModel):
    items: list[ContactOut]
    total: int
