# Synpo GTM Automation

A modern, containerized go-to-market (GTM) pipeline for Instagram creator
discovery. Capture creator handles, enrich them with public Instagram + website
data, generate AI dossiers and personalized outreach, and manage everything from
a Next.js console — with **PostgreSQL as the single source of truth**.

> **Status: v1.1 redesign implemented.** The pipeline is **snapshot-first**: the
> Chrome extension captures a public DOM snapshot so a lead can be processed
> **without HikerAPI**, HikerAPI remains an explicitly configured optional
> provider, and the console shows verified badges, precision-aware counts, and
> honest progress. Lead capture, the autonomous worker, website research,
> Gemini dossiers/outreach, the Next.js console, the extension, and the
> container deployment are implemented. PostgreSQL (SQLAlchemy + Alembic) is the
> single source of truth.
>
> See [IMPLEMENTATION_REPORT_v1.1.md](IMPLEMENTATION_REPORT_v1.1.md) for the
> as-built mapping against the redesign PRD (T00–T07), including intentional
> deviations.

---

## Screenshots
<img width="1919" height="902" alt="image" src="https://github.com/user-attachments/assets/8e1f8226-b1ec-48ad-a45c-28138f51a831" />
<img width="1858" height="320" alt="image" src="https://github.com/user-attachments/assets/b046740c-3b02-4cc7-be92-d780c91bdadd" />



## 1. Overview & Architecture

Synpo GTM is a small, opinionated stack:

- **FastAPI backend** (`:8000`) — the only component that touches the database;
  validates/normalizes leads, exposes read + action endpoints, and enqueues work.
- **Python autonomous worker** — polls the job table, runs pipeline stages, and
  persists progress. Idempotent, retry-aware, restart-safe. **One instance.**
  `profile_fetch` is **snapshot-first**; HikerAPI is used only when no snapshot
  exists and credentials are configured.
- **PostgreSQL 15** — durable state for leads, posts, website pages, dossiers,
  outreach drafts, and the job queue. Schema is managed by **Alembic**.
- **Next.js GTM Console** (`:3000`) — leads table, lead detail, dossiers, and
  outreach review (approve/reject), with an Aurora background and glass panels.
  Shows verified badges, precision-aware counts, and explicit missing fields.
- **Google Gemini** — structured dossiers + qualification scoring and email/DM
  outreach drafts (review-only; nothing is sent). Reviewed drafts are never
  overwritten by a rerun.
- **Chrome extension (MV3)** — zero-cost public **DOM snapshot** capture from the
  open Instagram profile, plus an **"Add All Verified"** batch scanner for the
  "Suggested for you" rail. No compulsory HikerAPI.

### Data flow

```text
        ┌───────────────────────────────┐
        │        Chrome Extension        │
        │   (MV3 · current IG profile)   │
        └───────────────┬───────────────┘
                        │  POST /api/v1/leads  (x-api-key)
                        ▼
   ┌───────────────────────────────────────────────────────────────┐
   │                     FastAPI backend  :8000                    │
   │   /health · /api/v1/leads · /api/v1/dossiers · /api/v1/outreach│
   └───────────────┬───────────────────────────────┬───────────────┘
                   │ SQLAlchemy (sync)              │ server-side reads
                   ▼                                │
   ┌──────────────────────────────┐                 │
   │        PostgreSQL 15         │◀────────────────┘
   │  leads · lead_posts ·        │
   │  website_pages · dossiers ·  │
   │  outreach_drafts ·           │
   │  pipeline_jobs               │
   │  (Alembic migrations)        │
   └───────────────▲──────────────┘
                   │  claim job · persist progress
   ┌───────────────┴───────────────────────────────────────────────┐
   │             Python autonomous worker (1 instance)             │
   │                                                               │
   │  profile_fetch  → DOM snapshot, else HikerAPI if configured   │
   │  profile_media  → HikerAPI  (recent posts/reels → lead_posts) │
   │  website_enrich → SSRF-safe crawler (snapshot URLs → pages)   │
   │  ai_dossier     → Gemini    (waits for evidence; + scoring)   │
   │  ai_outreach    → Gemini    (email + DM drafts, NEEDS_REVIEW) │
   └───────────────┬───────────────────────────────────────────────┘
                   │  reads via the API (server-side only)
   ┌───────────────▼───────────────┐
   │   Next.js GTM Console  :3000  │
   │   leads · dossiers · outreach │
   └───────────────────────────────┘
```

**Key principles**

- The browser/extension **never** touch PostgreSQL or provider APIs directly.
- **PostgreSQL is the only datastore** (no Google Sheets, no second DB).
- **Snapshot-first:** a captured DOM snapshot is enough to enrich a lead;
  HikerAPI is optional and only runs when configured. Missing snapshot data is
  never converted to zero.
- Provider secrets stay **server-side**; the dashboard is protected by a
  password gate.
