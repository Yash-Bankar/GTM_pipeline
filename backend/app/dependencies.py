"""FastAPI dependency providers (database-backed).

A SQLAlchemy session is created per request and wrapped in a `Repository`. The
MVP still assumes a single writer (one API instance + one worker); the database
now provides real concurrency safety at the row level.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dashboard.service import DashboardService
from app.db.database import get_db
from app.db.repository import Repository
from app.leads.service import LeadService


def get_repository(db: Session = Depends(get_db)) -> Repository:
    return Repository(db)


def get_lead_service(repo: Repository = Depends(get_repository)) -> LeadService:
    return LeadService(repo)


def get_dashboard_service(repo: Repository = Depends(get_repository)) -> DashboardService:
    return DashboardService(repo)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject requests missing a valid `x-api-key` when API_KEY is configured."""
    expected = get_settings().api_key.strip()
    if expected and x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )


__all__ = [
    "get_dashboard_service",
    "get_db",
    "get_lead_service",
    "get_repository",
    "require_api_key",
]
