"""Typed request/response schemas for the lead API."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.schemas import Lead

from .validation import InvalidLeadInput, parse_lead_input

# Status assigned to leads created via the API: picked up by the worker later.
LEAD_STATUS_QUEUED = "queued"

# Count precision labels for captured follower/following/post observations.
COUNT_PRECISIONS = ("exact", "approximate", "unknown")


class CountObservation(BaseModel):
    """A captured count with its original display text and precision.

    ``value`` is ``None`` when the value is unknown — never coerced to zero.
    """

    model_config = ConfigDict(extra="ignore")

    value: int | None = None
    display: str = Field(default="", max_length=40)
    precision: str = Field(default="unknown")


class ProfileSnapshot(BaseModel):
    """A public profile snapshot captured by the extension (PRD §11).

    Optional and lenient: malformed optional fields are sanitized to "missing"
    by the service rather than rejecting the whole capture.
    """

    model_config = ConfigDict(extra="ignore")

    display_name: str = Field(default="", max_length=255)
    is_verified: bool = False
    bio: str = Field(default="", max_length=4000)
    external_urls: list[str] = Field(default_factory=list, max_length=25)
    followers: CountObservation | None = None
    following: CountObservation | None = None
    post_count: CountObservation | None = None
    source_url: str = Field(default="", max_length=1024)
    captured_at: str = Field(default="", max_length=64)
    parser_version: str = Field(default="", max_length=32)
    missing_fields: list[str] = Field(default_factory=list, max_length=50)


class LeadCreateRequest(BaseModel):
    """Body for submitting a new lead.

    Backward compatible: handle-only clients send just ``username``/``source``.
    Capture clients may additionally send a ``request_id`` (stable, client
    generated) and a ``profile_snapshot``.
    """

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
    request_id: str = Field(
        default="",
        max_length=64,
        description="Stable client-generated id; repeated values return the original result.",
    )
    profile_snapshot: ProfileSnapshot | None = Field(
        default=None,
        description="Optional public profile snapshot captured in the browser.",
    )

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        try:
            parse_lead_input(value)
        except InvalidLeadInput as exc:
            raise ValueError(str(exc)) from exc
        return value.strip()


class ProfileSnapshotOut(BaseModel):
    """Read-only view of a captured snapshot for the dashboard (PRD T07).

    ``bio`` is omitted because the lead row already carries the canonical bio.
    V2-01 withdrew blanket pre-shortlist contact masking, so public contact
    details in the bio/page text are retained.
    """

    is_verified: bool = False
    external_urls: list[str] = Field(default_factory=list)
    followers: CountObservation | None = None
    following: CountObservation | None = None
    post_count: CountObservation | None = None
    source_url: str = ""
    captured_at: str = ""
    parser_version: str = ""
    missing_fields: list[str] = Field(default_factory=list)


def parse_snapshot_out(raw: str) -> ProfileSnapshotOut | None:
    """Parse the stored snapshot JSON; invalid/absent data yields ``None``."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return ProfileSnapshotOut.model_validate(data)
    except ValueError:
        return None


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
    progress: str = "needs_data"
    progress_remedy: str = ""
    snapshot: ProfileSnapshotOut | None = None
    fit_status: str = "not_reviewed"
    fit_note: str = ""
    fit_decided_at: str = ""
    decision_currency: str = "current"
    decision_currency_reason: str = ""
    new_evidence_available: bool = False
    evidence_version: int = 0
    evidence_version_id: str = ""
    research_status: str = "needs_data"
    # Contact types available for this creator (contact indicator). V2-08.
    contact_types: list[str] = []

    @classmethod
    def from_lead(
        cls,
        lead: Lead,
        *,
        progress: str = "needs_data",
        remedy: str = "",
        contact_types: list[str] | None = None,
    ) -> "LeadResponse":
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
            progress=progress,
            progress_remedy=remedy,
            snapshot=parse_snapshot_out(lead.profile_snapshot),
            fit_status=lead.fit_status or "not_reviewed",
            fit_note=lead.fit_note,
            fit_decided_at=lead.fit_decided_at,
            decision_currency=lead.decision_currency or "current",
            decision_currency_reason=lead.decision_currency_reason,
            new_evidence_available=lead.new_evidence_available,
            evidence_version=lead.evidence_version,
            evidence_version_id=lead.evidence_version_id,
            research_status=progress,
            contact_types=list(contact_types or []),
        )


