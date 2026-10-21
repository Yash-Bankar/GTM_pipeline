"""Draft revision lifecycle and manual outreach logging (V2-07).

Two rules drive everything here (PRD 4.5):

* **A draft version is immutable.** Editing, regenerating or reviewing creates
  the next revision and supersedes the previous one. An approved or manually
  authored draft is never silently replaced.
* **Manual actions are explicit.** Writing a draft needs no AI key; only an
  explicit generation request does. Copying or exporting never marks a draft
  as sent - only an explicit "Log sent" does, and that is recorded as history.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app import constants
from app.db.repository import Repository
from app.db.schemas import DraftRevision, Lead, OutreachEvent, OutreachRevision
from app.db.util import new_job_id, utc_now_iso, utc_now_iso_precise

logger = logging.getLogger(__name__)

# Field bounds for a saved draft body (matches the legacy dashboard limits).
SUBJECT_MAX = 2000
BODY_MAX = 20000

# A manual note attached to a logged event.
NOTE_MAX = 4000


class DraftNotFoundError(Exception):
    """Raised when the requested draft revision does not exist."""


class GenerationUnavailableError(Exception):
    """Raised when an explicit AI generation request cannot be accepted (V22)."""


class FitGateError(Exception):
    """Raised when gated draft work is requested for a non-shortlisted lead."""

    def __init__(self, fit_status: str, decision_currency: str = "current") -> None:
        super().__init__(fit_status)
        self.fit_status = fit_status
        self.decision_currency = decision_currency


class OutreachEventError(Exception):
    """Raised when a manual outreach event cannot be recorded (V24/V25)."""


@dataclass(frozen=True)
class DraftActionResult:
    """The outcome of a draft action."""

    revision: DraftRevision
    created: bool = False
    message: str = ""


@dataclass(frozen=True)
class OutreachEventResult:
    """The outcome of a manual outreach log action."""

    event: OutreachEvent
    created: bool = False
    message: str = ""


class DraftService:
    """Manual draft editing, revision history and manual outreach logging."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    # -- draft versions ----------------------------------------------------

    def list_revisions(self, lead_id: str) -> list[DraftRevision]:
        """Every saved draft version for a lead, oldest first."""
        return self._repo.list_draft_revisions(lead_id)

    def current_revision(self, lead_id: str) -> DraftRevision | None:
        """The version an editor should open: the newest non-superseded one."""
        return self._repo.get_latest_draft_revision(lead_id)

    def get_revision(self, revision_id: str) -> DraftRevision:
        revision = self._repo.get_draft_revision(revision_id)
        if revision is None:
            raise DraftNotFoundError(revision_id)
        return revision

    def save_draft(
        self,
        lead_id: str,
        *,
        subject: str,
        body: str,
        dm_body: str,
        channel: str = "",
        note: str = "",
        contact_id: str = "",
        parent_revision_id: str = "",
        method: str = constants.DRAFT_METHOD_MANUAL,
        model: str = "",
        evidence_scope: str = "",
    ) -> DraftActionResult:
        """Save the draft as a NEW revision (V23).

        Manual writing never needs an AI key. The previous version is
        superseded but stays visible as history, so an approved or manually
        authored draft is never silently replaced.
        """
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            raise DraftNotFoundError(lead_id)

        subject = subject[:SUBJECT_MAX]
        body = body[:BODY_MAX]
        dm_body = dm_body[:BODY_MAX]
        if not (subject.strip() or body.strip() or dm_body.strip()):
            raise DraftNotFoundError(lead_id)

        if not parent_revision_id:
            current = self._repo.get_latest_draft_revision(lead_id)
            parent_revision_id = current.revision_id if current is not None else ""

        if parent_revision_id:
            parent = self._repo.get_draft_revision(parent_revision_id)
            if parent is not None:
                # Only a superseded version may be replaced; a current one is
                # superseded explicitly below so history stays ordered.
                self._repo.supersede_draft_revision(parent.revision_id)

        now = utc_now_iso()
        revision = self._repo.create_draft_revision(
            DraftRevision(
                revision_id=new_job_id("dr"),
                lead_id=lead_id,
                username=lead.username,
                username_normalized=lead.username_normalized,
                channel=channel or "",
                subject=subject,
                body=body,
                dm_body=dm_body,
                status=constants.DRAFT_REVISION_NEEDS_REVIEW,
                method=method,
                model=model,
                parent_revision_id=parent_revision_id,
                contact_id=contact_id,
                request_id="",
                evidence_scope=evidence_scope,
                note=note[:NOTE_MAX],
                edited_at=now,
            )
        )
        return DraftActionResult(revision=revision, created=True, message="Draft saved.")

    def mark_reviewed(self, lead_id: str, revision_id: str) -> DraftActionResult:
        """Mark a saved draft version as reviewed.

        A draft that is already the current version keeps its identity - only
        its review state changes. No new version is created, so the content
        that was reviewed is the content that stays.
        """
        revision = self.get_revision(revision_id)
        if revision.lead_id != lead_id:
            raise DraftNotFoundError(revision_id)
        updated = self._repo.set_draft_revision_status(
            revision_id, constants.DRAFT_REVISION_REVIEWED
        )
        assert updated is not None
        return DraftActionResult(revision=updated, message="Marked reviewed.")

    def export_text(self, lead_id: str, revision_id: str) -> str:
        """Return the plain text of a draft version (export never marks sent)."""
        revision = self.get_revision(revision_id)
        if revision.lead_id != lead_id:
            raise DraftNotFoundError(revision_id)
        return export_draft_text(revision)

    def copy_text(self, lead_id: str, revision_id: str) -> str:
        """Return the copyable text of a draft version (copy never marks sent)."""
        return self.export_text(lead_id, revision_id)

    # -- generation requests (V22/V23) --------------------------------------

    def request_generation(
        self,
        lead_id: str,
        *,
        channel: str,
        ai_available: bool,
        parent_revision_id: str = "",
        contact_id: str = "",
    ) -> OutreachRevision:
        """Record an explicit AI generation request.

        The request creates **no** content and no revision of its own: the
        worker produces a new revision when it succeeds. When AI is unavailable
        the request is rejected before anything is written, so no orphan
        revision or job is left behind (V22).

        Generation is gated work: it needs a current shortlist (V17) and an
        enabled AI capability.
        """
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            raise DraftNotFoundError(lead_id)
        self._require_shortlisted(lead)
        if not ai_available:
            raise GenerationUnavailableError(constants.ERROR_AI_UNAVAILABLE)

        if not parent_revision_id:
            current = self._repo.get_latest_draft_revision(lead_id)
            parent_revision_id = current.revision_id if current is not None else ""

        now = utc_now_iso()
        request = self._repo.create_outreach_revision(
            OutreachRevision(
                revision_id=new_job_id("rev"),
                lead_id=lead_id,
                channel=channel,
                status=constants.DRAFT_GENERATION_QUEUED,
                requested_at=now,
                result_revision_id="",
                parent_revision_id=parent_revision_id,
                job_id="",
                error="",
            )
        )

        # Durable scheduling: the request is only accepted once the job exists.
        payload = json.dumps({"request_id": request.revision_id})
        _, job = self._repo.enqueue(
            constants.STAGE_AI_OUTREACH,
            lead_id,
            lead.username,
            lead.username_normalized,
            payload=payload,
            priority=10,
            max_attempts=3,
            on_duplicate="reenqueue",
        )
        self._repo.update_outreach_revision(
            request.revision_id, {"job_id": job.job_id}
        )
        return request

    def _require_shortlisted(self, lead: Lead) -> None:
        """Generation is gated work: a current shortlist is required (V17)."""
        fit_status = lead.fit_status or constants.FIT_STATUS_NOT_REVIEWED
        currency = lead.decision_currency or constants.DECISION_CURRENCY_CURRENT
        if (
            fit_status != constants.FIT_STATUS_SHORTLISTED
            or currency != constants.DECISION_CURRENCY_CURRENT
        ):
            raise FitGateError(fit_status, currency)

    def list_generation_requests(self, lead_id: str) -> list[OutreachRevision]:
        return self._repo.list_outreach_revisions(lead_id)

    # -- manual outreach logging (V24/V25) ---------------------------------

    def log_event(
        self,
        lead_id: str,
        *,
        outcome: str,
        channel: str,
        sent_at: str = "",
        revision_id: str = "",
        note: str = "",
        corrects_event_id: str = "",
        actor: str = constants.FIT_ACTOR_OPERATOR,
    ) -> OutreachEventResult:
        """Append a manually logged outreach event.

        A log requires a channel and a sent time, plus either the draft
        revision that was sent or a manual note. Corrections are **new**
        visible events that reference the event they correct - the original
        row is never rewritten (V25).
        """
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            raise OutreachEventError("lead not found")

        outcome = (outcome or "").strip().lower()
        if outcome not in constants.OUTREACH_EVENT_OUTCOMES:
            raise OutreachEventError(
                f"outcome must be one of {sorted(constants.OUTREACH_EVENT_OUTCOMES)}"
            )
        channel = (channel or "").strip().lower()
        if channel not in constants.DRAFT_CHANNELS:
            raise OutreachEventError(
                f"channel must be one of {sorted(constants.DRAFT_CHANNELS)}"
            )

        revision_id = (revision_id or "").strip()
        note = note.strip()[:NOTE_MAX]
        if not revision_id and not note:
            raise OutreachEventError(
                "A sent log needs the draft revision or a manual note."
            )
        if revision_id:
            revision = self._repo.get_draft_revision(revision_id)
            if revision is None or revision.lead_id != lead_id:
                raise OutreachEventError("Unknown draft revision.")

        corrects_event_id = (corrects_event_id or "").strip()
        source = constants.OUTREACH_EVENT_SOURCE_MANUAL
        if corrects_event_id:
            original = self._repo.get_outreach_event(corrects_event_id)
            if original is None or original.lead_id != lead_id:
                raise OutreachEventError("Unknown event to correct.")
            source = constants.OUTREACH_EVENT_SOURCE_CORRECTION
            # A correction inherits the original channel/revision when the
            # operator did not restate them.
            channel = channel or original.channel
            revision_id = revision_id or original.revision_id
            sent_at = sent_at or original.sent_at

        now = utc_now_iso()
        logged_at = utc_now_iso_precise()
        event = self._repo.create_outreach_event(
            OutreachEvent(
                event_id=new_job_id("oe"),
                lead_id=lead_id,
                outcome=outcome,
                channel=channel,
                revision_id=revision_id,
                note=note,
                source=source,
                corrects_event_id=corrects_event_id,
                actor=actor or constants.FIT_ACTOR_OPERATOR,
                sent_at=sent_at or now,
                logged_at=logged_at,
            )
        )
        message = "Correction logged." if corrects_event_id else "Logged manually."
        return OutreachEventResult(event=event, created=True, message=message)

    def list_events(self, lead_id: str) -> list[OutreachEvent]:
        """The manual outreach history for a lead, oldest first."""
        return self._repo.list_outreach_events(lead_id)

    def latest_event(self, lead_id: str) -> OutreachEvent | None:
        """The most recent event, ignoring superseded corrections.

        A correction supersedes the event it corrects, so the latest summary
        reflects the correction while the history keeps both rows.
        """
        events = self.list_events(lead_id)
        if not events:
            return None
        corrected = {
            event.corrects_event_id
            for event in events
            if event.corrects_event_id and event.source == constants.OUTREACH_EVENT_SOURCE_CORRECTION
        }
        live = [event for event in events if event.event_id not in corrected]
        return (live or events)[-1]


