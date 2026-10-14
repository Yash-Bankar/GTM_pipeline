"""Read/aggregate service backing the dashboard endpoints (database-backed)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app import constants
from app.db.repository import Repository
from app.db.schemas import (
    Dossier,
    Lead,
    LeadPost,
    OutreachEntry,
    PipelineJob,
    WebsitePage,
)

OUTREACH_STATUSES = {
    constants.AI_STATUS_NEEDS_REVIEW,
    "APPROVED",
    "REJECTED",
}


@dataclass
class LeadDetail:
    lead: Lead
    posts: list[LeadPost] = field(default_factory=list)
    website_pages: list[WebsitePage] = field(default_factory=list)
    jobs: list[PipelineJob] = field(default_factory=list)


class DashboardService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    # -- leads --------------------------------------------------------------

    def lead_detail(self, lead_id: str) -> LeadDetail | None:
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None
        return LeadDetail(
            lead=lead,
            posts=self._repo.list_posts(lead_id),
            website_pages=self._repo.list_website_pages(lead_id),
            jobs=self._repo.list_jobs(lead_id),
        )

    def retry_lead(self, lead_id: str) -> PipelineJob | None:
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None
        _, job = self._repo.enqueue(
            constants.STAGE_PROFILE_FETCH,
            lead_id,
            lead.username,
            lead.username_normalized,
            max_attempts=3,
            on_duplicate="reenqueue",
        )
        return job

    # -- dossiers -----------------------------------------------------------

    def list_dossiers(
        self, *, limit: int, offset: int, search: str | None = None
    ) -> tuple[list[Dossier], int]:
        rows = self._repo.list_dossiers()
        if search and search.strip():
            needle = search.strip().casefold()
            rows = [
                dossier
                for dossier in rows
                if needle in f"{dossier.username} {dossier.summary} {dossier.topics}".casefold()
            ]
        total = len(rows)
        return rows[offset : offset + limit], total

    def get_dossier(self, lead_id: str) -> Dossier | None:
        return self._repo.get_dossier(lead_id)

    # -- outreach -----------------------------------------------------------

    def list_outreach(
        self, *, limit: int, offset: int, status: str | None = None
    ) -> tuple[list[OutreachEntry], int]:
        rows = self._repo.list_outreach()
        if status:
            wanted = status.strip().upper()
            rows = [row for row in rows if row.status.upper() == wanted]
        total = len(rows)
        return rows[offset : offset + limit], total

    def get_outreach(self, lead_id: str) -> OutreachEntry | None:
        return self._repo.get_outreach(lead_id)

    def update_outreach(
        self,
        lead_id: str,
        *,
        status: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        dm_body: str | None = None,
    ) -> OutreachEntry | None:
        if self._repo.get_outreach(lead_id) is None:
            return None
        fields: dict[str, object] = {}
        if status is not None:
            normalized = status.strip().upper()
            if normalized not in OUTREACH_STATUSES:
                raise ValueError(f"status must be one of {sorted(OUTREACH_STATUSES)}")
            fields["status"] = normalized
        if subject is not None:
            fields["subject"] = subject[:2000]
        if body is not None:
            fields["body"] = body[:20000]
        if dm_body is not None:
            fields["dm_body"] = dm_body[:20000]
        if fields:
            return self._repo.update_outreach(lead_id, fields)
        return self._repo.get_outreach(lead_id)

    # -- stats --------------------------------------------------------------

    def stats(self) -> dict[str, object]:
        return self._repo.stats()
