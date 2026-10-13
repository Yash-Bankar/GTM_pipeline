# Synpo GTM — Chrome Extension (Phase 8)

Minimal MV3 extension that sends the **current Instagram profile** to the Synpo
backend API. It is the capture front door for the pipeline.

## What it does / does not do

- ✅ Detects the profile handle from the current Instagram URL.
- ✅ Adds one "Add to GTM" button on profile pages and an "Add to pipeline"
  button in the popup.
- ✅ POSTs `{ username, source: "extension" }` to `POST /api/v1/leads` and shows
  clear **created / duplicate / error / auth / network** states.
- ❌ No scraping (no bio, followers, or media), no Google Sheets access, no
  provider secrets, no messages sent.

## Files

```text
extension/
├─ manifest.json    MV3 manifest (storage + API host permissions)
├─ lib.js           shared pure helpers (handle parsing, request, response mapping)
├─ background.js    service worker — the only place that calls the API
├─ content.js       injects the profile button + states
├─ popup.html/.js   configure the API, add the current profile
├─ styles.css       popup styling
├─ lib.test.js      Node unit tests for lib.js
└─ README.md
```

## Configuration (stored in `chrome.storage.local`, never synced)

Open the extension popup → **Settings**:

- **API base URL** — e.g. `http://127.0.0.1:8000` (or your hosted API).
- **API key** — optional; sent as the `x-api-key` header. Required only if the
  backend has `API_KEY` set (it should match the backend's `API_KEY`).

No provider secrets (HikerAPI/Gemini/service account) are ever stored here.

## Backend prerequisites

1. The API is running: `cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`.
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

The manifest allows `https://www.instagram.com/*`, `http://127.0.0.1/*`,
`http://localhost/*`, and `https://*/*` (for a hosted API). Add your production
API host to `host_permissions` if it differs.

## Test

Unit tests for the shared helpers (no browser needed):

```powershell
node --test extension/lib.test.js
```

Manual checks (with the API running):

| Scenario | Steps | Expected |
| --- | --- | --- |
| Success | Open an IG profile, click **Add to GTM** | Button shows **Added ✓**; lead appears in the dashboard |
| Repeated clicks | Click again (or double-click quickly) | Second click → **Already added**; only one row created |
| Invalid profile | Open `/p/…`, `/explore/`, or a non-profile page | Button hidden; popup shows **Not a profile** |
| Network failure | Stop the API, click the button | **Offline — retry** (no crash) |
| Authentication | Set a wrong API key in settings, click | **Check API key** (HTTP 401) |
| Not configured | Clear the API base URL, click | **Set API URL** |

## Security notes

- The API key lives only in `chrome.storage.local` (this browser profile).
- The extension has no access to the Google service account or HikerAPI/Gemini
  keys — those stay server-side.
- Only the profile handle/URL is sent; no page content is collected.
