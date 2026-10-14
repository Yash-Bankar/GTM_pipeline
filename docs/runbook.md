# End-to-End Runbook

Step-by-step verification of the complete pipeline, from capture to outreach
review, on the PostgreSQL-backed stack. Run from the repository root.

## 0. Preconditions

- Python 3.14 venv at `backend/.venv`; Node 20.9+ for the frontend; Docker
  (optional, recommended) for Postgres and the container smoke test.
- A PostgreSQL 15+ database (local, Docker, or managed).
- HikerAPI key (profile/media) and, optionally, a Gemini key (AI stages).

## 1. Configure

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

Set at minimum in `.env`:
`DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/synpo`,
`HIKERAPI_KEY`, `API_KEY`, and `GEMINI_API_KEY` (or `AI_ENABLED=false`).
In `frontend/.env.local`: `API_BASE_URL=http://127.0.0.1:8000`,
`BACKEND_API_KEY=<same as API_KEY>`, `DASHBOARD_PASSWORD=<choose one>`.

## 2. Install dependencies

```powershell
py -3.14 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..
```

## 3. Unit tests (fast; in-memory SQLite, no network)

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
node --test extension/lib.test.js
cd frontend; npm run lint; npx tsc --noEmit; npm run build; cd ..
```

## 4. Apply migrations and verify the database

```powershell
# start Postgres if needed
docker run --name synpo-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=synpo -p 5432:5432 -d postgres:15-alpine

cd backend; .\.venv\Scripts\python.exe -m alembic upgrade head; cd ..
.\backend\.venv\Scripts\python.exe scripts\verify_db.py
```

Expected: `verify_db.py` prints the six tables and `OK`.

Optional provider checks:

```powershell
.\backend\.venv\Scripts\python.exe scripts\check_hikerapi.py --username natgeo
.\backend\.venv\Scripts\python.exe scripts\check_gemini.py
```

## 5. Start the stack (three terminals)

```powershell
# A - API
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# B - worker
cd backend; .\.venv\Scripts\python.exe -m app.worker
# C - dashboard
cd frontend; npm run dev
```

Health: `Invoke-RestMethod http://127.0.0.1:8000/health` → `{"status":"ok",...}`.

## 6. Capture a lead

- **Dashboard**: http://localhost:3000 → log in (if `DASHBOARD_PASSWORD` set) →
  **Leads** → add `@some.creator` or an `instagram.com` URL.
- **Extension**: load `extension/` unpacked, set API URL/key, open a profile,
  click **Add to GTM**.

Expected: a `leads` row with `status=queued`; a `profile_fetch` job in
`pipeline_jobs`; the dashboard shows the lead.

## 7. Run the pipeline

The worker (Terminal B) polls automatically. To drive it manually:

```powershell
cd backend; .\.venv\Scripts\python.exe -m app.worker --drain
```

Expected progression (worker logs + tables):

| Stage | Writes | Lead fields |
| --- | --- | --- |
| `profile_fetch` | `leads` profile fields | `status=enriched` (or `not_found`/`error`) |
| `profile_media` | `lead_posts` | `media_status` = done/none/error |
| `website_enrich` | `website_pages` | `website_status` = done/partial/none/blocked/error |
| `ai_dossier` | `dossiers` (`NEEDS_REVIEW`) | — |
| `ai_outreach` | `outreach_drafts` (`NEEDS_REVIEW`) | — |

## 8. Review outputs

- **Lead detail** (`/leads/<leadId>`): profile, recent posts, website pages, job
  history; use **Re-queue processing** to retry.
- **Dossiers** (`/dossiers/<leadId>`): summary, topics, criterion scores,
  qualification tier, cited source links, uncertainty.
- **Outreach** (`/outreach/<leadId>`): edit the email + DM, then **Approve** or
  **Reject**. Nothing is sent.

## 9. Failure drills

| Drill | Action | Expected |
| --- | --- | --- |
| Duplicate | Add the same handle again (dashboard + extension) | `200 created=false`; "already in the pipeline" |
| Invalid URL | Submit `https://example.com/x` or `/p/…` | `422` / "Invalid profile" |
| Auth | Send without / with a wrong `x-api-key` | `401` |
| DB down | Stop Postgres, call the API | `503` "Database is unavailable" |
| Missing website | Lead with no external link | `website_status=none`; pipeline continues |
| Blocked URL | External link to a private host | `website_pages` row `status=blocked` |
| Provider error | Run with an exhausted HikerAPI balance | job → `retry`/`error` with `last_error` |
| Restart recovery | Kill the worker mid-run, restart | stale `running` job returns to `retry` and completes |

## 10. Container smoke test (optional)

```powershell
Copy-Item .env.example .env
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/health
docker compose exec db psql -U postgres -d synpo -c "\dt"
docker compose logs -f worker
docker compose down
```

Expected: Postgres healthy, migrations applied by the API, worker polling with
no crashes.

## 11. Definition of done

- [ ] All unit tests green; frontend builds.
- [ ] Migrations apply cleanly; `verify_db.py` reports `OK`.
- [ ] A submitted lead reaches `enriched` with posts/website evidence recorded.
- [ ] Dossiers and Outreach rows exist as `NEEDS_REVIEW` (when AI enabled).
- [ ] Duplicate, invalid, auth, and DB-down paths behave as above.
- [ ] No secrets committed; `.env` files gitignored.
