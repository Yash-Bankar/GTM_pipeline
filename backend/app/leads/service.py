"""Lead application service (database-backed)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from app import constants
from app.config import get_settings
from app.db.repository import Repository
from app.db.schemas import (
    CaptureReceipt,
    Contact,
    ContactRequest,
    EvidenceVersion,
    FitDecision,
    Lead,
    OutreachRevision,
)
from app.db.util import contact_id, new_job_id, utc_now_iso, utc_now_iso_precise

from .evidence import (
    changed_snapshot_fields,
    field_provenance,
    material_change_reasons,
    merge_snapshot,
    payload_hash,
    recency,
)
from .schemas import (
    COUNT_PRECISIONS,
    LEAD_STATUS_QUEUED,
    CountObservation,
    LeadCreateRequest,
    ProfileSnapshot,
)
from .validation import parse_lead_input
from .views import (
    DEFAULT_VIEW,
    SAVED_VIEWS,
    VIEW_LABELS,
    matches_view,
    normalize_view,
    sort_rows,
    view_counts,
)

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
    research_queued: bool = False


class FitNotApprovedError(Exception):
    """Raised when a contact/draft request is not allowed by the fit gate (T08/V2-03)."""

    def __init__(
        self, fit_status: str, decision_currency: str = "current"
    ) -> None:
        super().__init__(fit_status)
        self.fit_status = fit_status
        self.decision_currency = decision_currency


class RequestIdConflictError(Exception):
    """Raised when a request id is reused with a different payload (V2-02)."""

    def __init__(self, request_id: str) -> None:
        super().__init__(request_id)
        self.request_id = request_id


class LeadService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def submit(self, request: LeadCreateRequest) -> LeadSubmission:
        """Capture a lead with receipts, evidence versions, and a safe merge (V2-02).

        - A request id is unique: replaying the same payload returns the original
          lead without work; reusing it with a different payload raises a conflict.
        - A snapshot becomes an immutable evidence version. Newer evidence may
          update known fields; stale evidence only fills gaps and never erases.
        - Handle-only intake becomes ``needs_data`` unless a research source is
          configured (snapshot or HikerAPI).
        """
        parsed = parse_lead_input(request.username)
        source = request.source or "api"
        sanitized = (
            _sanitize_snapshot(request.profile_snapshot)
            if request.profile_snapshot is not None
            else None
        )
        digest = payload_hash(parsed.normalized, source, sanitized)

        if request.request_id:
            receipt = self._repo.find_capture_receipt(request.request_id)
            if receipt is not None:
                if receipt.payload_hash and receipt.payload_hash != digest:
                    raise RequestIdConflictError(request.request_id)
                existing = self._repo.get_lead(receipt.lead_id)
                if existing is not None:
                    progress, remedy = self._repo.lead_progress(existing.lead_id)
                    return LeadSubmission(
                        created=False,
                        lead=existing,
                        progress=progress,
                        remedy=remedy,
                        outcome="unchanged",
                        missing_fields=_snapshot_missing(existing),
                    )
            else:
                # Leads captured before V2-02 have a request id but no receipt.
                legacy = self._repo.find_lead_by_request_id(request.request_id)
                if legacy is not None:
                    progress, remedy = self._repo.lead_progress(legacy.lead_id)
                    return LeadSubmission(
                        created=False,
                        lead=legacy,
                        progress=progress,
                        remedy=remedy,
                        outcome="unchanged",
                        missing_fields=_snapshot_missing(legacy),
                    )

        hiker_configured = bool(get_settings().hikerapi_key.strip())
        can_research = sanitized is not None or hiker_configured
        initial_status = (
            LEAD_STATUS_QUEUED if can_research else constants.LEAD_STATUS_NEEDS_DATA
        )
        created, lead = self._repo.create_or_get_lead(
            parsed.username,
            source=source,
            status=initial_status,
            profile_url=parsed.profile_url,
        )

        received_at = utc_now_iso()
        applied = False
        changed: list[str] = []
        missing: list[str] = []

        if sanitized is not None:
            latest = self._repo.latest_evidence_version(lead.lead_id)
            current_snapshot = _snapshot_dict(lead.profile_snapshot)
            encoded = _canonical_json(json.dumps(sanitized, ensure_ascii=False))
            identical = latest is not None and _canonical_json(
                latest.snapshot_json
            ) == encoded

            if identical:
                # Identical evidence creates no duplicate version or work.
                missing = sanitized.get("missing_fields", [])
                outcome = "new" if created else "unchanged"
            else:
                if latest is None:
                    incoming_newer = True
                else:
                    incoming_newer = recency(sanitized, received_at) >= recency(
                        current_snapshot, latest.received_at
                    )
                merged = merge_snapshot(
                    current_snapshot, sanitized, incoming_newer=incoming_newer
                )
                changed = changed_snapshot_fields(current_snapshot, merged)
                missing = (
                    merged.get("missing_fields", [])
                    if incoming_newer
                    else _snapshot_missing(lead)
                )

                version_number = self._repo.next_evidence_version_number(lead.lead_id)
                version = EvidenceVersion(
                    evidence_version_id=new_job_id("ev"),
                    lead_id=lead.lead_id,
                    version=version_number,
                    request_id=request.request_id,
                    snapshot_json=encoded,
                    captured_at=str(sanitized.get("captured_at") or ""),
                    received_at=received_at,
                    parser_version=str(sanitized.get("parser_version") or ""),
                    field_provenance=json.dumps(
                        field_provenance(sanitized), sort_keys=True
                    ),
                    changed_fields=json.dumps(changed),
                )
                self._repo.create_evidence_version(version)

                if incoming_newer:
                    fields = _snapshot_lead_fields(merged)
                    fields["profile_snapshot"] = json.dumps(merged, ensure_ascii=False)
                    if request.request_id:
                        fields["request_id"] = request.request_id
                    fields["evidence_version"] = version_number
                    fields["evidence_version_id"] = version.evidence_version_id

                    campaign = self._repo.get_active_campaign()
                    prior_status = lead.fit_status or constants.FIT_STATUS_NOT_REVIEWED
                    material: list[str] = []
                    if prior_status == constants.FIT_STATUS_SHORTLISTED and changed:
                        material = material_change_reasons(
                            current_snapshot,
                            merged,
                            follower_min=campaign.follower_min if campaign else 0,
                            follower_max=campaign.follower_max if campaign else 0,
                        )
                        if material:
                            fields["decision_currency"] = (
                                constants.DECISION_CURRENCY_REVIEW_NEEDED
                            )
                            fields["decision_currency_reason"] = "; ".join(material)
                    if prior_status == constants.FIT_STATUS_REJECTED and changed:
                        fields["new_evidence_available"] = True

                    lead = self._repo.update_lead(lead.lead_id, fields) or lead
                    applied = bool(changed)

                    if prior_status == constants.FIT_STATUS_SHORTLISTED and material:
                        self._record_decision(
                            lead.lead_id,
                            action="review_needed",
                            fit_status=constants.FIT_STATUS_SHORTLISTED,
                            decision_currency=constants.DECISION_CURRENCY_REVIEW_NEEDED,
                            evidence_version=version_number,
                            criteria_version=campaign.version if campaign else 0,
                            note="; ".join(material),
                            actor=constants.FIT_ACTOR_SYSTEM,
                        )
                    elif prior_status == constants.FIT_STATUS_REJECTED and changed:
                        self._record_decision(
                            lead.lead_id,
                            action="new_evidence",
                            fit_status=constants.FIT_STATUS_REJECTED,
                            decision_currency=lead.decision_currency
                            or constants.DECISION_CURRENCY_CURRENT,
                            evidence_version=version_number,
                            criteria_version=campaign.version if campaign else 0,
                            note="New evidence available",
                            actor=constants.FIT_ACTOR_SYSTEM,
                        )
                # Stale evidence is retained as immutable history but does not
                # mutate the lead or advance the current evidence pointer.
                outcome = (
                    "new"
                    if created
                    else ("updated" if incoming_newer and applied and changed else "unchanged")
                )
        else:
            outcome = "new" if created else "unchanged"
            if request.request_id:
                lead = (
                    self._repo.update_lead(
                        lead.lead_id, {"request_id": request.request_id}
                    )
                    or lead
                )

        research_queued = False
        if created:
            if can_research:
                self._repo.enqueue(
                    constants.STAGE_PROFILE_FETCH,
                    lead.lead_id,
                    lead.username,
                    lead.username_normalized,
                    max_attempts=3,
                )
                research_queued = True
        elif applied and changed and can_research:
            # A useful recapture restarts research for the new evidence version.
            self._repo.enqueue(
                constants.STAGE_PROFILE_FETCH,
                lead.lead_id,
                lead.username,
                lead.username_normalized,
                max_attempts=3,
                on_duplicate="reenqueue",
            )
            research_queued = True

        if request.request_id:
            self._repo.create_capture_receipt(
                CaptureReceipt(
                    request_id=request.request_id,
                    lead_id=lead.lead_id,
                    payload_hash=digest,
                    outcome=outcome,
                    received_at=received_at,
                )
            )

        progress, remedy = self._repo.lead_progress(lead.lead_id)
        logger.info(
            "Lead submission @%s -> %s (leadId=%s, progress=%s, outcome=%s, research=%s)",
            parsed.normalized,
            "created" if created else "existing",
            lead.lead_id,
            progress,
            outcome,
            research_queued,
        )
        return LeadSubmission(
            created=created,
            lead=lead,
            progress=progress,
            remedy=remedy,
            outcome=outcome,
            missing_fields=missing,
            research_queued=research_queued,
        )

    def get(self, lead_id: str) -> tuple[Lead, str, str] | None:
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None
        progress, remedy = self._repo.lead_progress(lead_id)
        return (lead, progress, remedy)

    def decide_fit(self, lead_id: str, *, action: str, note: str = "") -> Lead | None:
        """Record a manual fit decision with history (V2-03).

        Actions: ``shortlist``, ``research_more``, ``reject``, ``reopen``.
        Pre-v2 names ``approve``/``need_evidence`` are accepted as aliases.
        A rejection requires a note; a rejected creator must be reopened before
        any other decision, and reopen always returns to ``not_reviewed``.
        """
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None

        action = constants.FIT_ACTION_ALIASES.get(action, action)
        status = constants.FIT_ACTIONS.get(action)
        if status is None:
            raise ValueError(f"Unknown fit action '{action}'.")

        current = lead.fit_status or constants.FIT_STATUS_NOT_REVIEWED
        text = note.strip()
        if status == constants.FIT_STATUS_REJECTED and not text:
            raise ValueError("A note is required when rejecting a creator.")
        if current == constants.FIT_STATUS_REJECTED and action != "reopen":
            raise ValueError("A rejected creator must be reopened before another decision.")
        if action == "reopen" and current != constants.FIT_STATUS_REJECTED:
            raise ValueError("Only a rejected creator can be reopened.")

        campaign = self._repo.get_active_campaign()
        updated = self._repo.set_fit_decision(
            lead_id,
            status=status,
            note=text,
            decided_at=utc_now_iso(),
            currency=constants.DECISION_CURRENCY_CURRENT,
            currency_reason="",
            new_evidence=False,
        )
        self._record_decision(
            lead_id,
            action=action,
            fit_status=status,
            decision_currency=constants.DECISION_CURRENCY_CURRENT,
            evidence_version=lead.evidence_version,
            criteria_version=campaign.version if campaign else 0,
            note=text,
            actor=constants.FIT_ACTOR_OPERATOR,
        )
        return updated

    def list_fit_decisions(self, lead_id: str) -> list[FitDecision]:
        return self._repo.list_fit_decisions(lead_id)

    def request_contact(
        self, lead_id: str, *, note: str = "", search_again: bool = False
    ) -> tuple[ContactRequest, bool] | None:
        """Queue an explicit contact-discovery request (V2-06).

        Requires a current shortlist. Repeated clicks for the same evidence
        version return the existing in-flight/completed request; ``search_again``
        creates a new attempt. Returns ``(request, created)``.
        """
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None
        self._require_approved(lead)

        evidence_version = lead.evidence_version
        if not search_again:
            existing = self._repo.find_contact_request_for_evidence(
                lead_id, evidence_version
            )
            if (
                existing is not None
                and existing.status in constants.CONTACT_REQUEST_REUSABLE
            ):
                return (existing, False)

        now = utc_now_iso()
        request = self._repo.create_contact_request(
            ContactRequest(
                request_id=new_job_id("cr"),
                lead_id=lead_id,
                status=constants.CONTACT_REQUEST_QUEUED,
                note=note.strip(),
                evidence_version=evidence_version,
                requested_at=now,
            )
        )

        # Supersede any queued/running request for an older evidence version.
        for prior in self._repo.list_contact_requests(lead_id):
            if prior.request_id == request.request_id:
                continue
            if prior.status in constants.CONTACT_REQUEST_ACTIVE:
                self._repo.update_contact_request(
                    prior.request_id,
                    {
                        "status": constants.CONTACT_REQUEST_CANCELLED,
                        "error": "Superseded by a newer request",
                        "completed_at": now,
                    },
                )

        payload = json.dumps({"request_id": request.request_id})
        _, job = self._repo.enqueue(
            constants.STAGE_CONTACT_DISCOVERY,
            lead_id,
            lead.username,
            lead.username_normalized,
            payload=payload,
            max_attempts=3,
            on_duplicate="reenqueue",
        )
        # A queued job may still point at an older request; retarget it.
        self._repo.point_job_to_payload(job.job_id, payload)
        return (request, True)

    def list_contact_requests(self, lead_id: str) -> list[ContactRequest]:
        return self._repo.list_contact_requests(lead_id)

    def add_contact(
        self, lead_id: str, *, contact_type: str, value: str, source_url: str
    ) -> Contact | None:
        """Manually add a sourced public contact (no fit gate; V2-06 fallback)."""
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None
        text = value.strip()
        source = source_url.strip()
        if not text or not source:
            return None
        return self._repo.upsert_contact(
            Contact(
                contact_id=contact_id(lead_id, contact_type, text, source),
                lead_id=lead_id,
                type=contact_type,
                value=text,
                source_url=source,
                observed_at=utc_now_iso(),
                method=constants.CONTACT_METHOD_MANUAL,
                validation_state="unverified",
            )
        )

    def request_draft(self, lead_id: str, *, channel: str) -> OutreachRevision | None:
        """Create a new draft revision; requires an approved fit (T08).

        Each request appends a row to ``outreach_revisions`` so history is kept.
        """
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None
        self._require_approved(lead)
        now = utc_now_iso()
        return self._repo.create_outreach_revision(
            OutreachRevision(
                revision_id=new_job_id("rev"),
                lead_id=lead_id,
                channel=channel,
                status="requested",
                requested_at=now,
            )
        )

    def list_draft_revisions(self, lead_id: str) -> list[OutreachRevision]:
        return self._repo.list_outreach_revisions(lead_id)

    def _require_approved(self, lead: Lead) -> None:
        fit_status = lead.fit_status or constants.FIT_STATUS_NOT_REVIEWED
        currency = lead.decision_currency or constants.DECISION_CURRENCY_CURRENT
        if (
            fit_status != constants.FIT_STATUS_SHORTLISTED
            or currency != constants.DECISION_CURRENCY_CURRENT
        ):
            raise FitNotApprovedError(fit_status, currency)

    def _record_decision(
        self,
        lead_id: str,
        *,
        action: str,
        fit_status: str,
        decision_currency: str,
        evidence_version: int,
        criteria_version: int,
        note: str,
        actor: str,
    ) -> None:
        self._repo.create_fit_decision(
            FitDecision(
                decision_id=new_job_id("fd"),
                lead_id=lead_id,
                action=action,
                fit_status=fit_status,
                decision_currency=decision_currency,
                evidence_version=int(evidence_version or 0),
                criteria_version=int(criteria_version or 0),
                note=note,
                actor=actor,
                created_at=utc_now_iso_precise(),
            )
        )

    def list(
        self,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
        view: str | None = None,
        sort: str | None = None,
    ) -> tuple[list[tuple[Lead, str, str]], int]:
        """Return a filtered, ordered page of ``(lead, progress, remedy)``.

        The ``status`` filter matches the **derived progress**, so filters, row
        badges and counters use the same server-defined logic (PRD T01).

        ``view`` selects a saved creator view (V2-08). The default view is
        "To review": not reviewed plus shortlisters that need a reconfirmation,
        excluding rejected creators.
        """
        rows = self._repo.list_leads_with_progress()

        # The saved view selects the rows the operator is looking at.
        selected_view = normalize_view(view)
        rows = [
            row for row in rows if matches_view(row[0], row[1], selected_view)
        ]

        if status:
            wanted = status.strip().lower()
            rows = [row for row in rows if row[1].lower() == wanted]

        if search and search.strip():
            needle = search.strip().casefold()
            rows = [row for row in rows if needle in _search_blob(row[0]).casefold()]

        rows = sort_rows(rows, sort, selected_view)
        total = len(rows)
        return rows[offset : offset + limit], total

    def saved_view_counts(self) -> dict[str, int]:
        """Count creators per saved view (labelled counters, not a funnel)."""
        rows = self._repo.list_leads_with_progress()
        return view_counts(rows, self._repo.contact_types_by_lead())

    def contact_types_by_lead(self) -> dict[str, set[str]]:
        """Return ``{lead_id: {contact type}}`` for the contact indicator."""
        return self._repo.contact_types_by_lead()


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


def _snapshot_lead_fields(snapshot: dict[str, object]) -> dict[str, object]:
    """Map a merged snapshot to lead columns (non-empty values only)."""
    fields: dict[str, object] = {}
    display_name = str(snapshot.get("display_name") or "").strip()
    if display_name:
        fields["full_name"] = display_name
    bio = str(snapshot.get("bio") or "").strip()
    if bio:
        fields["bio"] = bio

    urls = snapshot.get("external_urls")
    if isinstance(urls, list) and urls:
        fields["external_url"] = urls[0]
        fields["all_external_urls"] = ",".join(str(url) for url in urls)

    followers = _count_value(snapshot.get("followers"))
    if followers is not None:
        fields["follower_count"] = followers
    following = _count_value(snapshot.get("following"))
    if following is not None:
        fields["follows_count"] = following

    source_url = str(snapshot.get("source_url") or "").strip()
    if source_url:
        fields["profile_url"] = source_url
    captured_at = str(snapshot.get("captured_at") or "").strip()
    if captured_at:
        fields["scraped_at"] = captured_at
    return fields


def _snapshot_dict(raw: str) -> dict[str, object]:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _canonical_json(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw or "{}"), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return raw or ""


def _snapshot_missing(lead: Lead) -> list[str]:
    fields = _snapshot_dict(lead.profile_snapshot).get("missing_fields")
    if isinstance(fields, list):
        return [str(field) for field in fields]
    return []


def _count_value(observation: object) -> int | None:
    if isinstance(observation, dict):
        value = observation.get("value")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None
