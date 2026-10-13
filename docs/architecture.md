# Synpo GTM Automation - Architecture and Phase Boundaries

Status: **proposal / foundation**. This document defines the intended
architecture. Only Phase 0 (this foundation) is implemented.

## 1. Purpose

Automate a go-to-market pipeline around Instagram finance creators:

1. Capture creator handles.
2. Deduplicate and qualify them.
3. Enrich with public Instagram profile data and public website/contact data.
4. Generate personalized outreach content with AI.
5. Track every stage in Google Sheets and expose an operations dashboard.

## 2. System context

```text
                          +-------------------------------+
   Browser  ------------> |  Frontend (Next.js App Router) |
                          |  Operations dashboard          |
                          +---------------+---------------+
                                          | HTTPS (JSON)
                                          v
                          +-------------------------------+
                          |  Backend API (FastAPI)         |
                          |  Stateless request handling    |
                          +---------------+---------------+
                                          |
             +----------------------------+-----------------------------+
             |                            |                             |
             v                            v                             v
   +-------------------+      +---------------------+        +---------------------+
   | Google Sheets     |      | Worker (Python)     |        | External services   |
   | SOURCE OF TRUTH   |<---->| Long-running process|------> | - HikerAPI (IG)     |
   | - IG Leads        |      | Orchestrates stages |        | - Gemini (AI)       |
   | - Deduplicated    |      +---------------------+        | - Website HTTP      |
   | - ..._enriched    |                                     | - Hermes (later)    |
   | - Outreach        |                                     +---------------------+
   +-------------------+
```

**No database.** Google Sheets holds all durable state.

## 3. Components

### 3.1 Frontend — `frontend/`
- Next.js (App Router) + React + TypeScript + Tailwind CSS.
- Responsibility: operations dashboard. Shows queue/status, lets operators
  trigger stages and review generated outreach.
- Talks only to the FastAPI backend. It never reads or writes Google Sheets
  directly and never holds provider secrets.

### 3.2 Backend API — `backend/app/main.py`
- FastAPI.
- Responsibility: validation + orchestration surface for the frontend and for
  inbound handle capture. Reads/writes operational state in Google Sheets
  through the Sheets adapter (Phase 1). Triggers worker work by writing job
  state to Sheets.
- Stateless: no in-memory job state that survives a restart and is not reflected
  in Sheets.
- Current state: health check + lead capture/retrieval endpoints (Phase 2); see
  [api.md](api.md).

### 3.3 Worker — `backend/app/worker.py`
- Long-running Python process.
- Responsibility: poll Google Sheets for pending work, run the enrichment and
  generation stages, and write results back to Sheets.
- Restart-safe and idempotent by relying on status columns in Sheets rather than
  an in-memory queue.
- Shares the same Python virtual environment and can reuse shared client modules
  with the API. (Split into a separate deployable later if needed.)
- Current state: entrypoint stub only.

### 3.4 Google Sheets — source of truth
Operational tabs and their roles:

| Tab | Role | Status |
| --- | --- | --- |
| `IG Leads` | Raw captured handles (input). | Contract to be finalized in Phase 1 |
| `Deduplicated Leads` | Deduplicated, qualified handles with a processing gate. | Contract to be finalized in Phase 1 |
| `instagram_leads_enriched` | Enriched profile + website evidence. | Contract to be finalized in Phase 1 |
| `Outreach` | AI-generated outreach content. | Contract to be finalized in Phase 4 |
| `Sheet4` | Unknown. | **Unverified — needs owner clarification** |

### 3.5 External services
- **HikerAPI** — Instagram profile/media data.
- **Google Gemini** — dossiers and personalized outreach (initially).
- **Website HTTP** — public site / link-in-bio enrichment and email extraction.
- **Hermes Agent** — later integration for agentic orchestration.

## 4. Data flow (target)

```text
[Capture]            [Dedup + gate]         [Enrich]                    [Generate]        [Track]
IG Leads   ------->  Deduplicated Leads -->  HikerAPI profile   ------>  Gemini dossier --> Outreach tab
(raw handles)        (status = pending)      + website evidence          + outreach draft  (+ Hermes later)
                                            -> instagram_leads_enriched
```

1. Handles enter `IG Leads` (extension/manual/import).
2. A dedup step produces `Deduplicated Leads` with a status gate
   (e.g. `pending` / `yes` / `no`).
