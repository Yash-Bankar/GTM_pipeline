"""Lead application service (database-backed)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app import constants
from app.db.repository import Repository
from app.db.schemas import Lead

from .schemas import LEAD_STATUS_QUEUED, LeadCreateRequest
from .validation import parse_lead_input

logger = logging.getLogger(__name__)

_SEARCHABLE_FIELDS = (
    "username",
    "username_normalized",
    "full_name",
    "bio",
    "business_email",
)


@dataclass(frozen=True)
class LeadSubmission:
    created: bool
    lead: Lead


class LeadService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def submit(self, request: LeadCreateRequest) -> LeadSubmission:
        """Create a lead or return the existing one (deduplicated), then enqueue it."""
        parsed = parse_lead_input(request.username)
        created, lead = self._repo.create_or_get_lead(
            parsed.username,
            source=request.source or "api",
            status=LEAD_STATUS_QUEUED,
            profile_url=parsed.profile_url,
        )
        self._repo.enqueue(
            constants.STAGE_PROFILE_FETCH,
            lead.lead_id,
            lead.username,
            lead.username_normalized,
            max_attempts=3,
        )
        logger.info(
            "Lead submission @%s -> %s (leadId=%s)",
            parsed.normalized,
            "created" if created else "existing",
            lead.lead_id,
        )
        return LeadSubmission(created=created, lead=lead)

    def get(self, lead_id: str) -> Lead | None:
        return self._repo.get_lead(lead_id)

    def list(
        self,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Lead], int]:
        """Return a filtered, newest-first page of leads plus the total count."""
        leads = self._repo.list_leads()

        if status:
            wanted = status.strip().lower()
            leads = [lead for lead in leads if lead.status.lower() == wanted]

        if search and search.strip():
            needle = search.strip().casefold()
            leads = [lead for lead in leads if needle in _search_blob(lead).casefold()]

        leads.sort(key=lambda lead: (lead.created_at, lead.lead_id), reverse=True)
        total = len(leads)
        return leads[offset : offset + limit], total


def _search_blob(lead: Lead) -> str:
    return " \n".join(str(getattr(lead, field, "")) for field in _SEARCHABLE_FIELDS)
