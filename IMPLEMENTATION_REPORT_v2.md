# Implementation Report v2 — Creator Review Workspace

**Project:** Synpo GTM Automation
**Reference specification:** `../GTM_Pipeline_PRD_v2_Creator_Review.md` (v2.0, 20 October 2026)
**Report date:** 2026-10-19
**Status:** V2-01 and V2-02 **Complete**. V2-03 through V2-09 are tracked but not started.

---

## 1. Work package tracking

| Package | Scope | Status |
| --- | --- | --- |
| **V2-01 · Stop unintended work** | Remove auto-outreach fan-out; guard disabled AI; withdraw blanket contact masking; preserve drafts | **COMPLETE** |
| V2-02 · Evidence and scheduling | Durable receipts, immutable versions, safe merge, recapture processing, concurrency | **COMPLETE** |
| V2-03 · Review and state | Separate research/fit, one campaign config, material-change rules, decision history | Not started |
| V2-04 · Brief and public contacts | Full non-AI evidence brief, incidental contact extraction/provenance, legacy migration | Not started (evidence-only brief foundation shipped in V2-01) |
| V2-05 · Extension reliability | Capture preview, scoped key, 50-item queue, connection/retry outcomes | Not started |
| V2-06 · Explicit discovery | Executable discovery requests, scoped adapter/manual path, idempotency, cancellation | Not started |
| V2-07 · Drafts and manual history | Manual editor, optional generation, immutable versions, copy/export, sent/reply events | Not started |
| V2-08 · Review workspace UX | Creators views/detail, contextual actions, live progress, responsive forms | Not started |
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

## 3. V2-02 � Evidence and scheduling (Complete)

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
