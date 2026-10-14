# Deployment Guide

How to run Synpo GTM Automation locally and in production. The system has three
runtime processes plus two static/browser artifacts:

| Component | What | Where |
| --- | --- | --- |
| API | FastAPI (`app.main:app`) | `backend/`, container image `Dockerfile` |
| Worker | background pipeline (`app.worker`) | same image, different command |
| Dashboard | Next.js App Router | `frontend/` |
| Extension | Chrome MV3 capture | `extension/` |
| Data | **PostgreSQL** (source of truth) | `db` service / managed Postgres |

## 1. Topology

```text
Browser/Extension ──HTTPS──▶ API (FastAPI) ──SQL──▶ PostgreSQL
                                   ▲                    ▲
                                   │                    │
                            Worker (1 instance) ────────┘
Dashboard (Next.js server) ──HTTP──▶ API
```

**Constraints**
- Schema is managed by **Alembic**; the API runs `alembic upgrade head` on start.
- Keep **one worker instance** for now (a database-based lease is a later phase).
- The browser/extension never talk to PostgreSQL or providers directly.

## 2. Configuration

Two env files, both with committed examples:

- Backend + worker: repo-root **`.env`** — see **`.env.example`** (and the
  mirrored `backend/.env.example`).
- Dashboard: **`frontend/.env.local`** — see **`frontend/.env.example`**.

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

### Required

| Variable | File | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `.env` | sync SQLAlchemy URL (see below) |
| `HIKERAPI_KEY` | `.env` | profile/media enrichment |
| `GEMINI_API_KEY` | `.env` | dossiers + outreach (or `AI_ENABLED=false`) |
| `API_KEY` | `.env` | if set, API requires `x-api-key` |
| `BACKEND_API_KEY` | `frontend/.env.local` | must equal `API_KEY` |
| `API_BASE_URL` | `frontend/.env.local` | server-side API URL |
| `DASHBOARD_PASSWORD` | `frontend/.env.local` | enables the login gate |
| `SESSION_SECRET` | `frontend/.env.local` | optional cookie HMAC secret |
| API URL + key | extension popup settings | stored in `chrome.storage.local` |

### `DATABASE_URL` formats

```text
# local dev / tests
postgresql+psycopg2://postgres:postgres@localhost:5432/synpo
# inside docker compose (service name `db`)
postgresql+psycopg2://postgres:postgres@db:5432/synpo
# managed Postgres
postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

### Secrets (never commit)

- Database credentials live in `DATABASE_URL` (gitignored `.env`); prefer a
  secrets manager in production.
- All `.env*` files are gitignored; `.env.example` files contain placeholders only.

## 3. Run locally (Docker Compose)

```powershell
Copy-Item .env.example .env
docker compose up --build            # postgres + API + worker
docker compose --profile frontend up # + dashboard on http://localhost:3000
```

- Postgres: `postgres:15-alpine`, volume `postgres_data`, healthcheck `pg_isready`.
- The API waits for Postgres to be healthy, runs `alembic upgrade head`, then
  serves on http://localhost:8000 (`/health`, `/docs`).
- The worker reuses the same image with `command: python -m app.worker`.
- Containers run **non-root**, `read_only`, `cap_drop: ALL`, `no-new-privileges`.

Useful commands:

```powershell
docker compose logs -f api worker
docker compose exec api alembic upgrade head     # run migrations manually
docker compose exec db psql -U postgres -d synpo -c "\dt"
docker compose down                              # keep the volume
docker compose down -v                           # also delete data
```

## 4. Run locally (no Docker, dev)

```powershell
# 1. start Postgres (local install or a container)
docker run --name synpo-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=synpo -p 5432:5432 -d postgres:15-alpine
# 2. apply migrations
cd backend; .\.venv\Scripts\python.exe -m alembic upgrade head; cd ..
# 3. run the processes
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
cd backend; .\.venv\Scripts\python.exe -m app.worker
cd frontend; npm run dev
```

Verify: `.\backend\.venv\Scripts\python.exe scripts\verify_db.py`.

## 5. Production — backend + worker

1. **Provision Postgres** (managed service recommended) and set `DATABASE_URL`
   with `sslmode=require`.
2. **Build & push the image**

   ```bash
   docker build -t registry.example.com/synpo-gtm-backend:1.0.0 .
   docker push registry.example.com/synpo-gtm-backend:1.0.0
   ```

3. **Migrations**: run `alembic upgrade head` as a release step (the API also
   runs it on start). For zero-downtime, run migrations before rolling the API.
4. **Run two workloads from the same image**:
   - API: `uvicorn app.main:app --host 0.0.0.0 --port 8000` (`replicas: 1` for now).
   - Worker: `python -m app.worker` (`replicas: 1`, `strategy: Recreate`).
5. **TLS + reverse proxy** (nginx/Caddy/Traefik) in front of the API. Set
   `CORS_ALLOW_ORIGINS` to your dashboard origin(s) and `chrome-extension://…`.
