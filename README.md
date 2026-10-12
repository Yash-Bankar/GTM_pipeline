# Synpo GTM Automation

Automation for a GTM (go-to-market) pipeline built around Instagram creator
discovery: collect creator handles, deduplicate them, enrich them with public
Instagram + website data, generate personalized outreach with AI, and track every
stage in Google Sheets.

> Status: **foundation only.** This repository currently contains project
> scaffolding, configuration, and documentation. No business logic has been
> implemented yet. See [docs/architecture.md](docs/architecture.md) for the
> proposed architecture and phase boundaries.

## Target stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js (App Router) + React + TypeScript + Tailwind CSS |
| Backend API | Python + FastAPI |
| Background worker | Python (long-running process) |
| Operational data | Google Sheets (source of truth) |
| Instagram data | HikerAPI |
| AI generation | Google Gemini (initially) |
| Agent orchestration | Hermes Agent (later) |
| Persistence | **None** for this MVP — no SQL or NoSQL database |

## Repository layout

```text
synpo-gtm-automation/
├─ frontend/          Next.js app (App Router, TS, Tailwind)
├─ backend/           FastAPI app + background worker (Python)
│  ├─ app/
│  │  ├─ config.py    Settings loaded from environment
│  │  ├─ main.py      FastAPI entrypoint (health check only for now)
│  │  ├─ worker.py    Worker entrypoint (stub for now)
│  │  └─ sheets/      Google Sheets storage layer (Phase 1)
│  └─ requirements.txt
├─ docs/
│  ├─ architecture.md      Proposed architecture, data flow, phase boundaries
│  └─ sheets-contract.md   Google Sheets tab schemas and setup
├─ scripts/           Helper scripts (verify_sheets.py)
├─ tests/             Unit tests (mocked Sheets client)
├─ pytest.ini         Pytest configuration
├─ .env.example       Environment variable template (safe placeholders)
├─ CLAUDE.md          Agent/contributor guidance for this repo
└─ README.md
```

## Getting started (Windows PowerShell)

### 1. Environment variables

```powershell
Copy-Item .env.example .env
# then edit .env and fill in your real values (never commit .env)
```

### 2. Backend (FastAPI)

A virtual environment is already present at `backend\.venv`. If you need to
recreate it:

```powershell
py -3.14 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Run the API (from the `backend` directory so the `app` package resolves):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
cd ..
```

Smoke test:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### 3. Worker (background process)

Run from the `backend` directory so the `app` package resolves:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.worker --once   # single cycle
.\.venv\Scripts\python.exe -m app.worker           # loop (later phases)
cd ..
```

### 4. Frontend (Next.js)

```powershell
cd frontend
npm install          # dependencies are already installed
npm run dev          # http://localhost:3000
```

Quality checks:

```powershell
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

## Google Sheets storage (Phase 1)

Google Sheets is the source of truth; there is no database. The storage adapter
is in `backend/app/sheets/` and maps rows to typed models by header name. See
[docs/sheets-contract.md](docs/sheets-contract.md) for the tab schemas, identity
rules, and the non-destructive header policy.

Run the unit tests (in-memory fake client, no credentials needed):

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
```

Verify your development spreadsheet (requires `secrets/service-account.json` and
`.env`):

```powershell
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --check-only
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --create-missing-tabs --extend-headers
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --write-test-row
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — components, data flow, Google
  Sheets data contract, and the phased implementation plan.
- [CLAUDE.md](CLAUDE.md) — conventions and guardrails for contributors and
  coding agents.

## Ground rules

- **Google Sheets is the single source of truth** for operational data in this MVP.
- **No database** (SQL or NoSQL) is introduced for the MVP.
- **No secrets in code or git.** Use `.env` (gitignored) with `.env.example` as
  the template.
- **Do not copy the legacy repository's architecture.** The old
  `insta_enrichment` project is read-only reference material; only selectively
  refactor small, well-tested pieces (e.g. HikerAPI calls, website enrichment)
  when a phase explicitly calls for it.
