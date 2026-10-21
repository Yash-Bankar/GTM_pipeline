# Lead API (Phase 2)

FastAPI application exposing lead capture and retrieval. It talks to Google
Sheets through the Phase 1 storage layer (`backend/app/sheets/`). The browser
never accesses Sheets directly, and there is no database.

## Running

```powershell
# from the repo root
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
cd ..
```

Interactive docs: <http://127.0.0.1:8000/docs> · Health: `GET /health`.

## Endpoints

### `POST /api/v1/leads`

Submit a username or Instagram profile URL. Idempotent by normalized username.

Request:

```json
{ "username": "@some.creator", "source": "api" }
```

- `username` (required): handle (with/without `@`) or `instagram.com` profile URL.
- `source` (optional, default `api`): provenance label.

Capture clients (the browser extension) may add a `request_id` and a
`profile_snapshot`. Both are optional and handle-only clients keep working:

```json
{
  "username": "@example_creator",
  "source": "extension",
  "request_id": "stable-client-generated-uuid",
  "profile_snapshot": {
    "display_name": "Example Creator",
    "is_verified": true,
    "bio": "Personal finance education.",
    "external_urls": ["https://example.com"],
    "followers": { "value": 12300, "display": "12.3K", "precision": "approximate" },
    "following": null,
    "post_count": null,
    "source_url": "https://www.instagram.com/example_creator/",
    "captured_at": "2026-10-19T04:50:00Z",
    "parser_version": "1",
    "missing_fields": ["following", "post_count"]
  }
}
```

- `request_id` (optional): a stable, client-generated id. Repeating the same id
  returns the original lead (HTTP 200) without creating a new job.
- `profile_snapshot` (optional): the sanitized public snapshot. Fields are
  bounded server-side — `bio` to 2,200 chars and `external_urls` to 10 valid
  http(s) URLs (tracking parameters removed, `instagram.com`/Meta hosts dropped).
  A malformed optional field becomes *missing*, never a fabricated value; a count
  with unknown precision stores `value: null`. The snapshot only **fills** lead
  fields that are empty — known values are never erased. Contact fields
  (`business_email`/`business_phone_number`) are **not** populated from a
  snapshot (PRD §5.4).

Responses:

- `201 Created` — new lead: `{ "created": true, "outcome": "new", "research_queued": true, "missing_fields": [...], "lead": { ... } }`
- `200 OK` — existing lead returned: `{ "created": false, "outcome": "unchanged" | "updated", ... }`
  (`updated` means newer evidence was applied).
- `409 Conflict` — `request_id` reused with a different payload:
  `{"detail": {"code": "REQUEST_ID_CONFLICT", ...}}`. Nothing is mutated.
- `422 Unprocessable Entity` — invalid username/URL or an unknown top-level field.

V2-02 capture semantics:

- A `request_id` writes an immutable **capture receipt**. Replaying the same
  payload returns the original lead with `outcome="unchanged"` and creates no
  new evidence version or job.
- Each accepted capture creates an **immutable evidence version** with the
  normalized snapshot, parser version, `captured_at`, server `received_at`, and
  field provenance. `lead.evidence_version` / `evidence_version_id` point at the
  current version.
- A client `captured_at` in the future is clamped to the server receipt time;
  older evidence is retained as history but never overwrites newer evidence.
- Handle-only with no snapshot and no configured source → `status="needs_data"`
  with `research_queued=false`. A useful recapture queues research.

There is **no bulk endpoint**: submit one account per request and aggregate the
results client-side.

Each returned `lead` also carries a read-only `snapshot` object (or `null` for
handle-only/HikerAPI leads) with `is_verified`, `external_urls`, the
`followers`/`following`/`post_count` observations (`value`, `display`,
`precision`), `source_url`, `captured_at`, `parser_version` and
`missing_fields`. `snapshot.bio` is omitted as redundant: the lead's canonical
`bio` is returned directly. **V2-01:** public business contacts in the bio/page
text are retained (blanket pre-shortlist masking withdrawn).

