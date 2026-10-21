"""Small helpers for the database layer."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone


def new_lead_id(prefix: str = "ld") -> str:
    """Stable internal lead identifier (also the `leads.lead_id` primary key)."""
    return f"{prefix}_{uuid.uuid4().hex}"


def new_job_id(prefix: str = "job") -> str:
    """Stable pipeline-job identifier (also the `pipeline_jobs.job_id` PK)."""
    return f"{prefix}_{uuid.uuid4().hex}"


def contact_id(lead_id: str, type: str, value: str, source_url: str = "") -> str:
    """Deterministic contact id so repeated extraction upserts rather than duplicates."""
    raw = f"{lead_id}|{type}|{value.strip().lower()}|{source_url.strip()}"
    return f"ct_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:20]}"


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (second precision).

    Timestamps are stored as ISO strings (lexicographically sortable and
    timezone-aware) to preserve the previous behaviour exactly.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_now_iso_precise() -> str:
    """Current UTC time with microseconds (stable ordering for history rows)."""
    return datetime.now(timezone.utc).isoformat()


def stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def normalize_username(raw: str | None) -> str:
    """Normalize an Instagram username for duplicate checks (dedupe key)."""
    value = (raw or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if "instagram.com/" in lowered:
        value = value.split("instagram.com/", 1)[1]
    value = value.split("?", 1)[0].split("#", 1)[0]
    value = value.strip("/")
    value = value.split("/", 1)[0]
    value = value.lstrip("@")
    return value.strip().lower()
