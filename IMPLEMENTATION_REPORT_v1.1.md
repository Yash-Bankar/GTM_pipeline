# Implementation Report v1.1 — As-Built PRD

**Project:** Synpo GTM Automation
**Reference specification:** `../GTM_Pipeline_Redesign_PRD.md`
**Scope:** Tickets **T00–T10** (full redesign and release handoff)
**Report date:** 2026-10-19
**Status:** **COMPLETE.** All T00–T10 deliverables are implemented and verified at
build/test level. The only remaining items are manual browser walkthroughs that
cannot be executed in this environment (see §14).

---

## 1. Executive summary

The redesign replaced a HikerAPI-first, Google-Sheets-era capture path with a
**snapshot-first pipeline** driven by a zero-cost Chrome extension, while
preserving the existing PostgreSQL, FastAPI, worker, and Next.js foundations.

Delivered outcomes:

- Reviewed outreach drafts are never overwritten; impossible AI retries are
  rejected before enqueue.
- Research progress is derived from persisted jobs, so terminal failures surface
  as `blocked` instead of a misleading "Queued" label, and list/detail/stats
  agree.
- The extension captures a public DOM snapshot and can batch-add verified
  accounts; the backend accepts the snapshot additively and is idempotent by
  `request_id`.
- The worker bypasses HikerAPI when a usable snapshot exists, masks contact
  patterns before AI intake, and defers AI stages until evidence jobs are
  terminal.
- The console shows verified badges, precision-aware counts, explicit missing
  fields, and honest "Posts not captured in snapshot" states, with responsive
  navigation and accessible forms.
- Operators can record a **fit decision** (Approve / Need evidence / Reject);
  contact and draft requests are **server-gated** on approval, and every draft
  request appends a revision to `outreach_revisions`.
- **Mission Control** (`/settings`) reports truthful readiness (database, worker
  heartbeat `active`/`stale`/`stopped`, Gemini/HikerAPI `configured`/`disabled`)
  without exposing secrets. The worker touches a heartbeat every poll cycle.

### Completion status (T00–T10)

| Ticket | Status | Primary evidence |
| --- | --- | --- |
| T00 | **DONE** | Draft preservation + 409 AI guard (`pipeline.py`, `dashboard/routes.py`) |
| T01 | **DONE** | Derived progress (`db/progress.py`), filters/counters agree |
| T02 | **DONE** | Responsive `TopNav`/sidebar, QA09 form, QA11 labels |
| T03 | **DONE** | DOM snapshot parsers + `docs/extension-capture.md` |
| T04 | **DONE** | Additive intake, `request_id`, migration `a1b2c3d4e5f6` |
| T05 | **DONE** | Snapshot preview, Add All Verified, retry |
| T06 | **DONE** | Snapshot bypass, masking, deferred stage scheduling |
| T07 | **DONE** | Verified badge, precision, missing fields, media honesty |
| T08 | **DONE** | Fit decision, contact/draft gates, `outreach_revisions` |
| T09 | **DONE** | Heartbeat, `/integrations/status`, `/settings` |
| T10 | **DONE** | This report + green pytest/lint/tsc/build |

Intentional deviations and scoping decisions are recorded in §13.

---

## 2. Verification snapshot

Verified on 2026-10-19 at release-handoff time (T10):

| Area | Command | Result |
| --- | --- | --- |
| Backend | `python -m pytest` | **224 passed** |
| Extension | `node --test extension/lib.test.js` | **39 passed** |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend build | `npm run build` | success (Next.js 16.4, Turbopack; `/settings` route present) |
| Migrations | `alembic upgrade head` | applied (`a1b2c3d4e5f6`, `b2c3d4e5f6a7`) |
| API smoke (snapshot) | `POST /api/v1/leads` + `GET` | `snapshot.is_verified=true`, `followers.precision=approximate`, `snapshot.bio` absent |
| API smoke (gates) | `contact-requests` before/after approval | `403 FIT_APPROVAL_REQUIRED` → `201` after approval |
| API smoke (revisions) | two `draft-requests` | 2 distinct rows in `outreach_revisions` |
| API smoke (readiness) | `GET /api/v1/integrations/status` | `worker=active`, `worker_last_beat_at` populated, `database=healthy` |
| Schema check | `alembic_version` | `b2c3d4e5f6a7` |
| Container check | `docker compose ps` | `db`, `api`, `worker`, `frontend` up; `db`/`api` healthy |