Leads also expose `evidence_version` and `evidence_version_id` (the current
pointer), `research_status` (`needs_data`/`queued`/`running`/`complete`/`blocked`),
`decision_currency` (`current`/`review_needed`), `decision_currency_reason`, and
`new_evidence_available`. Submission responses include `research_queued`.

### `GET /api/v1/leads/{lead_id}/brief`

Evidence-only creator brief. Works without AI and without a `dossiers` row
(`has_dossier=false`, `ai_status="not_generated"`). Returns identity, bio,
`observed_topics`, counts with precision, `external_urls`, `websites` (supplied
links plus crawled pages), `missing_fields`, `contacts`, evidence version, and any
existing AI summary.

### `GET /api/v1/leads/{lead_id}/contacts`

Publicly listed, evidence-backed contacts. Visible to authenticated dashboard
users **without a shortlist gate**. Each item has `type` (`email`/`phone`),
`value`, `source_url`, `observed_at`, `method`, `validation_state`, and a
`provenance` label. Contacts discovered post-migration are `Public website`;
contacts without provenance are `Legacy source unknown` (never an invented
source).

### `GET /api/v1/leads`

Paginated listing with optional search and status filter.

| Query | Default | Notes |
| --- | --- | --- |
| `limit` | 50 | 1–500 |
| `offset` | 0 | ≥ 0 |
| `q` | – | case-insensitive search over username, full name, bio, email |
| `status` | – | filter by lead status (e.g. `queued`, `done`) |

Response: `{ "items": [...], "total": 12, "limit": 50, "offset": 0 }`, newest first.

### `GET /api/v1/leads/{lead_id}`

Fetch one lead by its stable `leadId`. `404` if not found.

### `PATCH /api/v1/leads/{lead_id}/fit` (T08/V2-03)

Record the operator's manual fit decision. Separate from research progress.

```json
{ "action": "shortlist", "note": "Strong finance fit" }
```

- `action`: `shortlist` | `research_more` | `reject` | `reopen`.
  The legacy aliases `approve` (→ shortlist) and `need_evidence` (→ research_more)
  are accepted.
- `note`: optional except for `reject`, which requires a non-empty note (`422`).
- Stores `fit_status` (`not_reviewed`/`research_more`/`shortlisted`/`rejected`),
  `fit_note`, `fit_decided_at`, and resets `decision_currency` to `current`.
- A rejected creator must be `reopen`ed before another decision; `reopen` always
  returns to `not_reviewed` and clears `new_evidence_available`.
- Every decision writes a `fit_decisions` history row (action, evidence version,
  criteria version, note, actor, timestamp).

### `GET /api/v1/leads/{lead_id}/fit-decisions` (V2-03)

List the append-only decision history for a lead, including system events
(`review_needed`, `new_evidence`).

### `GET /api/v1/campaign` and `PUT /api/v1/campaign` (V2-03)

Read or replace the single active campaign: `name`, `description`,
`target_topics`, `language`, `follower_min`, `follower_max`. `version` is 0 when
unconfigured and increments on each `PUT`. Updating criteria marks current
shortlists `review_needed`.

### `POST /api/v1/leads/{lead_id}/contact-requests` (T08/V2-03/V2-06)

Queue an explicit contact-discovery request. **Requires
`fit_status == "shortlisted"` AND `decision_currency == "current"`**; otherwise
returns `403` with
`{"code": "FIT_APPROVAL_REQUIRED", "fit_status": ..., "decision_currency": ...}`.

Body (optional): `{ "note": "...", "search_again": false }`.

- Repeated clicks for the **same evidence version** return the existing
  in-flight/completed request with **HTTP 200** and the same `request_id`.
- `search_again: true` creates a new attempt (**HTTP 201**).
- The request is processed by the `contact_discovery` worker stage.

