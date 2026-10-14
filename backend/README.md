# Backend (FastAPI + worker)

Python backend for Synpo GTM Automation. The FastAPI app and the background
worker share one virtual environment: `backend/.venv`.

## Layout

```text
backend/
├─ app/
│  ├─ __init__.py
│  ├─ config.py    Settings loaded from environment variables
│  ├─ main.py      FastAPI app (health + lead API)
│  ├─ worker/      Autonomous worker (Phase 4)
│  ├─ common/      Shared helpers (retry)
│  ├─ leads/       Lead API (Phase 2)
│  ├─ providers/   HikerAPI provider (Phase 3)
│  └─ db/          PostgreSQL storage layer (Phase 11)
├─ alembic/        Database migrations
├─ alembic.ini
├─ requirements.txt
└─ .venv/          local virtual environment (gitignored)
```

## Setup

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run the API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: `Invoke-RestMethod http://127.0.0.1:8000/health`

## Run the worker

```powershell
.\.venv\Scripts\python.exe -m app.worker --drain
```

## Migrations

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Tests

Run from the repository root (uses `pytest.ini`); tests use in-memory SQLite:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
```

Database check (requires `DATABASE_URL` and applied migrations):

```powershell
.\backend\.venv\Scripts\python.exe scripts\verify_db.py
```

See [../docs/database.md](../docs/database.md) for the schema and contracts.

Configuration is read from environment variables (see the repo-root
`.env.example`). No secrets belong in this directory.
