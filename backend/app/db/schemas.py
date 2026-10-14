"""Typed domain models for the database layer.

These are plain (alias-free) pydantic models whose field names match the ORM
attributes 1:1, so the repository can map rows with ``model_validate(row,
from_attributes=True)``.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from .util import normalize_username  # re-exported for callers

__all__ = [
    "Dossier",
    "Lead",
    "LeadPost",
    "OutreachEntry",
    "PipelineJob",
    "RowModel",
    "WebsitePage",
    "normalize_username",
]


def _coerce_int(value: Any) -> Any:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return 0


IntField = Annotated[int, BeforeValidator(_coerce_int)]


class RowModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore", from_attributes=True)


class Lead(RowModel):
    """A row in `leads`."""

    lead_id: str = ""
    username: str = ""
    username_normalized: str = ""
    full_name: str = ""
    instagram_id: str = ""
    follower_count: IntField = 0
    follows_count: IntField = 0
    business_category_name: str = ""
    bio: str = ""
    business_email: str = ""
    business_phone_number: str = ""
    profile_url: str = ""
    external_url: str = ""
    all_external_urls: str = ""
    engagement_rate: str = ""
    scraped_at: str = ""
    status: str = "new"
    source: str = ""
    media_status: str = ""
    website_status: str = ""
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""


class LeadPost(RowModel):
    """A row in `lead_posts` (one recent media item)."""

    post_id: str = ""
    lead_id: str = ""
    username: str = ""
    username_normalized: str = ""
    media_type: str = ""
    product_type: str = ""
    short_code: str = ""
    url: str = ""
    caption: str = ""
    like_count: IntField = 0
    comment_count: IntField = 0
    play_count: IntField = 0
    taken_at: str = ""
    fetched_at: str = ""
    status: str = "done"
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""


class WebsitePage(RowModel):
    """A row in `website_pages` (one crawled page)."""

    page_id: str = ""
    lead_id: str = ""
    username: str = ""
    url: str = ""
    resolved_url: str = ""
    domain: str = ""
    title: str = ""
    text: str = ""
    links: str = ""
    http_status: IntField = 0
    status: str = ""
    error: str = ""
    fetched_at: str = ""
    created_at: str = ""
    updated_at: str = ""


class Dossier(RowModel):
    """A row in `dossiers` (one AI dossier per lead)."""

    lead_id: str = ""
    username: str = ""
    username_normalized: str = ""
    summary: str = ""
    topics: str = ""
    audience: str = ""
    evidence_urls: str = ""
    qualification_score: IntField = 0
    qualification_tier: str = ""
    rubric: str = ""
    criterion_scores: str = ""
    uncertainty: str = ""
    model: str = ""
    status: str = ""
    last_error: str = ""
    generated_at: str = ""
    created_at: str = ""
    updated_at: str = ""


class OutreachEntry(RowModel):
    """A row in `outreach_drafts` (one per lead)."""

    lead_id: str = ""
    username: str = ""
    username_normalized: str = ""
    channel: str = ""
    status: str = "draft"
    subject: str = ""
    body: str = ""
    dm_body: str = ""
    model: str = ""
    generated_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    last_error: str = ""


class PipelineJob(RowModel):
    """A row in `pipeline_jobs`."""

    job_id: str = ""
    stage: str = ""
    lead_id: str = ""
    username: str = ""
    username_normalized: str = ""
    status: str = "queued"
    attempt_count: IntField = 0
    max_attempts: IntField = 3
    priority: IntField = 0
    payload: str = ""
    result: str = ""
    last_error: str = ""
    locked_at: str = ""
    locked_by: str = ""
    run_after: str = ""
    created_at: str = ""
    updated_at: str = ""
