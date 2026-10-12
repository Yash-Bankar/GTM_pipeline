# Website Enrichment (Phase 5)

Crawls the external links found on a lead's Instagram profile (bio link +
link-in-bio pages), extracts page titles/URLs/text/links and public emails, and
stores one row per page in the `Website Pages` tab.

Ported and hardened from the legacy `website_crawler` / `enrichment_crawler`
(link-hub support, useful-link scoring, text/link extraction, email extraction).
No dependency on the old SQLite stores, Streamlit, or pipeline.

Module: `backend/app/providers/website.py`.

## Security: URL validation + SSRF protection

Every URL (including redirect targets) is validated before any request:

- **Allowed protocols:** `http` and `https` only. Other schemes (`file`, `ftp`,
  `gopher`, ...) are rejected.
- **Host block-list:** `localhost`, `*.localhost`, `*.local`, `*.internal`,
  `*.home.arpa`, `metadata.google.internal`.
- **DNS resolution check:** the host is resolved and **every** address must be
  public. Private, loopback, link-local (incl. `169.254.169.254`), multicast,
  reserved and unspecified addresses are rejected.
- **Manual redirects:** redirects are not followed automatically; each hop is
  re-validated (max 3), so a redirect into an internal host is blocked.
- **Size limit:** response bodies are streamed and capped at
  `WEBSITE_MAX_BYTES` (default 2 MB).
- **Timeouts:** `WEBSITE_TIMEOUT_SECONDS` (default 10s).
- **Bounded retries:** transient (429/5xx/timeout) retried
  `WEBSITE_MAX_ATTEMPTS` times.
- **Bounded crawl:** at most `WEBSITE_MAX_PAGES` pages per lead; at most
  `WEBSITE_MAX_LINKS_PER_PAGE` links parsed per page. Only same-host or
  link-hub outbound links matching useful keywords ("contact", "about",
  "work-with-me", ...) are followed. Social/aggregator domains and
  privacy/terms/login/cart paths are skipped. **Follower lists are never
  fetched.**

A blocked/invalid start URL is recorded as a page with `status="blocked"` — it
never raises, so one bad link cannot fail a job.

## Result mapping

Each `FetchedPage` becomes a `Website Pages` row:

| Field | Meaning |
| --- | --- |
| `pageId` | deterministic hash of `(leadId, url)` — the idempotency key |
| `url` / `resolvedUrl` / `domain` | requested and final URL + host |
| `title` / `text` | page title and cleaned visible text (capped) |
| `links` | `label \| url` lines (capped) |
| `httpStatus` | HTTP status code |
| `status` | `done` / `error` / `blocked` |
| `error` | reason when not `done` |
| `fetchedAt` | fetch timestamp |

## Lead status

The stage sets the lead's `websiteStatus` and, when present, the enriched row's
`websiteStatus`:

- `done` — all fetched pages succeeded
- `partial` — some pages succeeded, some failed/blocked
- `blocked` — every page was blocked by the SSRF rules
- `none` — the lead genuinely has no website/links
- `error` — all pages failed to fetch

The website stage is **optional**: it always completes the job (never blocks the
pipeline) even when the information is unavailable.

## Configuration

```text
WEBSITE_MAX_PAGES=5
WEBSITE_MAX_LINKS_PER_PAGE=30
WEBSITE_TIMEOUT_SECONDS=10
WEBSITE_MAX_BYTES=2000000
WEBSITE_MAX_ATTEMPTS=2
WEBSITE_USER_AGENT=SynpoGTM/0.1
```

## Tests

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\test_website_crawler.py tests\test_worker_stages_media_website.py
```

Coverage: disallowed schemes, internal/private hosts, successful extraction
(title/text/links/emails), response-size limit, non-HTML, transport errors,
blocked redirects, link-following boundaries, missing website, all-blocked,
partial failures, and idempotent page storage.
