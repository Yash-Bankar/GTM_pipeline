# Deploying Synpo GTM Automation on Oracle Cloud Infrastructure (OCI)

A standalone, copy-pasteable guide to run the full stack — PostgreSQL, the
FastAPI API, the Python worker, and the Next.js console — on an **OCI Linux
Compute Instance (Ubuntu 22.04 / 24.04 LTS)**, behind a reverse proxy with
HTTPS.

**What you'll end up with**

- `https://your-domain.com` → Next.js console
- `https://api.your-domain.com` → FastAPI (used by the console server-side and
  by the Chrome extension)
- All four services running under Docker Compose, with TLS via Let's Encrypt.

> HTTPS is **required** if you want the Chrome extension to talk to a remote API
> (extensions refuse insecure `http://` calls to non-localhost hosts, and
> `http://` also breaks some browser security features).

Commands below assume you are the `ubuntu` user and use `sudo` for privileged
steps.

---

## 1. OCI Instance Prerequisites & Ingress

### 1.1 Compute instance

- **Image:** Canonical Ubuntu **22.04** or **24.04** LTS.
- **Shape (recommended):**
  - **Ampere A1 Flex** — 2–4 OCPU / 12–24 GB RAM (best price/perf; ARM64 images
    are published for all services used here).
  - or **VM.Standard.E4/E5 Flex (AMD)** — 2 OCPU / 8–16 GB RAM.
- **Boot volume:** 50 GB minimum (Docker images + Postgres data). Add a block
  volume if you expect large datasets.
- **SSH key:** attach your public key at creation and keep the private key safe.

> `node:22-alpine` and `python:3.14-slim` images are multi-arch, so Ampere
> (aarch64) works out of the box.

### 1.2 OCI VCN Security List (ingress)

In **Networking → Virtual Cloud Networks → your VCN → Security Lists** (or a
Network Security Group), add **Ingress Rules**:

| Source CIDR | Protocol | Dest. port | Purpose |
| --- | --- | --- | --- |
| `<your-ip>/32` | TCP | 22 | SSH (restrict to your IP!) |
| `0.0.0.0/0` | TCP | 80 | HTTP (ACME + redirect) |
| `0.0.0.0/0` | TCP | 443 | HTTPS |
| `0.0.0.0/0` | TCP | 3000 | *(optional)* direct dashboard access for testing |
| `0.0.0.0/0` | TCP | 8000 | *(optional)* direct API access for testing |

Keep 3000/8000 **optional** — prefer the reverse proxy in §3. Remove them once
TLS is working.

### 1.3 OS firewall (important OCI gotcha)

OCI's Ubuntu images ship with `iptables` rules (via `netfilter-persistent`) that
**drop everything except SSH**, independent of the Security List. You must open
80/443 in the OS too.

Inspect the current INPUT chain (note the line number of the final `REJECT`):

```bash
sudo iptables -L INPUT --line-numbers
```

Insert ACCEPT rules **before** the REJECT rule (the example below inserts at
position 6; adjust to sit above your REJECT line):

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
# optional, for testing only:
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT

sudo netfilter-persistent save
sudo iptables -L INPUT --line-numbers   # verify the rules are above REJECT
```

<details>
<summary>Alternative: use <code>ufw</code></summary>

If you prefer `ufw`, install and enable it (it will coexist with the OCI rules
as long as 22 stays open):

```bash
sudo apt-get update && sudo apt-get install -y ufw
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status
```

</details>

---

## 2. Host Setup & Environment Prep

### 2.1 Install Docker Engine + Compose V2

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git

# Docker's official GPG key + repo
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Run docker without sudo (re-login afterwards)
sudo usermod -aG docker "$USER"
newgrp docker

docker --version && docker compose version
sudo systemctl enable --now docker
```

### 2.2 Clone the repository

```bash
cd ~
git clone <your-repo-url> synpo-gtm-automation
cd synpo-gtm-automation
```

> If the repo is private, use a deploy key or a PAT, or copy the folder over
> `scp`.

### 2.3 Production `.env`

```bash
cp .env.example .env
chmod 600 .env          # secrets file — keep it private
nano .env
```

