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
