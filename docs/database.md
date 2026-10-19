# Database Contract (PostgreSQL)

PostgreSQL is the **single source of truth** for all operational data. It replaces
the previous Google Sheets adapter entirely (no Sheets API, no service account).

- Engine: SQLAlchemy 2.x (sync) + `psycopg2`.
- Migrations: Alembic (`backend/alembic/`).
- Layer: `backend/app/db/` (`database.py`, `models.py`, `schemas.py`,
  `repository.py`, `util.py`, `errors.py`).

## Configuration

```text
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/synpo
```

Inside Docker Compose the host is the `db` service
(`postgresql+psycopg2://postgres:postgres@db:5432/synpo`). Tests use an
in-memory SQLite database, so no Postgres is needed to run `pytest`.

## Tables

Timestamps (`created_at`, `updated_at`, `locked_at`, `run_after`) are stored as
ISO-8601 UTC **strings** so ordering and the existing string comparisons are
preserved.

### `leads` (PK `lead_id`)
`username`, `username_normalized` (**unique** — the dedupe key), `full_name`,
`instagram_id`, `follower_count`, `follows_count`, `business_category_name`,
`bio`, `business_email`, `business_phone_number`, `profile_url`, `external_url`,
`all_external_urls`, `engagement_rate`, `scraped_at`, `status`, `source`,
`media_status`, `website_status`, `last_error`, `profile_snapshot` (JSON text),
`request_id` (indexed), `fit_status` (`not_reviewed`/`approved`/`rejected`/
`needs_evidence`, indexed), `fit_note`, `fit_decided_at`, timestamps.

### `lead_posts` (PK `post_id`)
`lead_id` → `leads` (cascade), `username`, `username_normalized`, `media_type`,
`product_type`, `short_code`, `url`, `caption`, `like_count`, `comment_count`,
`play_count`, `taken_at`, `fetched_at`, `status`, `last_error`, timestamps.

### `website_pages` (PK `page_id`)
`lead_id` → `leads` (cascade), `username`, `url`, `resolved_url`, `domain`,
`title`, `text`, `links`, `http_status`, `status`, `error`, `fetched_at`,
timestamps. `page_id` is a deterministic hash of `(lead_id, url)`.

### `dossiers` (PK `lead_id`)
`username`, `username_normalized`, `summary`, `topics`, `audience`,
`evidence_urls`, `qualification_score`, `qualification_tier`, `rubric`,
`criterion_scores` (JSON text), `uncertainty`, `model`, `status`, `last_error`,
`generated_at`, timestamps.

### `outreach_drafts` (PK `lead_id`)
`username`, `username_normalized`, `channel`, `status`, `subject`, `body`,
`dm_body`, `model`, `generated_at`, `last_error`, timestamps.

### `pipeline_jobs` (PK `job_id`, **unique `(stage, lead_id)`**)
`stage`, `lead_id` → `leads` (cascade), `username`, `username_normalized`,
`status` (`queued`/`running`/`retry`/`done`/`error`), `attempt_count`,
`max_attempts`, `priority`, `payload`, `result`, `last_error`, `locked_at`,
`locked_by`, `run_after`, timestamps.

### `contact_requests` (PK `request_id`) — T08
`lead_id` → `leads` (cascade), `status` (`requested`/...), `note`,
`requested_at`, timestamps. Created only after `leads.fit_status = approved`.

### `outreach_revisions` (PK `revision_id`) — T08
`lead_id` → `leads` (cascade), `channel` (`email`/`instagram_dm`), `status`,
`subject`, `body`, `dm_body`, `requested_at`, timestamps. One row per explicit
draft request, so history is preserved.

### `worker_heartbeat` (PK `heartbeat_id`, singleton `worker`) — T09
`worker_id`, `beat_at` (indexed), `updated_at`. Touched by the worker each poll
cycle; the readiness endpoint reports `active` (≤60s), `stale` (>60s), or
`stopped` (no row).

## Contracts preserved

- **Identity:** `lead_id` (`ld_<uuid hex>`) is the stable key; `job_id`
  (`job_<uuid hex>`) for jobs.
- **Deduplication:** usernames are normalized (lowercase, `@`/URL stripped) into
  `username_normalized`, which has a **unique index**; `create_or_get_lead`
  returns the existing lead on conflict.
- **Idempotent enqueue:** the unique `(stage, lead_id)` constraint plus
  `on_duplicate="skip"|"reenqueue"` mirrors the old behaviour.
- **Claim/complete/fail/recover:** identical semantics (priority-ordered claim,
  bounded retries with exponential backoff, stale-running recovery).
- **Upserts:** posts/pages/dossiers/outreach upsert by primary key; `created_at`
  is preserved on update.

## Migrations

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head          # apply
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "message"  # new revision
```

`alembic/env.py` reads `DATABASE_URL` from settings and loads `Base.metadata`
from `app.db.models`.

## Tests

Repository tests run against in-memory SQLite (`tests/conftest.py`), so they are
fast and require no external services.