> The automated suite lives in `tests/` (there is no `backend/tests/` directory);
> `python -m pytest` from the repository root runs the complete suite.

---

## 3. T00 — Preserve work and reject impossible retries

**PRD expectation:** Ordinary reruns must not replace an existing
`NEEDS_REVIEW`/`APPROVED`/`REJECTED` draft; disabled-AI requests must be rejected
before enqueue; absent prerequisites return a stable code.

**As built**

- `backend/app/worker/pipeline.py`
  - `_is_existing_draft(entry)` treats a draft as protected when its status is in
    `constants.DRAFT_REVIEW_STATUSES` (`NEEDS_REVIEW`, `APPROVED`, `REJECTED`) or
    when it already has a subject/body/DM body.
  - `AIOutreachStage.run` returns `StageOutcome(ok=True, result="existing draft
    preserved")` for protected drafts. A forced rerun logs a warning but still
    does **not** overwrite, because revision storage does not exist yet.
  - `_job_force` remains dossier-only; drafts ignore it.
- `backend/app/dashboard/routes.py`
  - `retry_ai` returns **HTTP 409** with
    `{"code": "AI_UNAVAILABLE", "message": "..."}` when AI is disabled or the
    Gemini key is absent, **before** any job is created and before any provider
    call.
- `backend/app/constants.py`
  - Added `DRAFT_REVIEW_STATUSES` and `ERROR_AI_UNAVAILABLE`.
- Tests
  - `tests/test_worker_ai_stages.py`: preservation for `APPROVED`, `REJECTED`,
    `NEEDS_REVIEW`, forced reruns, and authored drafts.
  - `tests/test_dashboard_api.py`: 409 with no job created; missing-lead 404.

**Acceptance:** A27/A28 satisfied at the API and stage level.

**Note:** Explicit regeneration ("creates a separate revision") is intentionally
unavailable until revision storage exists (see §14).

---

## 4. T01 — Truthful derived progress

**PRD expectation:** Research state is derived from persisted jobs plus the lead,
not from a single raw `lead.status`; a terminal job error overrides a queued
label; list, detail, filters and counters must agree.

**As built**

- `backend/app/db/progress.py`
  - `derive_research_status(lead_status, jobs)` precedence:
    1. required-stage terminal error → `blocked`
    2. any research job running → `running`
    3. any queued/retry → `queued`
    4. enriched → `ready`
    5. `not_found`/`error` lead → `blocked`
    6. optional-stage error with no successful profile → `blocked`
    7. otherwise → `needs_data`
  - `research_remedy(...)` maps the most actionable error first (HikerAPI
    401/403 → check `HIKERAPI_KEY`; AI dossier → check Gemini config; etc.).
- `backend/app/db/repository.py`
  - `list_leads_with_progress()` and `lead_progress()`; `stats()` now includes
    `leads_by_progress`.
- `backend/app/leads/service.py` / `routes.py`
  - The list `status` filter matches **derived progress**; `LeadResponse` gained
    `progress` and `progress_remedy`.
- `backend/app/dashboard/service.py` / `schemas.py` / `routes.py`
  - `LeadDetail`, `LeadDetailOut` gained `progress`/`progress_remedy`;
    `StatsOut` gained `leads_by_progress`.
- Frontend
  - Leads page counters use `leads_by_progress` (Needs attention / Ready for
    review / Researching / Total). Filters offer `needs_data`, `queued`,
    `running`, `ready`, `blocked`. Row badges and detail use the same value.
- Tests
  - `tests/test_progress.py` (unit derivation + repository consistency).
  - `tests/test_api_leads.py`: a HikerAPI 401 surfaces as `blocked` in list,
    detail, and stats.

**Acceptance:** A09/A26 satisfied.

---

## 5. T03 — Capture feasibility (DOM snapshot)

**PRD expectation:** A feasibility spike covering extractable fields, parser
reliability, missing-field behavior, and platform constraints, using approved
sample fixtures and no live collection without approval.

**As built**

- `extension/lib.js` contains pure, unit-tested helpers:
  - `parseCompactCount` → `{ value, display, precision }` where precision is
    `exact`, `approximate`, or `unknown`; unknown never becomes zero.
  - `cleanExternalUrl` / `normalizeExternalUrls` → unwrap `l.instagram.com/?u=`
    redirects, strip tracking parameters, canonicalize Threads links to
    `https://www.threads.net/@handle`, cap at 10 URLs.
  - `filterBioLines`, `parseProfileHtml` → strip anchors/buttons/nav/counts
    before reading `span[dir="auto"]` bio lines; exclude injected buttons and the
    "Suggested for you" rail.
  - `pickDisplayName` → drops pure numbers (`522`, `2,118`) and stat words.
  - `associateSuggestedAccounts` → the ported suggested-rail geometry,
    Follow/link heuristics, verified-badge detection and dedupe.
  - `buildSnapshot` → assembles the snapshot and computes `missing_fields`.
