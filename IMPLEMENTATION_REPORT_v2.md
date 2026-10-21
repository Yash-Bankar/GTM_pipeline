# Implementation Report v2 — Creator Review Workspace

**Project:** Synpo GTM Automation
**Reference specification:** `../GTM_Pipeline_PRD_v2_Creator_Review.md` (v2.0, 20 October 2026)
**Report date:** 2026-10-21
**Status:** V2-01 through V2-08 **Complete**. V2-09 is tracked but not started.

---

## 1. Work package tracking

| Package | Scope | Status |
| --- | --- | --- |
| **V2-01 · Stop unintended work** | Remove auto-outreach fan-out; guard disabled AI; withdraw blanket contact masking; preserve drafts | **COMPLETE** |
| V2-02 · Evidence and scheduling | Durable receipts, immutable versions, safe merge, recapture processing, concurrency | **COMPLETE** |
| V2-03 · Review and state | Separate research/fit, one campaign config, material-change rules, decision history | **COMPLETE** |
| V2-04 · Brief and public contacts | Full non-AI evidence brief, incidental contact extraction/provenance, legacy migration | **COMPLETE** |
| V2-05 · Extension reliability | Capture preview, scoped key, 50-item queue, connection/retry outcomes | **COMPLETE** |
| V2-06 · Explicit discovery | Executable discovery requests, scoped adapter/manual path, idempotency, cancellation | **COMPLETE** |
| **V2-07 · Drafts and manual history** | Manual editor, optional generation, immutable versions, copy/export, sent/reply events | **COMPLETE** |
| **V2-08 · Review workspace UX** | Creators views/detail, contextual actions, live progress, responsive forms | **COMPLETE** |
| V2-09 · Migration and release QA | Safe backfill, compatibility, test isolation, end-to-end sign-off | Not started |

---

## 2. V2-01 — Stop unintended work (Complete)

### 2.1 Remove auto-fan-out

| Behavior | Before | After |
| --- | --- | --- |
| AI dossier completion | Enqueued `ai_outreach` automatically | **No outreach/draft job**; dossier completion is terminal for that action |
| "Retry AI" (`POST /leads/{id}/retry-ai`) | Enqueued `ai_dossier` **and** `ai_outreach` | Enqueues **`ai_dossier` only** |
| Shortlist / fit approval | No scheduling (already) | Still no contact discovery, no draft generation; verified by test |
| Draft generation | Only via explicit `POST /leads/{id}/draft-requests` | Unchanged; never implicit |

Evidence:
- `backend/app/worker/pipeline.py` — removed the `STAGE_AI_OUTREACH` enqueue from
  `AIDossierStage.run`.
- `backend/app/dashboard/service.py` — `retry_ai` re-queues only the dossier.
- No route or stage automatically sends messages or schedules discovery.

### 2.2 Guard disabled AI

- Added `AIDisabledStage` (`backend/app/worker/pipeline.py`). When AI is not
  enabled, `build_stages` registers it for `ai_dossier` **and** `ai_outreach`.
  A queued AI job now completes with `"AI disabled; no provider call"` instead of
  failing as an unregistered stage.
- `retry_ai` still returns **HTTP 409 `AI_UNAVAILABLE`** before enqueue when AI
  is disabled.
- Manual workflow is fully usable without AI: fit decisions, contact requests,
  and draft requests do not depend on AI.
- Added an **evidence-only creator brief** so the former Dossier view renders
  without an AI call:
  - `GET /api/v1/leads/{lead_id}/brief` (`backend/app/dashboard/routes.py`).
  - Built from the lead, snapshot metadata, external links, and website pages;
    `has_dossier=false`, `ai_status="not_generated"` when no dossier exists.
  - `frontend/src/app/(dashboard)/dossiers/[leadId]/page.tsx` falls back to this
    brief on a missing dossier and renders an honest "AI summary not generated"
    view (no fabricated score).

### 2.3 Withdraw blanket contact masking (policy change)

Per v2 §1 and §10, blanket pre-shortlist contact masking is withdrawn. Public
business contacts present in a captured bio or researched page are retained and
visible to authenticated operators.

- `backend/app/worker/snapshot.py` — bio is whitespace-normalized only; no
  masking.
- `backend/app/worker/pipeline.py` — website page text is stored unmasked.
- `backend/app/ai/evidence.py` — AI evidence keeps public contacts (the v2 policy
  permits minimization later, but the blanket masking is removed).
- `backend/app/ai/masking.py` — now contains only `normalize_bio`; the
  `mask_contact_patterns` helper and its exports were removed.
- `business_email` / `business_phone_number` are still not auto-populated from a
  snapshot (structured contact records/provenance are V2-04); the public value is
  visible in the lead's `bio` immediately.

**Policy-change record (required by v2 §10):** the old blanket-masking
requirement (v1.1 A24 / QA F05) is intentionally superseded. The matching
assertions were removed or inverted. This is a deliberate policy change, not a
regression masked by retaining the old behavior.

### 2.4 Files changed

**Backend**

```text
app/worker/pipeline.py       remove dossier→outreach fan-out; add AIDisabledStage; no page masking
app/worker/main.py           register AI-disabled guard stages
app/worker/snapshot.py       normalize bio only (no masking)
app/ai/evidence.py           retain public contacts in AI evidence
app/ai/masking.py            normalize_bio only; mask_contact_patterns removed
app/ai/__init__.py           exports updated
app/dashboard/service.py     retry_ai -> dossier only; lead_brief()
app/dashboard/routes.py      GET /leads/{id}/brief
app/dashboard/schemas.py     BriefOut / BriefSourceOut
app/leads/schemas.py         ProfileSnapshotOut docstring (policy change)
```

**Frontend**

```text
lib/types.ts                              Brief types
lib/api.ts                                getBrief()
app/(dashboard)/dossiers/[leadId]/page.tsx evidence-brief fallback (no AI)
```

**Docs**

```text
docs/worker.md   V2-01 behavior, no fan-out, heartbeat/poll guidance, tests
docs/api.md      V2-01 contact policy + /brief endpoint
CLAUDE.md        public-contact and no-unintended-work rules
```

**Tests**

```text
tests/test_no_unintended_work.py   NEW (6 tests)
tests/test_worker_ai_stages.py     dossier completion asserts no outreach job
tests/test_dashboard_api.py        retry-ai asserts only ai_dossier
tests/test_worker_snapshot.py      V08 test; unmasked contacts; disabled guard stages
tests/test_api_leads.py            snapshot exposure comment updated
```

### 2.5 Tests added / updated (V2-01)

New `tests/test_no_unintended_work.py`:

1. `test_dossier_completion_does_not_enqueue_outreach` — direct stage execution;
   exactly one provider call; no outreach job/revision.
2. `test_retry_ai_enqueues_only_the_dossier` — API path; no outreach job.
3. `test_shortlist_does_not_schedule_contact_or_draft` — approve fit creates no
   jobs, contact requests, or draft revisions.
4. `test_ai_disabled_stages_complete_without_a_provider` — guard stages registered
   and complete harmlessly.
5. `test_manual_workflow_works_with_ai_disabled` — fit + contact + draft requests
   succeed with AI disabled; no outreach job.
6. `test_brief_renders_from_raw_evidence_without_ai` — `/brief` returns the bio
   (including a public email) with `has_dossier=false` and creates no work.

Updated:

- `tests/test_worker_ai_stages.py::test_dossier_stage_generates_without_scheduling_outreach`
  (renamed from `..._enqueues_outreach`; asserts no `ai_outreach` job and one call).
- `tests/test_dashboard_api.py::test_retry_ai_enqueues_only_the_dossier`.
- `tests/test_worker_snapshot.py::test_v08_public_business_contacts_saved_and_visible`
  (replaces the obsolete masking assertion; asserts the email/phone are saved and
  exposed via `LeadResponse`, and no discovery request is created).
- `tests/test_worker_snapshot.py::test_build_evidence_keeps_public_contacts`.
- `tests/test_worker_snapshot.py::test_website_enrich_runs_from_snapshot_urls`
  now asserts the public email is retained.
- `tests/test_worker_snapshot.py::test_build_stages_without_hiker_key_does_not_require_credentials`
  now asserts the disabled guard stages exist.

Removed obsolete masking tests:

- `test_snapshot_masks_bio_and_leaves_contacts_unpopulated`
- `test_mask_contact_patterns_masks_email_and_phone_but_not_dates`
- `test_build_evidence_masks_bio_posts_and_pages`

