# Synpo GTM — Chrome Extension

MV3 extension that captures the **open Instagram profile** (a public snapshot)
and the verified accounts in the "Suggested for you" rail, and submits them to
the Synpo backend API. It is the capture front door for the pipeline.

## What it does / does not do

- ✅ Detects the profile handle from the current Instagram URL.
- ✅ Reads a **public profile snapshot** (display name, verification, bio,
  external links, follower/following/post counts with precision) and shows a
  preview with missing-field indicators.
- ✅ Adds one "Add to GTM" button on profile pages and an **Add to pipeline**
  button in the popup.
- ✅ Discovers verified accounts in the profile page's "Suggested for you" rail
  and submits them with **Add All Verified**, reporting accurate
  added / already-saved / skipped / failed counts.
- ✅ Sends `{ username, source, request_id, profile_snapshot }` to
  `POST /api/v1/leads` and shows clear **created / updated / duplicate / error /
  auth / network** states. Each creator gets a stable client-generated
  `request_id` so retries cannot double-submit.
- ✅ Keeps one unsaved capture (and failed batch items) in local storage for retry.
- ❌ No provider secrets, no Google Sheets access, no messages sent.
- ❌ No automatic HikerAPI call just because profile data is missing.
- ❌ Does not handle Explore/Search grids or follower modals — only the
  "Suggested for you" rail (the layout the previous extension handled reliably).

## Files

```text
extension/
├─ manifest.json    MV3 manifest (storage + API host permissions)
├─ lib.js           shared pure helpers (handle parsing, snapshot building,
│                   count parsing, URL cleaning, verified association, bulk runner)
├─ background.js    service worker — the only place that calls the API
├─ content.js       reads the profile snapshot + discovers verified accounts,
│                   injects the profile button
├─ popup.html/.js   preview, Add to pipeline, Add All Verified, settings, retry
├─ styles.css       popup styling
├─ lib.test.js      Node unit tests for lib.js
└─ README.md
```

Feasibility notes (extractable fields, reliability, platform constraints):
[docs/extension-capture.md](../docs/extension-capture.md).

## Configuration (stored in `chrome.storage.local`, never synced)

Open the extension popup → **Settings**:

- **API base URL** — e.g. `http://127.0.0.1:8000` (or your hosted API).
- **API key** — optional; sent as the `x-api-key` header. Required only if the
  backend has `API_KEY` set (it should match the backend's `API_KEY`).

Use **Check connection** to verify the API URL + key before capturing.

No provider secrets (HikerAPI/Gemini/service account) are ever stored here.

## Backend prerequisites

1. The API is running with the capture migration applied
   (`alembic upgrade head` — adds `leads.profile_snapshot` and `leads.request_id`).
2. CORS allows the extension origin — `CORS_ALLOW_ORIGINS=*` (default) is fine
   for local dev.
3. If `API_KEY` is set in the backend `.env`, enter the same value in the
   extension settings.

## Load the unpacked extension

1. Open `chrome://extensions`.
2. Enable **Developer mode** (top right).
3. Click **Load unpacked** and select the `extension/` folder.
4. Pin **Synpo GTM Lead Capture**.
5. Open the popup → **Settings** → set the API base URL (and key if needed) →
   **Save settings**.

## Test

Unit tests for the shared helpers (no browser needed):

```powershell
node --test extension/lib.test.js
```

Manual checks (with the API running). These require a live Chrome run — they are
**not** executed by the automated suite:

| Scenario | Steps | Expected |
| --- | --- | --- |
| Snapshot preview | Open an IG profile, open the popup | Preview lists display name, counts, bio, links; missing fields show `unknown` |
| Add profile | Click **Add to pipeline** | **Added**; lead + snapshot appear in the dashboard |
| Already saved | Click again | **Already in the pipeline**; no duplicate |
| Changed profile | Re-open after the profile changed, add again | **Profile updated** (missing fields filled, known values preserved) |
| Add All Verified | On a profile with a "Suggested for you" rail, open the popup | Button shows `Add All Verified (N)`; counts show added/already-saved/skipped/failed |
| Unsupported page | Open Explore/Search | Add All Verified hidden; only the single-profile flow applies |
| Partial failure | Stop the API mid-batch | Batch counts show failures; **Retry unsaved** re-sends only failures with the same request ids |
| Network failure | Stop the API, click Add | **Not saved**; **Retry unsaved** reuses the payload + request id |
| Authentication | Set a wrong API key, click | **Check API key** (HTTP 401) |

## Security notes

- The API key lives only in `chrome.storage.local` (this browser profile).
- The extension has no access to the Google service account or HikerAPI/Gemini
  keys — those stay server-side.
- Page content is read locally and sent only to your backend, only after an
  explicit click.