class LeadSubmissionResponse(BaseModel):
    """Result of a lead submission.

    ``created`` is True for a new lead (HTTP 201) and False when an existing lead
    was returned (HTTP 200). ``outcome`` distinguishes an unchanged repeat from a
    snapshot that filled missing fields.
    """

    created: bool
    lead: LeadResponse
    outcome: str = "new"
    missing_fields: list[str] = []
    research_queued: bool = False


class LeadListResponse(BaseModel):
    """A page of leads."""

    items: list[LeadResponse]
    total: int
    limit: int
    offset: int
    # Saved view the page was rendered for, and the per-view counters
    # (labelled, not an additive funnel). V2-08.
    view: str = "to_review"
    view_counts: dict[str, int] = {}


class FitDecisionRequest(BaseModel):
    """Manual fit decision (T08). A rejection requires a note."""

    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "shortlist",
        "research_more",
        "reject",
        "reopen",
        # pre-v2 aliases
        "approve",
        "need_evidence",
    ]
    note: str = Field(default="", max_length=2000)


class ContactRequestCreate(BaseModel):
    """Optional note for an explicit contact request."""

    model_config = ConfigDict(extra="forbid")

    note: str = Field(default="", max_length=2000)
    # Explicit "Search again" creates a new attempt for the same evidence version.
    search_again: bool = False