> The v2 PRD refers to `test_intake_masks_contact_before_worker`; that exact name
> does not exist in this repository. The equivalent stale masking assertions
> above were the ones removed/inverted.

### 2.6 Acceptance coverage (V2-01)

| ID | Scenario | Status |
| --- | --- | --- |
| V08 | Public bio/page contains a business email before shortlist | **Covered** — saved, unmasked, visible; no discovery job |
| V10 | AI unavailable | **Covered** — brief + manual workflow work |
| V11 | AI recommendation/dossier completes | **Covered** — no discovery/draft job |
| V12 | Shortlist click | **Covered** — no contact/AI work scheduled |
| V22 | AI disabled; manual draft request | **Covered** — record created; no orphan AI job |

### 2.7 Verification

| Check | Command | Result |
| --- | --- | --- |
| Backend | `python -m pytest` | **229 passed** |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend build | `npm run build` | success |

Note: the backend suite lives in `tests/` (there is no `backend/tests/`); run
`python -m pytest` from the repository root.

### 2.8 Notes and boundaries

- Structured contact **records** with type/provenance/validation (V2-04) and
  executable discovery requests (V2-06) are not part of V2-01. The public
  contact is currently visible through the lead's `bio`/page evidence.
- The evidence brief is a **read-only fallback** for the Dossier view. The full
  brief experience (campaign criteria, decision history, provenance UI) is V2-04/
  V2-08.
- `draft-requests`/`contact-requests` persist gate records but do not yet enqueue
  adapters or generate text (V2-06/V2-07).
- Configuring `GEMINI_API_KEY`/`AI_ENABLED` remains optional; capture, research,
  the evidence brief, and manual decisions work without them.

---

## 3. V2-02 — Evidence and scheduling (Complete)

### 3.1 Capture receipts

- Every capture with a `request_id` writes an immutable `capture_receipts` row
  (`request_id` PK, `lead_id`, `payload_hash`, `outcome`, `received_at`).
- Replaying the **same** `request_id` + payload returns the original lead with
  `outcome="unchanged"` and creates **no** new evidence version, job, or spend.
- Reusing a `request_id` with a **different** payload returns **HTTP 409** with
  `{"code": "REQUEST_ID_CONFLICT"}` and mutates nothing.
- Pending queue retention is unchanged: the extension keeps a pending item until
  the server acknowledges or the operator discards it, and retries reuse the
  same request id.

### 3.2 Immutable evidence versions

New table `evidence_versions` (one row per accepted capture):

| Column | Meaning |
| --- | --- |
| `evidence_version_id` (PK) | `ev_<uuid hex>` |
| `lead_id` | FK ? `leads` (cascade) |
| `version` | per-lead sequence (unique with `lead_id`) |
| `request_id` | capture that produced this version |
| `snapshot_json` | the **exact normalized snapshot** (immutable) |
| `captured_at` | client capture time (as supplied) |
| `received_at` | server receipt time (authoritative ordering) |
| `parser_version` | extraction implementation version |
| `field_provenance` | JSON map of field ? `"snapshot"` |
| `changed_fields` | JSON list of material fields changed vs the current snapshot |
| `created_at` | row creation time |

`leads` gained a current evidence pointer: `evidence_version` (integer) and
`evidence_version_id`. `LeadResponse` exposes both. The brief endpoint also
returns `evidence_version`.

### 3.3 Safe merge, recency, and concurrent identity

- **Identity:** `normalize_username` + the unique `leads.username_normalized`
  index resolve handle/URL/uppercase variants to one lead. Concurrent inserts are
  handled by the existing `IntegrityError` ? re-fetch path.
- **Recency:** ordering uses the **server receipt time**. A client
  `captured_at` is used only when plausible; a missing or future clock (>5 min
  ahead) is clamped to `received_at`, so a manipulated clock cannot jump ahead.
- **Merge:** newer evidence may update known non-empty fields; stale evidence is
  retained as immutable history but **does not mutate the lead** or advance the
  pointer. Missing fields never erase known values; unknown counts never replace
  known counts. Identical payloads create no duplicate version or work.
- **Useful recapture:** a newer, changed snapshot enqueues `profile_fetch`
  (`on_duplicate="reenqueue"`) so research runs for the new evidence version.
- **Handle-only intake:** with no snapshot and no configured source, the lead is
  saved as `needs_data` and **no research job** is queued. With HikerAPI (or a
  snapshot) available, research is queued. A later useful recapture moves the
  lead out of `needs_data` and schedules research (V06).

### 3.4 Exact database/schema changes

Migration **`c3d4e5f6a7b8_capture_receipts_evidence_versions.py`**
(down_revision `b2c3d4e5f6a7`):

```text
leads
  + evidence_version      INTEGER NOT NULL DEFAULT 0
  + evidence_version_id   VARCHAR(64) NOT NULL DEFAULT ''
  + ix_leads_evidence_version_id (evidence_version_id)

capture_receipts (new)
  request_id    VARCHAR(64) PK
  lead_id       VARCHAR(64) FK leads(lead_id) ON DELETE CASCADE, indexed
  payload_hash  VARCHAR(64) NOT NULL DEFAULT ''
  outcome       VARCHAR(32) NOT NULL DEFAULT ''
  received_at   VARCHAR(40) NOT NULL DEFAULT ''
  created_at    VARCHAR(40) NOT NULL DEFAULT ''

evidence_versions (new)
  evidence_version_id VARCHAR(64) PK
  lead_id             VARCHAR(64) FK leads(lead_id) ON DELETE CASCADE, indexed
  version             INTEGER NOT NULL DEFAULT 1
  request_id          VARCHAR(64) NOT NULL DEFAULT '', indexed
  snapshot_json       TEXT NOT NULL DEFAULT ''
  captured_at         VARCHAR(40) NOT NULL DEFAULT ''
  received_at         VARCHAR(40) NOT NULL DEFAULT '', indexed
  parser_version      VARCHAR(32) NOT NULL DEFAULT ''
  field_provenance    TEXT NOT NULL DEFAULT ''
  changed_fields      TEXT NOT NULL DEFAULT ''
  created_at          VARCHAR(40) NOT NULL DEFAULT ''
  UNIQUE (lead_id, version)  -- uq_evidence_versions_lead_version
```

Current migration head: **`c3d4e5f6a7b8`** (verified in PostgreSQL).

### 3.5 API behavior

- `POST /api/v1/leads` now returns `research_queued` and the lead's
  `evidence_version`/`evidence_version_id`.
- Reusing a request id with a changed payload ? **409 `REQUEST_ID_CONFLICT`**.
- `outcome` semantics: `new` (created), `updated` (newer evidence applied),
  `unchanged` (replay, stale, or identical evidence).
- Handle-only with no source ? lead `status="needs_data"`, `research_queued=false`.

### 3.6 Tests (V2-02)

New `tests/test_evidence_versions.py` (8 tests):

1. `test_v01_handle_url_uppercase_resolve_to_one_lead`
2. `test_v01_concurrent_insert_race_returns_existing`
3. `test_v02_aba_replay_returns_original_without_rollback`
4. `test_v03_request_id_reused_with_different_payload_is_conflict`
5. `test_v04_future_clock_and_stale_snapshot_preserve_newer_evidence`
6. `test_v06_handle_only_needs_data_then_recapture_queues_research`
7. `test_receipt_and_immutable_evidence_version_are_recorded`
8. `test_identical_new_request_creates_no_duplicate_version`

Updated `tests/test_api_leads.py`:
`test_newer_snapshot_updates_and_stale_never_erases` (newer evidence updates;
older evidence is retained as history without mutating the lead).

`tests/conftest.py` now sets a deterministic `HIKERAPI_KEY` so handle-only
captures queue research in the default test environment; tests that need no
source override it and clear the settings cache.

### 3.7 Verification

| Check | Command | Result |
| --- | --- | --- |
| Backend | `python -m pytest` | **237 passed** |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend build | `npm run build` | success |
| Migration head | `alembic_version` | `c3d4e5f6a7b8` |
| Live replay | same request id/payload | `unchanged`, same lead, 1 version |
| Live conflict | same request id, changed payload | **409** |
| Live receipts | DB after capture | 1 receipt + 1 evidence version |

### 3.8 Files changed

**Backend**

