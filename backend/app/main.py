"""FastAPI application entrypoint.

Foundation only: exposes a health check so the service can be started and
verified. Business endpoints are added in later phases (see
docs/architecture.md).
"""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__

app = FastAPI(
    title="Synpo GTM Automation API",
    version=__version__,
    summary="Operations API for the Synpo GTM Instagram creator pipeline.",
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe used for smoke tests."""
    return {"status": "ok", "service": "synpo-gtm-api", "version": __version__}