Set at minimum:

```dotenv
APP_ENV=production
LOG_LEVEL=INFO

# Postgres runs in Compose as service `db`
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/synpo

# Providers
HIKERAPI_KEY=...
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash-lite        # or gemini-3.8-flash

# API auth + CORS (restrict to your real origins)
API_KEY=<long-random-secret>
CORS_ALLOW_ORIGINS=https://your-domain.com,chrome-extension://<extension-id>

# Worker
# Keep WORKER_POLL_INTERVAL <= 60 so /integrations/status reports "active".
WORKER_POLL_INTERVAL=30
WORKER_STALE_MINUTES=30
```

Generate a strong API key:

```bash
openssl rand -hex 32
```

### 2.4 Frontend auth (`frontend/.env.local`)

The console calls the API **server-side**, so it needs its own env:

```bash
cp frontend/.env.example frontend/.env.local
nano frontend/.env.local
```

```dotenv
API_BASE_URL=http://api:8000          # internal Compose network (leave as-is)
BACKEND_API_KEY=<same value as API_KEY>
DASHBOARD_PASSWORD=<your dashboard password>
SESSION_SECRET=<openssl rand -hex 32>
```

> The compose `frontend` service sets `API_BASE_URL=http://api:8000`
> automatically; you mainly need `BACKEND_API_KEY` (must equal `API_KEY`) and
> `DASHBOARD_PASSWORD`.

---

## 3. Reverse Proxy & SSL

Point DNS at the instance's public IP first:

| Record | Type | Value |
| --- | --- | --- |
| `your-domain.com` | A | `<instance public IP>` |
| `api.your-domain.com` | A | `<instance public IP>` |

Wait for DNS to resolve (`dig +short api.your-domain.com`) before requesting
certificates.

### 3.1 Option A — Caddy (automatic HTTPS, recommended)

Caddy obtains and renews Let's Encrypt certificates with zero config.

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
  sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
  sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy
```

`/etc/caddy/Caddyfile`:

```caddyfile
# Next.js console
your-domain.com {
    encode gzip
    reverse_proxy 127.0.0.1:3000
}