```text
app/constants.py                     LEAD_STATUS_NEEDS_DATA
app/db/models.py                     Lead evidence pointer; CaptureReceipt; EvidenceVersion
app/db/schemas.py                    matching row models
app/db/repository.py                 receipt + evidence-version methods
app/leads/evidence.py                NEW: recency, merge, provenance, payload hash
app/leads/service.py                 receipts, conflicts, versions, safe merge, research queueing
app/leads/schemas.py                 evidence_version fields + research_queued
app/leads/routes.py                  409 REQUEST_ID_CONFLICT
app/dashboard/service.py             brief evidence_version
app/dashboard/schemas.py             BriefOut.evidence_version
alembic/versions/c3d4e5f6a7b8_capture_receipts_evidence_versions.py
tests/test_evidence_versions.py      NEW (8 tests)
tests/test_api_leads.py              newer/stale merge test
tests/conftest.py                    deterministic HIKERAPI_KEY
```

**Frontend**

```text
lib/types.ts                          Brief.evidence_version
app/(dashboard)/dossiers/[leadId]/page.tsx  shows Evidence vN
```

**Docs**

```text
docs/api.md       409 conflict, receipts/versions, evidence_version
docs/database.md  new tables + lead evidence columns
```

---

## 4. V2-03 — Review and state (Complete)

### 4.1 State model

| Dimension | Values | Notes |
| --- | --- | --- |
| `fit_status` | `not_reviewed`, `research_more`, `shortlisted`, `rejected` | Manual operator intent |
| `decision_currency` | `current`, `review_needed` | Whether a shortlist still matches material evidence/criteria |
| `research_status` (derived) | `needs_data`, `queued`, `running`, `complete`, `blocked` | Computed from jobs; `ready` renamed to `complete` |

Pre-v2 action names are accepted as aliases (`approve` ? `shortlist`,
`need_evidence` ? `research_more`) but storage always uses the v2 values. The
migration maps existing `approved` ? `shortlisted` and `needs_evidence` ?
`research_more`.

### 4.2 Campaign configuration

One active campaign: `name`, `description`, `target_topics`, optional
`language`, `follower_min`, `follower_max`, and an incrementing `version`
(0 = not configured).

- `GET /api/v1/campaign` — current configuration (version 0 when absent).
- `PUT /api/v1/campaign` — replace/increment the version.
- Updating criteria marks every `shortlisted` decision with
  `decision_currency=review_needed` and writes a system history event; this is
  a deliberate deterministic invalidation, not AI judgment.

### 4.3 Material-change policy (deterministic)

When a creator is **shortlisted** and a newer capture is applied, the decision
becomes `review_needed` only if one or more of these are true:

1. **Bio changed** (normalized text differs).
2. **External domain changed** (the set of domains in external links differs).
3. **Follower count crossed the campaign threshold** (with a configured
   `follower_min`/`follower_max`; unknown values never count as a crossing).

Timestamp-only recaptures, display/precision-only changes, and identical evidence
do **not** invalidate a shortlist. Stale evidence is retained as history but does
not mutate the lead. A **rejected** creator receiving new evidence stays
`rejected`, keeps `decision_currency=current`, and gains
`new_evidence_available=true` (with a `new_evidence` history event); it cannot be
contacted/drafted until explicitly reopened.

### 4.4 Decision history

`fit_decisions` is append-only and records every manual decision plus system
events:

| Column | Meaning |
| --- | --- |
| `decision_id` (PK) | `fd_<uuid hex>` |
| `lead_id` | FK ? `leads` (cascade) |
| `action` | `shortlist`, `research_more`, `reject`, `reopen`, `review_needed`, `new_evidence` |
| `fit_status` | resulting status |
| `decision_currency` | resulting currency |
| `evidence_version` | lead's evidence version at the time |
| `criteria_version` | active campaign version (0 when none) |
| `note` | operator note or system reason |
| `actor` | `shared dashboard operator` or `system` |
| `created_at` | microsecond-precision timestamp for stable ordering |

`GET /api/v1/leads/{lead_id}/fit-decisions` returns the history.

Reopening is only valid from `rejected`, always returns the creator to
`not_reviewed`, clears `new_evidence_available`, and never auto-shortlists.

### 4.5 Gated actions

Contact and draft requests require **`fit_status=shortlisted` AND
`decision_currency=current`**. If review is needed, the API returns `403` with
`{"code": "FIT_APPROVAL_REQUIRED", "fit_status": ..., "decision_currency":
"review_needed"}` and the UI explains that fit must be reconfirmed.

### 4.6 Exact database/schema changes

Migration **`d4e5f6a7b8c9_review_state.py`** (down_revision `c3d4e5f6a7b8`):

```text
leads
  + decision_currency        VARCHAR(32) NOT NULL DEFAULT 'current', indexed
  + decision_currency_reason TEXT NOT NULL DEFAULT ''
  + new_evidence_available   BOOLEAN NOT NULL DEFAULT false
  (data) fit_status: 'approved' -> 'shortlisted', 'needs_evidence' -> 'research_more'

campaigns (new)
  campaign_id    VARCHAR(64) PK
  name           VARCHAR(255) NOT NULL DEFAULT ''
  description    TEXT NOT NULL DEFAULT ''
  target_topics  TEXT NOT NULL DEFAULT ''        -- JSON list
  language       VARCHAR(32) NOT NULL DEFAULT ''
  follower_min   INTEGER NOT NULL DEFAULT 0
  follower_max   INTEGER NOT NULL DEFAULT 0
  version        INTEGER NOT NULL DEFAULT 1
  is_active      BOOLEAN NOT NULL DEFAULT true, indexed
  created_at, updated_at VARCHAR(40)

fit_decisions (new)
  decision_id       VARCHAR(64) PK
  lead_id           VARCHAR(64) FK leads(lead_id) ON DELETE CASCADE, indexed
  action            VARCHAR(32) NOT NULL DEFAULT ''
  fit_status        VARCHAR(32) NOT NULL DEFAULT ''
  decision_currency VARCHAR(32) NOT NULL DEFAULT 'current'
  evidence_version  INTEGER NOT NULL DEFAULT 0
  criteria_version  INTEGER NOT NULL DEFAULT 0
  note              TEXT NOT NULL DEFAULT ''
  actor             VARCHAR(64) NOT NULL DEFAULT ''
  created_at        VARCHAR(40) NOT NULL DEFAULT '', indexed
```

Current migration head: **`d4e5f6a7b8c9`** (verified in PostgreSQL).

### 4.7 API additions

- `POST /api/v1/leads` responses expose `decision_currency`,
  `decision_currency_reason`, `new_evidence_available`, and `research_status`.
- `PATCH /api/v1/leads/{id}/fit` accepts `shortlist`, `research_more`, `reject`,
  `reopen` (plus the legacy aliases). Reject requires a note; a rejected creator
  must be reopened first.
- `GET /api/v1/campaign` / `PUT /api/v1/campaign`.
- `GET /api/v1/leads/{id}/fit-decisions`.
- Research filters/counters use `complete` instead of `ready`.

### 4.8 Frontend

- Fit bar: **Shortlist**, **Research more**, **Reject**, and **Reopen for review**
  (only when rejected).
- Review-needed and new-evidence badges on the detail and leads table.
- Contact/draft buttons are disabled until the shortlist is current, with the
  reason shown.
- Decision history card; campaign criterion version shown per event.
- Research status enum updated to `complete`.

### 4.9 Tests (V2-03)

New `tests/test_review_state.py` (9 tests):

1. `test_v13_research_more_reject_reopen_and_shortlist`
2. `test_v13_legacy_action_aliases_still_work`
3. `test_v14_bio_change_marks_review_needed_and_blocks_gates`
4. `test_v14_external_domain_change_marks_review_needed`
5. `test_v14_follower_threshold_crossing_marks_review_needed`
6. `test_v15_timestamp_only_and_unchanged_recaptures_do_not_invalidate`
7. `test_v16_rejected_creator_gains_new_evidence_flag_without_reopening`
8. `test_campaign_configuration_roundtrip_and_invalidates_shortlists`
9. `test_campaign_rejects_unknown_fields`

Updated existing tests for the v2 vocabulary (`shortlist`/`research_more`;
research `complete`).

### 4.10 Verification