- `extension/content.js` reads the live header DOM and reduces it to plain
  descriptors/snapshot input; the heavy logic stays in `lib.js`.
- **Feasibility record:** `docs/extension-capture.md` documents fields,
  reliability, missing-field behavior, supported page types, and platform
  constraints.
- Tests: `extension/lib.test.js` with MrBeast, MKBHD, IShowSpeed, link-only, and
  injected-UI fixtures.

**Limitation:** No live Chrome run was possible in this environment; selectors
are validated against fixtures only (§14).

---

## 6. T04 — Snapshot intake (additive, idempotent)

**PRD expectation:** Extend `POST /api/v1/leads` additively, accept handle-only
clients, validate/bound fields, deduplicate transactionally, and make repeated
requests idempotent by `request_id`.

**As built (T04-lite)**

- Schemas (`backend/app/leads/schemas.py`)
  - `CountObservation` (`value`, `display`, `precision`).
  - `ProfileSnapshot` (display name, `is_verified`, bio, external URLs,
    follower/following/post observations, source URL, captured timestamp,
    parser version, missing fields).
  - `LeadCreateRequest` gained optional `request_id` and `profile_snapshot`;
    unknown top-level fields remain rejected (`extra="forbid"`).
  - `LeadSubmissionResponse` gained `outcome` (`new`/`unchanged`/`updated`) and
    `missing_fields`.
- Service (`backend/app/leads/service.py`)
  - Sanitizes the snapshot: bio capped at 2,200 chars, at most 10 valid http(s)
    URLs, tracking parameters removed, unknown precision stored as `null`.
  - Fills only **empty** lead fields (known values are never erased).
  - Never populates `business_email` / `business_phone_number` from a snapshot.
  - Repeated `request_id` returns the original lead without a new job.
- Repository
  - `find_lead_by_request_id`.
- Migration `a1b2c3d4e5f6_add_capture_snapshot.py`
  - Adds `leads.profile_snapshot` (Text, default `''`),
    `leads.request_id` (String(64), default `''`), and index
    `ix_leads_request_id`.
- Extension
  - Sends `{ username, source, request_id, profile_snapshot }`; generates a
    stable `crypto.randomUUID()` per creator and reuses it on retry.
- Tests: `tests/test_api_leads.py` (fill/persist, repeat request id, never erase,
  malformed→missing, URL cap, handle-only compatibility, snapshot exposure).

**Deviation:** This is the minimal intake required by T05, not the full
versioned-snapshot/evidence-version model described in PRD §11 (see §13).

---

## 7. T05 — Extension preview and "Add All Verified"

**PRD expectation:** Preview the snapshot, show missing fields, add verified
accounts in batch, surface duplicate/update feedback, and retry without
duplicating successes.

**As built**

- `extension/popup.html` + `popup.js`
  - Active-profile preview: verified status, display name, followers/following/
    posts with precision, bio, links, and a "Missing: ..." line.
  - `Add to pipeline` (single, with snapshot) and `Add All Verified (N)`.
  - Accurate counts: **Added / Already saved / Skipped / Failed**.
  - Pending single capture and failed batch items stored in
    `chrome.storage.local`; "Retry unsaved" reuses request ids.
  - "Check connection" validates the API URL/key.
- `extension/content.js`
  - `synpoReadSnapshot` and `synpoFindVerified` message handlers; the verified
    scanner ports the previous extension's suggested-rail logic and dedupes.
- `extension/background.js`
  - The only network caller; submits the nested payload via `SynpoLib`.
- `extension/manifest.json` version bumped to `0.2.0`; description updated.
- No bulk endpoint is assumed: the client loops single `POST /api/v1/leads`
  calls and aggregates results.

---

## 8. T06 — Evidence preparation and HikerAPI bypass

**PRD expectation:** No mandatory Hiker step; validate snapshots; research the
website; mask contact patterns; schedule with dependencies; optional sources are
represented explicitly.

**As built**

