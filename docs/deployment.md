# Deployment Guide

How to run Synpo GTM Automation locally and in production. The system has three
runtime processes plus two static/browser artifacts:

| Component | What | Where |
| --- | --- | --- |
| API | FastAPI (`app.main:app`) | `backend/`, container image `Dockerfile` |
| Worker | background pipeline (`app.worker`) | same image, different command |
| Dashboard | Next.js App Router | `frontend/` |
| Extension | Chrome MV3 capture | `extension/` |
| Data | Google Sheets (source of truth) | external; **no database** |

> Phase 9 (data migration) was intentionally skipped — the system has no database
> to migrate.

## 1. Topology

```text
Browser/Extension ──HTTPS──▶ API (FastAPI) ──▶ Google Sheets
                                   ▲                 ▲
                                   │                 │
                            Worker (1 instance) ─────┘
Dashboard (Next.js server) ──HTTP──▶ API
```

**Hard constraints**
- **Exactly one worker instance** and **one API writer**: job state lives in
  Sheets with an in-process lock; there is no cross-process lease yet. Scale
  reads only.
- Google Sheets API quotas apply; keep `GOOGLE_SHEETS_MAX_ATTEMPTS` and worker
  polling sane.
- The browser/extension never talks to Google Sheets or providers directly.

## 2. Configuration

Two env files, both with committed examples:

- Backend + worker: repo-root **`.env`** — see **`.env.example`**.
- Dashboard: **`frontend/.env.local`** — see **`frontend/.env.example`**.

Copy and fill:

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

### Required for a working pipeline

| Variable | File | Notes |
| --- | --- | --- |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | `.env` | target spreadsheet id |
| `GOOGLE_APPLICATION_CREDENTIALS` | `.env` | path to service-account JSON |
| `HIKERAPI_KEY` | `.env` | profile/media enrichment |
| `GEMINI_API_KEY` | `.env` | dossiers + outreach (optional: `AI_ENABLED=false` to skip) |
| `API_KEY` | `.env` | if set, API requires `x-api-key` |
| `BACKEND_API_KEY` | `frontend/.env.local` | must equal `API_KEY` |
| `API_BASE_URL` | `frontend/.env.local` | server-side API URL |
| `DASHBOARD_PASSWORD` | `frontend/.env.local` | enables the login gate (unset = open) |
| `SESSION_SECRET` | `frontend/.env.local` | optional cookie HMAC secret |
| API URL + key | extension popup settings | stored in `chrome.storage.local` |

### Secrets (never commit)

- `backend/secrets/service-account.json` — Google service account key
  (gitignored). Share the spreadsheet with the service-account email as Editor.
- All `.env*` files are gitignored; `.env.example` files contain placeholders only.
- Prefer a secrets manager in production (see §5/§6) rather than a checked-in file.

## 3. Run locally (Docker Compose)

```powershell
Copy-Item .env.example .env
# put the service-account JSON at backend/secrets/service-account.json
docker compose up --build            # API + worker
docker compose --profile frontend up # + dashboard on http://localhost:3000
```

- API: http://localhost:8000 (`/health`, `/docs`).
- The worker reuses the same image with `command: python -m app.worker`.
- The service-account JSON is mounted **read-only** at `/app/secrets`.
- Containers run **non-root**, `read_only`, `cap_drop: ALL`, `no-new-privileges`.

Useful commands:

```powershell
docker compose logs -f api worker
docker compose ps
docker compose restart worker
docker compose down
```

## 4. Run locally (no Docker, dev)

```powershell
# API
cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# Worker (separate terminal)
cd backend; .\.venv\Scripts\python.exe -m app.worker
# Dashboard (separate terminal)
cd frontend; npm run dev
```

## 5. Production — backend + worker

1. **Build & push the image**

   ```bash
   docker build -t registry.example.com/synpo-gtm-backend:1.0.0 .
   docker push registry.example.com/synpo-gtm-backend:1.0.0
   ```

2. **Provide config as secrets**, not files:
   - Env vars from a secret manager (AWS Secrets Manager / GCP Secret Manager /
     Vault / K8s Secret).
   - The service-account JSON mounted as a read-only secret volume.

3. **Run two workloads from the same image**:
   - API: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
     (`replicas: 1` for the MVP).
   - Worker: `python -m app.worker` (`replicas: 1`, `strategy: Recreate`).

4. **TLS + reverse proxy** (nginx/Caddy/Traefik) in front of the API. Set
   `CORS_ALLOW_ORIGINS` to your dashboard origin(s) (and `chrome-extension://…`
   if you ship the extension).

5. **Health**: the API exposes `GET /health`; wire it to your load balancer and
   container orchestrator. The worker has no HTTP surface — monitor logs and the
   `Pipeline Jobs` tab.