| Check | Command | Result |
| --- | --- | --- |
| Backend | `python -m pytest` | **246 passed** |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend build | `npm run build` | success |
| Migration head | `alembic_version` | `d4e5f6a7b8c9` |
| Live: shortlist + recapture | changed bio + follower crossing | `review_needed`, evidence v2, both reasons |
| Live: gate | contact request while review needed | **403** with `decision_currency=review_needed` |
| Live: history | after shortlist + invalidation | `shortlist`, `review_needed` |
| Live: rejected + new evidence | recapture after reject | stays `rejected`, `new_evidence_available=true` |
| Live: reopen | reopen | `not_reviewed`, flag cleared |
| Live: campaign | GET/PUT | version 0 -> 1; invalidates current shortlists |

### 4.11 Files changed

**Backend**

```text
app/constants.py                     v2 fit/currency states + aliases; RESEARCH_COMPLETE
app/db/progress.py                   returns "complete"
app/db/models.py                     Lead currency/new-evidence; Campaign; FitDecision
app/db/schemas.py                    matching row models + Lead fields
app/db/repository.py                 bool field coercion; campaign; fit decisions
app/db/util.py                       utc_now_iso_precise
app/campaigns/{__init__,schemas,service,routes}.py   NEW
app/dependencies.py                  get_campaign_service
app/main.py                          campaign router
app/leads/evidence.py                material_change_reasons + domain extraction
app/leads/service.py                 transitions, history, invalidation, gates
app/leads/schemas.py                 LeadResponse fields; FitDecision models; actions
app/leads/routes.py                  gates + fit-decisions endpoint
alembic/versions/d4e5f6a7b8c9_review_state.py
tests/test_review_state.py           NEW (9 tests)
tests/test_fit_gates.py              v2 actions/statuses
tests/test_no_unintended_work.py     shortlist action
tests/test_api_leads.py              status=complete
```

**Frontend**

```text
lib/types.ts                         currency/new-evidence/research fields, FitDecision
lib/api.ts                           decideFit actions, listFitDecisions
lib/format.ts                        complete/shortlisted/research_more/review_needed tones
actions/fit.ts                       v2 actions/messages
components/fit-decision.tsx          shortlist/research more/reject/reopen + indicators
components/outreach-gates.tsx         shortlisted+current gate messaging
components/ui.tsx                    finished status set
components/lead-filters.tsx          complete option
components/leads-table.tsx           review-needed/new-evidence badges
app/(dashboard)/leads/page.tsx       complete counter
app/(dashboard)/leads/[leadId]/page.tsx  fit props, gate reason, decision history
```

**Docs**

```text
docs/api.md, docs/database.md
```

---

## 5. V2-04 — Brief and public contacts (Complete)

### 5.1 Non-AI creator brief

`GET /api/v1/leads/{lead_id}/brief` now returns a structured Creator brief built
entirely from parsed evidence — no AI provider, no dossier row required:

- identity (`username`, `full_name`, verified flag, category),
- bio and `observed_topics` (category plus campaign topics actually present in the
  text; never invented),
- counts with display/precision (`followers`, `following`, `post_count`),
- `websites` (supplied external links plus observed crawled pages, with status),
- `contacts` with provenance,
- `missing_fields`, evidence version, and optional AI summary if one exists.

The existing Dossier view falls back to this brief when no AI dossier exists.
The brief is read-only and creates no work.

### 5.2 Incidental contact extraction (worker)

The website crawler now extracts publicly listed **emails and phone numbers** from
each fetched page (existing limits: up to 5 pages, depth 2, 10 s/request).
`WebsiteEnrichStage` stores every discovery as an evidence-backed row in the new
`contacts` table:

| Column | Meaning |
| --- | --- |
| `contact_id` (PK) | deterministic `ct_<sha1(lead|type|value|source)>` |
| `lead_id` | FK ? `leads` (cascade) |
| `type` | `email` / `phone` |
| `value` | public value as observed |
| `source_url` | page that exposed it |
| `observed_at` | extraction time |
| `method` | `website_crawl` (or `legacy`) |
| `validation_state` | `unverified` (publicly listed, not verified) |

Repeated crawls upsert by contact id (no duplicate rows). The crawler's aggregate
email list is attributed to the first supplied URL when a page source is not
available.

**Visibility:** contacts are returned by `GET /api/v1/leads/{id}/contacts`, the
`/detail` response, and the brief — for authenticated dashboard users, **with no
shortlist/fit gate**.

### 5.3 Legacy contact migration

Existing public contact fields (`leads.business_email`,
`leads.business_phone_number`) are backfilled by the migration into `contacts`
with `method='legacy'`, empty `source_url`, and `observed_at` from the lead's
timestamps. The API labels any contact without a source/method as
**"Legacy source unknown"**; no source or validation claim is invented. The
original legacy fields remain on the lead.

### 5.4 Exact database/schema changes

Migration **`e5f6a7b8c9d0_contacts.py`** (down_revision `d4e5f6a7b8c9`):

```text
contacts (new)
  contact_id       VARCHAR(64) PK
  lead_id          VARCHAR(64) FK leads(lead_id) ON DELETE CASCADE, indexed
  type             VARCHAR(16) NOT NULL DEFAULT 'email', indexed
  value            VARCHAR(512) NOT NULL DEFAULT ''
  source_url       VARCHAR(1024) NOT NULL DEFAULT ''
  observed_at      VARCHAR(40) NOT NULL DEFAULT ''
  method           VARCHAR(32) NOT NULL DEFAULT ''
  validation_state VARCHAR(32) NOT NULL DEFAULT 'unverified'
  created_at, updated_at VARCHAR(40)

(data) backfill from leads.business_email / leads.business_phone_number
       with method='legacy', source_url='', deterministic contact_id (md5)
```

Current migration head: **`e5f6a7b8c9d0`** (verified in PostgreSQL; 4 legacy email
contacts backfilled from existing data).

### 5.5 Frontend

- Lead detail shows a **Public contacts** card (value, type, provenance, source,
  observed time) without any shortlist requirement.
- The Creator brief view shows observed topics, linked websites, and contacts.
- Legacy values render as **Legacy source unknown**.

### 5.6 Tests (V2-04)

New `tests/test_brief_contacts.py` (6 tests):

1. `test_brief_renders_without_ai` — brief works with AI disabled; no dossier.
2. `test_incidental_contacts_are_extracted_with_provenance` — email + phone from a
   crawled page with source/time/method; visible immediately.
3. `test_incidental_contacts_are_deduped_on_recrawl` — deterministic upsert.
4. `test_legacy_contacts_are_labeled_source_unknown` — legacy label, original
   fields preserved.
5. `test_brief_includes_contacts_and_websites`.
6. `test_phone_extraction_ignores_dates`.

### 5.7 Verification

| Check | Command | Result |
| --- | --- | --- |
| Backend | `python -m pytest` | **252 passed** |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend build | `npm run build` | success |
| Migration head | `alembic_version` | `e5f6a7b8c9d0` |
| Live legacy backfill | `contacts` grouped by type/method | 4 `email`/`legacy` |
| Live contacts API | `GET /leads/{id}/contacts` | `provenance="Legacy source unknown"` |
| Live brief | `GET /leads/{id}/brief` | websites + contacts included |

### 5.8 Files changed

**Backend**

```text
app/db/models.py                     Contact table
app/db/schemas.py                    Contact row model
app/db/util.py                       deterministic contact_id
app/db/repository.py                 upsert_contact / list_contacts
app/providers/emails.py              extract_phones
app/providers/website.py             FetchedPage.phones + extraction
app/worker/pipeline.py               website stage stores evidence-backed contacts
app/dashboard/schemas.py             ContactOut/ContactListOut; BriefOut/LeadDetailOut
app/dashboard/service.py             contacts(), brief topics/websites/contacts
app/dashboard/routes.py              contacts endpoint; detail contacts
alembic/versions/e5f6a7b8c9d0_contacts.py
tests/test_brief_contacts.py         NEW (6 tests)
```

**Frontend**

```text
lib/types.ts                         Contact + Brief fields + LeadDetail.contacts
app/(dashboard)/leads/[leadId]/page.tsx          Public contacts card
app/(dashboard)/dossiers/[leadId]/page.tsx       topics, linked websites, contacts
```

**Docs**

```text
docs/api.md, docs/database.md, docs/worker.md
```

---

## 6. V2-05 — Extension reliability (Complete)

### 6.1 Capture preview and payload

- The extension still captures **only profile-scoped fields** from the open
  profile: handle, display name, verified flag, bio, visible external links, and
  follower/following/post counts. It never reads cookies, session tokens, raw
  HTML, suggested accounts, hidden contact controls, or private content.
