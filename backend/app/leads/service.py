"""Lead application service (database-backed)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from app import constants
from app.db.repository import Repository
from app.db.schemas import Lead

from .schemas import (
    COUNT_PRECISIONS,
    LEAD_STATUS_QUEUED,
    CountObservation,
    LeadCreateRequest,
    ProfileSnapshot,
)
from .validation import parse_lead_input

logger = logging.getLogger(__name__)

_SEARCHABLE_FIELDS = (
    "username",
    "username_normalized",
    "full_name",
    "bio",
    "business_email",
)

# Intake bounds (PRD §11): bio length and external URL count are bounded.
_SNAPSHOT_BIO_MAX = 2200
_SNAPSHOT_MAX_URLS = 10
_IGNORED_HOSTS = ("instagram.com", "threads.net", "facebook.com", "fb.com", "meta.com")
_TRACKING_KEYS = {"igshid", "igsh", "fbclid", "gclid", "si"}


@dataclass(frozen=True)
class LeadSubmission:
    created: bool
    lead: Lead
    progress: str = "needs_data"
    remedy: str = ""
    outcome: str = "new"
    missing_fields: list[str] = field(default_factory=list)


class LeadService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def submit(self, request: LeadCreateRequest) -> LeadSubmission:
        """Create a lead or return the existing one (deduplicated), then enqueue it.

        Backward compatible with handle-only clients. When a ``profile_snapshot``
        is supplied it is sanitized, persisted, and used to fill only *missing*
        lead fields (known values are never erased). A repeated ``request_id``
        returns the original lead without re-enqueuing work.
        """
        parsed = parse_lead_input(request.username)

        if request.request_id:
            existing = self._repo.find_lead_by_request_id(request.request_id)
            if existing is not None:
                progress, remedy = self._repo.lead_progress(existing.lead_id)
                return LeadSubmission(
                    created=False,
                    lead=existing,
                    progress=progress,
                    remedy=remedy,
                    outcome="unchanged",
                )

        created, lead = self._repo.create_or_get_lead(
            parsed.username,
            source=request.source or "api",
            status=LEAD_STATUS_QUEUED,
            profile_url=parsed.profile_url,
        )

        outcome = "new" if created else "unchanged"
        missing: list[str] = []

        if request.profile_snapshot is not None:
            snapshot = _sanitize_snapshot(request.profile_snapshot)
            missing = snapshot["missing_fields"]
            before = _evidence_signature(lead)
            fields = _fields_to_fill(lead, snapshot)
            fields["profile_snapshot"] = json.dumps(snapshot, ensure_ascii=False)
            if request.request_id:
                fields["request_id"] = request.request_id
            updated = self._repo.update_lead(lead.lead_id, fields)
            if updated is not None:
                lead = updated
            if not created and _evidence_signature(lead) != before:
                outcome = "updated"
        elif request.request_id:
            updated = self._repo.update_lead(lead.lead_id, {"request_id": request.request_id})
            if updated is not None:
                lead = updated

        if created:
            self._repo.enqueue(
                constants.STAGE_PROFILE_FETCH,
                lead.lead_id,
                lead.username,
                lead.username_normalized,
                max_attempts=3,
            )

        progress, remedy = self._repo.lead_progress(lead.lead_id)
        logger.info(
            "Lead submission @%s -> %s (leadId=%s, progress=%s, outcome=%s)",
            parsed.normalized,
            "created" if created else "existing",
            lead.lead_id,
            progress,
            outcome,
        )
        return LeadSubmission(
            created=created,
            lead=lead,
            progress=progress,
            remedy=remedy,
            outcome=outcome,
            missing_fields=missing,
        )

    def get(self, lead_id: str) -> tuple[Lead, str, str] | None:
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None
        progress, remedy = self._repo.lead_progress(lead_id)
        return (lead, progress, remedy)

    def list(
        self,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
    ) -> tuple[list[tuple[Lead, str, str]], int]:
        """Return a filtered, newest-first page of ``(lead, progress, remedy)``.

        The ``status`` filter matches the **derived progress**, so filters, row
        badges and counters use the same server-defined logic (PRD T01).
        """
        rows = self._repo.list_leads_with_progress()

        if status:
            wanted = status.strip().lower()
            rows = [row for row in rows if row[1].lower() == wanted]

        if search and search.strip():
            needle = search.strip().casefold()
            rows = [row for row in rows if needle in _search_blob(row[0]).casefold()]

        rows.sort(key=lambda row: (row[0].created_at, row[0].lead_id), reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total


def _search_blob(lead: Lead) -> str:
    return " \n".join(str(getattr(lead, field, "")) for field in _SEARCHABLE_FIELDS)


def _clean_external_url(url: str) -> str:
    """Validate an http(s) URL, unwrap l.instagram.com redirects, drop trackers."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""

    host = parsed.netloc.lower().removeprefix("www.")
    if host == "l.instagram.com":
        target = dict(parse_qsl(parsed.query)).get("u")
        return _clean_external_url(unquote(target)) if target else ""

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    if any(host == ignored or host.endswith(f".{ignored}") for ignored in _IGNORED_HOSTS):
        return ""

    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_KEYS and not key.lower().startswith("utm_")
    ]
    return urlunparse(parsed._replace(query=urlencode(kept), fragment=""))


