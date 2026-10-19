"""Database repository.

Provides the same functional contracts as the previous Google Sheets layer
(deduplication by normalized username, idempotent enqueue per ``(stage, lead_id)``,
bounded retries, stale-job recovery) on top of SQLAlchemy.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import constants

from .errors import DuplicateLeadError
from .models import (
    Dossier as DossierORM,
)
from .models import (
    Lead as LeadORM,
)
from .models import (
    OutreachDraft as OutreachORM,
)
from .models import (
    PipelineJob as JobORM,
)
from .models import (
    Post as PostORM,
)
from .models import (
    WebsitePage as PageORM,
)
from .progress import derive_research_status, research_remedy
from .schemas import (
    Dossier,
    Lead,
    LeadPost,
    OutreachEntry,
    PipelineJob,
    WebsitePage,
)
from .util import new_job_id, new_lead_id, normalize_username, utc_now_iso

_LEAD_INT_FIELDS = {"follower_count", "follows_count"}
_LEAD_FIELDS = {column.name for column in LeadORM.__table__.columns}
_OUTREACH_FIELDS = {"status", "subject", "body", "dm_body", "channel", "model", "generated_at"}


def _iso_after(seconds: float) -> str:
    moment = datetime.now(timezone.utc) + timedelta(seconds=max(0.0, seconds))
    return moment.replace(microsecond=0).isoformat()


class Repository:
    """Data access for all entities, bound to a single SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    # -- leads --------------------------------------------------------------

    def get_lead(self, lead_id: str) -> Lead | None:
        row = self.session.get(LeadORM, lead_id)
        return Lead.model_validate(row) if row is not None else None

    def list_leads(self) -> list[Lead]:
        rows = self.session.scalars(select(LeadORM).order_by(LeadORM.created_at)).all()
        return [Lead.model_validate(row) for row in rows]

    def _jobs_by_lead(self) -> dict[str, list[PipelineJob]]:
        grouped: dict[str, list[PipelineJob]] = {}
        for row in self.session.scalars(select(JobORM)).all():
            grouped.setdefault(row.lead_id, []).append(PipelineJob.model_validate(row))
        return grouped

    def list_leads_with_progress(self) -> list[tuple[Lead, str, str]]:
        """Return ``(lead, derived_progress, remedy)`` for every lead.

        The derived progress is computed once, here, so list rows, filters and
        stats all agree (PRD T01).
        """
        jobs_by_lead = self._jobs_by_lead()
        result: list[tuple[Lead, str, str]] = []
        for lead in self.list_leads():
            jobs = jobs_by_lead.get(lead.lead_id, [])
            result.append(
                (
                    lead,
                    derive_research_status(lead.status, jobs),
                    research_remedy(lead.status, jobs),
                )
            )
        return result

    def lead_progress(self, lead_id: str) -> tuple[str, str]:
        """Return ``(derived_progress, remedy)`` for a single lead."""
        lead = self.get_lead(lead_id)
        if lead is None:
            return ("", "")
        jobs = self.list_jobs(lead_id)
        return (
            derive_research_status(lead.status, jobs),
            research_remedy(lead.status, jobs),
        )

    def find_lead_by_username(self, username: str) -> Lead | None:
        normalized = normalize_username(username)
        if not normalized:
            return None
        row = self.session.scalar(
            select(LeadORM).where(LeadORM.username_normalized == normalized)
        )
        return Lead.model_validate(row) if row is not None else None

    def find_lead_by_request_id(self, request_id: str) -> Lead | None:
        """Return the lead captured with this client request id (idempotent retries)."""
        if not request_id:
            return None
        row = self.session.scalar(
            select(LeadORM).where(LeadORM.request_id == request_id)
        )
        return Lead.model_validate(row) if row is not None else None

    def create_or_get_lead(
        self,
        username: str,
        *,
        source: str = "",
        status: str = "new",
        profile_url: str | None = None,
    ) -> tuple[bool, Lead]:
        """Atomically create a lead or return the existing one (dedup by username)."""
        normalized = normalize_username(username)
        if not normalized:
            raise ValueError("username is required")

        existing = self.find_lead_by_username(normalized)
        if existing is not None:
            return (False, existing)

        now = utc_now_iso()
        row = LeadORM(
            lead_id=new_lead_id(),
            username=username.strip().lstrip("@"),
            username_normalized=normalized,
            profile_url=profile_url or f"https://www.instagram.com/{normalized}/",
            status=status,
            source=source,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.find_lead_by_username(normalized)
            if existing is not None:
                return (False, existing)
            raise
        return (True, Lead.model_validate(row))

    def create_lead(
        self,
        username: str,
        *,
        source: str = "",
        status: str = "new",
        profile_url: str | None = None,
        on_duplicate: str = "error",
    ) -> Lead:
        created, lead = self.create_or_get_lead(
            username, source=source, status=status, profile_url=profile_url
        )
        if not created and on_duplicate == "error":
            raise DuplicateLeadError(
                f"A lead with username '{lead.username_normalized}' already exists "
                f"(leadId={lead.lead_id})."
            )
        return lead

    def update_lead(self, lead_id: str, fields: dict[str, object]) -> Lead | None:
        row = self.session.get(LeadORM, lead_id)
        if row is None:
            return None
        for key, value in fields.items():
            if key not in _LEAD_FIELDS:
                continue
            if key in _LEAD_INT_FIELDS:
                try:
                    setattr(row, key, int(value) if value not in (None, "") else 0)
                except (TypeError, ValueError):
                    setattr(row, key, 0)
            else:
                setattr(row, key, "" if value is None else str(value))
        row.updated_at = utc_now_iso()
        self.session.commit()
        return Lead.model_validate(row)

    # -- posts --------------------------------------------------------------

    def list_posts(self, lead_id: str) -> list[LeadPost]:
        rows = self.session.scalars(
            select(PostORM).where(PostORM.lead_id == lead_id)
        ).all()
        posts = [LeadPost.model_validate(row) for row in rows]
        posts.sort(key=lambda post: post.taken_at, reverse=True)
        return posts

    def upsert_post(self, post: LeadPost) -> None:
        now = utc_now_iso()
        row = self.session.get(PostORM, post.post_id)
        data = post.model_dump()
        data["created_at"] = data.get("created_at") or now
        data["updated_at"] = now
        if row is None:
            self.session.add(PostORM(**data))
        else:
            for key, value in data.items():
                if hasattr(row, key):
                    setattr(row, key, value)
        self.session.commit()

    # -- website pages ------------------------------------------------------

    def list_website_pages(self, lead_id: str) -> list[WebsitePage]:
        rows = self.session.scalars(
            select(PageORM).where(PageORM.lead_id == lead_id)
        ).all()
        return [WebsitePage.model_validate(row) for row in rows]

    def get_website_page(self, page_id: str) -> WebsitePage | None:
        row = self.session.get(PageORM, page_id)
        return WebsitePage.model_validate(row) if row is not None else None

    def upsert_website_page(self, page: WebsitePage) -> None:
        now = utc_now_iso()
        row = self.session.get(PageORM, page.page_id)
        data = page.model_dump()
        data["created_at"] = data.get("created_at") or now
        data["updated_at"] = now
        if row is None:
            self.session.add(PageORM(**data))
        else:
            for key, value in data.items():
                if hasattr(row, key):
                    setattr(row, key, value)
        self.session.commit()

    # -- dossiers -----------------------------------------------------------

    def get_dossier(self, lead_id: str) -> Dossier | None:
        row = self.session.get(DossierORM, lead_id)
        return Dossier.model_validate(row) if row is not None else None

    def list_dossiers(self) -> list[Dossier]:
        rows = self.session.scalars(select(DossierORM)).all()
        dossiers = [Dossier.model_validate(row) for row in rows]
        dossiers.sort(key=lambda dossier: (dossier.generated_at, dossier.lead_id), reverse=True)
        return dossiers

    def upsert_dossier(self, dossier: Dossier) -> None:
        now = utc_now_iso()
        row = self.session.get(DossierORM, dossier.lead_id)
        data = dossier.model_dump()
        data["created_at"] = data.get("created_at") or now
        data["updated_at"] = now
        if row is None:
            self.session.add(DossierORM(**data))
        else:
            for key, value in data.items():
                if hasattr(row, key):
                    setattr(row, key, value)
        self.session.commit()

    # -- outreach -----------------------------------------------------------

    def get_outreach(self, lead_id: str) -> OutreachEntry | None:
        row = self.session.get(OutreachORM, lead_id)
        return OutreachEntry.model_validate(row) if row is not None else None

    def list_outreach(self) -> list[OutreachEntry]:
        rows = self.session.scalars(select(OutreachORM)).all()
        entries = [OutreachEntry.model_validate(row) for row in rows]
        entries.sort(key=lambda entry: (entry.generated_at, entry.lead_id), reverse=True)
        return entries

    def upsert_outreach(self, entry: OutreachEntry) -> None:
        now = utc_now_iso()
        row = self.session.get(OutreachORM, entry.lead_id)
        data = entry.model_dump()
        data["created_at"] = data.get("created_at") or now
        data["updated_at"] = now
        if row is None:
            self.session.add(OutreachORM(**data))
        else:
            for key, value in data.items():
                if hasattr(row, key):
                    setattr(row, key, value)
        self.session.commit()

    def update_outreach(self, lead_id: str, fields: dict[str, object]) -> OutreachEntry | None:
        row = self.session.get(OutreachORM, lead_id)
        if row is None:
            return None
        for key, value in fields.items():
            if key in _OUTREACH_FIELDS:
                setattr(row, key, "" if value is None else str(value))
        row.updated_at = utc_now_iso()
        self.session.commit()
        return OutreachEntry.model_validate(row)

    # -- jobs ---------------------------------------------------------------

    def find_job(self, stage: str, lead_id: str) -> PipelineJob | None:
        row = self.session.scalar(
            select(JobORM).where(JobORM.stage == stage, JobORM.lead_id == lead_id)
        )
        return PipelineJob.model_validate(row) if row is not None else None

    def list_jobs(self, lead_id: str) -> list[PipelineJob]:
        rows = self.session.scalars(
            select(JobORM).where(JobORM.lead_id == lead_id).order_by(JobORM.created_at)
        ).all()
        return [PipelineJob.model_validate(row) for row in rows]

    def enqueue(
        self,
        stage: str,
        lead_id: str,
        username: str,
        username_normalized: str,
        *,
        payload: str = "",
        priority: int = 0,
        max_attempts: int = 3,
        on_duplicate: str = "skip",
    ) -> tuple[bool, PipelineJob]:
        existing = self.find_job(stage, lead_id)
        now = utc_now_iso()
        if existing is not None:
            if on_duplicate == "reenqueue" and existing.status in (
                constants.JOB_DONE,
                constants.JOB_ERROR,
                constants.JOB_RETRY,
            ):
                row = self.session.get(JobORM, existing.job_id)
                row.status = constants.JOB_QUEUED
                row.attempt_count = 0
                row.run_after = ""
                row.last_error = ""
                row.result = ""
                row.locked_at = ""
                row.locked_by = ""
                row.payload = payload
                row.updated_at = now
                self.session.commit()
                return (False, PipelineJob.model_validate(row))
            return (False, existing)

        row = JobORM(
            job_id=new_job_id(),
            stage=stage,
            lead_id=lead_id,
            username=username,
            username_normalized=username_normalized,
            status=constants.JOB_QUEUED,
            attempt_count=0,
            max_attempts=max_attempts,
            priority=priority,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.find_job(stage, lead_id)
            if existing is not None:
                return (False, existing)
            raise
        return (True, PipelineJob.model_validate(row))

    def claim_next(
        self, *, worker_id: str = "", now: str | None = None
    ) -> PipelineJob | None:
        """Claim the highest-priority eligible job (single-worker MVP)."""
        current = now or utc_now_iso()
        row = self.session.scalar(
            select(JobORM)
            .where(
                JobORM.status.in_(constants.JOB_ACTIVE_STATUSES),
                or_(JobORM.run_after == "", JobORM.run_after <= current),
            )
            .order_by(JobORM.priority.desc(), JobORM.created_at.asc(), JobORM.job_id.asc())
            .limit(1)
        )
        if row is None:
            return None
        row.status = constants.JOB_RUNNING
        row.attempt_count += 1
        row.locked_at = current
        row.locked_by = worker_id
        row.updated_at = current
        self.session.commit()
        return PipelineJob.model_validate(row)

    def complete(self, job: PipelineJob, result: str = "") -> None:
        row = self.session.get(JobORM, job.job_id)
        if row is None:
            return
        row.status = constants.JOB_DONE
        row.result = result[:1000]
        row.last_error = ""
        row.locked_at = ""
        row.locked_by = ""
        row.run_after = ""
        row.updated_at = utc_now_iso()
        self.session.commit()

    def fail(
        self,
        job: PipelineJob,
        error: str,
        *,
        retryable: bool,
        backoff_base: float = 60.0,
        backoff_max: float = 3600.0,
    ) -> str:
        row = self.session.get(JobORM, job.job_id)
        if row is None:
            return constants.JOB_ERROR
        if retryable and job.attempt_count < job.max_attempts:
            status = constants.JOB_RETRY
            delay = min(backoff_max, backoff_base * (2 ** (max(1, job.attempt_count) - 1)))
            run_after = _iso_after(delay)
        else:
            status = constants.JOB_ERROR
            run_after = ""
        row.status = status
        row.last_error = error[:1000]
        row.run_after = run_after
        row.locked_at = ""
        row.locked_by = ""
        row.updated_at = utc_now_iso()
        self.session.commit()
        return status

    def defer(self, job: PipelineJob, seconds: float = 30.0) -> None:
        """Return a claimed job to the queue without counting a failed attempt.

        Used for dependency-aware scheduling: a stage that must wait for another
        job's terminal state re-queues itself instead of retrying or failing.
        """
        row = self.session.get(JobORM, job.job_id)
        if row is None:
            return
        row.status = constants.JOB_QUEUED
        # Undo the increment performed when the job was claimed.
        row.attempt_count = max(0, job.attempt_count - 1)
        row.run_after = _iso_after(max(0.0, seconds))
        row.last_error = ""
        row.locked_at = ""
        row.locked_by = ""
        row.updated_at = utc_now_iso()
        self.session.commit()

    def recover_stale_jobs(self, stale_after_minutes: int = 30) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=max(0, stale_after_minutes))
        ).replace(microsecond=0).isoformat()
        now = utc_now_iso()
        rows = self.session.scalars(
            select(JobORM).where(JobORM.status == constants.JOB_RUNNING)
        ).all()
        recovered = 0
        for row in rows:
            if row.locked_at and row.locked_at >= cutoff:
                continue
            row.status = constants.JOB_RETRY
            row.run_after = ""
            row.locked_at = ""
            row.locked_by = ""
            row.last_error = "recovered after restart"
            row.updated_at = now
            recovered += 1
        if recovered:
            self.session.commit()
        return recovered

    # -- stats --------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        leads_with_progress = self.list_leads_with_progress()
        leads = [lead for lead, _progress, _remedy in leads_with_progress]

        by_status: dict[str, int] = {}
        for lead in leads:
            by_status[lead.status or "unknown"] = by_status.get(lead.status or "unknown", 0) + 1

        # Truthful counters use the same derived progress as rows/filters (T01).
        by_progress: dict[str, int] = {}
        for _lead, progress, _remedy in leads_with_progress:
            by_progress[progress] = by_progress.get(progress, 0) + 1

        jobs = self.session.scalars(select(JobORM)).all()
        job_status: dict[str, int] = {}
        for job in jobs:
            job_status[job.status] = job_status.get(job.status, 0) + 1

        dossiers = self.session.scalars(select(DossierORM)).all()
        outreach = self.session.scalars(select(OutreachORM)).all()
        return {
            "leads_total": len(leads),
            "leads_by_status": by_status,
            "leads_by_progress": by_progress,
            "jobs_by_status": job_status,
            "dossiers_total": len(dossiers),
            "outreach_total": len(outreach),
            "outreach_needs_review": sum(
                1
                for row in outreach
                if (row.status or "").upper() == constants.AI_STATUS_NEEDS_REVIEW
            ),
        }


def dossier_from_json_scores(raw: str) -> dict[str, int]:
    """Utility kept for parity with the old Sheets layer (unused by core paths)."""
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return {str(k): int(v) for k, v in data.items()}
