"""Typed request/response schemas for the lead API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.schemas import Lead

from .validation import InvalidLeadInput, parse_lead_input

# Status assigned to leads created via the API: picked up by the worker later.
LEAD_STATUS_QUEUED = "queued"


class LeadCreateRequest(BaseModel):
    """Body for submitting a new lead."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Instagram username (with or without @) or profile URL.",
        examples=["@some.creator", "https://www.instagram.com/some.creator/"],
    )
    source: str = Field(
        default="api",
        max_length=100,
        description="Where the lead came from (api, chrome-extension, import, ...).",
    )

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        try:
            parse_lead_input(value)
        except InvalidLeadInput as exc:
            raise ValueError(str(exc)) from exc
        return value.strip()


class LeadResponse(BaseModel):
    """A stored lead."""

    lead_id: str
    username: str
    username_normalized: str
    full_name: str
    instagram_id: str
    follower_count: int
    follows_count: int
    business_category_name: str
    bio: str
    business_email: str
    business_phone_number: str
    profile_url: str
    external_url: str
    all_external_urls: str
    engagement_rate: str
    scraped_at: str
    status: str
    source: str
    created_at: str
    updated_at: str
    last_error: str
    media_status: str
    website_status: str

    @classmethod
    def from_lead(cls, lead: Lead) -> "LeadResponse":
        return cls(
            lead_id=lead.lead_id,
            username=lead.username,
            username_normalized=lead.username_normalized,
            full_name=lead.full_name,
            instagram_id=lead.instagram_id,
            follower_count=lead.follower_count,
            follows_count=lead.follows_count,
            business_category_name=lead.business_category_name,
            bio=lead.bio,
            business_email=lead.business_email,
            business_phone_number=lead.business_phone_number,
            profile_url=lead.profile_url,
            external_url=lead.external_url,
            all_external_urls=lead.all_external_urls,
            engagement_rate=lead.engagement_rate,
            scraped_at=lead.scraped_at,
            status=lead.status,
            source=lead.source,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            last_error=lead.last_error,
            media_status=lead.media_status,
            website_status=lead.website_status,
        )


class LeadSubmissionResponse(BaseModel):
    """Result of a lead submission.

    ``created`` is True for a new lead (HTTP 201) and False when an existing lead
    was returned (HTTP 200).
    """

    created: bool
    lead: LeadResponse


class LeadListResponse(BaseModel):
    """A page of leads."""

    items: list[LeadResponse]
    total: int
    limit: int
    offset: int