def export_draft_text(revision: DraftRevision) -> str:
    """Render a draft version as plain text for copy/export."""
    parts: list[str] = []
    if revision.subject.strip():
        parts.append(revision.subject.strip())
    if revision.body.strip():
        parts.append(revision.body.strip())
    if revision.dm_body.strip():
        parts.append(revision.dm_body.strip())
    return "\n\n".join(parts)


def revision_summary(revision: DraftRevision) -> dict[str, object]:
    """A compact description of a draft version, used by list endpoints."""
    return {
        "revision_id": revision.revision_id,
        "lead_id": revision.lead_id,
        "channel": revision.channel,
        "status": revision.status,
        "method": revision.method,
        "model": revision.model,
        "parent_revision_id": revision.parent_revision_id,
        "request_id": revision.request_id,
        "edited_at": revision.edited_at,
        "created_at": revision.created_at,
    }


def event_summary(event: OutreachEvent) -> dict[str, object]:
    """A compact description of a logged event, used by list endpoints."""
    return {
        "event_id": event.event_id,
        "lead_id": event.lead_id,
        "outcome": event.outcome,
        "channel": event.channel,
        "revision_id": event.revision_id,
        "source": event.source,
        "corrects_event_id": event.corrects_event_id,
        "actor": event.actor,
        "sent_at": event.sent_at,
        "logged_at": event.logged_at,
        "note": event.note,
    }
