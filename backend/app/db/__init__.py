"""PostgreSQL-backed storage layer (replaces the Google Sheets adapter)."""

from __future__ import annotations

from .database import Base, get_db, get_engine, get_session_factory, reset_engine
from .errors import DuplicateLeadError, LeadNotFoundError, StorageError
from .repository import Repository
from .schemas import (
    Dossier,
    Lead,
    LeadPost,
    OutreachEntry,
    PipelineJob,
    RowModel,
    WebsitePage,
    normalize_username,
)
from .util import new_job_id, new_lead_id, stringify, utc_now_iso

__all__ = [
    "Base",
    "Dossier",
    "DuplicateLeadError",
    "Lead",
    "LeadNotFoundError",
    "LeadPost",
    "OutreachEntry",
    "PipelineJob",
    "Repository",
    "RowModel",
    "StorageError",
    "WebsitePage",
    "get_db",
    "get_engine",
    "get_session_factory",
    "new_job_id",
    "new_lead_id",
    "normalize_username",
    "reset_engine",
    "stringify",
    "utc_now_iso",
]
