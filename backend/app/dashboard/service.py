"""Read/aggregate service backing the dashboard endpoints (database-backed)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text

from app import constants
from app.config import get_settings
from app.db.repository import Repository
from app.leads.schemas import parse_snapshot_out
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
    progress: str = "needs_data"
    progress_remedy: str = ""
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
        progress, remedy = self._repo.lead_progress(lead_id)
        return LeadDetail(
            lead=lead,
            progress=progress,
            progress_remedy=remedy,
            posts=self._repo.list_posts(lead_id),
            website_pages=self._repo.list_website_pages(lead_id),
            jobs=self._repo.list_jobs(lead_id),
        )

    def lead_brief(self, lead_id: str) -> dict[str, object] | None:
        """Evidence-only creator brief. Never calls AI or a provider (V2-01)."""
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None

        snapshot = parse_snapshot_out(lead.profile_snapshot)
        dossier = self._repo.get_dossier(lead_id)
        pages = self._repo.list_website_pages(lead_id)

        urls: list[str] = []
        for raw in (lead.all_external_urls, lead.external_url):
            for part in str(raw or "").replace("\n", ",").split(","):
                value = part.strip()
                if value and value not in urls:
                    urls.append(value)

        return {
            "lead_id": lead.lead_id,
            "username": lead.username,
            "full_name": lead.full_name,
            "bio": lead.bio,
            "category": lead.business_category_name,
            "follower_count": lead.follower_count,
            "follower_display": snapshot.followers.display if snapshot and snapshot.followers else "",
            "follower_precision": (
                snapshot.followers.precision if snapshot and snapshot.followers else "unknown"
            ),
            "follows_count": lead.follows_count,
            "external_urls": urls,
            "captured_at": lead.scraped_at,
            "missing_fields": snapshot.missing_fields if snapshot else [],
            "is_verified": snapshot.is_verified if snapshot else False,
            "evidence_version": lead.evidence_version,
            "sources": [
                {
                    "url": page.resolved_url or page.url,
                    "title": page.title,
                    "status": page.status,
                    "fetched_at": page.fetched_at,
                }
                for page in pages
            ],
            "has_dossier": dossier is not None,
            "ai_summary": dossier.summary if dossier else "",
            "ai_status": dossier.status if dossier else "not_generated",
            "generated_at": dossier.generated_at if dossier else "",
            "model": dossier.model if dossier else "",
        }

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

    def retry_ai(self, lead_id: str) -> list[PipelineJob] | None:
        """Re-queue the AI summary/dossier stage only, forcing regeneration.

        V2-01: this must never fan out to outreach or draft generation. Drafts are
        an explicit, separate operation. Completed research stages are untouched.
        """
        lead = self._repo.get_lead(lead_id)
        if lead is None:
            return None

        payload = json.dumps({"force": True})
        _, dossier_job = self._repo.enqueue(
            constants.STAGE_AI_DOSSIER,
            lead_id,
            lead.username,
            lead.username_normalized,
            payload=payload,
            priority=10,
            max_attempts=3,
            on_duplicate="reenqueue",
        )
        return [dossier_job]

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

    # -- integrations / readiness (T09) -------------------------------------

    def integrations_status(self) -> dict[str, str]:
        """Secret-free system readiness; never returns credential values."""
        settings = get_settings()

        database = "healthy"
        try:
            self._repo.session.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - reported as unreachable, not raised
            database = "unreachable"

        worker = "stopped"
        beat_at = ""
        if database == "healthy":
            try:
                heartbeat = self._repo.get_heartbeat()
                beat_at = heartbeat.beat_at if heartbeat else ""
                worker = _worker_state(beat_at)
            except Exception:  # noqa: BLE001 - treat unreadable heartbeat as stopped
                worker = "stopped"

        gemini = (
            "configured"
            if settings.ai_enabled and settings.gemini_api_key.strip()
            else "disabled"
        )
        hikerapi = "configured" if settings.hikerapi_key.strip() else "disabled"
        return {
            "database": database,
            "worker": worker,
            "gemini": gemini,
            "hikerapi": hikerapi,
            "worker_last_beat_at": beat_at,
        }


def _worker_state(beat_at: str) -> str:
    """Map a stored heartbeat timestamp to ``active``/``stale``/``stopped``."""
    if not beat_at:
        return "stopped"
    try:
        moment = datetime.fromisoformat(beat_at)
    except (TypeError, ValueError):
        return "stopped"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - moment).total_seconds()
    if age < 0:
        age = 0
    return "active" if age <= constants.WORKER_STALE_SECONDS else "stale"