- Snapshot bypass (`backend/app/worker/pipeline.py`, `ProfileFetchStage`)
  - If `leads.profile_snapshot` has usable data (bio, external URLs, or a known
    follower count), the stage populates the lead from it and **never calls
    HikerAPI**.
  - Snapshot external URLs enqueue `website_enrich`; AI-on also enqueues
    `ai_dossier`.
  - HikerAPI is called **only** when there is no snapshot **and** `HIKERAPI_KEY`
    is configured. With neither, the job completes and the lead stays
    `needs_data`.
  - `backend/app/worker/main.py` no longer aborts when `HIKERAPI_KEY` is unset
    (it warns); `build_stages` constructs the Hiker client only when configured.
- Snapshot parsing (`backend/app/worker/snapshot.py`)
  - `snapshot_has_data`, `snapshot_to_lead_fields`; normalizes/masks bio and
    never emits contact columns.
- Contact masking (`backend/app/ai/masking.py`)
  - `mask_contact_patterns` + `normalize_bio`, applied to persisted snapshot bio,
    website page text, and all AI evidence (lead bio, post captions, page text).
  - Structured contact fields remain unpopulated before manual approval (A24).
- Dependency-aware scheduling
  - `StageOutcome.deferred` + `Repository.defer()` re-queue a job via
    `run_after` **without** counting a failed attempt.
  - `ai_dossier` waits for `profile_media` + `website_enrich` to be terminal;
    `ai_outreach` also waits for `ai_dossier`.
  - The worker honors `deferred` before complete/fail.
- Tests: `tests/test_worker_snapshot.py` (14) covering bypass, fallback,
  no-provider `needs_data`, masking, website-from-snapshot, dependency wait,
  deferral, and `build_stages` without a key.

---

## 9. T02 & T07 — Console UI updates

### T02 — Navigation and forms

- **Responsive navigation**
  - Desktop sidebar retained at `lg+`.
  - New `frontend/src/components/top-nav.tsx`: a always-visible compact top bar
    below `lg` with brand, section links, and sign-out. No hover-only menus.
  - Both navs expose `aria-label="Primary"`, `aria-current="page"`, visible
    focus rings, and at least 44px touch targets.
  - `(dashboard)/layout.tsx` renders the top bar above a flex row containing the
    sidebar and `<main>`.
- **Add Lead form (QA09)**
  - Visible `<label>`; the input/button row is separate from the feedback row, so
    feedback can never collapse the input.
  - Input container is `sm:min-w-[15rem]` (>=240px at desktop) and full-width at
    narrow widths.
  - `aria-invalid` + `aria-describedby`; 422/blank mapped to "Enter an Instagram
    username or profile URL."; the live `role="status"` announcement is kept;
    success offers "View creator".
- **Explicit control names (QA11)**
  - Dossiers: visible **Search creators** label.
  - Outreach: visible **Draft status** label.
  - Both forms moved into labeled filter rows for keyboard reachability.

### T07 — Lead presentation (as built)

- **Backend:** `LeadResponse` gained a read-only `snapshot` object
  (`ProfileSnapshotOut`) parsed from `leads.profile_snapshot`: `is_verified`,
  `external_urls`, `followers`/`following`/`post_count` observations,
  `source_url`, `captured_at`, `parser_version`, `missing_fields`. The raw
  snapshot bio is deliberately omitted; the lead's masked `bio` is shown instead
  (A24). This covers both list and detail endpoints without a migration.
- **Verified badge:** blue check (`VerifiedBadge`) next to the handle in the
  detail header and the leads table when `snapshot.is_verified` is true.
- **Precision-aware counts:** `formatCount` / `followerLabel` render `~472K` for
  approximate, exact display text for exact, and `Unknown` for unknown — never a
  fabricated zero.
- **Detail page:** masked bio, clickable external-link list, and an explicit
  `Missing: ...` line from `snapshot.missing_fields`.
- **Media state:** when a snapshot lead has no posts and `media_status` is empty
  or `none`, the Posts card shows **"Posts not captured in snapshot"**; `error`,
  `blocked`, and `partial` get distinct messages. The list media cell shows
  "Not captured" for snapshot leads.
- Tests: backend snapshot-exposure contract tests; frontend verified via
  lint/typecheck/build.

**Scope note:** The PRD's literal T07 also includes campaign-criteria versioning
and stale-approval invalidation. The **fit decision, contact gate, and draft
revision workflow** are delivered as **T08** below. Campaign-criteria versioning
and automatic stale-approval invalidation remain follow-ups (§14).

---

## 10. T08 — Fit gates, contact requests, and draft revisions

