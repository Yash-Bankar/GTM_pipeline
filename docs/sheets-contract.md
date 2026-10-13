# Google Sheets Data Contract (Phase 1)

Google Sheets is the **single source of truth** for all operational data in this
MVP. There is no SQL/NoSQL database.

The storage layer lives in `backend/app/sheets/` and maps rows to typed Pydantic
models **by header name** (never by fixed column index).

## Credentials model

- Server-side **service account** credentials (no user OAuth for the MVP).
- JSON key path comes from `GOOGLE_APPLICATION_CREDENTIALS` (see `.env.example`).
- Relative paths resolve against the repo root, then the backend directory, so
  both `secrets/service-account.json` and `backend/secrets/service-account.json`
  work.
- The key file lives under `secrets/` (gitignored) and is never logged or printed.
- The spreadsheet must be shared with the service account email (Editor).

## Tabs and schemas

Schema keys are stable in code; tab display names are configurable via env vars.

| Schema key | Env var (tab name) | Default tab |
| --- | --- | --- |
| `ig_leads` | `GOOGLE_SHEETS_IG_LEADS_TAB` | `IG Leads` |
| `deduplicated_leads` | `GOOGLE_SHEETS_DEDUP_TAB` | `Deduplicated Leads` |
| `instagram_leads_enriched` | `GOOGLE_SHEETS_ENRICHED_TAB` | `instagram_leads_enriched` |
| `outreach` | `GOOGLE_SHEETS_OUTREACH_TAB` | `Outreach` |
| `pipeline_jobs` | `GOOGLE_SHEETS_JOBS_TAB` | `Pipeline Jobs` |
| `lead_posts` | `GOOGLE_SHEETS_POSTS_TAB` | `Lead Posts` |
| `website_pages` | `GOOGLE_SHEETS_WEBSITE_PAGES_TAB` | `Website Pages` |
| `dossiers` | `GOOGLE_SHEETS_DOSSIERS_TAB` | `Dossiers` |

### `IG Leads` (canonical)

```text
leadId, username, usernameNormalized, fullName, instagramId, followerCount,
followsCount, businessCategoryName, bio, businessEmail, businessPhoneNumber,
profileUrl, externalUrl, allExternalUrls, engagementRate, scrapedAt, status,
source, createdAt, updatedAt, lastError, mediaStatus, websiteStatus
```

`mediaStatus` / `websiteStatus` track the optional Phase-5 stages
(`done` / `partial` / `none` / `blocked` / `error`).

### `Deduplicated Leads`

```text
leadId, username, usernameNormalized, status, reason, sourceLeadId, createdAt, updatedAt
```

### `instagram_leads_enriched`

Core:

```text
leadId, username, usernameNormalized, fullName, instagramId, followerCount,
followsCount, businessCategoryName, bio, businessEmail, businessPhoneNumber,
profileUrl, externalUrl, allExternalUrls, engagementRate, profileStatus,
websiteStatus, profileScrapedAt, websiteScrapedAt, lastError
```

Website evidence slots (`scrape1Url`, `scrape1Title`, `scrape1Text`,
`scrape1Links` ... `scrape5Url`, `scrape5Title`, `scrape5Text`, `scrape5Links`),
then `createdAt, updatedAt`. Evidence columns are intentionally carried as
**extra** model fields so their count can grow without a code change.

### `Outreach`

```text
leadId, username, usernameNormalized, channel, status, subject, body, dmBody,
model, generatedAt, createdAt, updatedAt, lastError
```

AI outreach drafts (Phase 6). `subject`/`body` = email, `dmBody` = DM. Drafts are
stored with `status=NEEDS_REVIEW`; nothing is sent. See [gemini.md](gemini.md).

### `Dossiers`

```text
leadId, username, usernameNormalized, summary, topics, audience, evidenceUrls,
qualificationScore, qualificationTier, rubric, criterionScores, uncertainty,
model, status, lastError, generatedAt, createdAt, updatedAt
```

One AI dossier per lead (Phase 6), keyed by `leadId`, `status=NEEDS_REVIEW`.
See [gemini.md](gemini.md).

### `Pipeline Jobs`

```text
jobId, stage, leadId, username, usernameNormalized, status, attemptCount,
maxAttempts, priority, payload, result, lastError, lockedAt, lockedBy, runAfter,
createdAt, updatedAt
```

The worker's queue. `(stage, leadId)` is the idempotency key; statuses are
`queued`/`running`/`retry`/`done`/`error`. See [worker.md](worker.md).

### `Lead Posts`

