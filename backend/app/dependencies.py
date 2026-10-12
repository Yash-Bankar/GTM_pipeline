"""FastAPI dependency providers and shared store wiring.

All stores share **one** `GoogleSheetsClient` and **one** in-process write lock,
so writes are serialized. The MVP supports exactly one backend instance and one
worker: do not run multiple API replicas or a separate writer process, or Sheets
writes can race. A Sheets-based lease is a later phase.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache

from app.config import Settings, get_settings
from app.leads.service import LeadService
from app.sheets.client import GoogleSheetsClient
from app.sheets.repository import (
    JobStore,
    LeadStore,
    SheetStore,
    tab_names_from_settings,
)


@dataclass(frozen=True)
class SheetStores:
    """The shared spreadsheet client and every repository built on it."""

    client: GoogleSheetsClient
    lock: threading.RLock
    tab_names: dict[str, str]
    lead_store: LeadStore
    job_store: JobStore
    enriched_store: SheetStore
    outreach_store: SheetStore


def build_sheet_stores(settings: Settings) -> SheetStores:
    """Build a fresh bundle (one client, one lock shared by all stores)."""
    client = GoogleSheetsClient.from_settings(settings)
    lock = threading.RLock()
    tab_names = tab_names_from_settings(settings)
    return SheetStores(
        client=client,
        lock=lock,
        tab_names=tab_names,
        lead_store=LeadStore(client, tab_names=tab_names, mutation_lock=lock),
        job_store=JobStore(client, tab_names=tab_names, mutation_lock=lock),
        enriched_store=SheetStore(client, tab_names=tab_names, mutation_lock=lock),
        outreach_store=SheetStore(client, tab_names=tab_names, mutation_lock=lock),
    )


@lru_cache(maxsize=1)
def get_sheet_stores() -> SheetStores:
    return build_sheet_stores(get_settings())


def get_lead_store() -> LeadStore:
    return get_sheet_stores().lead_store


def get_job_store() -> JobStore:
    return get_sheet_stores().job_store


def get_lead_service() -> LeadService:
    stores = get_sheet_stores()
    return LeadService(stores.lead_store, job_store=stores.job_store)


__all__ = [
    "SheetStores",
    "build_sheet_stores",
    "get_job_store",
    "get_lead_service",
    "get_lead_store",
    "get_sheet_stores",
]