- The popup renders a preview before saving: verified status, display name,
  followers/following/posts with precision, bio excerpt, link count/first link,
  and an explicit `Missing: ...` line.
- A unit test asserts the snapshot's exact key set and that no session/cookie
  fields can be present.

### 6.2 Pending queue (50 max)

- Replaced the single pending capture / batch list with one unified
  `captureQueue` in `chrome.storage.local`.
- Queue rules (pure helpers in `lib.js`, unit-tested):
  - capacity **50**; the 51st capture is rejected with `reason="queue_full"` and
    the popup explains: "Pending saves are full (50/50). Retry or discard an item
    before capturing more."
  - an item leaves the queue **only** after a successful server acknowledgement
    (`created`/`duplicate`/`updated`) or an explicit **Discard**;
  - failures (network/auth/config/invalid/error) remain queued;
  - retries reuse the **original request id** (`retryPayload`);
  - enqueueing an existing request id updates it in place (no duplicates).
- Popup UI: a pending-saves list with count (`N/50`), per-item **Retry** and
  **Discard**, plus **Retry all pending**. The queue persists across popup
  open/close and browser restarts because it lives in local storage.
- Bulk "Add All Verified" failures are enqueued respecting the same capacity and
  report how many could not be queued.

### 6.3 Scoped key and settings

- Settings labels are now **Backend URL** and **Capture key**; the configured
  backend URL is shown so local/production cannot be mixed accidentally.
- **Test connection** performs an authenticated request
  (`GET /api/v1/leads?limit=1` with `x-api-key`) and distinguishes:
  - `connected` (2xx),
  - `auth` (401/403: "Capture key rejected..."),
  - `network` (unreachable / no status),
  - `error` (other backend status).
- The extension stores only `apiBaseUrl` and the capture key in
  `chrome.storage.local`. It never receives or stores dashboard passwords,
  HikerAPI keys, Gemini keys, or service-account credentials. A source-scanning
  unit test enforces this.
- **Boundary:** the backend currently authenticates capture with the shared
  `API_KEY` (`x-api-key`); a separate capture-scoped credential remains a backend
  authorization change. The extension is ready to accept it as the "Capture key"
  without exposing administrative/provider credentials.

### 6.4 Tests (V2-05)

`extension/lib.test.js` grew to **49 tests** (10 new for V2-05):

- 50-item capacity + overflow reason/message (V26);
- dedupe by request id and in-place update;
- discard removes only the targeted item;
- retry payload reuses the original request id;
- acknowledged saves leave the queue; failures are retained;
- queue JSON round-trip at capacity (restart persistence);
- items without a request id are rejected;
- connection classification: auth vs network vs connected vs backend error (V27);
- snapshot captures only profile-scoped fields (V32);
- static source scan forbids admin/provider credential names (V27).

Verification:

```powershell
npm --prefix extension test      # 49 passed
node --test extension/lib.test.js
node --check extension/lib.js extension/background.js extension/popup.js extension/content.js
```

`extension/package.json` was added so `npm --prefix extension test` runs the
Node test suite.

### 6.5 Files changed

```text
extension/lib.js         queue helpers + classifyConnection
extension/background.js  connection check uses the shared classifier
extension/popup.html     pending queue section, Backend URL / Capture key labels
extension/popup.js       unified 50-item queue, per-item retry/discard, retry all
extension/styles.css     queue item styles
extension/package.json   NEW: test script
extension/lib.test.js    10 new V2-05 tests
extension/README.md      queue/settings/test docs
```

---

## 7. V2-06 — Explicit discovery (Complete)

### 7.1 Executable contact requests

- `POST /api/v1/leads/{id}/contact-requests` now creates a durable request and
  enqueues a new **`contact_discovery`** worker stage.
- `ContactDiscoveryStage` performs a contact-focused pass over the lead's
  supplied external links plus already-observed website pages, using the existing
  bounded crawler (SSRF-safe, max 5 pages, depth 2, 10 s/request) and the same
  email/phone extraction.
- Discovered contacts are stored in `contacts` with
  `method="contact_discovery"`, `source_url`, `observed_at`, and
  `validation_state="unverified"`. They are visible immediately (no gate).

### 7.2 Idempotency (V18)

- A repeated click for the **same evidence version** returns the existing
  in-flight/completed request with **HTTP 200** and the same `request_id`; no new
  request row or job is created.
- `search_again: true` creates a new attempt (HTTP 201). Any older queued/retrying
  request for the lead is marked `cancelled` ("Superseded by a newer request").
- If a queued discovery job still points at an older request, it is retargeted to
  the new request payload.

### 7.3 Statuses and revocation (V20)

`contact_requests.status` lifecycle:

`queued` -> `running` -> `found` | `not_found` | `failed` | `cancelled`

- The request stores `evidence_version`, `searched_scope`, `result_count`,
  `error`, `started_at`, and `completed_at`.
- The shortlist gate is checked **before** the crawl and **again before
  publishing**. If the creator becomes `rejected` or `review_needed` during the
  pass, the request is marked `cancelled` and **no contacts are written**.
- `failed` covers "no public sources" and "all sources blocked/unreachable";
  `not_found` means sources were searched but produced no contact.

### 7.4 Manual fallback

- `GET /api/v1/leads/{id}/contact-requests` lists request history; the lead detail
  exposes the latest `contact_request`.
- The UI shows the request state, and on `not_found` displays
  **"No public contact found in searched sources."** with the searched scope and
  completion time.
- `POST /api/v1/leads/{id}/contacts` adds a manual contact with
  `type` (`email`/`phone`), `value`, and an **http(s) source URL**; it is stored
  with `method="manual"` and `provenance="Public website"`. No fit gate is needed
  for manual contact entry.
- A "Search again" action is offered for terminal `not_found`/`failed`/`cancelled`
  requests.

### 7.5 Exact database/schema changes

Migration **`f6a7b8c9d0e1_contact_discovery.py`** (down_revision
`e5f6a7b8c9d0`):

```text
contact_requests
  + evidence_version  INTEGER NOT NULL DEFAULT 0
  + searched_scope    TEXT NOT NULL DEFAULT ''
  + result_count      INTEGER NOT NULL DEFAULT 0
  + error             TEXT NOT NULL DEFAULT ''
  + started_at        VARCHAR(40) NOT NULL DEFAULT ''
  + completed_at      VARCHAR(40) NOT NULL DEFAULT ''
  + ix_contact_requests_lead_version (lead_id, evidence_version)
  (data) status 'requested' -> 'failed' with
         error='Legacy request not scheduled'   -- never silently bulk-run
```

Current migration head: **`f6a7b8c9d0e1`** (verified in PostgreSQL).

### 7.6 API additions

- `POST /leads/{id}/contact-requests` body `{ note?, search_again? }`;
  `201` for a new attempt, `200` for a reused in-flight/completed request.
- `GET /leads/{id}/contact-requests` — request history.
- `POST /leads/{id}/contacts` — manual sourced contact.
- `LeadDetailOut.contact_request` — latest request for the detail UI.

### 7.7 Frontend

- Contact & drafts shows the request state, searched scope/time, and the
  `not_found` message.
- The button becomes **Search again** after a terminal result.
- **Add contact with source** form (type, value, source URL) in Public contacts.

### 7.8 Tests (V2-06)

New `tests/test_contact_discovery.py` (10 tests):

1. `test_v17_contact_request_requires_current_shortlist`
2. `test_v18_repeated_click_reuses_the_existing_request`
3. `test_v18_search_again_creates_a_new_attempt`
4. `test_v19_discovery_found_stores_contacts_and_scope`
5. `test_v19_discovery_not_found_reports_searched_scope`
6. `test_v19_discovery_blocked_sources_fail`
7. `test_v20_revocation_before_run_cancels_without_contacts`
8. `test_v20_revocation_during_run_does_not_publish`
9. `test_manual_contact_with_source_is_saved`
10. `test_manual_contact_requires_valid_source_and_type`

### 7.9 Verification

| Check | Command | Result |
| --- | --- | --- |
| Backend | `python -m pytest` | **262 passed** |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend build | `npm run build` | success |
| Migration head | `alembic_version` | `f6a7b8c9d0e1` |
| Live gate | contact request on non-shortlisted lead | **403** |
| Live manual contact | `POST /leads/{id}/contacts` | `201`, `method=manual`, public provenance |

### 7.10 Files changed

**Backend**