def _sanitize_count(observation: CountObservation | None) -> dict[str, object] | None:
    if observation is None:
        return None
    precision = (observation.precision or "").strip().lower()
    if precision not in COUNT_PRECISIONS:
        precision = "unknown"
    value = observation.value
    if precision == "unknown" or value is None or value < 0:
        value = None
        precision = "unknown"
    return {
        "value": value,
        "display": (observation.display or "").strip()[:40],
        "precision": precision,
    }


def _sanitize_snapshot(snapshot: ProfileSnapshot) -> dict[str, object]:
    """Bound and clean a captured snapshot; compute the effective missing fields."""
    urls: list[str] = []
    seen: set[str] = set()
    for candidate in snapshot.external_urls:
        cleaned = _clean_external_url(candidate)
        key = cleaned.rstrip("/")
        if cleaned and key not in seen:
            seen.add(key)
            urls.append(cleaned)
        if len(urls) >= _SNAPSHOT_MAX_URLS:
            break

    sanitized: dict[str, object] = {
        "display_name": (snapshot.display_name or "").strip()[:255],
        "is_verified": bool(snapshot.is_verified),
        "bio": (snapshot.bio or "").strip()[:_SNAPSHOT_BIO_MAX],
        "external_urls": urls,
        "followers": _sanitize_count(snapshot.followers),
        "following": _sanitize_count(snapshot.following),
        "post_count": _sanitize_count(snapshot.post_count),
        "source_url": (snapshot.source_url or "").strip()[:1024],
        "captured_at": (snapshot.captured_at or "").strip()[:64],
        "parser_version": (snapshot.parser_version or "").strip()[:32],
    }
    sanitized["missing_fields"] = _effective_missing(snapshot, sanitized)
    return sanitized


def _effective_missing(
    snapshot: ProfileSnapshot, sanitized: dict[str, object]
) -> list[str]:
    missing = {name for name in snapshot.missing_fields if name}
    if not sanitized["display_name"]:
        missing.add("display_name")
    if not sanitized["bio"]:
        missing.add("bio")
    if not sanitized["external_urls"]:
        missing.add("external_urls")
    for key in ("followers", "following", "post_count"):
        observation = sanitized[key]
        if not observation or observation["value"] is None:  # type: ignore[index]
            missing.add(key)
    return sorted(missing)


def _fields_to_fill(lead: Lead, snapshot: dict[str, object]) -> dict[str, object]:
    """Fill only fields the lead does not already have (never erase known values)."""
    fields: dict[str, object] = {}
    if not lead.full_name and snapshot["display_name"]:
        fields["full_name"] = snapshot["display_name"]
    if not lead.bio and snapshot["bio"]:
        fields["bio"] = snapshot["bio"]

    urls = snapshot["external_urls"]
    if isinstance(urls, list) and urls:
        if not lead.external_url:
            fields["external_url"] = urls[0]
        if not lead.all_external_urls:
            fields["all_external_urls"] = ",".join(str(url) for url in urls)

    if lead.follower_count == 0:
        value = _count_value(snapshot.get("followers"))
        if value is not None:
            fields["follower_count"] = value
    if lead.follows_count == 0:
        value = _count_value(snapshot.get("following"))
        if value is not None:
            fields["follows_count"] = value

    if not lead.profile_url and snapshot["source_url"]:
        fields["profile_url"] = snapshot["source_url"]
    if snapshot["captured_at"]:
        fields["scraped_at"] = snapshot["captured_at"]
    return fields


def _count_value(observation: object) -> int | None:
    if isinstance(observation, dict):
        value = observation.get("value")
        if isinstance(value, int) and value >= 0:
            return value
    return None


def _evidence_signature(lead: Lead) -> tuple[object, ...]:
    return (
        lead.full_name,
        lead.bio,
        lead.external_url,
        lead.all_external_urls,
        lead.follower_count,
        lead.follows_count,
    )