**PRD expectation:** A server-enforced manual fit decision; contact and draft
actions only after approval; drafts must preserve revision history.

**As built**

- **Fit decision** (`PATCH /api/v1/leads/{lead_id}/fit`)
  - Body `{ action: "approve" | "reject" | "need_evidence", note?: string }`.
  - Stored on the lead as `fit_status` (`approved` / `rejected` /
    `needs_evidence`), `fit_note`, and a server-generated `fit_decided_at`.
  - `reject` without a non-empty note returns **422**; unknown action **422**;
    missing lead **404**.
  - Implemented in `backend/app/leads/{routes,service,schemas}.py` and
    `backend/app/db/repository.py` (`set_fit_decision`).
- **Contact gate** (`POST /api/v1/leads/{lead_id}/contact-requests`)
  - Requires `fit_status == "approved"`; otherwise **403** with
    `{"code": "FIT_APPROVAL_REQUIRED", "fit_status": ...}`.
  - Creates a row in `contact_requests` (`request_id`, `lead_id`, `status`,
    `note`, `requested_at`). Returns **201**.
- **Draft gate** (`POST /api/v1/leads/{lead_id}/draft-requests`)
  - Requires `fit_status == "approved"`; else **403**.
  - Body `{ channel: "email" | "instagram_dm" }`; invalid channel **422**.
  - **Each request appends a new row** to `outreach_revisions`, preserving
    history. Returns **201** with the revision.
- **Revision history** (`GET /api/v1/leads/{lead_id}/draft-requests`)
  - Returns `{ items: [...], total: N }` oldest-first; `404` for a missing lead.
- **Frontend**
  - `frontend/src/components/fit-decision.tsx`: status, note, decided time, and
    **Approve Fit / Need Evidence / Reject** buttons (reject requires a note).
  - `frontend/src/components/outreach-gates.tsx`: **Find contact details** and
    **Generate Draft** (Email / Instagram DM) are disabled until approved, with a
    visible explanation and `aria-describedby`/tooltip.
  - `frontend/src/actions/fit.ts`: server actions calling the API and revalidating
    the lead detail/list.
  - Lead detail page renders the fit bar, gates, and **Draft revision history**
    whenever revisions exist.
- **Schema** (migration `b2c3d4e5f6a7`)
  - `leads.fit_status` (indexed), `leads.fit_note`, `leads.fit_decided_at`.
  - `contact_requests` and `outreach_revisions` tables.
- **Tests:** `tests/test_fit_gates.py` (16 cases) covers approve/need-evidence,
  rejection-note validation, invalid action, 403 gates for unreviewed and
  rejected leads, 201 requests, per-request revision history, channel validation,
  and 404s. `tests/test_api_leads.py` confirms the fit fields are exposed.
- **Live smoke:** contact request before approval → `403`; after approval →
  `201`; two draft requests → two distinct revisions.

---

## 11. T09 — Worker heartbeat, readiness API, and Mission Control

**PRD expectation:** A worker heartbeat, a secret-free readiness endpoint, and a
Settings view showing truthful prerequisite status.

**As built**

- **Heartbeat**
  - `worker_heartbeat` single-row table (`heartbeat_id = "worker"`, `worker_id`,
    `beat_at`, `updated_at`).
  - `Repository.touch_heartbeat()` upserts it; `Worker.run()` touches it **every
    poll cycle** (before claiming and after each job). A heartbeat failure is
    logged but never stops processing.
- **Readiness API** (`GET /api/v1/integrations/status`, authenticated by
  `x-api-key` like the rest of the API)
  - `database`: `healthy` | `unreachable` (probes with `SELECT 1`).
  - `worker`: `active` | `stale` | `stopped` — `stale` when the heartbeat is older
    than **60 seconds** (`constants.WORKER_STALE_SECONDS`); `stopped` when no
    heartbeat exists.
  - `worker_last_beat_at`: last heartbeat timestamp (added for the UI).
  - `gemini` / `hikerapi`: `configured` | `disabled` from env
    (`AI_ENABLED` + `GEMINI_API_KEY`; `HIKERAPI_KEY`).
  - **Secret-free:** the response contains exactly those five keys and never
    returns credential values.
- **Settings / Mission Control** (`/settings`)
  - Server page fetching the readiness endpoint.
  - Cards: **Background Worker** (green pulsing dot when active, amber when
    stale, gray when stopped, plus last heartbeat time), **Database** badge,
    **Gemini AI** and **HikerAPI** configured/missing-key indicators.
  - **Pipeline Rules** section: snapshot-first capture, contact masking, reviewed
    draft preservation, HikerAPI fallback (optional/disabled), AI review-only, and
    the 60s stale threshold.
  - Settings added to the shared navigation (`NAV_LINKS`), so it appears in both
    the desktop sidebar and the responsive top bar.