```text
app/constants.py                     contact discovery stage + request states/methods
app/db/models.py                     ContactRequest evidence/scope/result/timestamps
app/db/schemas.py                    matching row fields
app/db/repository.py                 request lookup/update/latest, job retarget
app/leads/service.py                 idempotent request, supersede, manual contact
app/leads/schemas.py                 request status fields, search_again, manual contact
app/leads/routes.py                  idempotent POST, request list, manual contact
app/worker/pipeline.py               ContactDiscoveryStage + revocation checks
app/worker/main.py                   register contact_discovery
app/dashboard/{schemas,service,routes}.py  latest contact_request in detail
alembic/versions/f6a7b8c9d0e1_contact_discovery.py
tests/test_contact_discovery.py      NEW (10 tests)
tests/test_fit_gates.py              status queued
```

**Frontend**

```text
lib/types.ts                         ContactRequest + LeadDetail.contact_request
lib/api.ts                           requestContact(searchAgain), addContact
actions/fit.ts                       search again + add contact
components/outreach-gates.tsx        request state, scope/time, not-found copy
components/manual-contact-form.tsx   NEW
app/(dashboard)/leads/[leadId]/page.tsx  pass status, manual form
```

**Docs**

```text
docs/api.md, docs/database.md, docs/worker.md
```

---

## 8. V2-07 · Drafts and manual history (Complete)

### 8.1 Manual editor without an AI key (V22)

`POST /api/v1/leads/{lead_id}/drafts` saves the draft as a **new version**. It
never touches the AI provider and never needs a Gemini key, so the whole
manual workflow stays usable with AI disabled (PRD 4.5).

An explicit AI request is a different operation:
`POST /api/v1/leads/{lead_id}/drafts/generate`.

| Precondition | Result |
| --- | --- |
| AI disabled / key missing | `409` `{"code": "AI_UNAVAILABLE"}` — **no revision, request or job is written** |
| Creator not on a current shortlist | `403` `{"code": "FIT_APPROVAL_REQUIRED"}` |
| Both satisfied | `202` with the generation request; the worker writes a new version |

The availability check happens **before** anything is persisted, so a rejected
request leaves no orphan row (V22).

### 8.2 Immutable versions (V23)

Draft content lives in the new `draft_revisions` table. Versions are
**append-only**:

- Saving an edit creates the next version and marks the previous one
  `superseded`. The old content stays visible as history.
- Generating a version writes a **new** row whose `parent_revision_id` points at
  the version it was generated from.
- A request completes **once**: the stage checks `result_revision_id` and
  returns "revision already generated" on a retry, crash or restart, so a second
  version is never produced for the same request.
- An approved or manually authored draft is never silently replaced; it is
  superseded, and the new version sits beside it.

Review state is per version: `needs_review` → `reviewed`. Editing reviewed
content returns the **new** version to `needs_review`; the reviewed version
itself keeps its state so the record of what was reviewed survives.

### 8.3 Draft actions

| Action | Endpoint | Notes |
| --- | --- | --- |
| Edit / Save | `POST /leads/{id}/drafts` | Creates a new version; previous one superseded |
| Mark reviewed | `POST /leads/{id}/drafts/{rev}/review` | Changes only the review state |
| Copy | `GET /leads/{id}/drafts/{rev}/text` | Returns plain text; **never** marks sent |
| Export text | `GET /leads/{id}/drafts/{rev}/text` | Same payload, downloaded as `.txt` |
| Generate new version | `POST /leads/{id}/drafts/generate` | Requires enabled AI + a current shortlist |
| History | `GET /leads/{id}/drafts` | Every version, oldest first |

### 8.4 Manual outreach logging (V24)

`POST /api/v1/leads/{lead_id}/outreach-events` records a **manually logged**
event. It requires:

- a **channel** (`email` | `instagram_dm`),
- a **sent time** (pre-populated with the current time in the UI, always
  correctable),
- and either the **draft revision** that was sent or a **manual note**.

Outcomes: `Sent`, `Replied`, `Interested`, `Not interested`, `Follow up`. Every
event is labelled `manually_logged` and records the actor as the shared
dashboard operator — shared authentication is not a named employee.

**Copy/export and Mark reviewed never create a Sent event.** Only an explicit
manual log does. No route or stage sends a message.

### 8.5 Corrections as visible history (V25)

A correction is a **new event** that references the one it corrects
(`corrects_event_id`, `source="manually_logged_correction"`). The original row
is never rewritten, so the history keeps both entries while the latest summary
reflects the correction.

```
sent      manually_logged             <- original, untouched
replied   manually_logged             <- original, untouched
interested manually_logged_correction  <- corrects "replied"
```

### 8.6 Exact database/schema changes

Migration `a7b8c9d0e1f2` (down_revision `f6a7b8c9d0e1`):

| Table | Purpose |
| --- | --- |
| `draft_revisions` (new) | One row per saved draft version: content, `status`, `method`, `model`, `parent_revision_id`, `contact_id`, `request_id`, `evidence_scope`, `note`, `edited_at` |
| `outreach_events` (new) | Append-only manual log: `outcome`, `channel`, `revision_id`, `note`, `source`, `corrects_event_id`, `actor`, `sent_at`, `logged_at` |
| `outreach_revisions` (extended) | Generation request → result link: `result_revision_id`, `parent_revision_id`, `job_id`, `error` |

**Backfill:** every existing `outreach_drafts` row with content became the
first `draft_revisions` row for its lead (`dr_legacy_<lead_id>`), preserving the
content, its review state and the model that produced it. Nothing is discarded
and no job or sent event is created. On the live database this preserved **8**
existing drafts.

### 8.7 API additions

```text
GET  /api/v1/leads/{lead_id}/drafts                      saved versions, oldest first
POST /api/v1/leads/{lead_id}/drafts                      save/edit as a new version
POST /api/v1/leads/{lead_id}/drafts/{revision_id}/review mark reviewed
GET  /api/v1/leads/{lead_id}/drafts/{revision_id}/text   copy / export text
POST /api/v1/leads/{lead_id}/drafts/generate             request a new AI version
GET  /api/v1/leads/{lead_id}/outreach-events             manual outreach history
POST /api/v1/leads/{lead_id}/outreach-events             log an event / a correction
```

### 8.8 Frontend

| File | Change |
| --- | --- |
| `components/draft-editor.tsx` (new) | Save, Mark reviewed, Copy, Export text, Generate new version; unsaved-edit exit warning |
| `components/outreach-log-form.tsx` (new) | Log sent / outcome form: channel, pre-filled sent time, revision or note |
| `components/outreach-history.tsx` (new) | Manual history with "Manually logged" / "Correction" labels and a correct-this-entry action |
| `app/(dashboard)/outreach/[leadId]/page.tsx` | Draft editor + log form + history + earlier versions |
| `actions/drafts.ts` (new) | Server actions for every draft and logging operation |
| `lib/api.ts`, `lib/types.ts` | Client methods and types for the new endpoints |

### 8.9 Tests (V2-07)

`tests/test_drafts_manual.py` — **22 new tests** covering the four acceptance
scenarios:

| Scenario | Coverage |
| --- | --- |
| **V22** | Manual draft works without an AI key; an AI request without a key is rejected with **no** orphan revision/request/job; a manual draft survives an AI-disabled request |
| **V23** | Generation creates a new linked revision and supersedes the old one; a retry completes **once** and preserves earlier edits; a reviewed draft is never silently replaced; editing a reviewed draft returns the new version to `needs_review`; Mark reviewed does not fork a version |
| **V24** | A sent log requires channel, sent time and a revision **or** a note; a note alone is accepted; copy/export never mark sent; Mark reviewed never marks sent; all five outcomes are logged as `manually_logged`; unknown outcome/channel are rejected |
| **V25** | A correction is a new visible event and the original is untouched; the latest summary reflects the correction; a reply does not rewrite the sent log; correcting an unknown event is rejected; logging schedules no work |

Existing coverage kept green: `test_outreach_stage_preserves_reviewed_drafts`,
`test_outreach_stage_force_does_not_overwrite_approved_draft` and
`test_outreach_stage_preserves_authored_draft_without_review_status` still
pass, now via the revision path.

### 8.10 Verification