3. The worker picks pending rows, fetches Instagram data (HikerAPI) and website
   evidence, and writes results to `instagram_leads_enriched`, flipping status.
4. Gemini generates a dossier and outreach draft from the enriched row; the
   result lands in `Outreach`.
5. `Sheet4` and Hermes Agent are future/unverified.

## 5. State management without a database

- **Header row = schema.** First row of each tab defines columns; a canonical
  schema constant lives in code and is validated against the sheet in Phase 1.
- **Status columns = job state.** Each row carries a stage status
  (`pending`, `processing`, `done`, `error`) plus timestamps and last error.
- **Idempotency by key.** Rows are keyed by normalized `username` (lowercased,
  `@` stripped). Reprocessing a `done` row is a no-op unless forced.
- **Claiming work.** The worker marks a row `processing` before external calls
  and `done`/`error` after, so restarts do not lose or double-claim work.
- **Concurrency.** Single writer (the worker) per stage to avoid Sheet write
  races; the API only appends/reads. Batch writes where possible.

## 6. Cross-cutting concerns

- **Secrets/config:** environment variables loaded from `.env` via a single
  settings loader (Phase 1). `.env.example` documents every variable.
- **Rate limiting / politeness:** bounded concurrency and delays for HikerAPI and
  website crawling; stop on throttle/challenge signals.
- **Observability:** structured logging; per-row `last_error`; no silent failures.
- **Testing:** `pytest` for backend/worker; lint + typecheck for frontend.
- **Security:** no secrets in code or git; service account JSON stays in
  `secrets/` (gitignored); the frontend never receives provider credentials.

## 7. Explicit non-goals (MVP)

- No SQL/NoSQL database.
- No authentication/multi-tenancy.
- No production hosting/infrastructure-as-code yet.
- No automated DM sending (outreach is content generation; sending is out of
  scope for the MVP).
- No reuse of the legacy Streamlit app, SQLite stores, or Apps Script pipeline.

## 8. Legacy reference policy

The old repository (`../insta_enrichment`) is **read-only reference**. We may
selectively refactor small units later (HikerAPI profile fetch; website link/email
extraction) into this repo's conventions. We must **not** copy its architecture,
Streamlit UI, divergent SQLite stores, broken entry points, or Apps Script
pipeline.

## 9. Phase boundaries

Each phase is independently shippable and testable. Do not start a later phase
before its predecessor's exit criteria are met.

### Phase 0 — Foundation (this change)
- **Deliverables:** repo skeleton, `README.md`, `CLAUDE.md`, `.gitignore`,
  `.env.example`, `.editorconfig`, this architecture doc, runnable API health
  endpoint, worker stub.
- **Exit criteria:** backend `/health` responds; `frontend` builds; no secrets
  committed; docs reviewed.

### Phase 1 — Google Sheets data contract + adapter
- **Deliverables:** settings loader; Sheets auth (service account); read/write
  adapter; canonical schemas for the four known tabs; schema validation; a dry
  read of each tab.
- **Boundary:** no scraping, no AI.
- **Exit criteria:** can list/read/append rows and update status cells against a
  test spreadsheet; headers validated.
- **Status:** implemented in `backend/app/sheets/`. Contract, identity rules and
  the non-destructive header policy are documented in
  [sheets-contract.md](sheets-contract.md).

### Phase 2 — Lead API (FastAPI)
- **Deliverables:** lead endpoints (submit/list/get); username/URL validation and
  normalization; duplicate prevention with a clear existing/new result; stable
  `leadId`; enqueue by storing `status="queued"`; typed request/response schemas;
  pagination and search; error mapping (config/quota/network/schema).
- **Boundary:** no scraping, no AI; the browser never touches Sheets directly.
- **Exit criteria:** submitting a handle stores a deduplicated lead; repeated
  submissions return the existing lead; invalid input is rejected.
- **Status:** implemented in `backend/app/leads/` + `backend/app/main.py`. See
  [api.md](api.md).

### Phase 3 — HikerAPI provider (profile fetch + normalization)
- **Deliverables:** typed HikerAPI client (`GET /v2/user/by/username`,
  `x-access-key`); input validation; normalized `HikerProfile`; `to_lead_fields`
  mapping; timeouts; bounded retries; typed errors; mocked-response tests; a
  manual check script.
