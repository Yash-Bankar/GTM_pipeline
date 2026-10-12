"""Small helpers for the Google Sheets storage layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def new_lead_id(prefix: str = "ld") -> str:
    """Return a new, stable internal lead identifier.

    The id is opaque and generated once per lead. It is the value stored in the
    `leadId` column and used as the internal key across every tab.
    """
    return f"{prefix}_{uuid.uuid4().hex}"


def new_job_id(prefix: str = "job") -> str:
    """Return a new, stable pipeline-job identifier (`jobId`)."""
    return f"{prefix}_{uuid.uuid4().hex}"


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (second precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stringify(value: object) -> str:
    """Coerce a cell value to the string form written to Google Sheets."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
