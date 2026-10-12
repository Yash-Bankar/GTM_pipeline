"""Shared constants: pipeline stage names and job/lead statuses.

Kept neutral (no imports) so API, storage and worker can all depend on it.
"""

from __future__ import annotations

# Pipeline stages
STAGE_PROFILE_FETCH = "profile_fetch"

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