class ManualContactCreate(BaseModel):
    """Operator-entered public contact with a source URL (V2-06)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["email", "phone"]
    value: str = Field(..., min_length=1, max_length=512)
    source_url: str = Field(..., min_length=1, max_length=1024)

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, value: str) -> str:
        text = value.strip()
        if not text.lower().startswith(("http://", "https://")):
            raise ValueError("Source URL must be an http(s) URL.")
        return text


class DraftRequestCreate(BaseModel):
    """Explicit draft request with a channel (T08)."""

    model_config = ConfigDict(extra="forbid")

    channel: Literal["email", "instagram_dm"]


class ContactRequestOut(BaseModel):
    request_id: str
    lead_id: str
    status: str
    note: str
    evidence_version: int = 0
    searched_scope: str = ""
    result_count: int = 0
    error: str = ""
    requested_at: str
    started_at: str = ""
    completed_at: str = ""
    created_at: str

    @classmethod
    def from_model(cls, request) -> "ContactRequestOut":
        return cls(
            request_id=request.request_id,
            lead_id=request.lead_id,
            status=request.status,
            note=request.note,
            evidence_version=request.evidence_version,
            searched_scope=request.searched_scope,
            result_count=request.result_count,
            error=request.error,
            requested_at=request.requested_at,
            started_at=request.started_at,
            completed_at=request.completed_at,
            created_at=request.created_at,
        )


class ContactRequestListOut(BaseModel):
    items: list[ContactRequestOut]
    total: int


class OutreachRevisionOut(BaseModel):
    revision_id: str
    lead_id: str
    channel: str
    status: str
    subject: str
    body: str
    dm_body: str
    requested_at: str
    created_at: str

    @classmethod
    def from_model(cls, revision) -> "OutreachRevisionOut":
        return cls(
            revision_id=revision.revision_id,
            lead_id=revision.lead_id,
            channel=revision.channel,
            status=revision.status,
            subject=revision.subject,
            body=revision.body,
            dm_body=revision.dm_body,
            requested_at=revision.requested_at,
            created_at=revision.created_at,
        )


class OutreachRevisionListOut(BaseModel):
    items: list[OutreachRevisionOut]
    total: int


# -- V2-07: draft versions and manual outreach events ----------------------


class DraftRevisionOut(BaseModel):
    """A saved draft content version."""

    revision_id: str
    lead_id: str
    username: str = ""
    channel: str = ""
    subject: str = ""
    body: str = ""
    dm_body: str = ""
    status: str = "needs_review"
    method: str = "manual"
    model: str = ""
    parent_revision_id: str = ""
    contact_id: str = ""
    request_id: str = ""
    evidence_scope: str = ""
    note: str = ""
    edited_at: str = ""
    created_at: str = ""

    @classmethod
    def from_model(cls, revision) -> "DraftRevisionOut":
        return cls(
            revision_id=revision.revision_id,
            lead_id=revision.lead_id,
            username=revision.username,
            channel=revision.channel,
            subject=revision.subject,
            body=revision.body,
            dm_body=revision.dm_body,
            status=revision.status,
            method=revision.method,
            model=revision.model,
            parent_revision_id=revision.parent_revision_id,
            contact_id=revision.contact_id,
            request_id=revision.request_id,
            evidence_scope=revision.evidence_scope,
            note=revision.note,
            edited_at=revision.edited_at,
            created_at=revision.created_at,
        )


class DraftRevisionListOut(BaseModel):
    items: list[DraftRevisionOut]
    total: int


class DraftSaveRequest(BaseModel):
    """Save (or edit) a draft as a new version. Never needs an AI key."""

    model_config = ConfigDict(extra="forbid")

    subject: str = ""
    body: str = ""
    dm_body: str = ""
    channel: str = ""
    note: str = ""
    contact_id: str = ""
    parent_revision_id: str = ""


class DraftGenerateRequest(BaseModel):
    """An explicit AI generation request (requires enabled AI)."""

    model_config = ConfigDict(extra="forbid")

    channel: Literal["email", "instagram_dm"] = "email"
    contact_id: str = ""
    parent_revision_id: str = ""


class DraftTextOut(BaseModel):
    """The plain text of a draft version (copy/export never marks it sent)."""

    revision_id: str
    text: str


class OutreachEventOut(BaseModel):
    """A manually logged outreach event."""

    event_id: str
    lead_id: str
    outcome: str
    channel: str
    revision_id: str = ""
    note: str = ""
    source: str = "manually_logged"
    corrects_event_id: str = ""
    actor: str = ""
    sent_at: str = ""
    logged_at: str = ""
    created_at: str = ""

    @classmethod
    def from_model(cls, event) -> "OutreachEventOut":
        return cls(
            event_id=event.event_id,
            lead_id=event.lead_id,
            outcome=event.outcome,
            channel=event.channel,
            revision_id=event.revision_id,
            note=event.note,
            source=event.source,
            corrects_event_id=event.corrects_event_id,
            actor=event.actor,
            sent_at=event.sent_at,
            logged_at=event.logged_at,
            created_at=event.created_at,
        )


class OutreachEventListOut(BaseModel):
    items: list[OutreachEventOut]
    total: int
    latest_outcome: str = ""


class OutreachEventCreate(BaseModel):
    """Log an outreach event manually (V24)."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["sent", "replied", "interested", "not_interested", "follow_up"]
    channel: Literal["email", "instagram_dm"]
    # Pre-populated with the current time, but always correctable.
    sent_at: str = ""
    revision_id: str = ""
    note: str = ""
    # Correcting an earlier log creates a new visible event (V25).
    corrects_event_id: str = ""



class FitDecisionOut(BaseModel):
    decision_id: str
    lead_id: str
    action: str
    fit_status: str
    decision_currency: str
    evidence_version: int
    criteria_version: int
    note: str
    actor: str
    created_at: str

    @classmethod
    def from_model(cls, decision) -> "FitDecisionOut":
        return cls(
            decision_id=decision.decision_id,
            lead_id=decision.lead_id,
            action=decision.action,
            fit_status=decision.fit_status,
            decision_currency=decision.decision_currency,
            evidence_version=decision.evidence_version,
            criteria_version=decision.criteria_version,
            note=decision.note,
            actor=decision.actor,
            created_at=decision.created_at,
        )


class FitDecisionListOut(BaseModel):
    items: list[FitDecisionOut]
    total: int
