# HikerAPI Provider (Phase 3)

Server-side client for fetching a public Instagram profile. Ported selectively
from the legacy reference project's `HikerAPIClient` (`user/by/username` +
`to_lead_row`), rebuilt on this repo's conventions. It lives in
`backend/app/providers/`.

## Endpoint and auth (current docs)

- `GET https://api.hikerapi.com/v2/user/by/username?username=<handle>`
- `GET https://api.hikerapi.com/v2/user/medias?user_id=<pk>` — recent posts/reels
  (v2 pagination via `page_id`/`next_page_id`), used by the media stage.
- Header: `x-access-key: <HIKERAPI_KEY>`
- Response (v2 user): `{ "user": { ... }, "status": "ok" }`

Credentials are read from the environment and stay **server-side**; the key is
never logged or returned by the API.

## Layout

```text
backend/app/providers/
├─ hikerapi.py   HikerAPIClient (fetch + timeouts + retries + error mapping)
├─ models.py     HikerProfile (typed) + parse_profile_payload + to_lead_fields
├─ emails.py     extract_emails (regex; ported from legacy contact_extractor)
├─ errors.py     HikerAPI* error hierarchy
└─ __init__.py   public exports
```

## Behavior

- **Validation**: `fetch_profile(handle_or_url)` runs the shared
  `parse_lead_input` first and raises `InvalidLeadInput` for bad input — no HTTP
  call is made.
- **Normalization**: `parse_profile_payload` unwraps the v2 `user` object (or a
  bare object), reads field names leniently with fallbacks, coerces stringy
  scalars, and merges emails from `public_email`/`business_email` plus the bio.
  `HikerProfile` is the stable shape; provider field names never leak further.
- **`to_lead_fields`** maps a profile to canonical `IG Leads` column names
  (`username`, `fullName`, `instagramId`, `followerCount`, ..., `scrapedAt`) so
  it can be written by the storage layer without column-index assumptions.
- **Timeouts + retries**: `httpx` request timeout; bounded exponential backoff
  with full jitter on `429`/`5xx` and transport errors. Attempts/backoff are
  configurable.
- **Typed errors**: `HikerAPIConfigError` (no key), `HikerAPIAuthError`
  (401/403), `HikerAPINotFoundError` (404), `HikerAPIQuotaError` (402),
  `HikerAPIRateLimitError` (429 after retries), `HikerAPINetworkError`
  (timeout/transport), `HikerAPIResponseError` (non-JSON / unexpected payload).

## Configuration

Set in `.env` (see `.env.example`):

```text
HIKERAPI_BASE_URL=https://api.hikerapi.com/v2
HIKERAPI_KEY=
HIKERAPI_TIMEOUT_SECONDS=20
HIKERAPI_MAX_ATTEMPTS=4
HIKERAPI_BACKOFF_BASE_SECONDS=0.5
HIKERAPI_BACKOFF_MAX_SECONDS=10
```

## Usage

```python
from app.config import get_settings
from app.providers import HikerAPIClient, to_lead_fields

with HikerAPIClient.from_settings(get_settings()) as client:
    profile = client.fetch_profile("natgeo")   # or a profile URL
    fields = to_lead_fields(profile)           # canonical IG Leads columns
```

## Tests

Unit tests mock the provider with `httpx.MockTransport` (no network):

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_hikerapi_normalize.py tests\test_hikerapi_client.py
```

Coverage: successful normalization, 401/403/404/402, 429 retry-then-success,
429 exhaustion, 5xx after retries, timeout, non-JSON, missing user, invalid
input rejected before any call, `validate_key`, and missing-key config error.

## Manual check (one approved public profile)

```powershell
.\backend\.venv\Scripts\python.exe scripts\check_hikerapi.py
.\backend\.venv\Scripts\python.exe scripts\check_hikerapi.py --username natgeo
```

Note: an account with no balance returns HTTP 402, surfaced as
`HikerAPIQuotaError`.

## Out of scope (Phase 3)

No recent-media research, no website crawling, no Gemini generation, and the
provider is not yet wired into the worker or any HTTP endpoint.
