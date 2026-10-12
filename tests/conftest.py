from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the tests directory importable (for `fakes`) in addition to `backend`
# (which pytest adds via pythonpath in pytest.ini).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.sheets.repository import LeadStore  # noqa: E402
from app.sheets.schemas import IG_LEADS_HEADERS  # noqa: E402
from fakes import FakeSheetsClient  # noqa: E402


@pytest.fixture
def ig_client() -> FakeSheetsClient:
    """A fake client with an `IG Leads` tab that has the canonical header row."""
    return FakeSheetsClient({"IG Leads": [list(IG_LEADS_HEADERS)]})


@pytest.fixture
def lead_store(ig_client: FakeSheetsClient) -> LeadStore:
    return LeadStore(ig_client)


@pytest.fixture
def api_store(ig_client: FakeSheetsClient) -> LeadStore:
    return LeadStore(ig_client, tab_names={"ig_leads": "IG Leads"})


@pytest.fixture
def api_client(api_store: LeadStore):
    """A FastAPI TestClient whose lead service is backed by the fake store."""
    from fastapi.testclient import TestClient

    from app.dependencies import get_lead_service
    from app.leads.service import LeadService
    from app.main import app

    service = LeadService(api_store)
    app.dependency_overrides[get_lead_service] = lambda: service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