6. **Health**: the API exposes `GET /health`; wire it to your load balancer.
   The worker has no HTTP surface — monitor logs and the `pipeline_jobs` table.

## 6. Production — dashboard (Next.js)

- **Vercel**: import `frontend/`, set env (`API_BASE_URL`, `BACKEND_API_KEY`,
  `DASHBOARD_PASSWORD`, `SESSION_SECRET`), deploy.
- **Container**:

  ```bash
  docker build -t registry.example.com/synpo-gtm-frontend:1.0.0 ./frontend
  docker run -p 3000:3000 --env-file frontend/.env.production \
    -e API_BASE_URL=https://api.example.com \
    registry.example.com/synpo-gtm-frontend:1.0.0
  ```

The dashboard talks to the API **server-side only**; `BACKEND_API_KEY` is never
sent to the browser. Do not add `NEXT_PUBLIC_` secrets.

## 7. Kubernetes (sketch)

```yaml
apiVersion: v1
kind: Secret
metadata: { name: synpo-gtm-env }
type: Opaque
stringData:
  DATABASE_URL: "postgresql+psycopg2://user:pass@db-host:5432/synpo?sslmode=require"
  HIKERAPI_KEY: "REPLACE"
  GEMINI_API_KEY: "REPLACE"
  API_KEY: "REPLACE"
  CORS_ALLOW_ORIGINS: "https://dashboard.example.com"
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: synpo-gtm-api }
spec:
  replicas: 1
  selector: { matchLabels: { app: synpo-gtm-api } }
  template:
    metadata: { labels: { app: synpo-gtm-api } }
    spec:
      securityContext: { runAsNonRoot: true, runAsUser: 10001 }
      containers:
        - name: api
          image: registry.example.com/synpo-gtm-backend:1.0.0
          ports: [{ containerPort: 8000 }]
          envFrom: [{ secretRef: { name: synpo-gtm-env } }]
          readinessProbe: { httpGet: { path: /health, port: 8000 }, initialDelaySeconds: 15 }
          livenessProbe:  { httpGet: { path: /health, port: 8000 }, initialDelaySeconds: 30 }
          securityContext: { allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: ["ALL"] } }
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: synpo-gtm-worker }
spec:
  replicas: 1                      # EXACTLY one
  strategy: { type: Recreate }
  selector: { matchLabels: { app: synpo-gtm-worker } }
  template:
    metadata: { labels: { app: synpo-gtm-worker } }
    spec:
      securityContext: { runAsNonRoot: true, runAsUser: 10001 }
      containers:
        - name: worker
          image: registry.example.com/synpo-gtm-backend:1.0.0
          command: ["python", "-m", "app.worker"]
          envFrom: [{ secretRef: { name: synpo-gtm-env } }]
          securityContext: { allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: ["ALL"] } }
---
apiVersion: v1
kind: Service
metadata: { name: synpo-gtm-api }
spec:
  selector: { app: synpo-gtm-api }
  ports: [{ port: 80, targetPort: 8000 }]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: synpo-gtm-api
  annotations: { nginx.ingress.kubernetes.io/ssl-redirect: "true" }
spec:
  tls: [{ hosts: ["api.example.com"], secretName: synpo-gtm-tls }]
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend: { service: { name: synpo-gtm-api, port: { number: 80 } } }
```

Run migrations as an init container or a `Job` before rolling out the API.

## 8. Security checklist

- [ ] No secrets in git or images (`.dockerignore`, `.gitignore`).
- [ ] Postgres reachable only from the app network; TLS (`sslmode=require`) in prod.
- [ ] Containers non-root, read-only root FS, capabilities dropped.
- [ ] `API_KEY` set; dashboard `BACKEND_API_KEY` matches; extension key matches.
- [ ] `CORS_ALLOW_ORIGINS` restricted to real origins in production.
- [ ] `DASHBOARD_PASSWORD` set; `SESSION_SECRET` unique per environment.
- [ ] Backups + point-in-time recovery configured for Postgres.
- [ ] `AI_ENABLED=false` if Gemini is not desired.
- [ ] One worker replica.

## 9. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| API 503 "Database is unavailable" | wrong `DATABASE_URL`, DB not running, or network/firewall |
| `relation "leads" does not exist` | migrations not applied — `alembic upgrade head` |
| API 401 | `API_KEY` set but caller didn't send `x-api-key` |
| Worker does nothing | no eligible jobs, or `HIKERAPI_KEY` unset |
| Dossiers/outreach never appear | `AI_ENABLED=false` or `GEMINI_API_KEY` unset |
| Gemini 404 | retired model — pick a current one (see `docs/gemini.md`) |
| HikerAPI 402 | account has no balance/credits |

See also: [database.md](database.md), [dashboard.md](dashboard.md),
[worker.md](worker.md), [gemini.md](gemini.md),
[../extension/README.md](../extension/README.md).
