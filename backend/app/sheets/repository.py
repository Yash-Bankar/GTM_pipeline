"""Repository layer over a spreadsheet.

`SheetStore` provides schema-driven, header-name-based read/write access to the
configured tabs. All mutating operations are serialized through a single
in-process lock: the MVP assumes one backend instance and one worker, so
concurrent writers are avoided by design.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.constants import (
    JOB_ACTIVE_STATUSES,
    JOB_DONE,
    JOB_ERROR,
    JOB_QUEUED,
    JOB_RETRY,
    JOB_RUNNING,
)

from .client import GoogleSheetsClient, SheetsClient
from .errors import (
    DuplicateLeadError,
    SchemaError,
    SheetTabMissingError,
    SheetsNotFoundError,
)
from .models import Lead, PipelineJob, SheetModel
from .schemas import (
    KEY_DEDUP,
    KEY_DOSSIERS,
    KEY_ENRICHED,
    KEY_IG_LEADS,
    KEY_JOBS,
    KEY_OUTREACH,
    KEY_POSTS,
    KEY_WEBSITE_PAGES,
    SCHEMAS,
    SheetSchema,
    normalize_username,
    schema_for,
)
from .util import new_job_id, new_lead_id, stringify, utc_now_iso

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RowRecord:
    """A single data row with its 1-based sheet row number and header mapping."""

    row_number: int
    values: dict[str, str]


@dataclass
class TabLayout:
    """The live layout of a tab: its configured schema plus the header row found."""

    schema: SheetSchema
    tab: str
    headers: list[str]

    @property
    def header_index(self) -> dict[str, int]:
        index: dict[str, int] = {}
        for position, name in enumerate(self.headers):
            if name and name not in index:
                index[name] = position
        return index

    def missing_headers(self) -> list[str]:
        present = set(self.headers)
        return [name for name in self.schema.headers if name not in present]

    def extra_headers(self) -> list[str]:
        known = set(self.schema.headers)
        return [name for name in self.headers if name and name not in known]


@dataclass
class SchemaReport:
    """Outcome of ensuring a tab's schema exists and is correct."""

    key: str
    tab: str
    ok: bool
    created: bool = False
    header_written: bool = False
    missing_headers: list[str] = field(default_factory=list)
    extended_headers: list[str] = field(default_factory=list)
    note: str = ""


def tab_names_from_settings(settings: Settings) -> dict[str, str]:
    return {
        KEY_IG_LEADS: settings.google_sheets_ig_leads_tab,
        KEY_DEDUP: settings.google_sheets_dedup_tab,
        KEY_ENRICHED: settings.google_sheets_enriched_tab,
        KEY_OUTREACH: settings.google_sheets_outreach_tab,
        KEY_JOBS: settings.google_sheets_jobs_tab,
        KEY_POSTS: settings.google_sheets_posts_tab,
        KEY_WEBSITE_PAGES: settings.google_sheets_website_pages_tab,
        KEY_DOSSIERS: settings.google_sheets_dossiers_tab,
    }