# FastAPI (console server-side calls go direct to api:8000 internally;
# this public host serves the Chrome extension and external clients)
api.your-domain.com {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
```

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
```

Caddy listens on 80/443, issues certs, and redirects HTTP→HTTPS automatically.

### 3.2 Option B — Nginx + Certbot

```bash
sudo apt-get install -y nginx
```

`/etc/nginx/sites-available/synpo`:

```nginx
# Next.js console
server {
    listen 80;
    server_name your-domain.com;
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# FastAPI
server {
    listen 80;
    server_name api.your-domain.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/synpo /etc/nginx/sites-enabled/synpo
sudo nginx -t && sudo systemctl reload nginx

sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d api.your-domain.com \
  --agree-tos -m you@example.com --redirect
```

Certbot installs a renewal timer automatically (`systemctl list-timers | grep certbot`).

> **CORS:** after enabling HTTPS, ensure `CORS_ALLOW_ORIGINS` in `.env` lists
> `https://your-domain.com` and the extension origin
> `chrome-extension://<extension-id>` (find the id at `chrome://extensions`).
> `*` works but is not recommended for production.

---

## 4. Container Orchestration & Database Initialization

### 4.1 Start the stack (detached)

```bash
cd ~/synpo-gtm-automation
docker compose --profile frontend up -d --build
```

This builds the backend + frontend images and starts four containers:
`db`, `api`, `worker`, `frontend`.

### 4.2 Database migrations

The **API container runs `alembic upgrade head` on startup**, so migrations are
applied automatically. To run them explicitly:

```bash
docker compose exec api alembic upgrade head
```

### 4.3 Verify database health & tables

```bash
docker compose ps
# db should be "(healthy)"; api "(healthy)"; worker "Up"

docker compose exec db psql -U postgres -d synpo -c "\dt"
```

Expected tables:

```text
 alembic_version
 contact_requests
 dossiers
 lead_posts
 leads
 outreach_drafts
 outreach_revisions
 pipeline_jobs
 website_pages
 worker_heartbeat
```

The current migration head is `b2c3d4e5f6a7` (adds fit-decision columns,
`contact_requests`, `outreach_revisions`, and `worker_heartbeat`). Confirm with:

```bash
docker compose exec db psql -U postgres -d synpo \
  -c "select version_num from alembic_version;"
```

The Postgres container is named **`synpo-gtm-automation-db-1`** (project folder
name + service + index) and persists data in the `postgres_data` volume.

---

## 5. Verification & Health Monitoring

### 5.1 API health check

```bash
curl -s https://api.your-domain.com/health
# {"status":"ok","service":"synpo-gtm-api","version":"0.1.0"}
```

Authenticated call (when `API_KEY` is set):

```bash
curl -s -H "x-api-key: $API_KEY" https://api.your-domain.com/api/v1/stats
```

### 5.2 Container status & logs

```bash
docker compose ps
docker compose logs -f api worker       # follow API + worker
docker compose logs --tail=100 frontend
```

### 5.3 Console & extension

- Open `https://your-domain.com` and log in with `DASHBOARD_PASSWORD`.
- **Chrome extension:** popup → **Settings**:
  - **API base URL:** `https://api.your-domain.com`
  - **API key:** the same value as `API_KEY`
   Then open an Instagram profile and click **Add to GTM**; the lead appears in
   the console.

### 5.4 Readiness and worker heartbeat (T09)

The worker upserts a single `worker_heartbeat` row every poll cycle. The
authenticated readiness endpoint reports health without exposing secrets:

```bash
curl -s -H "x-api-key: $API_KEY" \
  https://api.your-domain.com/api/v1/integrations/status

# {"database":"healthy","worker":"active","gemini":"configured",
#  "hikerapi":"configured","worker_last_beat_at":"2026-10-19T18:28:36+00:00"}
```

| Field | Values | Meaning |
| --- | --- | --- |
| `database` | `healthy` / `unreachable` | `SELECT 1` succeeded / failed |
| `worker` | `active` / `stale` / `stopped` | heartbeat ≤60s / older than 60s / no heartbeat |
| `worker_last_beat_at` | ISO timestamp | last recorded heartbeat |
| `gemini` | `configured` / `disabled` | `AI_ENABLED` and `GEMINI_API_KEY` |
| `hikerapi` | `configured` / `disabled` | `HIKERAPI_KEY` set |

The console **Settings** (`/settings`) page renders the same values.

**No new environment variables are required.** The heartbeat is stored in
PostgreSQL. Keep `WORKER_POLL_INTERVAL` at or below **60 seconds** (default
`30`) so the worker reports `active` between polls; a larger interval will show
`stale` between cycles. If the worker is `stopped`/`stale`, check
`docker compose ps` and `docker compose logs worker`, then
`docker compose restart worker`. `gemini=disabled`/`hikerapi=disabled` only means
the optional credential is unset; snapshot-only capture still works.

---

## 6. Maintenance & Operational Runbook

### 6.1 Gemini model & rate-limit management

- Choose the model via `GEMINI_MODEL` in `.env`:
  - **`gemini-3.5-flash-lite`** — lower cost / higher throughput; good default.
  - **`gemini-3.8-flash`** — higher quality dossiers/outreach.
- If a model is retired, the API returns HTTP 404; pick a current model
  (`docs/gemini.md` has a command to list available models).
- **429 / 503 (high demand):** bounded retries + exponential backoff apply
  automatically; jobs surface `AIModelError` with the reason and can be retried
  from the console with **"Re-process AI Jobs Only"**.
- Disable AI entirely with `AI_ENABLED=false` (dossier/outreach stages are
  skipped) to control spend.

After editing `.env`, recreate the affected services:

```bash
docker compose up -d api worker        # picks up new env
```

### 6.2 Restarting services

```bash
docker compose restart worker          # restart just the worker
docker compose restart api
docker compose restart                 # restart all
```

### 6.3 Deploying updates

```bash
cd ~/synpo-gtm-automation
git pull
docker compose --profile frontend up -d --build   # rebuild + recreate
docker compose exec api alembic upgrade head      # if new migrations
```

### 6.4 PostgreSQL volume: persistence & backups

Data lives in the named volume **`postgres_data`** (survives `docker compose
down`; removed only by `docker compose down -v`).

**Logical backup (recommended):**

```bash
mkdir -p ~/backups
docker compose exec -T db pg_dump -U postgres -d synpo \
  | gzip > ~/backups/synpo_$(date +%F_%H%M).sql.gz
```

**Restore:**

```bash
gunzip -c ~/backups/synpo_YYYY-MM-DD_HHMM.sql.gz \
  | docker compose exec -T db psql -U postgres -d synpo
```

**Volume-level backup** (stop writers first for consistency):

```bash
docker compose stop worker api
docker run --rm -v synpo-gtm-automation_postgres_data:/data -v ~/backups:/backup \
  alpine tar czf /backup/postgres_data_$(date +%F).tar.gz -C /data .
docker compose start api worker
```

Schedule the `pg_dump` above via cron for daily backups and copy them off-box
(e.g. OCI Object Storage).

### 6.5 Disk cleanup

```bash
docker image prune -f          # dangling images
docker system prune -f         # unused containers/networks/images (safe)
docker system df               # review usage
```

### 6.6 Security hardening

- Restrict the SSH Security List rule to your IP; use key-based auth only.
- Keep `API_KEY` long and random; rotate if leaked; set `BACKEND_API_KEY` to match.
- Restrict `CORS_ALLOW_ORIGINS` to your domain + extension id.
- Keep `DASHBOARD_PASSWORD` strong and `SESSION_SECRET` unique.
- Do **not** expose Postgres (5432) publicly — it isn't published by compose, and
  keep it that way. For extra safety, bind published ports to localhost by
  editing `docker-compose.yml` (`"127.0.0.1:8000:8000"`, `"127.0.0.1:3000:3000"`)
  and let only the reverse proxy reach them.
- Optional: install `fail2ban` for SSH brute-force protection.

### 6.7 Troubleshooting quick table

| Symptom | Likely cause / fix |
| --- | --- |
| `curl` to domain hangs / connection refused | OCI Security List **and** OS `iptables` rules not open (§1.2–1.3) |
| `relation "leads" does not exist` | migrations not applied → `docker compose exec api alembic upgrade head` |
| API `503 Database is unavailable` | `DATABASE_URL` wrong, or `db` container unhealthy → `docker compose ps` |
| Console returns 401 | `BACKEND_API_KEY` in `frontend/.env.local` ≠ `API_KEY` |
| Extension can't reach API | API base URL must be `https://…`; CORS must include the extension origin |
| Caddy/Nginx can't get certs | DNS not pointing at the instance, or port 80 blocked |
| Worker idle / no jobs | no queued jobs; `HIKERAPI_KEY` is optional (snapshot leads need no key) |
| `/settings` shows worker **stale**/**stopped** | worker not running, or `WORKER_POLL_INTERVAL` > 60 → `docker compose ps`, `docker compose logs worker`, `docker compose restart worker` |
| `/settings` shows Gemini/HikerAPI **disabled** | optional credential unset; snapshot-only capture and manual review still work |
| `contact-requests`/`draft-requests` return `403` | `fit_status` is not `approved`; record an Approve Fit decision first |

---

## Appendix — one-shot command summary

```bash
# 1) Ingress: open 80/443 (OCI Security List + OS firewall) — see §1
# 2) Install Docker — see §2.1
# 3) Clone + configure
git clone <repo> ~/synpo-gtm-automation && cd ~/synpo-gtm-automation
cp .env.example .env && cp frontend/.env.example frontend/.env.local
nano .env && nano frontend/.env.local
# 4) Reverse proxy + TLS — see §3
# 5) Run
docker compose --profile frontend up -d --build
docker compose exec api alembic upgrade head
# 6) Verify
curl -s https://api.your-domain.com/health
curl -s -H "x-api-key: $API_KEY" https://api.your-domain.com/api/v1/integrations/status
docker compose ps
```
