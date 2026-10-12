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

Responses:

- `201 Created` — new lead: `{ "created": true, "lead": { ... } }`
- `200 OK` — existing lead returned: `{ "created": false, "lead": { ... } }`
- `422 Unprocessable Entity` — invalid username/URL (typed validation error).

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
mapping (502/503). `POST` against a live sheet can be exercised via
`scripts/verify_sheets.py --write-test-row`.

## Out of scope (Phase 2)

No HikerAPI, no Gemini, no website scraping, no worker job claiming.