class SheetStore:
    """Schema-driven storage for one spreadsheet."""

    def __init__(
        self,
        client: SheetsClient,
        *,
        tab_names: dict[str, str] | None = None,
        schemas: dict[str, SheetSchema] | None = None,
        mutation_lock: threading.RLock | None = None,
    ) -> None:
        self._client = client
        self._tab_names = dict(tab_names or {})
        self._schemas = dict(schemas or SCHEMAS)
        self._lock = mutation_lock or threading.RLock()

    # -- construction -------------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Settings) -> "SheetStore":
        client = GoogleSheetsClient.from_settings(settings)
        return cls(client, tab_names=tab_names_from_settings(settings))

    # -- schema / layout ----------------------------------------------------

    def schema(self, key: str) -> SheetSchema:
        return self._schemas[key] if key in self._schemas else schema_for(key)

    def tab_name(self, key: str) -> str:
        return self._tab_names.get(key) or self.schema(key).default_tab

    def get_layout(self, key: str) -> TabLayout:
        """Load a tab's live layout, raising if the tab or header row is absent."""
        schema = self.schema(key)
        tab = self.tab_name(key)
        titles = self._client.list_tab_titles()
        if tab not in titles:
            raise SheetTabMissingError(
                f"Tab '{tab}' not found in the spreadsheet (available: {titles})."
            )
        headers = self._client.read_row(tab, 1)
        if not any((h or "").strip() for h in headers):
            raise SchemaError(f"Tab '{tab}' has no header row.")
        return TabLayout(schema=schema, tab=tab, headers=[h.strip() for h in headers])

    def list_tab_titles(self) -> list[str]:
        return self._client.list_tab_titles()

    def ensure_schema(
        self,
        key: str,
        *,
        create_missing: bool = True,
        extend_headers: bool = False,
    ) -> SchemaReport:
        """Make a tab usable without destroying existing headers or data.

        - Missing tab: created (only if ``create_missing``) with the full header row.
        - Empty tab: the full header row is written.
        - Missing required headers: reported. They are only appended when
          ``extend_headers`` is True, and never overwrite existing cells.
        """
        with self._lock:
            schema = self.schema(key)
            tab = self.tab_name(key)
            titles = self._client.list_tab_titles()

            if tab not in titles:
                if not create_missing:
                    return SchemaReport(
                        key=key,
                        tab=tab,
                        ok=False,
                        missing_headers=list(schema.headers),
                        note="tab does not exist",
                    )
                self._client.create_tab(tab)
                self._client.append_rows(tab, [list(schema.headers)])
                logger.info("Created tab '%s' with %s headers", tab, len(schema.headers))
                return SchemaReport(
                    key=key, tab=tab, ok=True, created=True, header_written=True
                )

            headers = [h.strip() for h in self._client.read_row(tab, 1)]
            if not any(headers):
                self._client.append_rows(tab, [list(schema.headers)])
                return SchemaReport(
                    key=key, tab=tab, ok=True, header_written=True, created=False
                )

            present = set(headers)
            missing = [name for name in schema.headers if name not in present]
            if not missing:
                return SchemaReport(key=key, tab=tab, ok=True)

            if not extend_headers:
                return SchemaReport(
                    key=key,
                    tab=tab,
                    ok=False,
                    missing_headers=missing,
                    note="missing headers; pass extend_headers to append them",
                )

            extended = self._append_missing_headers(tab, headers, missing)
            remaining = [name for name in missing if name not in set(extended)]
            return SchemaReport(
                key=key,
                tab=tab,
                ok=not remaining,
                missing_headers=remaining,
                extended_headers=extended,
                note="headers extended without touching existing cells",
            )

    def _append_missing_headers(
        self, tab: str, existing: list[str], missing: list[str]
    ) -> list[str]:
        """Fill blank header cells then append the rest; never overwrite values."""
        updates: list[tuple[int, int, str]] = []
        extended: list[str] = []
        working = list(existing)

        for name in missing:
            blank = next((i for i, h in enumerate(working) if not h), None)
            if blank is not None:
                working[blank] = name
                updates.append((1, blank, name))
            else:
                column = len(working)
                working.append(name)
                updates.append((1, column, name))
            extended.append(name)

        if updates:
            self._client.update_cells(tab, updates)
            logger.info("Extended tab '%s' headers: %s", tab, extended)
        return extended

    # -- reads --------------------------------------------------------------

    def read_rows(self, key: str) -> list[RowRecord]:
        """Return all non-empty data rows as header-mapped dicts."""
        layout = self.get_layout(key)
        values = self._client.read_tab(layout.tab)
        if not values:
            return []

        header = [str(h).strip() for h in values[0]]
        records: list[RowRecord] = []
        for offset, row in enumerate(values[1:], start=2):
            if not any(str(cell).strip() for cell in row):
                continue
            data: dict[str, str] = {}
            for column, name in enumerate(header):
                if not name:
                    continue
                data[name] = stringify(row[column]) if column < len(row) else ""
            records.append(RowRecord(row_number=offset, values=data))
        return records

    def read_models(self, key: str) -> list[SheetModel]:
        schema = self.schema(key)
        return [schema.model.model_validate(rec.values) for rec in self.read_rows(key)]

    def find_row(
        self, key: str, key_value: str, *, key_header: str | None = None
    ) -> RowRecord | None:
        layout = self.get_layout(key)
        target = key_header or layout.schema.key_header
        for record in self.read_rows(key):
            if record.values.get(target) == key_value:
                return record
        return None

    # -- writes (serialized) ------------------------------------------------

    def append_model(self, key: str, model: SheetModel) -> None:
        with self._lock:
            layout = self.get_layout(key)
            row = self._model_to_row(layout, model)
            self._client.append_rows(layout.tab, [row])

    def append_models(self, key: str, models: list[SheetModel]) -> None:
        if not models:
            return
        with self._lock:
            layout = self.get_layout(key)
            rows = [self._model_to_row(layout, model) for model in models]
            self._client.append_rows(layout.tab, rows)

    def upsert_model(
        self, key: str, model: SheetModel, *, key_header: str | None = None
    ) -> bool:
        """Insert or update a row keyed by ``key_header``; returns True if appended.

        Only columns known to the model are written, so unknown/extra columns in
        the sheet are preserved. Idempotent: re-running with the same values is a
        no-op write.
        """
        with self._lock:
            layout = self.get_layout(key)
            target_header = key_header or layout.schema.key_header
            dumped = model.model_dump(by_alias=True)
            key_value = stringify(dumped.get(target_header, ""))
            row_number = (
                self._find_row_number(layout, target_header, key_value)
                if key_value
                else None
            )

            index = layout.header_index
            if row_number is None:
                self._client.append_rows(layout.tab, [self._model_to_row(layout, model)])
                return True

            updates = [
                (row_number, index[header], stringify(value))
                for header, value in dumped.items()
                if header in index
            ]
            self._client.update_cells(layout.tab, updates)
            return False

    def update_by_key(
        self,
        key: str,
        key_value: str,
        fields: dict[str, object],
        *,
        key_header: str | None = None,
        touch_updated_at: bool = True,
    ) -> None:
        """Update only the named columns of the row matching ``key_value``.

        Unknown header names are ignored. The row is never rewritten wholesale,
        so unrelated/unknown columns are preserved.
        """
        with self._lock:
            layout = self.get_layout(key)
            target_header = key_header or layout.schema.key_header
            row_number = self._find_row_number(layout, target_header, key_value)
            if row_number is None:
                raise SheetsNotFoundError(
                    f"No row in '{layout.tab}' where {target_header}={key_value!r}."
                )

            index = layout.header_index
            updates: list[tuple[int, int, str]] = []
            for header, value in fields.items():
                column = index.get(header)
                if column is None:
                    logger.debug(
                        "Skipping unknown header %r for tab '%s'", header, layout.tab
                    )
                    continue
                updates.append((row_number, column, stringify(value)))

            if touch_updated_at and "updatedAt" in index and "updatedAt" not in fields:
                updates.append((row_number, index["updatedAt"], utc_now_iso()))

            self._client.update_cells(layout.tab, updates)

    # -- helpers ------------------------------------------------------------

    def _model_to_row(self, layout: TabLayout, model: SheetModel) -> list[str]:
        dumped = model.model_dump(by_alias=True)
        return [stringify(dumped.get(header, "")) for header in layout.headers]

    def _find_row_number(
        self, layout: TabLayout, key_header: str, key_value: str
    ) -> int | None:
        column = layout.header_index.get(key_header)
        if column is None:
            raise SchemaError(
                f"Key header '{key_header}' is missing from tab '{layout.tab}'."
            )
        values = self._client.read_tab(layout.tab)
        for offset, row in enumerate(values[1:], start=2):
            if column < len(row) and stringify(row[column]) == key_value:
                return offset
        return None


