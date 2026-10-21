# Autonomous Worker (Phase 4)

`backend/app/worker/` polls the **`pipeline_jobs`** table, claims one eligible
job, runs its stage, persists progress, and repeats. It sends **no external
messages** — only PostgreSQL reads/writes and provider fetches. HikerAPI is
**optional**: a captured snapshot is processed without it (PRD T06).

```text
backend/app/worker/
├─ main.py     Worker class + CLI + signal handling
├─ pipeline.py Stages + StageOutcome
├─ snapshot.py Captured snapshot → lead fields (+ normalization)
├─ __main__.py `python -m app.worker`
└─ __init__.py exports
```

## Stages

| Stage | What it does | Writes | Idempotency key |
| --- | --- | --- | --- |
| `profile_fetch` | Snapshot → lead fields (else HikerAPI when configured); enqueues follow-ups | `leads` | `lead_id` |
| `profile_media` | bounded recent posts/reels | `lead_posts`, lead `media_status` | `post_id` |
| `website_enrich` | SSRF-safe crawl of external links; extracts public emails/phones | `website_pages`, `contacts`, lead `website_status` | `page_id` |
| `ai_dossier` | Gemini creator brief/dossier + qualification score | `dossiers` | `lead_id` |
| `ai_outreach` | Gemini email/DM drafts (`NEEDS_REVIEW`), only when explicitly queued | `outreach_drafts` | `lead_id` |

## Snapshot bypass and optional HikerAPI (T06)

`profile_fetch` is **snapshot-first**:

1. If the lead has a usable `profile_snapshot` (bio, external URLs, or a known
   follower count), the stage populates `leads` from it and **never calls
   HikerAPI**. Bio text is whitespace-normalized only; public business contacts
   (email/phone) are **retained** and visible to authenticated operators (V2-01
   withdrew blanket pre-shortlist masking). Snapshot external URLs enqueue
   `website_enrich`.
2. With no snapshot, HikerAPI is called **only if `HIKERAPI_KEY` is set**.
3. With no snapshot and no key, the job completes without enrichment and the lead
   stays `needs_data` — the worker never silently spends HikerAPI credits.

`profile_media`/`website_enrich` need no HikerAPI data: website research uses the
snapshot's external URLs, and media is explicitly skipped (`media_status=none`)
when no Instagram id is known.

Public emails and phone numbers found on crawled pages are stored in `contacts`
with `type`, `value`, `source_url`, `observed_at`, and `method="website_crawl"`
(V2-04). They are visible to authenticated dashboard users immediately and do not
require a shortlist/fit gate. Recrawls upsert by a deterministic contact id.
Legacy `business_email`/`business_phone_number` rows are backfilled with
`method="legacy"` and labeled "Legacy source unknown".

`profile_fetch` enqueues `profile_media` (when an Instagram id is known) and
`website_enrich` (when the profile has links). The media/website stages are
**optional**: when data is genuinely unavailable they mark a status
(`none`/`blocked`/`error`/`partial`) and still complete the job so the pipeline
keeps moving. See [website-enrichment.md](website-enrichment.md).

When AI is enabled, `profile_fetch` also enqueues `ai_dossier` (low priority so
evidence is gathered first). It does **not** enqueue outreach. See
[gemini.md](gemini.md).

**V2-01 — no unintended work:**

- Dossier completion **never** schedules outreach or draft generation.
- `ai_outreach` runs only when a job is created explicitly; shortlisting and
  contact/draft requests never auto-schedule work beyond the requested record.
- When AI is disabled, `build_stages` registers no-op `AIDisabledStage`s for
  `ai_dossier`/`ai_outreach`, so a queued AI job completes harmlessly instead of
  failing as an unregistered stage. Research, the evidence brief, and the manual
  workflow remain usable.

**Dependency-aware scheduling:** `ai_dossier` and `ai_outreach` do not run until
their required evidence stages (`profile_media`, `website_enrich`, and for
outreach `ai_dossier`) reach a **terminal** state (`done`/`error`). While a
dependency is queued/running/retrying, the AI job is **deferred** — re-queued via
`run_after` without counting a failed attempt — so a temporary retry is never
mistaken for completed evidence (PRD §5.4).

**Manual AI re-processing:** `POST /api/v1/leads/{id}/retry-ai` re-queues
**`ai_dossier` only** with a `{"force": true}` payload. It does not create an
outreach/draft job (V2-01). Draft generation is an explicit, separate request.

## `pipeline_jobs` table