```text
postId, leadId, username, usernameNormalized, mediaType, productType, shortCode,
url, caption, likeCount, commentCount, playCount, takenAt, fetchedAt, status,
lastError, createdAt, updatedAt
```

Recent posts/reels per lead (Phase 5). `postId` (Instagram media id) is the
idempotency key.

### `Website Pages`

```text
pageId, leadId, username, url, resolvedUrl, domain, title, text, links,
httpStatus, status, error, fetchedAt, createdAt, updatedAt
```

Crawled website pages (Phase 5). `pageId` is a deterministic hash of
`(leadId, url)`, so re-runs upsert rather than duplicate. `status` is
`done`/`error`/`blocked`. See [website-enrichment.md](website-enrichment.md).

> `Sheet4` is still undefined/unverified and is intentionally not implemented.

## Identity and deduplication

- **`leadId`** is the stable internal identifier (`ld_<uuid hex>`), assigned once
  when a lead is created and used as the key across every tab.
- **`usernameNormalized`** is the dedup key: lowercase, no leading `@`, URL forms
  (`instagram.com/<handle>`, query/hash/trailing slash) reduced to the handle.
- `LeadStore.create_lead(...)` generates the id/timestamps and rejects duplicates
  (or returns the existing lead with `on_duplicate="return"`).

## Non-destructive header policy

- Missing tab: created with the full canonical header row (only when asked).
- Empty tab: full header row written.
- Existing header row: **never overwritten**. Missing required headers are
  reported; they are appended only when `extend_headers=True`, filling blank
  header cells first, then appending — existing cells are never touched.
- Row updates are **targeted cell updates by header name**, so unknown/extra
  columns are preserved.

## Reliability

- Batch reads (`batchGet`) and batch writes (`batchUpdate`) where possible.
- Per-request timeout via `GOOGLE_SHEETS_REQUEST_TIMEOUT_SECONDS`.
- Exponential backoff with full jitter on transient errors (5xx and transport
  timeouts): `GOOGLE_SHEETS_MAX_ATTEMPTS`, `GOOGLE_SHEETS_BACKOFF_BASE_SECONDS`,
  `GOOGLE_SHEETS_BACKOFF_MAX_SECONDS`.
- **429 quota/rate-limit** errors use a separate, much longer backoff
  (`GOOGLE_SHEETS_QUOTA_BACKOFF_BASE_SECONDS` → `..._MAX_SECONDS`, default
  **10s → 60s**) so retries don't immediately re-burn the 60 req/min quota.
- **In-memory layout cache**: tab titles and header rows are cached per store for
  `GOOGLE_SHEETS_LAYOUT_CACHE_TTL_SECONDS` (default 300s; `0` disables), so reads
  and writes don't re-fetch headers every operation. Header writes (schema
  creation/extension) invalidate the cache automatically.
- Typed errors: `SheetsAuthError`, `SheetsPermissionError`, `SheetsQuotaError`,
  `SheetsNetworkError`, `SheetsNotFoundError`, `SheetTabMissingError`,
  `SchemaError`, `DuplicateLeadError`, `SheetsApiError`.

## Concurrency model (MVP)

- **One backend instance, one background worker.** Mutating operations are
  serialized by an in-process lock (`SheetStore._lock`), and there is no
  concurrent job claimer. Do not run multiple workers or API replicas until a
  Sheets-based lease is introduced (later phase).
- Worker and API coordinate through Sheets status columns, not a database.

## Setup

1. In Google Cloud, create/select a project and enable the **Google Sheets API**.
2. Create a **service account**, create a **JSON key**, and save it to
   `backend/secrets/service-account.json` (gitignored).
3. Share the target spreadsheet with the service account email as **Editor**.
4. Configure `.env` (copy from `.env.example`):

   ```powershell
   Copy-Item .env.example .env
   # Set GOOGLE_SHEETS_SPREADSHEET_ID, GOOGLE_APPLICATION_CREDENTIALS, tab names
   ```

## Tests and verification

Unit tests use an in-memory fake Sheets client — no network, no credentials:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
```

Integration check against the development spreadsheet (reads/writes a test row):

```powershell
# Inspect tabs and headers (read-only)
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --check-only

# Create missing tabs / append missing headers (non-destructive)
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --create-missing-tabs --extend-headers

# Append a test lead to IG Leads and read it back
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --write-test-row
```

Credentials are never printed; the spreadsheet id is masked in output.

## Out of scope for Phase 1

No HikerAPI calls, no Gemini calls, no website scraping, and no dedup/enrichment
business logic — Phase 1 is storage only.