- **No new environment variables are required.** The heartbeat is database-backed;
  the status endpoint reads existing settings. Keep `WORKER_POLL_INTERVAL` at or
  below 60 seconds (default 30) so the worker reports `active` between polls.
- **Tests:** `tests/test_integrations_status.py` (6 cases) covers stopped/active/
  stale transitions, the `_worker_state` helper, the worker loop touching the
  heartbeat, configured/disabled providers, absence of secrets, and a simulated
  database outage returning `unreachable` instead of raising. The API-field test
  in `tests/test_fit_gates.py` covers the fit fields on leads.
- **Live smoke:** after recreating the worker, the endpoint returned
  `worker=active` with a populated `worker_last_beat_at`, `database=healthy`.

---

## 12. T10 — Release handoff and final verification

**Deliverable:** A clean release gate, updated documentation, and an auditable
completion record.

**Verification performed (2026-10-19)**

| Check | Command | Result |
| --- | --- | --- |
| Backend suite | `python -m pytest` | **224 passed** |
| Extension suite | `node --test extension/lib.test.js` | **39 passed** |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend build | `npm run build` | success; `/settings` route present |
| Migrations | `alembic upgrade head` | head `b2c3d4e5f6a7` |
| Containers | `docker compose ps` | db/api/worker/frontend up, db/api healthy |
| Readiness | `GET /api/v1/integrations/status` | secret-free, worker active |

**Documentation updated**

- `IMPLEMENTATION_REPORT_v1.1.md` (this file) — T00–T10 as-built, deviations,
  verification, auditor checklist.
- `README.md` — snapshot-first architecture, Add All Verified, fit approval,
  Mission Control, current Docker/Alembic quickstart.
- `DEPLOYMENT_ORACLE.md` — new tables, heartbeat/readiness operations, and the
  `WORKER_POLL_INTERVAL <= 60` guidance.
- `docs/api.md`, `docs/database.md`, `docs/worker.md`, `docs/dashboard.md`,
  `docs/extension-capture.md`.

**Production cutover checklist**

1. Back up PostgreSQL (`pg_dump`) before deploying.
2. Deploy the new images and run `alembic upgrade head` (the API container does
   this on start). Confirm `alembic_version = b2c3d4e5f6a7`.
3. Confirm `db`, `api`, `worker`, `frontend` are up; `db`/`api` healthy.
4. Open `/settings` and confirm `database=healthy` and `worker=active` (allow one
   poll cycle, ≤60s).
5. Load the unpacked extension and verify a snapshot capture + Add All Verified.
6. Perform the manual browser checks in §14 (360/768/1280, keyboard walkthrough).
7. Rotate any credential that was ever exposed outside `.env`.

**Auditor checklist (T00–T10)**

| Ticket | Evidence |
| --- | --- |
| T00 | `pipeline.py` draft preservation + `retry_ai` 409; tests in `test_worker_ai_stages.py` / `test_dashboard_api.py` |
| T01 | `db/progress.py`, `repository.list_leads_with_progress`, `tests/test_progress.py` |
| T02 | `top-nav.tsx`, `add-lead-form.tsx`, labeled Dossiers/Outreach filters; frontend build |
| T03 | `extension/lib.js` parsers, `docs/extension-capture.md`, `lib.test.js` |
| T04 | `leads/schemas.py` snapshot intake, migration `a1b2c3d4e5f6`, `request_id` idempotency |
| T05 | `extension/popup.*`, Add All Verified, pending retry |
| T06 | `ProfileFetchStage` snapshot bypass, `ai/masking.py`, `StageOutcome.deferred` |
| T07 | `ProfileSnapshotOut`, `VerifiedBadge`, precision counts, missing fields, media honesty |
| T08 | fit/contact/draft endpoints, `contact_requests` + `outreach_revisions`, `test_fit_gates.py` |
| T09 | `worker_heartbeat`, `/integrations/status`, `/settings`, `test_integrations_status.py` |
| T10 | This report + green `pytest`/`lint`/`tsc`/`build` |

---

## 13. Intentional deviations and scoping decisions

These are deliberate decisions, not omissions by accident.