Columns: `job_id` (PK), `stage`, `lead_id`, `username`, `username_normalized`,
`status`, `attempt_count`, `max_attempts`, `priority`, `payload`, `result`,
`last_error`, `locked_at`, `locked_by`, `run_after`, `created_at`, `updated_at`.

- `job_id` — stable key (`job_<uuid hex>`).
- `(stage, lead_id)` — **unique** idempotency key; `enqueue` skips duplicates.
- `status` — `queued` → `running` → `done` | `retry` | `error`.
- `attempt_count` — incremented on claim; retries stop at `max_attempts`.
- `run_after` — earliest time a `queued`/`retry` job may be claimed (backoff).
- `locked_at`/`locked_by` — set while running; used for restart recovery.
- `last_error` / `result` — stored error details and a short success summary.

## Lifecycle

1. The API enqueues a `profile_fetch` job when a lead is submitted (idempotent).
2. The worker claims the highest-priority eligible job (`queued`/`retry` with
   `runAfter` in the past), setting it `running` and incrementing `attemptCount`.
3. The stage runs:
   - **success** → job `done`; the `leads` row is updated.
   - **retryable error** (rate limit, quota, network, bad payload) → job `retry`
     with exponential `run_after`, until `max_attempts` is reached, then `error`.
   - **terminal error** (not found, auth/config, invalid input) → job `error`.
   - **deferred** (dependency not terminal) → job re-queued with `run_after`,
     `attempt_count` unchanged.
4. The worker continues until no work remains (or is stopped).

## Reliability

- **Bounded API calls + retries**: HikerAPI timeouts/backoff (Phase 3); job-level
  retries with exponential backoff.
- **Idempotent stages**: posts/pages/dossiers/outreach are upserted by primary
  key (`created_at` preserved); re-running a job does not duplicate rows.
- **Serialized writes**: each job runs in its own DB session/transaction.
- **Restart recovery**: `recover_stale_jobs` returns `running` jobs whose
  `locked_at` is older than `WORKER_STALE_MINUTES` to `retry`.
- **Heartbeat (T09)**: every poll cycle the worker upserts a single
  `worker_heartbeat` row (`worker_id`, `beat_at`). A heartbeat write failure is
  logged but never stops processing. `GET /api/v1/integrations/status` reports
  `active` (≤60s), `stale` (>60s), or `stopped` (no row).
- **Graceful shutdown**: `SIGINT`/`SIGTERM` set a stop event; the in-flight job
  finishes, then the worker exits.

## Single instance only (MVP)

Run exactly **one** worker and **one** API instance. Job state lives in Postgres
and there is no cross-process lease; multiple writers could double-claim. A
database lease is a later phase.

## Running (two terminals)

Terminal A — API:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal B — worker (run from `backend` so the `app` package resolves):

```powershell
cd backend

# long-running poller (Ctrl+C to stop after the current job)
.\.venv\Scripts\python.exe -m app.worker

# process everything currently queued, then exit
.\.venv\Scripts\python.exe -m app.worker --drain

# process exactly one job and exit
.\.venv\Scripts\python.exe -m app.worker --once

# options: --max-jobs N --poll-interval S --stale-minutes M --worker-id ID
```

## Configuration

See `.env.example`: `WORKER_POLL_INTERVAL` (seconds; a hard **minimum of 5s** is
enforced so an idle worker does not spin; keep it **≤60s** so readiness stays
`active`), `WORKER_STALE_MINUTES`, `PIPELINE_MAX_ATTEMPTS`,
`PIPELINE_RETRY_BACKOFF_BASE_SECONDS`, `PIPELINE_RETRY_BACKOFF_MAX_SECONDS`, and
`DATABASE_URL`. `HIKERAPI_KEY`, `GEMINI_API_KEY`, and `AI_ENABLED` are optional
configuration for those capabilities.

## Tests

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_worker_pipeline.py tests\test_worker_loop.py tests\test_worker_stages_media_website.py tests\test_worker_snapshot.py tests\test_no_unintended_work.py
```

Coverage: enqueue/dedupe, claim, run-after gating, complete/fail with bounded
retries, stale-job recovery, successful profile fetch, not-found (terminal),
quota (retryable), idempotent re-run, unknown stage, drain/max-jobs, graceful
shutdown, restart recovery, media storage/dedupe/skip, website partial/blocked/
missing, downstream enqueue, snapshot bypass, optional HikerAPI fallback,
bio normalization, dependency-aware deferral, no unintended AI/outreach fan-out,
and AI-disabled guard stages.

## Out of scope

No automatic sending of messages. Follower/following lists are never fetched.
Contact-discovery adapters and draft generation requests are separate work
packages (V2-06/V2-07).
