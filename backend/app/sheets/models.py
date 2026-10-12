"""Typed row models for each Google Sheets tab.

Each model maps to a row using **named headers** (the Google Sheets header row)
rather than fixed column indexes. Pydantic aliases are the exact header names.

All models allow extra fields (`extra="allow"`) so unknown / future columns are
preserved on read and written back untouched instead of being dropped.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _coerce_int(value: Any) -> Any:
    """Convert sheet values (strings, blanks, floats) into an int, defaulting 0."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text == "":
        return 0
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return 0


IntField = Annotated[int, BeforeValidator(_coerce_int)]


class SheetModel(BaseModel):
    """Base model: address by field name or header alias, keep unknown columns."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Lead(SheetModel):
    """Canonical row in the `IG Leads` tab."""

    lead_id: str = Field(default="", alias="leadId")
    username: str = Field(default="", alias="username")
    username_normalized: str = Field(default="", alias="usernameNormalized")
    full_name: str = Field(default="", alias="fullName")
    instagram_id: str = Field(default="", alias="instagramId")
    follower_count: IntField = Field(default=0, alias="followerCount")
    follows_count: IntField = Field(default=0, alias="followsCount")
    business_category_name: str = Field(default="", alias="businessCategoryName")
    bio: str = Field(default="", alias="bio")
    business_email: str = Field(default="", alias="businessEmail")
    business_phone_number: str = Field(default="", alias="businessPhoneNumber")
    profile_url: str = Field(default="", alias="profileUrl")
    external_url: str = Field(default="", alias="externalUrl")
    all_external_urls: str = Field(default="", alias="allExternalUrls")
    engagement_rate: str = Field(default="", alias="engagementRate")
    scraped_at: str = Field(default="", alias="scrapedAt")
    status: str = Field(default="new", alias="status")
    source: str = Field(default="", alias="source")
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")
    last_error: str = Field(default="", alias="lastError")


class DedupLead(SheetModel):
    """Row in the `Deduplicated Leads` tab."""

    lead_id: str = Field(default="", alias="leadId")
    username: str = Field(default="", alias="username")
    username_normalized: str = Field(default="", alias="usernameNormalized")
    status: str = Field(default="pending", alias="status")
    reason: str = Field(default="", alias="reason")
    source_lead_id: str = Field(default="", alias="sourceLeadId")
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")


class EnrichedLead(SheetModel):
    """Core row in the `instagram_leads_enriched` tab.

    Website evidence columns (`scrape1Url` ... `scrape5Links`) are intentionally
    not declared: they are carried as extra fields so their number can grow
    without a code change.
    """

    lead_id: str = Field(default="", alias="leadId")
    username: str = Field(default="", alias="username")
    username_normalized: str = Field(default="", alias="usernameNormalized")
    full_name: str = Field(default="", alias="fullName")
    instagram_id: str = Field(default="", alias="instagramId")
    follower_count: IntField = Field(default=0, alias="followerCount")
    follows_count: IntField = Field(default=0, alias="followsCount")
    business_category_name: str = Field(default="", alias="businessCategoryName")
    bio: str = Field(default="", alias="bio")
    business_email: str = Field(default="", alias="businessEmail")
    business_phone_number: str = Field(default="", alias="businessPhoneNumber")
    profile_url: str = Field(default="", alias="profileUrl")
    external_url: str = Field(default="", alias="externalUrl")
    all_external_urls: str = Field(default="", alias="allExternalUrls")
    engagement_rate: str = Field(default="", alias="engagementRate")
    profile_status: str = Field(default="", alias="profileStatus")
    website_status: str = Field(default="", alias="websiteStatus")
    profile_scraped_at: str = Field(default="", alias="profileScrapedAt")
    website_scraped_at: str = Field(default="", alias="websiteScrapedAt")
    last_error: str = Field(default="", alias="lastError")
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")


class OutreachEntry(SheetModel):
    """Row in the `Outreach` tab."""

    lead_id: str = Field(default="", alias="leadId")
    username: str = Field(default="", alias="username")
    username_normalized: str = Field(default="", alias="usernameNormalized")
    channel: str = Field(default="", alias="channel")
    status: str = Field(default="draft", alias="status")
    subject: str = Field(default="", alias="subject")
    body: str = Field(default="", alias="body")
    model: str = Field(default="", alias="model")
    generated_at: str = Field(default="", alias="generatedAt")
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")
    last_error: str = Field(default="", alias="lastError")


class PipelineJob(SheetModel):
    """Row in the `Pipeline Jobs` tab.

    A unit of work for the background worker. `jobId` is the stable key;
    `(stage, leadId)` is the logical idempotency key.
    """

    job_id: str = Field(default="", alias="jobId")
    stage: str = Field(default="", alias="stage")
    lead_id: str = Field(default="", alias="leadId")
    username: str = Field(default="", alias="username")
    username_normalized: str = Field(default="", alias="usernameNormalized")
    status: str = Field(default="queued", alias="status")
    attempt_count: IntField = Field(default=0, alias="attemptCount")
    max_attempts: IntField = Field(default=3, alias="maxAttempts")
    priority: IntField = Field(default=0, alias="priority")
    payload: str = Field(default="", alias="payload")
    result: str = Field(default="", alias="result")
    last_error: str = Field(default="", alias="lastError")
    locked_at: str = Field(default="", alias="lockedAt")
    locked_by: str = Field(default="", alias="lockedBy")
    run_after: str = Field(default="", alias="runAfter")
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")
