"""SQLAlchemy ORM models (PostgreSQL / SQLite).

Mirrors the previous Google Sheets schema 1:1. Timestamps are stored as ISO-8601
UTC strings so ordering and the existing string comparisons are preserved.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Lead(Base):
    __tablename__ = "leads"

    lead_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(255), default="")
    username_normalized: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, default=""
    )
    full_name: Mapped[str] = mapped_column(String(255), default="")
    instagram_id: Mapped[str] = mapped_column(String(64), default="")
    follower_count: Mapped[int] = mapped_column(Integer, default=0)
    follows_count: Mapped[int] = mapped_column(Integer, default=0)
    business_category_name: Mapped[str] = mapped_column(String(255), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    business_email: Mapped[str] = mapped_column(String(255), default="")
    business_phone_number: Mapped[str] = mapped_column(String(64), default="")
    profile_url: Mapped[str] = mapped_column(String(512), default="")
    external_url: Mapped[str] = mapped_column(String(512), default="")
    all_external_urls: Mapped[str] = mapped_column(Text, default="")
    engagement_rate: Mapped[str] = mapped_column(String(64), default="")
    scraped_at: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    source: Mapped[str] = mapped_column(String(64), default="")
    media_status: Mapped[str] = mapped_column(String(32), default="")
    website_status: Mapped[str] = mapped_column(String(32), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    # Capture intake (T04-lite): the latest sanitized extension snapshot as JSON,
    # plus the client-generated request id used for idempotent retries.
    profile_snapshot: Mapped[str] = mapped_column(Text, default="")
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    # Current evidence pointer (V2-02). Versions themselves are immutable rows.
    evidence_version: Mapped[int] = mapped_column(Integer, default=0)
    evidence_version_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    # Fit-decision dimension (V2-03). Independent of research progress.
    fit_status: Mapped[str] = mapped_column(String(32), default="not_reviewed", index=True)
    fit_note: Mapped[str] = mapped_column(Text, default="")
    fit_decided_at: Mapped[str] = mapped_column(String(40), default="")
    decision_currency: Mapped[str] = mapped_column(String(32), default="current", index=True)
    decision_currency_reason: Mapped[str] = mapped_column(Text, default="")
    new_evidence_available: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")

    posts: Mapped[list["Post"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    website_pages: Mapped[list["WebsitePage"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    dossier: Mapped["Dossier | None"] = relationship(
        back_populates="lead", cascade="all, delete-orphan", uselist=False
    )
    outreach: Mapped["OutreachDraft | None"] = relationship(
        back_populates="lead", cascade="all, delete-orphan", uselist=False
    )
    jobs: Mapped[list["PipelineJob"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class Post(Base):
    __tablename__ = "lead_posts"

    post_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    username: Mapped[str] = mapped_column(String(255), default="")
    username_normalized: Mapped[str] = mapped_column(String(255), default="")
    media_type: Mapped[str] = mapped_column(String(32), default="")
    product_type: Mapped[str] = mapped_column(String(64), default="")
    short_code: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    taken_at: Mapped[str] = mapped_column(String(64), default="")
    fetched_at: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="done")
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")

    lead: Mapped["Lead"] = relationship(back_populates="posts")


class WebsitePage(Base):
    __tablename__ = "website_pages"

    page_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    username: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    resolved_url: Mapped[str] = mapped_column(String(1024), default="")
    domain: Mapped[str] = mapped_column(String(255), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[str] = mapped_column(Text, default="")
    http_status: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")

    lead: Mapped["Lead"] = relationship(back_populates="website_pages")


class Dossier(Base):
    __tablename__ = "dossiers"

    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), primary_key=True
    )
    username: Mapped[str] = mapped_column(String(255), default="")
    username_normalized: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    topics: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(Text, default="")
    evidence_urls: Mapped[str] = mapped_column(Text, default="")
    qualification_score: Mapped[int] = mapped_column(Integer, default=0)
    qualification_tier: Mapped[str] = mapped_column(String(8), default="")
    rubric: Mapped[str] = mapped_column(String(128), default="")
    criterion_scores: Mapped[str] = mapped_column(Text, default="")
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="", index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")

    lead: Mapped["Lead"] = relationship(back_populates="dossier")


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"

    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), primary_key=True
    )
    username: Mapped[str] = mapped_column(String(255), default="")
    username_normalized: Mapped[str] = mapped_column(String(255), default="")
    channel: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    dm_body: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    generated_at: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")

    lead: Mapped["Lead"] = relationship(back_populates="outreach")


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        UniqueConstraint("stage", "lead_id", name="uq_pipeline_jobs_stage_lead"),
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage: Mapped[str] = mapped_column(String(64), index=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    username: Mapped[str] = mapped_column(String(255), default="")
    username_normalized: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    locked_at: Mapped[str] = mapped_column(String(40), default="")
    locked_by: Mapped[str] = mapped_column(String(64), default="")
    run_after: Mapped[str] = mapped_column(String(40), default="", index=True)
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")

    lead: Mapped["Lead"] = relationship(back_populates="jobs")


class ContactRequest(Base):
    """An explicit post-approval request to find public contact details (T08)."""

    __tablename__ = "contact_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    evidence_version: Mapped[int] = mapped_column(Integer, default=0)
    searched_scope: Mapped[str] = mapped_column(Text, default="")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[str] = mapped_column(String(40), default="")
    started_at: Mapped[str] = mapped_column(String(40), default="")
    completed_at: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")


class OutreachRevision(Base):
    """An explicit draft request; one row per request preserves history (T08)."""

    __tablename__ = "outreach_revisions"

    revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="requested", index=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    dm_body: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")


class WorkerHeartbeat(Base):
    """Single-row worker liveness marker used by the readiness endpoint (T09)."""

    __tablename__ = "worker_heartbeat"

    heartbeat_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    worker_id: Mapped[str] = mapped_column(String(64), default="")
    beat_at: Mapped[str] = mapped_column(String(40), default="", index=True)
    updated_at: Mapped[str] = mapped_column(String(40), default="")


class CaptureReceipt(Base):
    """Immutable record of an acknowledged capture request (V2-02).

    Keyed by the client request id. Reusing an id with a different payload is a
    conflict; replaying the same payload returns this receipt's lead without work.
    """

    __tablename__ = "capture_receipts"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    outcome: Mapped[str] = mapped_column(String(32), default="")
    received_at: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[str] = mapped_column(String(40), default="")


class EvidenceVersion(Base):
    """Immutable normalized snapshot captured for a lead (V2-02)."""

    __tablename__ = "evidence_versions"
    __table_args__ = (
        UniqueConstraint("lead_id", "version", name="uq_evidence_versions_lead_version"),
    )

    evidence_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    snapshot_json: Mapped[str] = mapped_column(Text, default="")
    captured_at: Mapped[str] = mapped_column(String(40), default="")
    received_at: Mapped[str] = mapped_column(String(40), default="", index=True)
    parser_version: Mapped[str] = mapped_column(String(32), default="")
    field_provenance: Mapped[str] = mapped_column(Text, default="")
    changed_fields: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default="")


class Campaign(Base):
    """A single active campaign configuration (V2-03)."""

    __tablename__ = "campaigns"

    campaign_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    target_topics: Mapped[str] = mapped_column(Text, default="")  # JSON list
    language: Mapped[str] = mapped_column(String(32), default="")
    follower_min: Mapped[int] = mapped_column(Integer, default=0)
    follower_max: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")


class FitDecision(Base):
    """Append-only fit decision / invalidation history (V2-03)."""

    __tablename__ = "fit_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(32), default="")
    fit_status: Mapped[str] = mapped_column(String(32), default="")
    decision_currency: Mapped[str] = mapped_column(String(32), default="current")
    evidence_version: Mapped[int] = mapped_column(Integer, default=0)
    criteria_version: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(40), default="", index=True)


class Contact(Base):
    """A publicly listed, evidence-backed contact (V2-04)."""

    __tablename__ = "contacts"

    contact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.lead_id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(16), default="email", index=True)
    value: Mapped[str] = mapped_column(String(512), default="")
    source_url: Mapped[str] = mapped_column(String(1024), default="")
    observed_at: Mapped[str] = mapped_column(String(40), default="")
    method: Mapped[str] = mapped_column(String(32), default="")
    validation_state: Mapped[str] = mapped_column(String(32), default="unverified")
    created_at: Mapped[str] = mapped_column(String(40), default="")
    updated_at: Mapped[str] = mapped_column(String(40), default="")
