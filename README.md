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
├─ extension/         Chrome MV3 lead-capture extension (Phase 8)
├─ backend/           FastAPI app + background worker (Python)
│  ├─ app/
│  │  ├─ config.py    Settings loaded from environment
│  │  ├─ main.py      FastAPI app (health + lead API)
│  │  ├─ worker/      Autonomous worker: poll/claim/run stages (Phase 4)
│  │  ├─ common/      Shared helpers (retry)
│  │  ├─ leads/       Lead API: validation, service, routes (Phase 2)
│  │  ├─ providers/   HikerAPI client + normalization (Phase 3)
│  │  └─ sheets/      Google Sheets storage layer (Phase 1)
│  └─ requirements.txt
├─ docs/
│  ├─ architecture.md      Proposed architecture, data flow, phase boundaries
│  ├─ sheets-contract.md   Google Sheets tab schemas and setup
│  ├─ api.md               Lead API reference (Phase 2)
│  ├─ hikerapi.md          HikerAPI provider reference (Phase 3)
│  ├─ worker.md            Autonomous worker reference (Phase 4)
│  ├─ website-enrichment.md Website crawl + SSRF rules (Phase 5)
│  ├─ gemini.md            Gemini + AI outputs (Phase 6)
│  └─ dashboard.md         Next.js dashboard + access control (Phase 7)
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

## Lead API (Phase 2)

Submit and retrieve leads over HTTP; the browser never accesses Google Sheets
directly. See [docs/api.md](docs/api.md) for the full reference.

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
cd ..

# submit a lead (201 new, 200 if it already exists)
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/leads -ContentType application/json -Body '{"username":"@some.creator"}'

# list with pagination/search
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/leads?limit=20&q=crypto&status=queued"
```

Endpoints: `POST /api/v1/leads`, `GET /api/v1/leads`, `GET /api/v1/leads/{leadId}`,
plus `GET /health`. New leads are stored with `status="queued"` for the worker.

## HikerAPI provider (Phase 3)

Typed client for fetching a public Instagram profile (profile fetch +
normalization only). See [docs/hikerapi.md](docs/hikerapi.md).

```powershell
.\backend\.venv\Scripts\python.exe scripts\check_hikerapi.py --username natgeo
```

## Autonomous worker (Phase 4)

Polls the `Pipeline Jobs` tab, claims one job, runs its stage, and persists
progress (idempotent, retry-aware, restart-safe). See [docs/worker.md](docs/worker.md).

Run the API and worker in **separate terminals**:

```powershell
# Terminal A - API
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal B - worker (from backend)
cd backend
.\.venv\Scripts\python.exe -m app.worker          # long-running poller
.\.venv\Scripts\python.exe -m app.worker --drain  # run queued jobs then exit
.\.venv\Scripts\python.exe -m app.worker --once   # process one job
```

One worker and one API instance only (spreadsheet-backed MVP).

## Profile media + website enrichment (Phase 5)

After `profile_fetch`, the worker enqueues two optional stages:

- `profile_media` — bounded recent posts/reels → `Lead Posts` (keyed by `postId`).
- `website_enrich` — SSRF-safe crawl of the profile's links → `Website Pages`
  (keyed by `pageId`), with strict URL validation, size/timeout limits and
  bounded retries. See [docs/website-enrichment.md](docs/website-enrichment.md).

Both are idempotent and never stall the pipeline when data is unavailable
(missing website, blocked URLs, partial failures). Follower lists are never
fetched.

## AI outputs (Phase 6)

Server-side Gemini generation (provider abstraction + `GeminiProvider`), with
structured dossier + qualification scoring and personalized email/DM drafts.
Scraped text is treated as untrusted; outputs are stored in `Dossiers` and
`Outreach` (keyed by `leadId`) and marked `NEEDS_REVIEW` — **nothing is sent**.
See [docs/gemini.md](docs/gemini.md). Disable with `AI_ENABLED=false`.

## Dashboard (Phase 7)

Internal Next.js App Router dashboard (React 19 + TypeScript + Tailwind v4) over
the Python API: searchable leads table, add-lead form, lead detail (profile,
posts, website pages, job history), dossier view, and outreach review with
approve/reject. Server-only API access, a password access gate, and loading /
empty / duplicate / error+retry states. See [docs/dashboard.md](docs/dashboard.md).

```powershell
cd frontend
Copy-Item .env.example .env.local   # set API_BASE_URL, BACKEND_API_KEY, DASHBOARD_PASSWORD
npm run dev                          # http://localhost:3000
```

## Chrome extension (Phase 8)

Minimal MV3 extension that sends the current Instagram profile to the API
(`POST /api/v1/leads`) with clear created/duplicate/error states — no scraping,
no Sheets access, no provider secrets. Load `extension/` unpacked from
`chrome://extensions`. See [extension/README.md](extension/README.md).

```powershell
node --test extension/lib.test.js
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
