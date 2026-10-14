# Autonomous Worker (Phase 4)

`backend/app/worker/` polls the **`pipeline_jobs`** table, claims one eligible
job, runs its stage, persists progress, and repeats. It sends **no external
messages** — only PostgreSQL reads/writes and (for now) HikerAPI profile
fetches.

```text
backend/app/worker/
├─ main.py     Worker class + CLI + signal handling
├─ pipeline.py Stages (Phase 4: profile_fetch) + StageOutcome
├─ __main__.py `python -m app.worker`
└─ __init__.py exports
```

## Stages

| Stage | What it does | Writes | Idempotency key |
| --- | --- | --- | --- |
| `profile_fetch` | HikerAPI profile → lead fields; enqueues the optional follow-ups | `leads` | `lead_id` |
| `profile_media` | bounded recent posts/reels | `lead_posts`, lead `media_status` | `post_id` |
| `website_enrich` | SSRF-safe crawl of external links | `website_pages`, lead `website_status` | `page_id` |
| `ai_dossier` | Gemini dossier + qualification score | `dossiers` | `lead_id` |
| `ai_outreach` | Gemini email/DM drafts (`NEEDS_REVIEW`) | `outreach_drafts` | `lead_id` |

`profile_fetch` enqueues `profile_media` (when an Instagram id is known) and
`website_enrich` (when the profile has links). The media/website stages are
**optional**: when data is genuinely unavailable they mark a status
(`none`/`blocked`/`error`/`partial`) and still complete the job so the pipeline
keeps moving. See [website-enrichment.md](website-enrichment.md).

When AI is enabled, `profile_fetch` also enqueues `ai_dossier` (low priority so
evidence is gathered first), and `ai_dossier` enqueues `ai_outreach`. Both are
idempotent and store `NEEDS_REVIEW` outputs; nothing is sent. See
[gemini.md](gemini.md).

**Manual AI re-processing:** `POST /api/v1/leads/{id}/retry-ai` re-queues
`ai_dossier` (priority 10) and `ai_outreach` (priority 5) with a
`{"force": true}` payload, so the stages regenerate rather than skip the existing
output. Profile/media/website jobs are left untouched.

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
   - **success** → job `done`; the `leads` row is updated (profile fields,
     `status=enriched`).
   - **retryable error** (rate limit, quota, network, bad payload) → job `retry`
     with exponential `run_after`, until `max_attempts` is reached, then `error`.
   - **terminal error** (not found, auth/config, invalid input) → job `error`.
4. The worker continues until no work remains (or is stopped).

## Reliability

- **Bounded API calls + retries**: HikerAPI timeouts/backoff (Phase 3); job-level
  retries with exponential backoff.
- **Idempotent stages**: posts/pages/dossiers/outreach are upserted by primary
  key (`created_at` preserved); re-running a job does not duplicate rows.
- **Serialized writes**: each job runs in its own DB session/transaction.
- **Restart recovery**: `recover_stale_jobs` returns `running` jobs whose
  `locked_at` is older than `WORKER_STALE_MINUTES` to `retry`.
- **Graceful shutdown**: `SIGINT`/`SIGTERM` set a stop event; the in-flight job
  finishes, then the worker exits.

## Single instance only (MVP)

Run exactly **one** worker and **one** API instance. Job state lives in Postgres
and there is no cross-process lease; multiple writers could double-claim. A
Sheets-based lease is a later phase.

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
enforced so an idle worker does not spin), `WORKER_STALE_MINUTES`,
`PIPELINE_MAX_ATTEMPTS`, `PIPELINE_RETRY_BACKOFF_BASE_SECONDS`,
`PIPELINE_RETRY_BACKOFF_MAX_SECONDS`, and `DATABASE_URL`.

## Tests

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_jobs_store.py tests\test_worker_pipeline.py tests\test_worker_loop.py tests\test_worker_stages_media_website.py
```

Coverage: enqueue/dedupe, claim, run-after gating, complete/fail with bounded
retries, stale-job recovery, successful profile fetch, not-found (terminal),
quota (retryable), idempotent re-run, unknown stage, drain/max-jobs, graceful
shutdown, restart recovery, media storage/dedupe/skip, website partial/blocked/
missing, and downstream enqueue.

## Out of scope (Phase 5)

No Gemini generation and no sending of any external messages. Followers/following
lists are never fetched.
