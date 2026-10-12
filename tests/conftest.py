from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the tests directory importable (for `fakes`) in addition to `backend`
# (which pytest adds via pythonpath in pytest.ini).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.sheets.repository import JobStore, LeadStore  # noqa: E402
from app.sheets.schemas import (  # noqa: E402
    ENRICHED_HEADERS,
    IG_LEADS_HEADERS,
    LEAD_POSTS_HEADERS,
    PIPELINE_JOBS_HEADERS,
    WEBSITE_PAGES_HEADERS,
)
from fakes import FakeSheetsClient  # noqa: E402


@pytest.fixture
def ig_client() -> FakeSheetsClient:
    """A fake client with the canonical `IG Leads` and `Pipeline Jobs` headers."""
    return FakeSheetsClient(
        {
            "IG Leads": [list(IG_LEADS_HEADERS)],
            "Pipeline Jobs": [list(PIPELINE_JOBS_HEADERS)],
        }
    )


@pytest.fixture
def worker_stores():
    """Stores sharing one fake client, including the enriched/post/website tabs."""
    from types import SimpleNamespace

    from app.sheets.repository import SheetStore

    client = FakeSheetsClient(
        {
            "IG Leads": [list(IG_LEADS_HEADERS)],
            "Pipeline Jobs": [list(PIPELINE_JOBS_HEADERS)],
            "instagram_leads_enriched": [list(ENRICHED_HEADERS)],
            "Lead Posts": [list(LEAD_POSTS_HEADERS)],
            "Website Pages": [list(WEBSITE_PAGES_HEADERS)],
        }
    )
    return SimpleNamespace(
        client=client,
        lead=LeadStore(client),
        jobs=JobStore(client),
        enriched=SheetStore(client),
        posts=SheetStore(client),
        website=SheetStore(client),
    )


@pytest.fixture
def lead_store(ig_client: FakeSheetsClient) -> LeadStore:
    return LeadStore(ig_client)


@pytest.fixture
def job_store(ig_client: FakeSheetsClient) -> JobStore:
    return JobStore(ig_client)


@pytest.fixture
def api_store(ig_client: FakeSheetsClient) -> LeadStore:
    return LeadStore(ig_client, tab_names={"ig_leads": "IG Leads"})


@pytest.fixture
def api_client(api_store: LeadStore, job_store: JobStore):
    """A FastAPI TestClient whose lead service is backed by the fake stores."""
    from fastapi.testclient import TestClient

    from app.dependencies import get_lead_service
    from app.leads.service import LeadService
    from app.main import app

    service = LeadService(api_store, job_store=job_store)
    app.dependency_overrides[get_lead_service] = lambda: service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
