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
