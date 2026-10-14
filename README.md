# Synpo GTM Automation

A modern, containerized go-to-market (GTM) pipeline for Instagram creator
discovery. Capture creator handles, enrich them with public Instagram + website
data, generate AI dossiers and personalized outreach, and manage everything from
a Next.js console — with **PostgreSQL as the single source of truth**.

> **Status: production-ready MVP.** Lead capture, the autonomous worker,
> Instagram + website enrichment, Gemini dossiers/outreach, the Next.js console,
> the Chrome extension, and the full container deployment are implemented.
> The storage layer was migrated from Google Sheets to PostgreSQL (SQLAlchemy +
> Alembic).

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
- **PostgreSQL 15** — durable state for leads, posts, website pages, dossiers,
  outreach drafts, and the job queue. Schema is managed by **Alembic**.
- **Next.js GTM Console** (`:3000`) — leads table, lead detail, dossiers, and
  outreach review (approve/reject), with an Aurora background and glass panels.
- **Google Gemini** — structured dossiers + qualification scoring and email/DM
  outreach drafts (review-only; nothing is sent).
- **Chrome extension (MV3)** — one-click lead capture from the current Instagram
  profile.

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
   │  profile_fetch  → HikerAPI  (profile → lead fields)           │
   │  profile_media  → HikerAPI  (recent posts/reels → lead_posts) │
   │  website_enrich → SSRF-safe crawler (evidence → website_pages)│
   │  ai_dossier     → Gemini    (structured dossier + scoring)    │
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
- Provider secrets stay **server-side**; the dashboard is protected by a
  password gate.
- AI output is always `NEEDS_REVIEW`; **no messages are ever sent**.

---

## 2. Features

- **Single-click lead ingestion** — the Chrome extension sends the current
  Instagram profile to the API (`POST /api/v1/leads`) with clear
  created / duplicate / invalid / auth / network states.
- **Automated enrichment** — creator profile fields (followers, bio, category,
  public contact), recent posts/reels, and SSRF-safe website crawling with
  email extraction.
- **AI dossiers & outreach** — structured dossiers with a configurable
  qualification rubric and personalized email + DM drafts via the Google Gemini
  API (`gemini-3.5-flash-lite` for cost/throughput or `gemini-3.8-flash` for
  quality).
- **Next.js GTM Console** — searchable/filterable leads table, lead detail with
  posts + website evidence + job history, dossier view, outreach approval, and
  **manual AI re-processing** ("Re-process AI Jobs Only").
- **Durable, idempotent pipeline** — a database-backed job queue with bounded
  retries, exponential backoff, and stale-job recovery after restarts.
- **Visual status** — animated circular loaders for `running`/`queued`/`retry`
  jobs and a check for completed ones.

---

## 3. Repository layout

```text
synpo-gtm-automation/
├─ frontend/           Next.js console (App Router, React 19, TS, Tailwind v4)
├─ extension/          Chrome MV3 lead-capture extension
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
| `HIKERAPI_KEY` | ✅ | HikerAPI key for Instagram profile/media enrichment. |
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
serving, so the schema is created automatically.

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
4. Open an Instagram profile and click **Add to GTM**.

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
- [docs/api.md](docs/api.md) — lead API reference
- [docs/hikerapi.md](docs/hikerapi.md) — HikerAPI provider
- [docs/worker.md](docs/worker.md) — autonomous worker + job queue
- [docs/website-enrichment.md](docs/website-enrichment.md) — crawling + SSRF rules
- [docs/gemini.md](docs/gemini.md) — Gemini provider, rubric, prompts
- [docs/dashboard.md](docs/dashboard.md) — Next.js console + access control
- [docs/deployment.md](docs/deployment.md) — containers, production, Kubernetes
- [docs/runbook.md](docs/runbook.md) — end-to-end verification runbook
- [DEPLOYMENT_ORACLE.md](DEPLOYMENT_ORACLE.md) — Oracle Cloud (OCI) deployment
- [extension/README.md](extension/README.md) — Chrome extension

---

## 6. Ground rules

- **PostgreSQL is the single source of truth.** No Google Sheets, no second DB.
- **No secrets in code or git.** Use `.env` (gitignored); keep `.env.example` as
  the template.
- **One worker instance** until a database-based lease is added.
- **No sending** — outreach drafts are review-only.
- The legacy `insta_enrichment` repository is read-only reference material; only
  small, well-tested pieces are refactored into this project.