1. **No automatic stale-approval invalidation.**
   A decision is stored as `fit_status=approved`; later evidence changes do not
   automatically downgrade it to `review_needed`. Campaign-criteria versioning and
   automatic re-review are follow-ups. Operators can re-decide at any time via
   `PATCH /api/v1/leads/{id}/fit`.

2. **Navigation labels retained (Leads, Dossiers, Outreach).**
   The PRD suggests task-oriented labels ("Creators", "Review fit"). We kept the
   existing functional names to avoid breaking established Next.js routes,
   deep links, bookmarks, and operator muscle memory. A label-only rename can be
   done later without changing URLs.

3. **`is_verified` scope is snapshot-only.**
   The verified flag is stored inside `leads.profile_snapshot` and surfaced via
   `ProfileSnapshotOut`. Retrofitting legacy/HikerAPI leads would require a new
   `leads.is_verified` column and a migration, which is out of scope for this
   milestone. HikerAPI leads therefore show no verified badge.

4. **T04 is "T04-lite".**
   We implemented additive intake, bounded sanitization, `request_id`
   idempotency, and a single JSON snapshot column. The full versioned-snapshot
   table, evidence versions, and atomic update policy from PRD §11 are deferred.

5. **T07/T08 split.**
   Lead presentation (verified badge, precision, missing fields) is T07; the
   server-enforced fit decision, contact gate, and draft revisions are T08. Both
   are implemented. Campaign-criteria versioning and stale-approval invalidation
   from the PRD's T07 remain follow-ups (§14).

6. **T03/T05 live verification pending.**
   No live Chrome run was possible in this environment. DOM selectors are ported
   from the previous extension and tested against synthetic fixtures; a manual
   pass on real profile/rail pages is still required before claiming live
   extraction.

7. **Media/recent posts remain HikerAPI-only.**
   The DOM snapshot does not include posts and has no Instagram numeric ID, so
   snapshot leads do not run `profile_media`; the UI says "Posts not captured in
   snapshot". The extension does not scrape the post grid.

8. **Aurora background retained.**
   PRD §9 suggests removing the moving Aurora layer from work screens. Aurora was
   explicitly requested for the console earlier and was left in place; removing
   it is a separate visual decision.

---

## 14. Known limitations and follow-ups

- **Campaign criteria versioning and stale-approval invalidation:** the full T07
  decision lifecycle beyond the implemented fit/contact/draft gates.
- **Versioned snapshots (full T04):** snapshot/evidence versions and
  "newer changed snapshot" update policy beyond the current fill-only behavior.
- **Verified flag for HikerAPI leads:** requires a `leads.is_verified` column.
- **Live browser verification:** extension DOM extraction and 360/768/1280
  keyboard/visual walkthroughs.
- **Contact adapter and draft generation:** `contact-requests` and
  `draft-requests` persist the gate records but do not yet enqueue a contact
  adapter or regenerate draft text. Existing `ai_outreach` remains the draft
  generator.
- **Worker media without HikerAPI:** a future snapshot-media path would need the
  extension to capture recent post metadata.

---

## 15. Data model and API changes (summary)

### Migration `a1b2c3d4e5f6` (T04)

| Change | Detail |
| --- | --- |
| `leads.profile_snapshot` | `Text`, not null, default `''` — sanitized snapshot JSON |
| `leads.request_id` | `String(64)`, not null, default `''` |
| `ix_leads_request_id` | B-tree index on `request_id` |

### Migration `b2c3d4e5f6a7` (T08/T09)

| Change | Detail |
| --- | --- |
| `leads.fit_status` | `String(32)`, default `not_reviewed`, indexed |
| `leads.fit_note` | `Text`, default `''` |
| `leads.fit_decided_at` | `String(40)`, default `''` |
| `contact_requests` | PK `request_id`, FK `lead_id` (cascade), `status`, `note`, `requested_at` |
| `outreach_revisions` | PK `revision_id`, FK `lead_id` (cascade), `channel`, `status`, subject/body/DM, `requested_at` |
| `worker_heartbeat` | PK `heartbeat_id` (singleton `worker`), `worker_id`, `beat_at` (indexed) |

Both migrations are applied by the API container on start
(`alembic upgrade head`); the current head is `b2c3d4e5f6a7`, verified in
PostgreSQL.

### API contract additions (backward compatible)

- `POST /api/v1/leads` accepts optional `request_id` and `profile_snapshot`;
  handle-only clients are unchanged.
- Responses include `outcome` and `missing_fields` on submission.
- `LeadResponse` includes `progress`, `progress_remedy`, a read-only `snapshot`
  object, and `fit_status`/`fit_note`/`fit_decided_at`.