- AI output is always `NEEDS_REVIEW`; **no messages are ever sent**, and an
  existing reviewed draft is never overwritten.
- Before fit approval, bio/website text is stored with contact patterns masked;
  structured contact fields stay unpopulated.

---

## 2. Features

- **Zero-cost DOM snapshot capture** — the Chrome extension reads the open
  Instagram profile (display name, verified flag, bio, external links,
  follower/following/post counts with precision) and submits it with a stable
  `request_id`. Handle-only clients still work. No compulsory HikerAPI.
- **"Add All Verified" scanner** — discovers verified accounts in the profile's
  "Suggested for you" rail, deduplicates them, and batch-submits with accurate
  Added / Already saved / Skipped / Failed counts and retry of unsaved items.
- **Snapshot-first enrichment** — the worker completes `profile_fetch` from the
  snapshot, masks email/phone patterns before AI intake, and runs website
  research from the captured links. HikerAPI is optional and only called when
  no snapshot exists and `HIKERAPI_KEY` is configured.
- **AI dossiers & outreach with safeguards** — structured dossiers and
  personalized email + DM drafts via Gemini, stored `NEEDS_REVIEW`. Ordinary
  reruns never overwrite `NEEDS_REVIEW`/`APPROVED`/`REJECTED` drafts, and
  disabled-AI retries are rejected server-side with HTTP 409 (`AI_UNAVAILABLE`).
- **Truthful progress** — research state is derived from persisted jobs, so a
  terminal failure shows as **blocked** (with a remedy) instead of a misleading
  "Queued". List rows, filters, detail, and counters agree.
- **Next.js GTM Console** — searchable/filterable leads table, lead detail with
  verified badges, precision-aware counts (`~472K` or `Unknown`), explicit
  missing fields, snapshot links, posts/website evidence, and job history; plus
  dossier view, outreach approval, and manual AI re-processing.
- **Honest media state** — snapshot leads show "Posts not captured in snapshot"
  instead of an ambiguous empty posts section.
- **Responsive, accessible UI** — sidebar at desktop, always-visible compact top
  navigation below `lg` (no hover-only menus), visible form labels, stable
  add-lead feedback, and accessible filter controls.
- **Durable, idempotent pipeline** — a database-backed job queue with bounded
  retries, exponential backoff, dependency-aware deferral, and stale-job
  recovery after restarts.

---

## 3. Repository layout

```text
synpo-gtm-automation/
├─ frontend/           Next.js console (App Router, React 19, TS, Tailwind v4)
├─ extension/          Chrome MV3 snapshot capture + verified scanner
├─ backend/            FastAPI app + background worker (Python 3.14)
│  ├─ app/
│  │  ├─ config.py     Settings from environment
│  │  ├─ main.py       FastAPI app (health + leads + dashboard API)
│  │  ├─ worker/       Autonomous worker (poll/claim/run stages)
│  │  ├─ providers/    HikerAPI client, Gemini provider, website crawler
│  │  ├─ ai/           Rubric, prompts, evidence, AI service
│  │  ├─ leads/        Lead validation/service/routes
│  │  ├─ dashboard/    Dashboard read/action endpoints
│  │  └─ db/           PostgreSQL models + repository
│  ├─ alembic/         Database migrations
│  └─ requirements.txt
├─ docs/               Detailed references (see index below)
├─ scripts/            verify_db.py, check_hikerapi.py, check_gemini.py
├─ tests/              Unit tests (in-memory SQLite)
├─ Dockerfile          Backend + worker image (non-root, no secrets)
├─ docker-compose.yml  db + api + worker (+ optional frontend profile)
├─ DEPLOYMENT_ORACLE.md  OCI (Oracle Cloud) deployment guide
├─ .env.example        Backend/worker environment template
└─ README.md
```

---

## 4. Local Development Quickstart

### Prerequisites

| Tool | Why |
| --- | --- |
| **Docker Desktop** | Runs Postgres, the API, the worker, and the dashboard |
| **WSL2** (Windows) | Docker Desktop's Linux backend on Windows |
| **Git** | Clone the repository |
| Chrome / Edge | Load the unpacked extension |

You do **not** need Python or Node installed to run via Docker.

### Configure `.env`

```bash
cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env
```

Fill in the values below. Never commit `.env` (it is gitignored).

