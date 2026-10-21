"""Shared constants: pipeline stage names and job/lead statuses.

Kept neutral (no imports) so API, storage and worker can all depend on it.
"""

from __future__ import annotations

# Pipeline stages
STAGE_PROFILE_FETCH = "profile_fetch"
STAGE_PROFILE_MEDIA = "profile_media"
STAGE_WEBSITE_ENRICH = "website_enrich"
STAGE_AI_DOSSIER = "ai_dossier"
STAGE_AI_OUTREACH = "ai_outreach"
# Explicit, contact-focused discovery pass (V2-06).
STAGE_CONTACT_DISCOVERY = "contact_discovery"

# Job statuses (`Pipeline Jobs` tab)
JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_RETRY = "retry"
JOB_DONE = "done"
JOB_ERROR = "error"

JOB_ACTIVE_STATUSES = (JOB_QUEUED, JOB_RETRY)

# Lead statuses (`IG Leads` tab)
LEAD_STATUS_QUEUED = "queued"
LEAD_STATUS_ENRICHED = "enriched"
LEAD_STATUS_NOT_FOUND = "not_found"
LEAD_STATUS_ERROR = "error"
# Handle-only capture with no supported research source (V2-02).
LEAD_STATUS_NEEDS_DATA = "needs_data"

# Optional-stage statuses (lead `mediaStatus` / `websiteStatus`)
STAGE_STATUS_DONE = "done"
STAGE_STATUS_PARTIAL = "partial"
STAGE_STATUS_NONE = "none"          # genuinely no data (no posts / no website)
STAGE_STATUS_BLOCKED = "blocked"    # URL rejected by SSRF/allow-list rules
STAGE_STATUS_ERROR = "error"

# AI output statuses (`Dossiers` / `Outreach`)
AI_STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
AI_STATUS_INSUFFICIENT = "insufficient_evidence"
AI_STATUS_ERROR = "error"

# Derived research/progress states (PRD §10; V2-03 uses "complete").
# These are computed from persisted jobs + the lead, and returned consistently by
# list, detail and stats.
RESEARCH_NEEDS_DATA = "needs_data"
RESEARCH_QUEUED = "queued"
RESEARCH_RUNNING = "running"
RESEARCH_COMPLETE = "complete"
RESEARCH_READY = RESEARCH_COMPLETE  # deprecated alias (pre-v2 name)
RESEARCH_BLOCKED = "blocked"

# Research stages (profile + media + website + dossier). Outreach belongs to the
# separate "draft" dimension and does not influence research progress.
RESEARCH_STAGES = (
    STAGE_PROFILE_FETCH,
    STAGE_PROFILE_MEDIA,
    STAGE_WEBSITE_ENRICH,
    STAGE_AI_DOSSIER,
)
# A terminal failure in a required stage blocks research. Failures in optional
# stages (media, website) can still yield "ready" with an explicit limitation.
REQUIRED_RESEARCH_STAGES = (STAGE_PROFILE_FETCH, STAGE_AI_DOSSIER)

# Outreach review statuses that must never be silently overwritten by a rerun.
DRAFT_REVIEW_STATUSES = (AI_STATUS_NEEDS_REVIEW, "APPROVED", "REJECTED")

# Stable error code returned when an AI action is requested but AI is unavailable.
ERROR_AI_UNAVAILABLE = "AI_UNAVAILABLE"

# Fit-decision dimension (V2-03). Separate from research progress and drafts.
FIT_STATUS_NOT_REVIEWED = "not_reviewed"
FIT_STATUS_RESEARCH_MORE = "research_more"
FIT_STATUS_SHORTLISTED = "shortlisted"
FIT_STATUS_REJECTED = "rejected"
FIT_STATUSES = (
    FIT_STATUS_NOT_REVIEWED,
    FIT_STATUS_RESEARCH_MORE,
    FIT_STATUS_SHORTLISTED,
    FIT_STATUS_REJECTED,
)
# Backward-compatible aliases (pre-v2 names); storage always uses the v2 values.
FIT_STATUS_APPROVED = FIT_STATUS_SHORTLISTED
FIT_STATUS_NEEDS_EVIDENCE = FIT_STATUS_RESEARCH_MORE

# Action -> stored fit status. Reject requires a note; reopen returns a rejected
# creator to not_reviewed (never directly to shortlisted).
FIT_ACTIONS = {
    "shortlist": FIT_STATUS_SHORTLISTED,
    "research_more": FIT_STATUS_RESEARCH_MORE,
    "reject": FIT_STATUS_REJECTED,
    "reopen": FIT_STATUS_NOT_REVIEWED,
}
# Accept the pre-v2 action names from older callers / UI.
FIT_ACTION_ALIASES = {
    "approve": "shortlist",
    "need_evidence": "research_more",
}

# Decision currency: whether a shortlist still matches material evidence.
DECISION_CURRENCY_CURRENT = "current"
DECISION_CURRENCY_REVIEW_NEEDED = "review_needed"
DECISION_CURRENCIES = (DECISION_CURRENCY_CURRENT, DECISION_CURRENCY_REVIEW_NEEDED)

# Shared dashboard authentication does not identify a named employee.
FIT_ACTOR_OPERATOR = "shared dashboard operator"
FIT_ACTOR_SYSTEM = "system"

# Draft channels accepted by explicit draft requests.
DRAFT_CHANNELS = ("email", "instagram_dm")

# A worker heartbeat older than this is reported as stale (PRD T09).
WORKER_STALE_SECONDS = 60
WORKER_HEARTBEAT_ID = "worker"

# Explicit contact discovery request states (V2-06).
CONTACT_REQUEST_QUEUED = "queued"
CONTACT_REQUEST_RUNNING = "running"
CONTACT_REQUEST_FOUND = "found"
CONTACT_REQUEST_NOT_FOUND = "not_found"
CONTACT_REQUEST_FAILED = "failed"
CONTACT_REQUEST_CANCELLED = "cancelled"
CONTACT_REQUEST_STATUSES = (
    CONTACT_REQUEST_QUEUED,
    CONTACT_REQUEST_RUNNING,
    CONTACT_REQUEST_FOUND,
    CONTACT_REQUEST_NOT_FOUND,
    CONTACT_REQUEST_FAILED,
    CONTACT_REQUEST_CANCELLED,
)
CONTACT_REQUEST_ACTIVE = (CONTACT_REQUEST_QUEUED, CONTACT_REQUEST_RUNNING)
# Terminal states which a repeated click reuses for the same evidence version.
CONTACT_REQUEST_REUSABLE = (
    CONTACT_REQUEST_QUEUED,
    CONTACT_REQUEST_RUNNING,
    CONTACT_REQUEST_FOUND,
    CONTACT_REQUEST_NOT_FOUND,
    CONTACT_REQUEST_FAILED,
)

# Contact extraction methods.
CONTACT_METHOD_WEBSITE = "website_crawl"
CONTACT_METHOD_DISCOVERY = "contact_discovery"
CONTACT_METHOD_MANUAL = "manual"
CONTACT_METHOD_LEGACY = "legacy"
