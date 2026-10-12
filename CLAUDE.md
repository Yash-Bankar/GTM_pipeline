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

# Frontend
cd frontend; npm run lint; npx tsc --noEmit; npm run build
```

## Definition of done (per change)

- Runs locally with the commands above.
- No secrets added; `.env.example` reflects any new required variables.
- `frontend`: `npm run lint` and `npx tsc --noEmit` pass.
- `backend`: `pytest` passes (once tests exist).
- Docs updated when behavior or contracts change.