class LeadStore(SheetStore):
    """`SheetStore` specialized for the canonical `IG Leads` tab."""

    SCHEMA_KEY = KEY_IG_LEADS

    def find_by_username(self, username: str) -> Lead | None:
        normalized = normalize_username(username)
        if not normalized:
            return None
        for record in self.read_rows(self.SCHEMA_KEY):
            candidate = normalize_username(
                record.values.get("usernameNormalized")
                or record.values.get("username", "")
            )
            if candidate == normalized:
                return Lead.model_validate(record.values)
        return None

    def is_duplicate(self, username: str) -> bool:
        return self.find_by_username(username) is not None

    def create_lead(
        self,
        username: str,
        *,
        source: str = "",
        status: str = "new",
        profile_url: str | None = None,
        on_duplicate: str = "error",
    ) -> Lead:
        """Create a lead with a fresh ``leadId`` and normalized username.

        ``on_duplicate``: ``"error"`` (default) raises ``DuplicateLeadError``;
        ``"return"`` returns the existing lead.
        """
        normalized = normalize_username(username)
        if not normalized:
            raise ValueError("username is required")

        with self._lock:
            existing = self.find_by_username(normalized)
            if existing is not None:
                if on_duplicate == "return":
                    return existing
                raise DuplicateLeadError(
                    f"A lead with username '{normalized}' already exists "
                    f"(leadId={existing.lead_id})."
                )

            now = utc_now_iso()
            lead = self._build_lead(
                username,
                normalized,
                source=source,
                status=status,
                profile_url=profile_url,
                now=now,
            )
            self.append_model(self.SCHEMA_KEY, lead)
            logger.info("Created lead %s (@%s)", lead.lead_id, normalized)
            return lead

    def create_or_get_lead(
        self,
        username: str,
        *,
        source: str = "",
        status: str = "new",
        profile_url: str | None = None,
    ) -> tuple[bool, Lead]:
        """Atomically create a lead or return the existing one.

        Returns ``(created, lead)``. The duplicate check and append happen under
        the store's write lock, so concurrent submissions cannot both create the
        same username.
        """
        normalized = normalize_username(username)
        if not normalized:
            raise ValueError("username is required")

        with self._lock:
            existing = self.find_by_username(normalized)
            if existing is not None:
                return (False, existing)
            lead = self._build_lead(
                username,
                normalized,
                source=source,
                status=status,
                profile_url=profile_url,
                now=utc_now_iso(),
            )
            self.append_model(self.SCHEMA_KEY, lead)
            logger.info("Created lead %s (@%s)", lead.lead_id, normalized)
            return (True, lead)

    def _build_lead(
        self,
        username: str,
        normalized: str,
        *,
        source: str,
        status: str,
        profile_url: str | None,
        now: str,
    ) -> Lead:
        return Lead(
            leadId=new_lead_id(),
            username=username.strip().lstrip("@"),
            usernameNormalized=normalized,
            profileUrl=profile_url or f"https://www.instagram.com/{normalized}/",
            status=status,
            source=source,
            createdAt=now,
            updatedAt=now,
        )

    def get_or_create_lead(self, username: str, **kwargs: object) -> Lead:
        return self.create_lead(username, on_duplicate="return", **kwargs)

    @classmethod
    def from_settings(cls, settings: Settings) -> "LeadStore":
        client = GoogleSheetsClient.from_settings(settings)
        return cls(client, tab_names=tab_names_from_settings(settings))