| Check | Result |
| --- | --- |
| `python -m pytest` | **293 passed** (271 + 22 new) |
| `alembic upgrade head` | `a7b8c9d0e1f2 (head)` applied to the live database |
| Live backfill | 8 legacy drafts preserved as `dr_legacy_*` revisions; 0 discarded |
| Live API smoke | save → mark reviewed → copy text → log sent → log reply → correct → history: all `2xx`, history shows 3 events with the correction last |
| Live V22 check | `409 AI_UNAVAILABLE`, 0 orphan requests, 0 orphan revisions, 0 orphan jobs |
| `npm run lint` | clean |
| `npx tsc --noEmit` | clean |
| `npm run build` | success |

### 8.11 Files changed

**Backend**

```text
alembic/versions/a7b8c9d0e1f2_draft_revisions_outreach_events.py  NEW
app/constants.py                    draft revision/generation/event constants
app/db/models.py                    DraftRevision + OutreachEvent models
app/db/schemas.py                   DraftRevision + OutreachEvent row models
app/db/repository.py                draft revision + outreach event methods
app/leads/drafts.py                 NEW DraftService (versions, events, generation)
app/leads/draft_routes.py           NEW draft + outreach event routes
app/leads/schemas.py                V2-07 request/response schemas
app/dependencies.py                 get_draft_service
app/main.py                         register the draft router
app/worker/pipeline.py              AIOutreachStage writes a NEW revision
tests/test_drafts_manual.py         NEW (22 tests)
```

**Frontend**

```text
actions/drafts.ts                   NEW server actions
components/draft-editor.tsx         NEW
components/outreach-log-form.tsx    NEW
components/outreach-history.tsx     NEW
app/(dashboard)/outreach/[leadId]/page.tsx  draft editor + logging + history
lib/api.ts, lib/types.ts            new endpoints and types
```

**Docs**

```text
docs/api.md                         draft + event endpoints
docs/database.md                    draft_revisions + outreach_events
docs/worker.md                      generation as new versions
```

---

## 9. V2-08 · Review workspace UX (Complete)

### 9.1 Navigation: Creators, Outreach, Settings

The navigation now uses exactly the three names the PRD specifies (PRD 6.1).

| Item | Before | After |
| --- | --- | --- |
| Sidebar / top nav | Leads, Dossiers, Outreach, Settings | **Creators**, Outreach, Settings |
| `/leads` | The list workspace | **Redirects to `/creators`** (no content deleted) |
| `/dossiers` | The AI research list | **Redirects to `/creators`** (no content deleted) |
| `/dossiers/{leadId}` | The dossier/brief page | **Redirects to `/creators/{leadId}`** |

Creator briefs now live **inside** the creator detail view, so the legacy
Dossiers route redirects to the appropriate creator view rather than 404ing.
The dossier data itself is untouched: the creator detail page renders the
evidence brief and, when present, the AI summary.

### 9.2 Creators - the default workspace

The list is now a **saved-view** workspace (PRD 6.2). The default view is
**To review**.

| View | Contents |
| --- | --- |
| **To review** (default) | `Not reviewed` **plus** shortlisters whose evidence changed (`Review needed`). **Excludes `Rejected`.** |
| All creators | Every captured creator, including rejected and blocked ones |
| Research more | Creators an operator asked for more research on |
| Shortlisted | Creators on a shortlist, whatever their decision currency |
| Rejected | Rejected creators, kept for deduplication and history |
| Needs attention | Blocked system work that needs a remedy |

- The view is part of the URL (`?view=…`), so the browser's back button works
  and a view can be linked to.
- Counters are **labelled per view**, not a single additive funnel: a creator
  may appear in an operational view *and* a decision view, so the counts are
  never summed.
- An unknown view falls back to `to_review` instead of erroring.
- The review queue is ordered **oldest unreviewed first**, so nothing is
  starved. `Sort` also offers oldest/newest explicitly.
- Search, research-state filter and sort are preserved when switching views.
- The primary page action is **Add creator** (a single handle/URL form).
- Each row has a clear **Review creator** action.

### 9.3 Backend: saved views