- `retry-ai` returns HTTP 409 with a stable `AI_UNAVAILABLE` detail when AI is
  not configured.
- Stats include `leads_by_progress`; the list `status` filter matches derived
  progress.
- `PATCH /api/v1/leads/{id}/fit` records a fit decision.
- `POST /api/v1/leads/{id}/contact-requests` and `/draft-requests` are
  approval-gated (403 otherwise); `GET .../draft-requests` lists revision history.
- `GET /api/v1/integrations/status` returns secret-free readiness including
  `worker_last_beat_at`.

---

## 16. File inventory (redesign)

**Backend**

```text
app/constants.py                     stages/statuses, derived states, fit/draft constants
app/db/progress.py                   derived research status + remedies
app/db/models.py                     snapshot, fit, contact requests, revisions, heartbeat
app/db/schemas.py                    corresponding row models
app/db/repository.py                 progress, defer(), fit, requests, revisions, heartbeat
app/leads/schemas.py                 snapshot intake, ProfileSnapshotOut, fit/request models
app/leads/service.py                 sanitization, idempotency, fit gates, revision history
app/leads/routes.py                  leads + PATCH /fit + contact/draft/revision endpoints
app/dashboard/routes.py              409 AI guard, detail progress, /integrations/status
app/dashboard/service.py             detail progress + integrations_status()
app/dashboard/schemas.py             LeadDetailOut, StatsOut, IntegrationsStatusOut
app/worker/pipeline.py               snapshot bypass, masking, deferral, draft guard
app/worker/main.py                   optional HikerAPI, deferred outcomes, heartbeat
app/worker/snapshot.py               snapshot -> lead fields
app/ai/masking.py                    contact-pattern masking
app/ai/evidence.py                   masked AI evidence
alembic/versions/a1b2c3d4e5f6_add_capture_snapshot.py
alembic/versions/b2c3d4e5f6a7_fit_requests_heartbeat.py
tests/test_progress.py
tests/test_worker_snapshot.py
tests/test_fit_gates.py
tests/test_integrations_status.py
tests/test_api_leads.py
tests/test_dashboard_api.py
tests/test_worker_ai_stages.py
```

**Extension**

```text
lib.js, content.js, background.js, popup.html, popup.js, styles.css,
manifest.json, lib.test.js, README.md
```

**Frontend**

```text
lib/types.ts, lib/format.ts, lib/api.ts,
actions/leads.ts, actions/fit.ts,
components/ui.tsx, components/nav.tsx, components/top-nav.tsx,
components/add-lead-form.tsx, components/leads-table.tsx, components/lead-filters.tsx,
components/fit-decision.tsx, components/outreach-gates.tsx,
app/(dashboard)/layout.tsx, app/(dashboard)/leads/page.tsx,
app/(dashboard)/leads/[leadId]/page.tsx, app/(dashboard)/dossiers/page.tsx,
app/(dashboard)/outreach/page.tsx,
app/(dashboard)/settings/page.tsx, app/(dashboard)/settings/loading.tsx
```

**Docs**

```text
docs/api.md, docs/database.md, docs/worker.md, docs/dashboard.md,
docs/extension-capture.md, README.md, DEPLOYMENT_ORACLE.md,
IMPLEMENTATION_REPORT_v1.1.md
```

---

## 17. How to verify

```powershell
# Backend (suite lives in tests/, not backend/tests/)
.\backend\.venv\Scripts\python.exe -m pytest

# Extension (fixtures only; no browser)
node --test extension/lib.test.js

# Frontend
cd frontend
npm run lint
npx tsc --noEmit
npm run build

# Containers + migrations
docker compose --profile frontend up -d --build
docker compose exec api alembic upgrade head
docker compose exec db psql -U postgres -d synpo -c "select version_num from alembic_version;"
# expected: b2c3d4e5f6a7

# Readiness (replace with your key)
curl -s -H "x-api-key: $API_KEY" http://127.0.0.1:8000/api/v1/integrations/status
```

Transactional checks:

```powershell
# 1) create a lead, 2) contact gate should 403, 3) approve, 4) gate should 201
# 5) two draft requests should yield two revisions
```

Manual follow-ups (cannot run headless here): load the unpacked extension on a
real profile, confirm the snapshot preview and verified-rail scan; then walk the
console at 360, 768, and 1280 CSS pixels with keyboard-only navigation, including
`/settings` and the lead fit-approval controls.
