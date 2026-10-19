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

- `201 Created` — new lead: `{ "created": true, "outcome": "new", "missing_fields": [...], "lead": { ... } }`
- `200 OK` — existing lead returned: `{ "created": false, "outcome": "unchanged" | "updated", ... }`
  (`updated` means the snapshot filled at least one previously-empty field).
- `422 Unprocessable Entity` — invalid username/URL or an unknown top-level field.

There is **no bulk endpoint**: submit one account per request and aggregate the
results client-side.

Each returned `lead` also carries a read-only `snapshot` object (or `null` for
handle-only/HikerAPI leads) with `is_verified`, `external_urls`, the
`followers`/`following`/`post_count` observations (`value`, `display`,
`precision`), `source_url`, `captured_at`, `parser_version` and
`missing_fields`. The snapshot's raw `bio` is intentionally **not** exposed — the
lead's masked `bio` is returned instead (PRD A24).

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
