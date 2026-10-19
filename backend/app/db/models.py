"""SQLAlchemy ORM models (PostgreSQL / SQLite).

Mirrors the previous Google Sheets schema 1:1. Timestamps are stored as ISO-8601
UTC strings so ordering and the existing string comparisons are preserved.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
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
