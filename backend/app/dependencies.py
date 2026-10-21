"""FastAPI dependency providers (database-backed).

A SQLAlchemy session is created per request and wrapped in a `Repository`. The
MVP still assumes a single writer (one API instance + one worker); the database
now provides real concurrency safety at the row level.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.campaigns.service import CampaignService
from app.dashboard.service import DashboardService
from app.db.database import get_db
from app.db.repository import Repository
from app.leads.drafts import DraftService
from app.leads.service import LeadService


def get_repository(db: Session = Depends(get_db)) -> Repository:
    return Repository(db)


def get_lead_service(repo: Repository = Depends(get_repository)) -> LeadService:
    return LeadService(repo)


def get_draft_service(repo: Repository = Depends(get_repository)) -> DraftService:
    return DraftService(repo)


def get_dashboard_service(repo: Repository = Depends(get_repository)) -> DashboardService:
    return DashboardService(repo)


def get_campaign_service(repo: Repository = Depends(get_repository)) -> CampaignService:
    return CampaignService(repo)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject requests missing a valid `x-api-key` when API_KEY is configured.

    This is the **dashboard operator** credential: it grants full
    administrative access (decisions, discovery, drafts, retries, settings).
    """
    expected = get_settings().api_key.strip()
    if expected and x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


def require_capture_key(x_api_key: str | None = Header(default=None)) -> None:
    """Authorise a **capture-scoped** request (the extension, V2-09).

    PRD server rule 6: "Capture credentials can submit evidence/check
    connectivity/read their receipt; dashboard administration controls
    decisions, discovery and drafts."

    A capture key may:
      - submit a profile capture (``POST /leads``),
      - check connectivity (``GET /leads?limit=1``),
      - read its own receipt (``GET /leads/{lead_id}``).

    It is **rejected** on every dashboard-administration route. When
    ``CAPTURE_API_KEY`` is not configured the extension falls back to the shared
    operator key, which preserves the existing single-key deployment.
    """
    settings = get_settings()
    capture_key = settings.capture_api_key.strip()
    provided = (x_api_key or "").strip()

    if not capture_key:
        # No capture-scoped credential configured: behave exactly as before.
        require_api_key(x_api_key)
        return

    if provided == capture_key:
        return
    if provided and provided == settings.api_key.strip():
        # The operator key is also accepted here; the route itself is a
        # capture route, so this is not a privilege escalation.
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing capture key.",
    )


def require_operator_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject a **capture-scoped** key on a dashboard-administration route.

    Used by the administration routers so the extension's capture key cannot
    make decisions, run discovery, prepare drafts or retry work (V27).
    """
    settings = get_settings()
    capture_key = settings.capture_api_key.strip()
    provided = (x_api_key or "").strip()

    if capture_key and provided == capture_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "The capture key cannot access dashboard administration. "
                "Use the operator API key."
            ),
        )
    require_api_key(x_api_key)


__all__ = [
    "get_campaign_service",
    "get_dashboard_service",
    "get_db",
    "get_draft_service",
    "get_lead_service",
    "get_repository",
    "require_api_key",
    "require_capture_key",
    "require_operator_key",
]
