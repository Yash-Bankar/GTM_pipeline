"""FastAPI dependency providers.

The `LeadStore` is a process-wide singleton so its in-process write lock is
shared by every request. **The MVP supports exactly one backend instance**: do
not run multiple API replicas or a separate writer process, or Sheets writes can
race. A Sheets-based lease is a later phase.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.leads.service import LeadService
from app.sheets.repository import LeadStore


@lru_cache(maxsize=1)
def _lead_store_singleton() -> LeadStore:
    """Build (once) the process-wide lead store, sharing the write lock."""
    return LeadStore.from_settings(get_settings())


def get_lead_store() -> LeadStore:
    return _lead_store_singleton()


def get_lead_service() -> LeadService:
    return LeadService(get_lead_store())
