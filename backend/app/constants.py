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

# Derived research/progress states (PRD §10). These are computed from persisted
# jobs + the lead, and returned consistently by list, detail and stats.
RESEARCH_NEEDS_DATA = "needs_data"
RESEARCH_QUEUED = "queued"
RESEARCH_RUNNING = "running"
RESEARCH_READY = "ready"
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
