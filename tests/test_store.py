from __future__ import annotations

import pytest

from app.sheets.errors import (
    DuplicateLeadError,
    SchemaError,
    SheetTabMissingError,
    SheetsNotFoundError,
)
from app.sheets.models import Lead
from app.sheets.repository import LeadStore, SheetStore
from app.sheets.schemas import IG_LEADS_HEADERS


def _row_values(client, tab: str, row_number: int) -> list[str]:
    return client.read_row(tab, row_number)


def test_create_lead_assigns_id_normalizes_and_appends(lead_store, ig_client) -> None:
    lead = lead_store.create_lead("@Some.Creator", source="test")

    assert lead.lead_id.startswith("ld_")
    assert lead.username == "Some.Creator"
    assert lead.username_normalized == "some.creator"
    assert lead.status == "new"
    assert lead.source == "test"
    assert lead.created_at and lead.updated_at

    row = _row_values(ig_client, "IG Leads", 2)
    assert row[0] == lead.lead_id
    assert row[1] == "Some.Creator"
    assert row[2] == "some.creator"


def test_duplicate_username_raises(lead_store) -> None:
    lead_store.create_lead("creator.one")
    with pytest.raises(DuplicateLeadError):
        lead_store.create_lead("https://instagram.com/creator.one/")


def test_get_or_create_returns_existing(lead_store) -> None:
    first = lead_store.create_lead("creator.one")
    second = lead_store.get_or_create_lead("Creator.One")
    assert second.lead_id == first.lead_id
    assert len(lead_store.read_models("ig_leads")) == 1


def test_find_by_username(lead_store) -> None:
    lead = lead_store.create_lead("find.me")
    found = lead_store.find_by_username("instagram.com/find.me")
    assert found is not None
    assert found.lead_id == lead.lead_id
    assert lead_store.find_by_username("nobody") is None


def test_read_models_returns_typed_leads(lead_store) -> None:
    lead_store.create_lead("typed.one")
    models = lead_store.read_models("ig_leads")
    assert len(models) == 1
    assert isinstance(models[0], Lead)


def test_update_by_key_targets_only_named_columns(lead_store, ig_client) -> None:
    lead = lead_store.create_lead("update.me")
    lead_store.update_by_key("ig_leads", lead.lead_id, {"status": "enriched", "bio": "hi"})

    row = _row_values(ig_client, "IG Leads", 2)
    index = {name: i for i, name in enumerate(IG_LEADS_HEADERS)}
    assert row[index["status"]] == "enriched"
    assert row[index["bio"]] == "hi"
    # username is untouched by the update
    assert row[index["username"]] == "update.me"
    assert row[index["updatedAt"]] != ""


def test_update_by_key_unknown_key_raises(lead_store) -> None:
    lead_store.create_lead("update.missing")
    with pytest.raises(SheetsNotFoundError):
        lead_store.update_by_key("ig_leads", "ld_nope", {"status": "x"})


def test_missing_tab_raises() -> None:
    from fakes import FakeSheetsClient

    store = LeadStore(FakeSheetsClient({}))
    with pytest.raises(SheetTabMissingError):
        store.read_rows("ig_leads")


def test_no_header_row_raises() -> None:
    from fakes import FakeSheetsClient

    store = LeadStore(FakeSheetsClient({"IG Leads": [[]]}))
    with pytest.raises(SchemaError):
        store.get_layout("ig_leads")


def test_ensure_schema_creates_missing_tab() -> None:
    from fakes import FakeSheetsClient

    client = FakeSheetsClient({})
    store = SheetStore(client, tab_names={"ig_leads": "IG Leads"})
    report = store.ensure_schema("ig_leads", create_missing=True)

    assert report.ok and report.created and report.header_written
    assert client.read_row("IG Leads", 1) == list(IG_LEADS_HEADERS)


def test_ensure_schema_reports_missing_headers_without_writing() -> None:
    from fakes import FakeSheetsClient

    partial = ["leadId", "username"]
    client = FakeSheetsClient({"IG Leads": [partial]})
    store = SheetStore(client, tab_names={"ig_leads": "IG Leads"})

    report = store.ensure_schema("ig_leads", create_missing=False, extend_headers=False)
    assert not report.ok
    assert "status" in report.missing_headers
    # header row is untouched
    assert client.read_row("IG Leads", 1) == partial


def test_ensure_schema_extends_headers_non_destructively() -> None:
    from fakes import FakeSheetsClient

    partial = ["leadId", "username"]
    client = FakeSheetsClient({"IG Leads": [partial]})
    store = SheetStore(client, tab_names={"ig_leads": "IG Leads"})

    report = store.ensure_schema("ig_leads", create_missing=False, extend_headers=True)
    assert report.ok
    assert "status" in report.extended_headers

    header = client.read_row("IG Leads", 1)
    assert header[:2] == partial  # existing cells preserved, in place
    assert "status" in header


def test_update_preserves_unknown_columns() -> None:
    from fakes import FakeSheetsClient

    headers = list(IG_LEADS_HEADERS) + ["customField"]
    client = FakeSheetsClient({"IG Leads": [headers]})
    store = LeadStore(client, tab_names={"ig_leads": "IG Leads"})
    idx = {name: i for i, name in enumerate(headers)}

    lead = store.create_lead("keep.extra")
    # Simulate another column being populated by an external process.
    client.update_cells("IG Leads", [(2, idx["customField"], "keep-me")])

    store.update_by_key("ig_leads", lead.lead_id, {"status": "done"})

    row = client.read_row("IG Leads", 2)
    assert row[idx["customField"]] == "keep-me"  # untouched by the targeted update
    assert row[idx["status"]] == "done"

def test_get_layout_and_tab_titles_are_cached(ig_client) -> None:
    store = SheetStore(ig_client, tab_names={"ig_leads": "IG Leads"})
    store.get_layout("ig_leads")
    store.get_layout("ig_leads")
    store.read_rows("ig_leads")
    assert ig_client.titles_calls == 1  # titles fetched once, then cached
    assert ig_client.read_row_calls == 1  # header row read once, then cached


def test_layout_cache_can_be_disabled(ig_client) -> None:
    store = SheetStore(ig_client, tab_names={"ig_leads": "IG Leads"}, layout_cache_ttl=0.0)
    store.get_layout("ig_leads")
    store.get_layout("ig_leads")
    assert ig_client.titles_calls == 2
    assert ig_client.read_row_calls == 2


def test_ensure_schema_invalidates_layout_cache() -> None:
    from fakes import FakeSheetsClient

    client = FakeSheetsClient({"IG Leads": [["leadId", "username"]]})
    store = SheetStore(client, tab_names={"ig_leads": "IG Leads"})
    store.get_layout("ig_leads")  # caches the 2-column layout
    store.ensure_schema("ig_leads", create_missing=False, extend_headers=True)
    assert "status" in store.get_layout("ig_leads").headers
