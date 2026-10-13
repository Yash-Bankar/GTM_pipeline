"""Read/aggregate service backing the dashboard endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field

from app import constants
from app.sheets.models import (
    Dossier,
    Lead,
    LeadPost,
    OutreachEntry,
    PipelineJob,
    WebsitePage,
)
from app.sheets.repository import JobStore, LeadStore, SheetStore
from app.sheets.schemas import (
    KEY_DOSSIERS,
    KEY_ENRICHED,
    KEY_IG_LEADS,
    KEY_JOBS,
    KEY_OUTREACH,
    KEY_POSTS,
    KEY_WEBSITE_PAGES,
)
from app.sheets.util import utc_now_iso

OUTREACH_STATUSES = {
    constants.AI_STATUS_NEEDS_REVIEW,
    "APPROVED",
    "REJECTED",
}


@dataclass
class LeadDetail:
    lead: Lead
    enriched: dict[str, str] = field(default_factory=dict)
    posts: list[LeadPost] = field(default_factory=list)
    website_pages: list[WebsitePage] = field(default_factory=list)
    jobs: list[PipelineJob] = field(default_factory=list)


class DashboardService:
    def __init__(
        self,
        *,
        lead_store: LeadStore,
        job_store: JobStore,
        enriched_store: SheetStore,
        post_store: SheetStore,
        website_store: SheetStore,
        dossier_store: SheetStore,
        outreach_store: SheetStore,
    ) -> None:
        self._lead_store = lead_store
        self._job_store = job_store
        self._enriched_store = enriched_store
        self._post_store = post_store
        self._website_store = website_store
        self._dossier_store = dossier_store
        self._outreach_store = outreach_store

    # -- leads --------------------------------------------------------------

    def lead_detail(self, lead_id: str) -> LeadDetail | None:
        record = self._lead_store.find_row(KEY_IG_LEADS, lead_id)
        if record is None:
            return None
        lead = Lead.model_validate(record.values)

        enriched_record = self._enriched_store.find_row(
            KEY_ENRICHED, lead_id, key_header="leadId"
        )
        posts = [
            LeadPost.model_validate(row.values)
            for row in self._post_store.read_rows(KEY_POSTS)
            if row.values.get("leadId") == lead_id
        ]
        pages = [
            WebsitePage.model_validate(row.values)
            for row in self._website_store.read_rows(KEY_WEBSITE_PAGES)
            if row.values.get("leadId") == lead_id
        ]
        jobs = [
            PipelineJob.model_validate(row.values)
            for row in self._job_store.read_rows(KEY_JOBS)
            if row.values.get("leadId") == lead_id
        ]
        jobs.sort(key=lambda job: job.created_at)
        posts.sort(key=lambda post: post.taken_at, reverse=True)
        return LeadDetail(
            lead=lead,
            enriched=dict(enriched_record.values) if enriched_record else {},
            posts=posts,
            website_pages=pages,
            jobs=jobs,
        )

    def retry_lead(self, lead_id: str) -> PipelineJob | None:
        record = self._lead_store.find_row(KEY_IG_LEADS, lead_id)
        if record is None:
            return None
        _, job = self._job_store.enqueue(
            constants.STAGE_PROFILE_FETCH,
            lead_id,
            record.values.get("username", ""),
            record.values.get("usernameNormalized", ""),
            max_attempts=3,
            on_duplicate="reenqueue",
        )
        return job

    # -- dossiers -----------------------------------------------------------

    def list_dossiers(
        self, *, limit: int, offset: int, search: str | None = None
    ) -> tuple[list[Dossier], int]:
        rows = [Dossier.model_validate(r.values) for r in self._dossier_store.read_rows(KEY_DOSSIERS)]
        if search and search.strip():
            needle = search.strip().casefold()
            rows = [
                d
                for d in rows
                if needle in f"{d.username} {d.summary} {d.topics}".casefold()
            ]
        rows.sort(key=lambda d: (d.generated_at, d.lead_id), reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total

    def get_dossier(self, lead_id: str) -> Dossier | None:
        record = self._dossier_store.find_row(KEY_DOSSIERS, lead_id, key_header="leadId")
        return Dossier.model_validate(record.values) if record else None

    # -- outreach -----------------------------------------------------------

    def list_outreach(
        self, *, limit: int, offset: int, status: str | None = None
    ) -> tuple[list[OutreachEntry], int]:
        rows = [
            OutreachEntry.model_validate(r.values)
            for r in self._outreach_store.read_rows(KEY_OUTREACH)
        ]
        if status:
            wanted = status.strip().upper()
            rows = [row for row in rows if row.status.upper() == wanted]
        rows.sort(key=lambda row: (row.generated_at, row.lead_id), reverse=True)
        total = len(rows)
        return rows[offset : offset + limit], total

    def get_outreach(self, lead_id: str) -> OutreachEntry | None:
        record = self._outreach_store.find_row(KEY_OUTREACH, lead_id, key_header="leadId")
        return OutreachEntry.model_validate(record.values) if record else None

    def update_outreach(
        self,
        lead_id: str,
        *,
        status: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        dm_body: str | None = None,
    ) -> OutreachEntry | None:
        existing = self.get_outreach(lead_id)
        if existing is None:
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
            fields["dmBody"] = dm_body[:20000]
        if fields:
            fields["updatedAt"] = utc_now_iso()
            self._outreach_store.update_by_key(
                KEY_OUTREACH, lead_id, fields, key_header="leadId", touch_updated_at=False
            )
        return self.get_outreach(lead_id)

    # -- stats --------------------------------------------------------------

    def stats(self) -> dict[str, object]:
        leads = [Lead.model_validate(r.values) for r in self._lead_store.read_rows(KEY_IG_LEADS)]
        by_status: dict[str, int] = {}
        for lead in leads:
            key = lead.status or "unknown"
            by_status[key] = by_status.get(key, 0) + 1

        jobs = self._job_store.read_rows(KEY_JOBS)
        job_status: dict[str, int] = {}
        for row in jobs:
            key = row.values.get("status", "unknown")
            job_status[key] = job_status.get(key, 0) + 1

        dossiers = self._dossier_store.read_rows(KEY_DOSSIERS)
        outreach = self._outreach_store.read_rows(KEY_OUTREACH)
        return {
            "leads_total": len(leads),
            "leads_by_status": by_status,
            "jobs_by_status": job_status,
            "dossiers_total": len(dossiers),
            "outreach_total": len(outreach),
            "outreach_needs_review": sum(
                1
                for row in outreach
                if row.values.get("status", "").upper() == constants.AI_STATUS_NEEDS_REVIEW
            ),
        }