Lifecycle: `queued` → `running` → `found` | `not_found` | `failed` |
`cancelled`. The response includes `evidence_version`, `searched_scope`,
`result_count`, `error`, `started_at`, and `completed_at`. If the shortlist is
revoked (rejected/review needed) before or during the pass, the request is
`cancelled` and no contacts are published.

### `GET /api/v1/leads/{lead_id}/contact-requests` (V2-06)

List contact-discovery request history for a lead.

### `POST /api/v1/leads/{lead_id}/contacts` (V2-06)

Add a manual, sourced public contact (the fallback when discovery returns no
result). No shortlist gate. Body:

```json
{ "type": "email", "value": "name@example.com", "source_url": "https://example.com/contact" }
```

`type` is `email` | `phone`; `source_url` must be an http(s) URL. Stored with
`method="manual"` and `provenance="Public website"`.

### `POST /api/v1/leads/{lead_id}/draft-requests` (T08/V2-03)

Request a new outreach draft revision. **Requires a current shortlist** (else
`403`). Body:

```json
{ "channel": "email" }
```

- `channel`: `email` | `instagram_dm` (anything else is `422`).
- Creates a **new row** in `outreach_revisions` (history is preserved; repeated
  requests create new revisions). Returns `201` with the revision.

### `GET /api/v1/integrations/status` (T09)

Secret-free readiness snapshot (authenticated like the rest of the API):

```json
{
  "database": "healthy",
  "worker": "active",
  "gemini": "configured",
  "hikerapi": "disabled",
  "worker_last_beat_at": "2026-10-19T10:20:00+00:00"
}
```

- `database`: `healthy` | `unreachable`.
- `worker`: `active` | `stale` | `stopped` — based on the worker heartbeat;
  stale when older than 60 seconds.
- `worker_last_beat_at`: the last recorded heartbeat timestamp (empty when none).
- `gemini` / `hikerapi`: `configured` | `disabled` (credential values are never
  returned).

### `GET /api/v1/leads/{lead_id}/draft-requests` (T08)

List the outreach draft revision history for a lead, oldest first:
`{ "items": [ ... ], "total": 2 }`. `404` for a missing lead.

### Draft versions and manual logging (V2-07)

Draft actions: **Edit, Save, Mark reviewed, Copy, Export text, Generate new
version**. Manual writing never needs an AI key; only an explicit generation
request does.

#### `GET /api/v1/leads/{lead_id}/drafts`

Every saved draft version for a lead, oldest first. Each version records its
content, `status` (`needs_review` | `reviewed` | `superseded`), `method`
(`manual` | `ai`), the model, the `parent_revision_id` it was derived from, the
generation `request_id`, and the `evidence_scope` it was built from.

```json
{ "items": [ { "revision_id": "dr_...", "status": "needs_review", "method": "manual", "...": "..." } ], "total": 1 }
```

#### `POST /api/v1/leads/{lead_id}/drafts` (Save / Edit)

Save the draft as a **new version**. The previous version is superseded but
stays visible as history, so an approved or manually authored draft is never
silently replaced. No AI key required.

```json
{
  "subject": "Partnership",
  "body": "Hi there",
  "dm_body": "",
  "channel": "email",
  "note": "",
  "contact_id": "",
  "parent_revision_id": "dr_..."
}
```

Returns `201` with the new version. `404` for a missing lead; `422` when the
draft is completely empty.

#### `POST /api/v1/leads/{lead_id}/drafts/{revision_id}/review` (Mark reviewed)

Marks a saved version as `reviewed`. Only the review state changes - no new
version is created, so the content that was reviewed is the content that stays.
Editing reviewed content later returns the *new* version to `needs_review`.

#### `GET /api/v1/leads/{lead_id}/drafts/{revision_id}/text` (Copy / Export text)

Returns the plain text of a version: `{ "revision_id": "dr_...", "text": "..." }`.
Copying and exporting **never** mark a draft as sent.

#### `POST /api/v1/leads/{lead_id}/drafts/generate` (Generate new version)

