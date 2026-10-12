# Autonomous Worker (Phase 4)

`backend/app/worker/` polls the **`Pipeline Jobs`** tab, claims one eligible job,
runs its stage, persists progress, and repeats. It sends **no external
messages** — only Google Sheets reads/writes and (for now) HikerAPI profile
fetches.

```text
backend/app/worker/
├─ main.py     Worker class + CLI + signal handling
├─ pipeline.py Stages (Phase 4: profile_fetch) + StageOutcome
├─ __main__.py `python -m app.worker`
└─ __init__.py exports
```

## `Pipeline Jobs` tab

Header row (contract):

```text
jobId, stage, leadId, username, usernameNormalized, status, attemptCount,
maxAttempts, priority, payload, result, lastError, lockedAt, lockedBy, runAfter,
createdAt, updatedAt
```

- `jobId` — stable key (`job_<uuid hex>`).
- `(stage, leadId)` — logical idempotency key; `enqueue` skips duplicates.
- `status` — `queued` → `running` → `done` | `retry` | `error`.
- `attemptCount` — incremented on claim; retries stop at `maxAttempts`.
- `runAfter` — earliest time a `queued`/`retry` job may be claimed (backoff).
- `lockedAt`/`lockedBy` — set while running; used for restart recovery.
- `lastError` / `result` — stored error details and a short success summary.

## Lifecycle

1. The API enqueues a `profile_fetch` job when a lead is submitted (idempotent).
2. The worker claims the highest-priority eligible job (`queued`/`retry` with
   `runAfter` in the past), setting it `running` and incrementing `attemptCount`.
3. The stage runs:
   - **success** → job `done`; enriched row upserted (by `leadId`) and the IG
     Leads row updated to `enriched`.
   - **retryable error** (rate limit, quota, network, bad payload) → job `retry`
     with exponential `runAfter`, until `maxAttempts` is reached, then `error`.
   - **terminal error** (not found, auth/config, invalid input) → job `error`.
4. The worker continues until no work remains (or is stopped).

## Reliability

- **Bounded API calls + retries**: HikerAPI timeouts/backoff (Phase 3); job-level
  retries with exponential backoff.
- **Idempotent stages**: enriched rows are upserted by `leadId` (`createdAt`
  preserved); re-running a job does not duplicate rows.
- **Batch, serialized writes**: status transitions are single `batchUpdate`
  calls; all stores share one client and one in-process write lock.
- **Restart recovery**: `recover_stale_jobs` returns `running` jobs whose
  `lockedAt` is older than `WORKER_STALE_MINUTES` to `retry`.
- **Graceful shutdown**: `SIGINT`/`SIGTERM` set a stop event; the in-flight job
  finishes, then the worker exits.

## Single instance only (MVP)

Run exactly **one** worker and **one** API instance. Job state lives in Sheets
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

See `.env.example`: `WORKER_POLL_SECONDS`, `WORKER_STALE_MINUTES`,
`PIPELINE_MAX_ATTEMPTS`, `PIPELINE_RETRY_BACKOFF_BASE_SECONDS`,
`PIPELINE_RETRY_BACKOFF_MAX_SECONDS`, `GOOGLE_SHEETS_JOBS_TAB`.

## Tests

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_jobs_store.py tests\test_worker_pipeline.py tests\test_worker_loop.py
```

Coverage: enqueue/dedupe, claim, run-after gating, complete/fail with bounded
retries, stale-job recovery, successful profile fetch, not-found (terminal),
quota (retryable), idempotent re-run, unknown stage, drain/max-jobs, graceful
shutdown, and restart recovery.

## Out of scope (Phase 4)

No recent-media research, no website crawling, no Gemini, no outreach sending.