## 6. Production — dashboard (Next.js)

The dashboard is a standard Next.js app. Options:

- **Vercel (simplest)**: import `frontend/`, set env (`API_BASE_URL`,
  `BACKEND_API_KEY`, `DASHBOARD_PASSWORD`, `SESSION_SECRET`), deploy.
- **Node server / container**: build the included image and run it.

  ```bash
  docker build -t registry.example.com/synpo-gtm-frontend:1.0.0 ./frontend
  docker run -p 3000:3000 --env-file frontend/.env.production \
    -e API_BASE_URL=https://api.example.com \
    registry.example.com/synpo-gtm-frontend:1.0.0
  ```

- Put it behind TLS and set `API_BASE_URL` to the public API URL.

> The dashboard talks to the API **server-side only**; `BACKEND_API_KEY` is never
> sent to the browser. Do not add `NEXT_PUBLIC_` secrets.

## 7. Kubernetes (sketch)

A minimal, single-replica layout. Store env + the service-account JSON in a
Secret; the JSON is mounted read-only.

```yaml
apiVersion: v1
kind: Secret
metadata: { name: synpo-gtm-env }
type: Opaque
stringData:
  GOOGLE_SHEETS_SPREADSHEET_ID: "REPLACE"
  HIKERAPI_KEY: "REPLACE"
  GEMINI_API_KEY: "REPLACE"
  API_KEY: "REPLACE"
  CORS_ALLOW_ORIGINS: "https://dashboard.example.com"
  GOOGLE_APPLICATION_CREDENTIALS: /var/secrets/google/service-account.json
---
apiVersion: v1
kind: Secret
metadata: { name: synpo-gtm-sa }
type: Opaque
stringData:
  service-account.json: |
    { "type": "service_account", "...": "REPLACE" }
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: synpo-gtm-api }
spec:
  replicas: 1                      # single writer
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
          volumeMounts:
            - { name: sa, mountPath: /var/secrets/google, readOnly: true }
          readinessProbe: { httpGet: { path: /health, port: 8000 }, initialDelaySeconds: 10 }
          livenessProbe:  { httpGet: { path: /health, port: 8000 }, initialDelaySeconds: 20 }
          securityContext: { allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: ["ALL"] } }
      volumes:
        - name: sa
          secret: { secretName: synpo-gtm-sa }
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
          volumeMounts:
            - { name: sa, mountPath: /var/secrets/google, readOnly: true }
          securityContext: { allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: ["ALL"] } }
      volumes:
        - name: sa
          secret: { secretName: synpo-gtm-sa }
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

Notes:
- Set `GOOGLE_APPLICATION_CREDENTIALS` to the mounted path (`/var/secrets/google/...`).
- Keep `replicas: 1` for both API and worker until a Sheets-based lease exists
  (later phase). Scale the **dashboard** freely.
- Consider a `NetworkPolicy` restricting egress to Google APIs + HikerAPI + Gemini.

## 8. Security checklist

- [ ] No secrets in git or images (`.dockerignore`, `.gitignore`).
- [ ] Containers non-root, read-only root FS, capabilities dropped.
- [ ] `API_KEY` set; dashboard `BACKEND_API_KEY` matches; extension key matches.
- [ ] `CORS_ALLOW_ORIGINS` restricted to real origins in production.
- [ ] `DASHBOARD_PASSWORD` set; `SESSION_SECRET` unique per environment.
- [ ] TLS everywhere; spreadsheet shared only with the service account.
- [ ] `AI_ENABLED=false` if Gemini is not desired.
- [ ] One worker replica.

## 9. Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| API 503 "storage is not configured" | missing `GOOGLE_SHEETS_SPREADSHEET_ID` / credentials |
| API 401 | `API_KEY` set but caller didn't send `x-api-key` |
| Sheets 403 | spreadsheet not shared with the service-account email |
| Repeated Sheets 429 | back off: keep `GOOGLE_SHEETS_LAYOUT_CACHE_TTL_SECONDS` > 0, raise `WORKER_POLL_INTERVAL`, increase `GOOGLE_SHEETS_QUOTA_BACKOFF_*` |
| Worker does nothing | no eligible jobs, or `HIKERAPI_KEY` unset, or wrong `Pipeline Jobs` tab name |
| Dossiers/outreach never appear | `AI_ENABLED=false` or `GEMINI_API_KEY` unset |
| Gemini 404 | retired model — pick a current one (see `docs/gemini.md`) |
| HikerAPI 402 | account has no balance/credits |

See also: [dashboard.md](dashboard.md), [worker.md](worker.md),
[gemini.md](gemini.md), [website-enrichment.md](website-enrichment.md),
[../extension/README.md](../extension/README.md).
