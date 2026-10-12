"""FastAPI application entrypoint.

Exposes the lead capture API and maps storage/validation failures to clear HTTP
statuses. Google Sheets is accessed server-side only; the frontend never talks to
it directly.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.leads.routes import router as leads_router
from app.leads.validation import InvalidLeadInput
from app.sheets.errors import (
    DuplicateLeadError,
    SheetsConfigError,
    SheetsError,
    SheetsQuotaError,
)

app = FastAPI(
    title="Synpo GTM Automation API",
    version=__version__,
    summary="Operations API for the Synpo GTM Instagram creator pipeline.",
)

app.include_router(leads_router)


def _problem(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message})


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe used for smoke tests."""
    return {"status": "ok", "service": "synpo-gtm-api", "version": __version__}


@app.exception_handler(InvalidLeadInput)
async def _handle_invalid_input(_request: Request, exc: InvalidLeadInput) -> JSONResponse:
    return _problem(422, str(exc))


@app.exception_handler(SheetsConfigError)
async def _handle_config_error(_request: Request, exc: SheetsConfigError) -> JSONResponse:
    return _problem(503, f"Google Sheets storage is not configured: {exc}")


@app.exception_handler(SheetsQuotaError)
async def _handle_quota_error(_request: Request, exc: SheetsQuotaError) -> JSONResponse:
    return _problem(503, f"Google Sheets is rate limited, retry shortly: {exc}")


@app.exception_handler(DuplicateLeadError)
async def _handle_duplicate(_request: Request, exc: DuplicateLeadError) -> JSONResponse:
    return _problem(409, str(exc))


@app.exception_handler(SheetsError)
async def _handle_sheets_error(_request: Request, exc: SheetsError) -> JSONResponse:
    return _problem(502, f"Google Sheets error: {exc}")