`backend/app/leads/views.py` owns the view semantics, so the filters, the row
badges and the counters all use one server-defined rule (PRD 6.1 - "list
badges, filters, summaries and detail must consume the same effective state
contract").

```text
GET /api/v1/leads?view=to_review&sort=oldest&q=&status=&offset=&limit=
```

The response now carries the resolved view and the per-view counters:

```json
{
  "items": [ ... ],
  "total": 8,
  "view": "to_review",
  "view_counts": {
    "to_review": 8, "all": 9, "research_more": 0,
    "shortlisted": 1, "rejected": 0, "attention": 0
  }
}
```

Each row also carries `contact_types` (`["email"]`, `["phone"]`, …), the
**contact indicator** the PRD asks for, so the list can show contact readiness
without loading every contact row.

### 9.4 Live progress (QA V29)

`components/view-switcher.tsx` exports `LiveRefresh`, used on the Creators
list and in the creator detail's activity panel. While a visible state is
`queued`, `running` or `retry`, the view refreshes **every 5 seconds** - well
inside the ten-second requirement.

The refresh is deliberately non-disruptive:

| Requirement | How it is met |
| --- | --- |
| Refresh within 10s | 5s polling interval, paused entirely when nothing is pending |
| No focus movement | The focused element's id is captured before the refresh and restored afterwards - but **only** if the re-render actually dropped focus. Focus is never stolen back from where the user moved it. |
| No cleared unsaved edits | The draft editor holds the subject/body/DM in **React state** (not the DOM), so a background re-render cannot wipe a half-written draft. Server values are only adopted when the user has no unsaved edits. |
| Announce once | The "pending work finished" message is announced through a single `aria-live="polite"` region and fires **once**, not on every poll. |
| Stable layout | The poll re-renders the server components in place; it does not remount the page or change the scroll position. |

### 9.5 Responsive layout (QA V30)

The layout is stable at the four widths the PRD names. The rules applied:

| Width | Layout |
| --- | --- |
| **360px** | Single column. The creator list renders as a **stacked card list** (not a table), so the decision, research state and contact columns stay visible without horizontal scrolling. Page padding is `px-4` (16px), leaving 328px of content. |
| **390px** | Same single-column layout; the card list has room for the two-column definition grid. |
| **768px** | Still the card list - the eight-column table needs more room than 768px can give without horizontal scrolling, which would hide the decision and contact columns. The filter row wraps to full-width selects. |
| **1280px** | The full table plus the sidebar. The detail view uses the two-column `1.6fr / 1fr` grid. |

Supporting rules: `min-w-0` on the main column so flex children can shrink;
no fixed pixel width above 320px anywhere in `src`; long identifiers use
`break-all`; every control is at least 44px tall.

### 9.6 Keyboard accessibility and visible labels

Every interactive element was audited. The audit is reproducible:

```powershell
.\backend\.venv\Scripts\python.exe scripts\audit_frontend_a11y.py
```

```text
audited 50 interactive elements (29 buttons/links)
issues: 0
OK - every action has an accessible name, a visible focus ring, a >= 44px target, and no overflow at 360px.
```

What the audit checks, and what was changed to pass it:

| Check | Result |
| --- | --- |
| Accessible name on every button, link and form control | 50/50 - text content, `aria-label`, `aria-labelledby`, or a `<label htmlFor>` association (including the template-literal `htmlFor={`…-${id}`}` form) |
| Visible focus ring | 50/50 - a `focus-visible:outline` utility on buttons and links; form controls use the shared `.field` class, which shows a focus border plus halo in `globals.css` |
| Touch target >= 44px | 29/29 buttons and links use `min-h-11` (44px) or larger |
| No horizontal overflow at 360px | 0 fixed widths above 320px |

Additional keyboard work:

- The view switcher is a `role="group"` with `aria-label="Saved creator views"`
  and each link carries `aria-current`.
- The creator table has a `<caption class="sr-only">` and `scope="col"`
  headers; the mobile card list is a real `<ul>`.
- The activity/job history on the creator detail is a native `<details>` /
  `<summary>`, so it is keyboard-operable without custom JavaScript.
- The live-refresh region uses `role="status"` with `aria-live="polite"`, and
  the animated dot is `aria-hidden` so it is not announced repeatedly.
- Focus is always visible: every interactive element has a `focus-visible`
  outline, and the `:focus` state of `.field` changes both the border colour
  and the halo.

### 9.7 Creator detail

The detail view now carries the PRD's **contextual primary action**, with its
prerequisite explained beside it rather than hidden behind a disabled button:

| Situation | Action |
| --- | --- |
| No useful evidence | Add profile data |
| Not reviewed with evidence | Review and decide |
| Current shortlist with an email | Write draft |
| Current shortlist without a usable contact | Find missing contact |
| Shortlist needs review | Review changes and reconfirm |
| Blocked research | Read the research remedy |

The creator brief and the AI summary were moved into the detail view (the
legacy Dossiers route now redirects here). The job history is a collapsed
`<details>` activity section.

### 9.8 API additions

```text
GET /api/v1/leads?view=&sort=     saved view, sorting, and per-view counters
```

No new endpoint was needed: the existing lead list grew two query parameters
and two response fields, so existing callers keep working unchanged.

### 9.9 Tests (V2-08)

`tests/test_creator_views.py` - **9 new backend tests**:

| Test | Covers |
| --- | --- |
| `test_default_view_is_to_review` | The default view is `to_review`; an unknown view falls back to it |
| `test_every_view_has_a_label` | All six views exist and are labelled |
| `test_to_review_includes_not_reviewed_and_review_needed` | Both halves of the default view |
| `test_to_review_excludes_rejected` | Rejected creators are excluded |
| `test_each_view_selects_the_right_rows` | All creators / Research more / Shortlisted / Rejected |
| `test_view_counts_are_labelled_not_additive` | Counters are per view, not a funnel |
| `test_matches_view_is_pure` | The matcher itself, including blocked work |
| `test_review_order_is_oldest_unreviewed_first` | The review queue order |
| `test_contact_indicator_is_reported_per_lead` | The contact indicator data |

### 9.10 Verification

| Check | Result |
| --- | --- |
| `python -m pytest` | **302 passed** (293 + 9 new) |
| `npm run lint` | clean (0 problems) |
| `npx tsc --noEmit` | clean (exit 0) |
| `npm run build` | success - 13 routes, **no hydration or routing errors** |
| `scripts/audit_frontend_a11y.py` | 50/50 elements pass; 0 issues |
| Live API (all views) | every view returns 200 with matching counts; `view=bogus` resolves to `to_review` |
| Live API (default) | `view=to_review`, `total=8`, counts `to_review=8 all=9 shortlisted=1` |

### 9.11 Files changed

**Backend**

```text
app/leads/views.py                  NEW - saved view semantics, counts, ordering
app/leads/service.py                list(view/sort) + saved_view_counts
app/leads/schemas.py                LeadResponse.contact_types, LeadListResponse.view
app/leads/routes.py                 ?view= and ?sort= query parameters
app/db/repository.py                contact_types_by_lead
tests/test_creator_views.py         NEW (9 tests)
```

**Frontend**

```text
app/(dashboard)/creators/page.tsx         NEW - the review workspace
app/(dashboard)/creators/[leadId]/page.tsx NEW - creator detail + contextual action
app/(dashboard)/creators/loading.tsx       NEW
app/(dashboard)/leads/page.tsx             redirect to /creators
app/(dashboard)/dossiers/page.tsx          redirect to /creators
app/(dashboard)/dossiers/[leadId]/page.tsx  redirect to /creators/{leadId}
components/creators-table.tsx        NEW - table (lg+) and card list (<lg)
components/creator-filters.tsx       NEW - search, research state, sort
components/view-switcher.tsx         NEW - saved views + LiveRefresh
lib/views.ts                        NEW - shared view constants
lib/api.ts, lib/types.ts            view/sort params, contact_types, view_counts
components/nav.tsx, top-nav.tsx      Creators / Outreach / Settings
components/draft-editor.tsx          controlled inputs so a poll cannot clear edits
```

**Docs / scripts**

```text
scripts/audit_frontend_a11y.py      NEW - reproducible a11y + layout audit
```

---

## Appendix A. Hotfix: strict contact extraction (V2-04/V2-06 regression)

**Status:** Complete. Shipped after V2-06.

### A.1 Problem

The V2 crawler stored 416 `type='phone'` rows in `contacts` that were not phone
numbers. Every one was numeric noise harvested from page source on
`https://www.georgious.nl` (CSS dimensions, script constants, decimal prices):

```text
0 2.17-.01 2.444-.046 3.292-.036.858-.173 1.442-.374 1.943-.2.53-.474.976-.92 1.423
10512572169863695511792575716
4 4 0 0 0 3.99 4.27
0000000000
```

Two root causes:

1. `app/providers/website.py` extracted contacts from `html + " " + text` — the
   **raw page source**, which is full of CSS values and script constants.
2. `app/providers/emails.py` accepted any digit run of 10+ digits, or 8+ with a
   leading `+`, so 30-digit tracking codes and decimal groups passed.

A fabricated contact is worse than a missed one (PRD 4.4 - never guess
addresses), so the extractor was tightened rather than loosened.

### A.2 Phone extraction (strict, no new dependency)

`app/providers/emails.py` now exposes `is_plausible_phone(value)` and validates
every candidate. A candidate is kept only when **all** hold:

| Rule | Detail |
| --- | --- |
| Shape | optional country code, then groups separated by single space/dash/dot, optionally parenthesised (`+1 (415) 555-0199`, `415-555-0199`, `01 23 45 67 89`) |
| Digit count | 10-15 digits (8+ with a leading `+`); 15 is the E.164 maximum |
| Not a date | `2026-10-19`, `19.10.2026` are rejected |
| Group sizes | with `+` the first group is a 1-3 digit country code; without it the first group is 2-4 digits; every other group is 2-4 digits |
| Group count | at most 6 groups |
| Not degenerate | digits are not all identical (`0000000000`) |
| Bare runs | a contiguous run with no separators is accepted only in pure E.164 form (`+<digits>`); bare IDs/hashes/timestamps are rejected |

`phonenumbers` was **not** added: it is not installed and the environment's
PyPI throughput (~15 kB/s) makes the new dependency - and the Docker rebuild it
implies - a poor trade for a hotfix. The rules above are dependency-free and
fully covered by tests.

### A.3 Email extraction (audit)

`extract_emails` now rejects, in addition to the previous filters:

- **image / retina filenames** - `logo@2x.png`, `hero@3x.jpg`, `banner@2x.webp`
  (matched by `IMAGE_FILENAME_EMAIL_RE`, plus the existing asset-suffix list);
- **transactional senders** - `noreply@`, `no-reply@`, `no_reply@`,
  `donotreply@`, `do-not-reply@`, `mailer-daemon@`, `postmaster@`.

### A.4 Crawler hardening

`app/providers/website.py` no longer scans raw HTML for contacts. Contacts come
from the **visible text** plus explicit `mailto:`/`tel:` links; `tel:` hrefs are
read directly and accepted when they pass `is_plausible_phone`.

### A.5 Database cleanup

`scripts/clean_garbage_phones.py` (one-off, supports `--dry-run`) deletes
`type='phone'` rows that the strict extractor would never produce: more than 15
digits, decimal prices, single-digit groups, or any value that fails
`is_plausible_phone`. It reuses the extraction rules, so the cleanup and the
extractor cannot drift.

```powershell
.\backend\.venv\Scripts\python.exe scripts\clean_garbage_phones.py --dry-run
.\backend\.venv\Scripts\python.exe scripts\clean_garbage_phones.py
```

Live result: **416 garbage phone rows deleted**, 0 phone rows remaining, 4
legitimate legacy email rows untouched.

### A.6 Tests

`tests/test_contact_extraction.py` (NEW) asserts that
`35771933781168458101792575716` and `4 4 0 0 0 3.99 4.27` (and the other
observed garbage) are **ignored**, that real formats survive, and that image
filenames / noreply addresses are rejected. `tests/test_website_crawler.py`
gained two crawler-level regressions (CSS + tracking code in page source; a
`tel:` link is used).

### A.7 Verification

| Check | Result |
| --- | --- |
| `python -m pytest` | **271 passed** |
| Live DB phone rows | 416 -> **0** (4 legacy emails intact) |
| `georgious.nl` (3 pages) re-crawl | 0 phones, 0 emails extracted (was 416 phones) |
| `scripts/clean_garbage_phones.py --dry-run` | 0 garbage remaining |

### A.8 Files changed

```text
backend/app/providers/emails.py       strict is_plausible_phone + email filters
backend/app/providers/website.py      visible-text/tel-link extraction
scripts/clean_garbage_phones.py       NEW (one-off DB cleanup)
tests/test_contact_extraction.py      NEW (9 tests)
tests/test_website_crawler.py         2 new crawler regressions
docs/website-enrichment.md            contact extraction contract
```
