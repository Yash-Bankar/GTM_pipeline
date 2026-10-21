"""FastAPI application entrypoint.

Exposes the lead capture API and maps storage/validation failures to clear HTTP
statuses. PostgreSQL is accessed server-side only; the frontend never talks to it
directly.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app import __version__
from app.campaigns.routes import router as campaign_router
from app.config import get_settings
from app.dashboard.routes import router as dashboard_router
from app.db.errors import DuplicateLeadError, StorageError
from app.leads.routes import router as leads_router
from app.leads.validation import InvalidLeadInput

app = FastAPI(
    title="Synpo GTM Automation API",
    version=__version__,
    summary="Operations API for the Synpo GTM Instagram creator pipeline.",
)

_cors_origins = [o.strip() for o in get_settings().cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(leads_router)
app.include_router(dashboard_router)
app.include_router(campaign_router)


def _problem(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message})


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe used for smoke tests."""
    return {"status": "ok", "service": "synpo-gtm-api", "version": __version__}


@app.exception_handler(InvalidLeadInput)
async def _handle_invalid_input(_request: Request, exc: InvalidLeadInput) -> JSONResponse:
    return _problem(422, str(exc))


@app.exception_handler(DuplicateLeadError)
async def _handle_duplicate(_request: Request, exc: DuplicateLeadError) -> JSONResponse:
    return _problem(409, str(exc))


@app.exception_handler(OperationalError)
async def _handle_db_unavailable(_request: Request, exc: OperationalError) -> JSONResponse:
    return _problem(503, f"Database is unavailable: {exc.orig if hasattr(exc, 'orig') else exc}")


@app.exception_handler(StorageError)
async def _handle_storage_error(_request: Request, exc: StorageError) -> JSONResponse:
    return _problem(500, f"Storage error: {exc}")


@app.exception_handler(SQLAlchemyError)
async def _handle_sqlalchemy_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return _problem(500, f"Database error: {type(exc).__name__}")
