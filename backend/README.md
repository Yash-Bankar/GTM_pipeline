# Backend (FastAPI + worker)

Python backend for Synpo GTM Automation. The FastAPI app and the background
worker share one virtual environment: `backend/.venv`.

## Layout

```text
backend/
├─ app/
│  ├─ __init__.py
│  ├─ config.py    Settings loaded from environment variables
│  ├─ main.py      FastAPI app (health check only for now)
│  ├─ worker.py    Worker entrypoint (stub for now)
│  └─ sheets/      Google Sheets storage layer (Phase 1)
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
.\.venv\Scripts\python.exe app\worker.py --once
```

## Tests

Run from the repository root (uses `pytest.ini`):

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
```

Storage integration check (requires `.env` + `secrets/service-account.json`):

```powershell
.\backend\.venv\Scripts\python.exe scripts\verify_sheets.py --check-only
```

See [../docs/sheets-contract.md](../docs/sheets-contract.md) for the Sheets setup.

Configuration is read from environment variables (see the repo-root
`.env.example`). No secrets belong in this directory.