- **Boundary:** provider only — no worker wiring, no recent-media research, no
  website crawling, no AI.
- **Exit criteria:** one approved public profile can be fetched and normalized.
- **Status:** implemented in `backend/app/providers/`. See
  [hikerapi.md](hikerapi.md).

### Phase 4 — Autonomous worker + profile fetch
- **Deliverables:** worker that polls `Pipeline Jobs`, claims one job, runs a
  stage, persists progress (idempotent, retry-aware, restart-safe); the
  `profile_fetch` stage writing `instagram_leads_enriched`.
- **Boundary:** no AI; no media/website yet.
- **Exit criteria:** queued jobs enrich leads and survive restarts.
- **Status:** implemented in `backend/app/worker/` (see
  [worker.md](worker.md)).

### Phase 5 — Profile media + website enrichment
- **Deliverables:** `profile_media` stage (bounded recent posts/reels →
  `Lead Posts`) and `website_enrich` stage (SSRF-safe crawl + email extraction →
  `Website Pages`), both optional and idempotent.
- **Boundary:** no AI; no follower-list fetching.
- **Exit criteria:** leads gain media and website evidence; missing/blocked data
  never stalls the pipeline.
- **Status:** implemented in `backend/app/providers/website.py` and
  `backend/app/worker/pipeline.py` (see
  [website-enrichment.md](website-enrichment.md)).

### Phase 6 — AI generation (Gemini)
- **Deliverables:** Gemini client; dossier + personalized outreach prompts;
  results written to `Outreach`; schema finalized.
- **Boundary:** generation only, no sending.
- **Exit criteria:** enriched leads produce outreach drafts in the sheet.
- **Status:** implemented — AI provider abstraction + `GeminiProvider`
  (`backend/app/providers/ai.py`), rubric/prompts/service (`backend/app/ai/`),
  `ai_dossier`/`ai_outreach` stages writing `Dossiers` + `Outreach`
  (`NEEDS_REVIEW`). See [gemini.md](gemini.md).

### Phase 7 — Frontend dashboard
- **Deliverables:** queue/status views, manual stage triggers, lead detail, and
  generated-outreach review; consumes the FastAPI API.
- **Boundary:** UI only; no direct Sheets access.
- **Exit criteria:** operators can drive the pipeline from the browser.
- **Status:** implemented in `frontend/` (App Router + Server Actions + a
  password access gate) with supporting read endpoints in `backend/app/dashboard/`.
  See [dashboard.md](dashboard.md).

### Phase 8 — Extension integration
- **Deliverables:** minimal MV3 extension that captures the current Instagram
  profile and submits it to the authenticated API (`POST /api/v1/leads`), with
  clear created/duplicate/error/auth states; no scraping, no Sheets access.
- **Boundary:** capture only; no provider secrets.
- **Exit criteria:** adding a creator from Instagram queues a deduplicated lead.
- **Status:** implemented in `extension/`. See
  [../extension/README.md](../extension/README.md).

### Phase 9 — Orchestration & scheduling hardening
- **Deliverables:** worker scheduling, retries/backoff, stale-job recovery,
  observability, run configuration; a Sheets-based work lease to allow more than
  one writer.
- **Exit criteria:** unattended daily operation is reliable.
- **Note:** a planned data-migration phase was intentionally skipped — there is
  no database to migrate.

### Phase 10 — Operations, testing & deployment
- **Deliverables:** backend/worker container images + Compose, a deployment guide
  (local, production, Kubernetes, Next.js), accurate `.env.example` files, and an
  end-to-end runbook.
- **Status:** implemented — `Dockerfile`, `docker-compose.yml`, `frontend/Dockerfile`,
  [deployment.md](deployment.md), [runbook.md](runbook.md).

### Phase 11 — Hermes Agent integration
- **Deliverables:** agent integration over enriched/outreach data.
- **Exit criteria:** defined once Hermes's interface is known.

## 10. Open questions (need owner input)

- What is `Sheet4` for? (currently **unverified**)
- Exact column contract for `Outreach`.
- Google Sheets auth: service account vs OAuth user flow.
- HikerAPI plan/limits and the Instagram session model.
- Hosting/runtime target for API + worker and desired schedule.
- Hermes Agent interface and responsibilities.
