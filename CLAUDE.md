# CLAUDE.md

Guidance for contributors and coding agents working in the **Synpo GTM
Automation** repository.

## What this project is

An automation pipeline for a GTM motion around Instagram creators. It collects
handles, deduplicates them, enriches them with public Instagram + website data,
generates AI outreach, and tracks every stage in Google Sheets.

## Orientation (read before coding)

1. Read [docs/architecture.md](docs/architecture.md). It defines the components,
   the data flow, the Google Sheets data contract, and the phased plan.
2. Identify the phase you are working in. **Do not implement work from a later
   phase.** Phase 0 is foundation only.
3. Prefer the smallest change that satisfies the current phase.

## Stack and layout

- `frontend/` — Next.js (App Router) + React + TypeScript + Tailwind CSS.
- `backend/app/main.py` — FastAPI application.
- `backend/app/worker.py` — long-running background worker.
- `backend/requirements.txt` — Python dependencies (backend + worker share one
  virtual environment: `backend/.venv`).
- `docs/`, `scripts/`, `tests/` — documentation, PowerShell helpers, tests.

## Hard rules

- **Google Sheets is the source of truth** for operational data. Do not add a
  SQL/NoSQL database for the MVP.
- **Never commit secrets.** No API keys, tokens, spreadsheet IDs, or service
  account JSON in source. Use `.env` (gitignored). Keep `.env.example` updated
  with placeholder names only.
- **Do not import the legacy architecture.** The old repository at
  `../insta_enrichment` is read-only reference material. It contains a Streamlit
  app, divergent SQLite stores, broken entry points, and an Apps Script pipeline
  that must **not** be copied. Reuse only small, refactored units (e.g. a
  HikerAPI profile fetch or the website email extractor) when a phase explicitly
  requires it, and port them to this repo's conventions.
- **Keep the backend stateless.** API and worker coordinate through Google
  Sheets, not shared process memory or a database.
- **No business logic outside its phase.** Foundation files must stay runnable
  skeletons.

## Next.js version warning

`frontend/` uses a very recent Next.js release whose APIs and conventions may
differ from older material. Before writing frontend code, read
`frontend/AGENTS.md` and the bundled docs under
`frontend/node_modules/next/dist/docs/`. Do not rely on memory of older Next.js
versions.

## Conventions

- Python: type hints on public functions, `from __future__ import annotations`,
  small modules, no global side effects at import time.
- TypeScript: strict mode; keep the App Router structure (`frontend/src/app`).
- Config is read from environment variables via a single settings loader
  (added in Phase 1) — never hardcode environment-specific values.
- Windows-first: provide PowerShell commands in docs and scripts.

## Google Sheets storage rules (Phase 1)

- The Sheets adapter is `backend/app/sheets/`. Tab schemas, identity rules, and
  the non-destructive header policy are in
  [docs/sheets-contract.md](docs/sheets-contract.md).
- Map rows by **header name**, never by fixed column index.
- `leadId` is the stable internal identifier; `usernameNormalized` is the dedup
  key. Use `LeadStore.create_lead(...)` rather than writing rows by hand.
- Never overwrite an existing header row or unrelated cells; use targeted,
  header-named updates.
- One backend instance / one worker only: mutations are serialized in-process.
  Do not add a concurrent job claimer until a Sheets-based lease exists.
- Do not call HikerAPI, Gemini, or scrape websites from the storage layer.

## Lead API rules (Phase 2)

- The API is `backend/app/leads/` + `backend/app/main.py`; reference in
  [docs/api.md](docs/api.md).
- The browser/frontend must never call Google Sheets directly — only this API.
- Validate and normalize usernames via `app/leads/validation.py`; reject
  non-Instagram URLs and invalid handles with `422`.
- Deduplicate by normalized username and return a clear `created` true/false. Use
  `LeadStore.create_or_get_lead(...)`, which checks and appends under the write
  lock — do not hand-roll find-then-create.
- Assign the stable `leadId` in the store, never in the route handler.
- New leads are enqueued by setting `status="queued"`; do not start scraping/AI.
- Keep request/response models typed (`app/leads/schemas.py`).
- Map storage failures to HTTP via the handlers in `main.py` (503 config/quota,
  502 other Sheets errors).

## External provider rules (Phase 3)

- Providers live in `backend/app/providers/`; HikerAPI reference in
  [docs/hikerapi.md](docs/hikerapi.md).
- Use the current documented endpoint/header:
  `GET /v2/user/by/username` with `x-access-key`; keys stay server-side and are
  never logged or returned.
- Return typed models (`HikerProfile`); never let raw provider field names leak
  past `parse_profile_payload`.
- Validate input (`parse_lead_input`) before making any HTTP call.
- Configure timeouts and bounded retries; reuse `app.common.retry.call_with_retry`.
- Raise the typed `HikerAPI*` errors; do not swallow them.
- Phase 3 scope: profile fetch + normalization only. Do not add recent-media
  research, website crawling, or Gemini here.

## Commands

```powershell
# Backend API (dev)
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir backend

# Backend health smoke test
Invoke-RestMethod http://127.0.0.1:8000/health

# Worker (run from backend/ so the app package resolves)
cd backend; .\.venv\Scripts\python.exe -m app.worker --once; cd ..

# Python tests
.\backend\.venv\Scripts\python.exe -m pytest

# Sheets storage integration check (needs .env + service account)
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --check-only

# HikerAPI manual profile check (needs HIKERAPI_KEY)
.\backend\.venv\Scripts\python.exe scripts\check_hikerapi.py --username natgeo

# Frontend
cd frontend; npm run lint; npx tsc --noEmit; npm run build
```

## Definition of done (per change)

- Runs locally with the commands above.
- No secrets added; `.env.example` reflects any new required variables.
- `frontend`: `npm run lint` and `npx tsc --noEmit` pass.
- `backend`: `pytest` passes (once tests exist).
- Docs updated when behavior or contracts change.
