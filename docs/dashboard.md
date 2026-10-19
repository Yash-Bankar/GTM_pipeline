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
| `/leads` | Searchable, filterable leads table; verified badge; follower precision; add-lead form; pipeline stats |
| `/leads/[leadId]` | Profile snapshot (verified badge, bio, links, follower precision, missing fields), recent posts, website pages, job history, **fit decision**, **contact/draft gates**, and **draft revision history**; re-queue processing or **re-process AI jobs only** |
| `/dossiers` | Dossier list with qualification score/tier; visible **Search creators** label |
| `/dossiers/[leadId]` | Structured AI findings, criterion scores, cited sources, uncertainty |
| `/outreach` | Draft list with a visible **Draft status** filter |
| `/outreach/[leadId]` | Editable email + DM draft with Approve / Reject (nothing is sent) |
| `/settings` | System health: worker heartbeat, database, Gemini/HikerAPI readiness, pipeline rules |

Navigation is a sidebar at `lg+` and a visible compact top bar below `lg` (no
hover-only menus); section links expose `aria-current`. Snapshot-only leads show
"Posts not captured in snapshot" instead of an ambiguous empty posts section.

## States

- **Loading**: `loading.tsx` per route (skeleton tables/cards) — also satisfies
  Next's Cache Components requirement for a Suspense boundary around runtime data.
- **Empty**: dedicated empty states for leads, dossiers, posts, pages, drafts.
- **Duplicate**: the add-lead form reports "already in the pipeline".
- **Error + retry**: pages render an error card with a Retry link; a route-level
  `error.tsx` boundary offers "Try again".

## Backend endpoints used

`GET /api/v1/leads`, `POST /api/v1/leads`, `GET /api/v1/leads/{id}/detail`,
`POST /api/v1/leads/{id}/retry`, `POST /api/v1/leads/{id}/retry-ai`,
`GET /api/v1/dossiers[/{id}]`, `GET /api/v1/outreach[/{id}]`,
`PATCH /api/v1/outreach/{id}`, `GET /api/v1/stats`.
All accept/return typed JSON; the client lives in `frontend/src/lib/api.ts`.

## Quality checks

```powershell
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

## Not implemented

No direct Instagram scraping and no sending of messages — outreach drafts are
review-only.