Requests an AI-generated version.

- `409` with `{"code": "AI_UNAVAILABLE"}` when AI is disabled or the Gemini key
  is missing. **No revision, request or job is created** - the request is
  rejected before anything is written.
- `403` with `{"code": "FIT_APPROVAL_REQUIRED"}` when the creator is not on a
  current shortlist.
- `202` with the generation request when accepted. The worker writes a **new**
  version when it succeeds; earlier versions are preserved.

```json
{ "channel": "email", "parent_revision_id": "dr_..." }
```

#### `GET /api/v1/leads/{lead_id}/outreach-events`

The manual outreach history, oldest first, plus the current summary:

```json
{
  "items": [
    { "event_id": "oe_...", "outcome": "sent", "channel": "email", "source": "manually_logged", "...": "..." }
  ],
  "total": 1,
  "latest_outcome": "sent"
}
```

#### `POST /api/v1/leads/{lead_id}/outreach-events` (Log sent / outcomes)

Records a **manually logged** outreach event. Requires a channel, a sent time,
and either the draft revision or a manual note.

```json
{
  "outcome": "sent",
  "channel": "email",
  "sent_at": "2026-10-21T10:00:00Z",
  "revision_id": "dr_...",
  "note": "",
  "corrects_event_id": ""
}
```

- `outcome`: `sent` | `replied` | `interested` | `not_interested` | `follow_up`.
- `channel`: `email` | `instagram_dm`.
- `sent_at` is pre-populated with the current time in the UI and is always
  correctable.
- `corrects_event_id` turns the entry into a **correction**: a new visible event
  that references the one it corrects. The original row is never rewritten, so
  the history keeps both. `422` if the referenced event does not exist.
- `422` when the outcome or channel is unknown, or when neither a revision nor a
  note is given.

Every event is labelled `manually_logged` (or `manually_logged_correction` for a
correction) and records the actor as the shared dashboard operator - shared
authentication is not a named employee. Logging never dispatches a message.

### `GET /api/v1/leads/{lead_id}/detail`

Dashboard detail (lead, derived progress, posts, website pages, contacts, latest `contact_request`, jobs).

## Behavior

- **Validation**: accepts bare handles or `instagram.com` URLs; rejects other
  hosts, reserved paths (`p`, `reel`, `stories`, ...), invalid characters, and
  handles longer than 30 chars. The original case is preserved in `username`;
  `usernameNormalized` (lowercased, `@`/URL stripped) is the dedup key.
- **Dedup**: a repeated submission returns the existing lead with `created=false`
  and the same `leadId`. The check + append run under the store's write lock.
- **Stable id**: `leadId` (`ld_<uuid hex>`) is assigned once per lead.
- **Enqueue**: new leads are stored with `status="queued"` for the future worker
  to claim. No scraping/AI happens here.

## Error mapping

| Condition | Status |
| --- | --- |
| Invalid username/URL | `422` |
| Duplicate (raised internally) | `409` |
| Sheets not configured (missing id/credentials) | `503` |
| Sheets quota / rate limit | `503` |
| Sheets auth, permission, network, not-found, schema | `502` |

Errors are returned as `{ "detail": "..." }`.

## Concurrency model (MVP)

**One backend instance only.** `LeadStore` is a process-wide singleton, so its
in-process write lock serializes all lead creation/update. Do not run multiple
API replicas or a separate writer process yet — a Sheets-based lease is a later
phase. One worker only, and no concurrent job claimer.

## Tests

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
```

API tests use `fastapi.testclient.TestClient` with the in-memory fake Sheets
client (no network/credentials) and cover: duplicate submissions, invalid URLs,
pagination/search/status filters, missing configuration (503), and Sheets error
mapping (502/503). A live write can be exercised via
`scripts/verify_db.py`.

## Out of scope (Phase 2)

No HikerAPI, no Gemini, no website scraping, no worker job claiming.