def _iso_after(seconds: float) -> str:
    moment = datetime.now(timezone.utc) + timedelta(seconds=max(0.0, seconds))
    return moment.replace(microsecond=0).isoformat()


def _to_int(value: object) -> int:
    try:
        return int(str(value).strip() or 0)
    except (TypeError, ValueError):
        return 0


class JobStore(SheetStore):
    """Repository for the `Pipeline Jobs` tab.

    Coordinates the worker: enqueue (idempotent per ``(stage, leadId)``), claim
    one eligible job, complete or fail it. Claiming and status transitions happen
    under the shared write lock so a single worker cannot double-claim.
    """

    SCHEMA_KEY = KEY_JOBS

    def find_job(self, stage: str, lead_id: str) -> PipelineJob | None:
        for record in self.read_rows(self.SCHEMA_KEY):
            values = record.values
            if values.get("stage") == stage and values.get("leadId") == lead_id:
                return PipelineJob.model_validate(values)
        return None

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
        """Enqueue a job. Returns ``(created, job)``.

        ``on_duplicate="skip"`` (default) returns the existing job unchanged.
        ``on_duplicate="reenqueue"`` resets a finished/failed job back to queued.
        """
        with self._lock:
            existing = self.find_job(stage, lead_id)
            if existing is not None:
                if on_duplicate == "reenqueue" and existing.status in (
                    JOB_DONE,
                    JOB_ERROR,
                    JOB_RETRY,
                ):
                    self.update_by_key(
                        self.SCHEMA_KEY,
                        existing.job_id,
                        {
                            "status": JOB_QUEUED,
                            "attemptCount": 0,
                            "runAfter": "",
                            "lastError": "",
                            "result": "",
                            "lockedAt": "",
                            "lockedBy": "",
                        },
                    )
                    existing = self.find_job(stage, lead_id) or existing
                return (False, existing)

            now = utc_now_iso()
            job = PipelineJob(
                jobId=new_job_id(),
                stage=stage,
                leadId=lead_id,
                username=username,
                usernameNormalized=username_normalized,
                status=JOB_QUEUED,
                attemptCount=0,
                maxAttempts=max_attempts,
                priority=priority,
                payload=payload,
                createdAt=now,
                updatedAt=now,
            )
            self.append_model(self.SCHEMA_KEY, job)
            logger.info("Enqueued job %s (%s @%s)", job.job_id, stage, username_normalized)
            return (True, job)

    def claim_next(
        self, *, worker_id: str = "", now: str | None = None
    ) -> PipelineJob | None:
        """Atomically claim the highest-priority eligible job, or None."""
        with self._lock:
            layout = self.get_layout(self.SCHEMA_KEY)
            index = layout.header_index
            current = now or utc_now_iso()
            rows = self.read_rows(self.SCHEMA_KEY)

            eligible = [
                record
                for record in rows
                if record.values.get("status") in JOB_ACTIVE_STATUSES
                and (not record.values.get("runAfter") or record.values["runAfter"] <= current)
            ]
            if not eligible:
                return None

            eligible.sort(
                key=lambda record: (
                    -_to_int(record.values.get("priority")),
                    record.values.get("createdAt", ""),
                    record.row_number,
                )
            )
            chosen = eligible[0]
            attempt = _to_int(chosen.values.get("attemptCount")) + 1

            self._client.update_cells(
                layout.tab,
                [
                    (chosen.row_number, index["status"], JOB_RUNNING),
                    (chosen.row_number, index["attemptCount"], str(attempt)),
                    (chosen.row_number, index["lockedAt"], current),
                    (chosen.row_number, index["lockedBy"], worker_id),
                    (chosen.row_number, index["updatedAt"], current),
                ],
            )
            claimed = {**chosen.values, "status": JOB_RUNNING, "attemptCount": attempt,
                       "lockedAt": current, "lockedBy": worker_id, "updatedAt": current}
            return PipelineJob.model_validate(claimed)

    def complete(self, job: PipelineJob, result: str = "") -> None:
        self.update_by_key(
            self.SCHEMA_KEY,
            job.job_id,
            {
                "status": JOB_DONE,
                "result": result[:1000],
                "lastError": "",
                "lockedAt": "",
                "lockedBy": "",
                "runAfter": "",
            },
        )

    def fail(
        self,
        job: PipelineJob,
        error: str,
        *,
        retryable: bool,
        backoff_base: float = 60.0,
        backoff_max: float = 3600.0,
    ) -> str:
        """Record a failed job. Returns the resulting status (retry/error)."""
        if retryable and job.attempt_count < job.max_attempts:
            status = JOB_RETRY
            attempt = max(1, job.attempt_count)
            delay = min(backoff_max, backoff_base * (2 ** (attempt - 1)))
            run_after = _iso_after(delay)
        else:
            status = JOB_ERROR
            run_after = ""
        self.update_by_key(
            self.SCHEMA_KEY,
            job.job_id,
            {
                "status": status,
                "lastError": error[:1000],
                "runAfter": run_after,
                "lockedAt": "",
                "lockedBy": "",
            },
        )
        return status

    def recover_stale_jobs(self, stale_after_minutes: int = 30) -> int:
        """Return interrupted `running` jobs to `retry` (restart recovery)."""
        with self._lock:
            layout = self.get_layout(self.SCHEMA_KEY)
            index = layout.header_index
            now = utc_now_iso()
            cutoff = (
                datetime.now(timezone.utc) - timedelta(minutes=max(0, stale_after_minutes))
            ).replace(microsecond=0).isoformat()

            updates: list[tuple[int, int, str]] = []
            recovered = 0
            for record in self.read_rows(self.SCHEMA_KEY):
                if record.values.get("status") != JOB_RUNNING:
                    continue
                locked_at = record.values.get("lockedAt", "")
                if locked_at and locked_at >= cutoff:
                    continue  # still fresh; another worker may be on it
                updates.extend(
                    [
                        (record.row_number, index["status"], JOB_RETRY),
                        (record.row_number, index["runAfter"], ""),
                        (record.row_number, index["lockedAt"], ""),
                        (record.row_number, index["lockedBy"], ""),
                        (record.row_number, index["lastError"], "recovered after restart"),
                        (record.row_number, index["updatedAt"], now),
                    ]
                )
                recovered += 1

            if updates:
                self._client.update_cells(layout.tab, updates)
                logger.info("Recovered %s stale running job(s)", recovered)
            return recovered

    @classmethod
    def from_settings(cls, settings: Settings) -> "JobStore":
        client = GoogleSheetsClient.from_settings(settings)
        return cls(client, tab_names=tab_names_from_settings(settings))
