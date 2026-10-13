# End-to-End Runbook

Step-by-step verification of the complete pipeline, from capture to outreach
review. Run from the repository root unless noted.

## 0. Preconditions

- Python 3.14 venv at `backend/.venv`; Node 20.9+ for the frontend; Docker
  (optional) for the container smoke test.
- A Google Cloud **service account** with the Sheets API enabled, key saved to
  `backend/secrets/service-account.json`, and the target spreadsheet shared with
  the service-account email (Editor).
- HikerAPI key (profile/media) and, optionally, a Gemini key (AI stages).

## 1. Configure

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

Set at minimum in `.env`: `GOOGLE_SHEETS_SPREADSHEET_ID`,
`GOOGLE_APPLICATION_CREDENTIALS=./backend/secrets/service-account.json`,
`HIKERAPI_KEY`, `API_KEY`, and `GEMINI_API_KEY` (or `AI_ENABLED=false`).
In `frontend/.env.local`: `API_BASE_URL=http://127.0.0.1:8000`,
`BACKEND_API_KEY=<same as API_KEY>`, `DASHBOARD_PASSWORD=<choose one>`.

## 2. Install dependencies

```powershell
py -3.14 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..
```

## 3. Unit tests (fast, no network/credentials)

```powershell
.\backend\.venv\Scripts\python.exe -m pytest        # backend: expect all green
node --test extension/lib.test.js                   # extension helpers
cd frontend; npm run lint; npx tsc --noEmit; npm run build; cd ..
```

## 4. Provision the spreadsheet tabs (idempotent, non-destructive)

```powershell
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --create-missing-tabs --extend-headers
```

Expected: `IG Leads`, `Deduplicated Leads`, `instagram_leads_enriched`,
`Outreach`, `Pipeline Jobs`, `Lead Posts`, `Website Pages`, `Dossiers` all `[OK]`.

Optional provider checks:

```powershell
.\backend\.venv\Scripts\python.exe scripts\check_hikerapi.py --username natgeo
.\backend\.venv\Scripts\python.exe scripts\check_gemini.py
```

## 5. Start the stack (three terminals)

```powershell
# A - API
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# B - worker
cd backend; .\.venv\Scripts\python.exe -m app.worker
# C - dashboard
cd frontend; npm run dev
```

Health: `Invoke-RestMethod http://127.0.0.1:8000/health` → `{"status":"ok",...}`.

## 6. Capture a lead

- **Dashboard**: http://localhost:3000 → log in (if `DASHBOARD_PASSWORD` set) →
  **Leads** → add `@some.creator` or an `instagram.com` URL.
- **Extension**: load `extension/` unpacked, set API URL/key, open a profile,
  click **Add to GTM**.

Expected: a new row in `IG Leads` with `status=queued`; a `profile_fetch` job in
`Pipeline Jobs`; the dashboard shows the lead.

## 7. Run the pipeline

The worker (Terminal B) polls and processes automatically. To drive it manually:

```powershell
cd backend; .\.venv\Scripts\python.exe -m app.worker --drain
```

Expected progression (worker logs + tabs):

| Stage | Writes | Lead status |
| --- | --- | --- |
| `profile_fetch` | `instagram_leads_enriched` | `enriched` (or `not_found`/`error`) |
| `profile_media` | `Lead Posts` | `mediaStatus` = done/none/error |
| `website_enrich` | `Website Pages` | `websiteStatus` = done/partial/none/blocked/error |
| `ai_dossier` | `Dossiers` (`NEEDS_REVIEW`) | — |
| `ai_outreach` | `Outreach` (`NEEDS_REVIEW`) | — |

## 8. Review outputs

- **Lead detail** (`/leads/<leadId>`): profile, recent posts, website pages, job
  history; use **Re-queue processing** to retry.
- **Dossiers** (`/dossiers/<leadId>`): summary, topics, criterion scores,
  qualification tier, cited source links, uncertainty.
- **Outreach** (`/outreach/<leadId>`): edit the email + DM, then **Approve** or
  **Reject**. Nothing is sent.

## 9. Failure drills

| Drill | Action | Expected |
| --- | --- | --- |
| Duplicate | Add the same handle again (dashboard + extension) | `200 created=false`; "already in the pipeline" |
| Invalid URL | Submit `https://example.com/x` or `/p/…` | `422` / "Invalid profile" |
| Auth | Send without / with a wrong `x-api-key` | `401` |
| Missing website | Lead with no external link | `websiteStatus=none`; pipeline continues |
| Blocked URL | External link to a private host | `Website Pages` row `status=blocked` |
| Provider error | Run with an exhausted HikerAPI balance | job → `retry`/`error` with `lastError` |
| Restart recovery | Kill the worker mid-run, restart | stale `running` job returns to `retry` and completes |

## 10. Container smoke test (optional)

```powershell
Copy-Item .env.example .env   # ensure GOOGLE_APPLICATION_CREDENTIALS points at ./backend/secrets
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8000/health
docker compose logs -f worker
docker compose down
```

Expected: API healthy, worker logs show job polling with no crashes.

## 11. Definition of done

- [ ] All unit tests green; frontend builds.
- [ ] A submitted lead reaches `enriched` with posts/website evidence recorded.
- [ ] Dossiers and Outreach rows exist as `NEEDS_REVIEW` (when AI enabled).
- [ ] Duplicate, invalid, and auth paths behave as above.
- [ ] No secrets committed; `.env` files gitignored.
