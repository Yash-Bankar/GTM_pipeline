# Dashboard (Phase 7)

Internal GTM dashboard built in the existing Next.js App Router app
(`frontend/`), React 19 + TypeScript + Tailwind v4. It talks only to the Python
API over a configured base URL; provider/backend secrets stay server-side.

## Running (three terminals)

```powershell
# Terminal A - Python API (from backend/)
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal B - worker (from backend/)
cd backend; .\.venv\Scripts\python.exe -m app.worker

# Terminal C - dashboard (from frontend/)
cd frontend; npm run dev   # http://localhost:3000
```

## Configuration (`frontend/.env.local`, copy from `frontend/.env.example`)

```text
API_BASE_URL=http://127.0.0.1:8000   # server-side only
BACKEND_API_KEY=                     # sent as x-api-key (match backend API_KEY)
DASHBOARD_PASSWORD=                  # enables the access gate; unset = open (dev)
SESSION_SECRET=                      # optional HMAC secret for the session cookie
```

- `API_BASE_URL` / `BACKEND_API_KEY` are **server-only** and never reach the
  browser (the client never calls the API directly).
- If backend `API_KEY` is set, set the same value in `BACKEND_API_KEY`.

## Access control

- `proxy.ts` (Next 16 replacement for `middleware.ts`) does an optimistic cookie
  check and redirects to `/login` when `DASHBOARD_PASSWORD` is set.
- Every page and Server Action also calls `requireSession()` (defence in depth).
- `/login` verifies the password in a Server Action and sets an HttpOnly,
  SameSite=Lax session cookie (HMAC of `SESSION_SECRET`/password).

## Pages

| Route | What it shows |
| --- | --- |
| `/creators` | The review workspace: saved views (default **To review**), search, research-state filter, sort, labelled counters, add-creator form, and the creator list (table at `lg+`, stacked cards below) |
| `/creators/[leadId]` | Contextual primary action, creator brief + AI summary, profile snapshot, recent posts, website pages, public contacts, **fit decision**, **contact/draft gates**, and a collapsed activity/job history |
| `/outreach` | Draft list with a visible **Draft status** filter |
| `/outreach/[leadId]` | Draft versions (Save / Mark reviewed / Copy / Export text / Generate new version) and the manual sent/outcome history (nothing is sent) |
| `/settings` | System health: worker heartbeat, database, Gemini/HikerAPI readiness, pipeline rules |
| `/leads` | Legacy path — **redirects to `/creators`** |
| `/dossiers` | Legacy path — **redirects to `/creators`** (briefs live in the creator detail view) |
| `/dossiers/[leadId]` | Legacy path — **redirects to `/creators/{leadId}`** |

Navigation uses exactly **Creators**, **Outreach** and **Settings**. It is a
sidebar at `lg+` and a visible compact top bar below `lg` (no hover-only
menus); section links expose `aria-current`. Snapshot-only leads show
"Posts not captured in snapshot" instead of an ambiguous empty posts section.

### Saved views (V2-08)

The Creators page is a saved-view workspace. The default is **To review**:
`Not reviewed` plus shortlisters whose evidence changed, **excluding
`Rejected`**. The other views are All creators, Research more, Shortlisted,
Rejected and Needs attention. The view lives in the URL (`?view=…`), and the
counters are labelled per view rather than summed - a creator can appear in an
operational view *and* a decision view.

### Live progress (V2-08)

While a visible state is `queued`, `running` or `retry`, the Creators list and
the creator detail's activity panel refresh every 5 seconds. The refresh never
moves focus and never clears an unsaved edit: the draft editor keeps the text
in React state, and focus is restored only if the re-render actually dropped
it. Completion is announced once through an `aria-live` region.

### Responsive and accessible (V2-08)

- Stable at **360, 390, 768 and 1280** CSS pixels. The creator list is a
  stacked card list below `lg` so the decision and contact columns stay
  visible without horizontal scrolling.
- Every button, link and form control has an accessible name and a visible
  focus ring; every control is at least 44px tall.
- The audit is reproducible:

```powershell
.\backend\.venv\Scripts\python.exe scripts\audit_frontend_a11y.py
```

## States

- **Loading**: `loading.tsx` per route (skeleton tables/cards) — also satisfies
  Next's Cache Components requirement for a Suspense boundary around runtime data.
- **Empty**: dedicated empty states for leads, dossiers, posts, pages, drafts.
- **Duplicate**: the add-lead form reports "already in the pipeline".
- **Error + retry**: pages render an error card with a Retry link; a route-level
  `error.tsx` boundary offers "Try again".

## Backend endpoints used

`GET /api/v1/leads` (with `view` and `sort`), `POST /api/v1/leads`,
`GET /api/v1/leads/{id}/detail`, `GET /api/v1/leads/{id}/brief`,
`POST /api/v1/leads/{id}/retry`, `POST /api/v1/leads/{id}/retry-ai`,
`GET|POST /api/v1/leads/{id}/drafts[/{rev}/review|/text]`,
`POST /api/v1/leads/{id}/drafts/generate`,
`GET|POST /api/v1/leads/{id}/outreach-events`,
`GET /api/v1/outreach[/{id}]`, `PATCH /api/v1/outreach/{id}`,
`GET /api/v1/stats`, `GET /api/v1/integrations/status`.
All accept/return typed JSON; the client lives in `frontend/src/lib/api.ts`.

## Quality checks

```powershell
cd frontend
npm run lint
npx tsc --noEmit
npm run build

cd ..
.\backend\.venv\Scripts\python.exe scripts\audit_frontend_a11y.py
```

## Not implemented

No direct Instagram scraping and no sending of messages — outreach drafts are
review-only.