| Variable | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | ✅ | Sync SQLAlchemy URL. In Compose use `postgresql+psycopg2://postgres:postgres@db:5432/synpo`; for local (non-Docker) use `@localhost`. |
| `GEMINI_API_KEY` | ✅ for AI | Google Gemini API key (dossiers + outreach). Leave blank and set `AI_ENABLED=false` to skip AI. |
| `GEMINI_MODEL` | ✅ for AI | `gemini-3.5-flash-lite` (cheaper/faster) or `gemini-3.8-flash` (higher quality). |
| `HIKERAPI_KEY` | optional | HikerAPI key for profile/media enrichment. **Not required** for snapshot-first capture. Without it, profile fields come from the extension snapshot and handle-only leads stay `needs_data`; recent posts are skipped. |
| `API_KEY` | ✅ | Shared secret. When set, the API requires the `x-api-key` header. |
| `CORS_ALLOW_ORIGINS` | optional | Comma-separated origins (default `*`; restrict in production). |
| `AI_ENABLED` | optional | `true`/`false` — disables all AI stages. |
| `WORKER_POLL_INTERVAL` | optional | Idle poll seconds (min 5). |

> **Dashboard auth:** the Next.js console talks to the API server-side using
> `frontend/.env.local` → `BACKEND_API_KEY` (must equal `API_KEY`) and
> `DASHBOARD_PASSWORD` (login gate). Create it so the console can authenticate:

```bash
cp frontend/.env.example frontend/.env.local
# set BACKEND_API_KEY=<same as API_KEY> and DASHBOARD_PASSWORD=<your password>
```

### Spin up the whole stack (single command)

```bash
docker compose --profile frontend up --build
```

- Dashboard: <http://localhost:3000>
- API + docs: <http://localhost:8000> (`/health`, `/docs`)
- PostgreSQL: `localhost:5432`

The API container **runs migrations on start** (`alembic upgrade head`) before
serving, so the schema is created automatically. The current head is
`a1b2c3d4e5f6` (adds `leads.profile_snapshot` and `leads.request_id`).

### Database migrations (Alembic)

Migrations run automatically when the API starts. To run them manually:

```bash
docker compose exec api alembic upgrade head
```

Create a new migration after changing models:

```bash
docker compose exec api alembic revision --autogenerate -m "describe change"
```

Verify the schema:

```bash
docker compose exec db psql -U postgres -d synpo -c "\dt"
```

(`scripts/verify_db.py` can also be run from the host with
`DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/synpo`.)

### Load the Chrome extension

1. Open `chrome://extensions/` and enable **Developer mode**.
2. Click **Load unpacked** and select the **`extension/`** folder.
3. Open the extension popup → **Settings** → set:
   - **API base URL**: `http://127.0.0.1:8000` (local) or your production HTTPS API.
   - **API key**: the same value as `API_KEY`.
4. Open an Instagram profile and click **Add to GTM** (sends the visible profile
   snapshot).
5. Open the popup to preview the snapshot and missing fields. On a profile with a
   "Suggested for you" rail, **Add All Verified** batch-adds the verified
   accounts.

No HikerAPI key is needed for snapshot-only capture. See
[extension/README.md](extension/README.md) and
[docs/extension-capture.md](docs/extension-capture.md) for supported page types
and limitations.

### Useful commands

```bash
docker compose ps                      # service status
docker compose logs -f api worker      # follow logs
docker compose restart worker          # restart one service
docker compose down                    # stop (keeps the postgres volume)
docker compose down -v                 # stop and DELETE data
```

---

## 5. Documentation index

- [docs/architecture.md](docs/architecture.md) — components, data flow, phases
- [docs/database.md](docs/database.md) — PostgreSQL schema and contracts
- [docs/api.md](docs/api.md) — lead API reference (capture payload, snapshot)
- [docs/hikerapi.md](docs/hikerapi.md) — optional HikerAPI provider
- [docs/worker.md](docs/worker.md) — autonomous worker, snapshot bypass, deferral
- [docs/website-enrichment.md](docs/website-enrichment.md) — crawling + SSRF rules
- [docs/gemini.md](docs/gemini.md) — Gemini provider, rubric, prompts
- [docs/dashboard.md](docs/dashboard.md) — Next.js console + access control
- [docs/extension-capture.md](docs/extension-capture.md) — DOM snapshot feasibility
- [docs/deployment.md](docs/deployment.md) — containers, production, Kubernetes
- [docs/runbook.md](docs/runbook.md) — end-to-end verification runbook
- [IMPLEMENTATION_REPORT_v1.1.md](IMPLEMENTATION_REPORT_v1.1.md) — as-built PRD (T00–T07)
- [DEPLOYMENT_ORACLE.md](DEPLOYMENT_ORACLE.md) — Oracle Cloud (OCI) deployment
- [extension/README.md](extension/README.md) — Chrome extension

---

## 6. Ground rules

- **PostgreSQL is the single source of truth.** No Google Sheets, no second DB.
- **Snapshot-first capture.** HikerAPI is optional; never call it when a usable
  snapshot exists or when no key is configured.
- **No secrets in code or git.** Use `.env` (gitignored); keep `.env.example` as
  the template.
- **One worker instance** until a database-based lease is added.
- **No sending** — outreach drafts are review-only and reviewed drafts are
  preserved across reruns.
- The legacy `insta_enrichment` repository is read-only reference material; only
  small, well-tested pieces are refactored into this project.
