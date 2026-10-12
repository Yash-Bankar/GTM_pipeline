from __future__ import annotations

import pytest

from app.sheets.models import DedupLead, EnrichedLead, Lead, OutreachEntry
from app.sheets.schemas import (
    DEDUP_HEADERS,
    ENRICHED_HEADERS,
    IG_LEADS_HEADERS,
    OUTREACH_HEADERS,
    SCHEMAS,
    normalize_username,
    scrape_headers,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@Foo", "foo"),
        ("  Foo  ", "foo"),
        ("instagram.com/Bar/", "bar"),
        ("https://instagram.com/baz/?hl=en", "baz"),
        ("https://www.instagram.com/Qux#x", "qux"),
        ("Foo.Bar", "foo.bar"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_username(raw: str | None, expected: str) -> None:
    assert normalize_username(raw) == expected


def test_scrape_headers_shape() -> None:
    headers = scrape_headers(5)
    assert headers[:4] == ["scrape1Url", "scrape1Title", "scrape1Text", "scrape1Links"]
    assert headers[-1] == "scrape5Links"
    assert len(headers) == 20


@pytest.mark.parametrize(
    "schema",
    list(SCHEMAS.values()),
    ids=list(SCHEMAS.keys()),
)
def test_schema_headers_are_unique_and_include_key(schema) -> None:
    assert len(schema.headers) == len(set(schema.headers))
    assert schema.key_header in schema.headers
    assert schema.headers[0] == schema.key_header


@pytest.mark.parametrize(
    "headers",
    [IG_LEADS_HEADERS, DEDUP_HEADERS, ENRICHED_HEADERS, OUTREACH_HEADERS],
)
def test_no_blank_headers(headers: tuple[str, ...]) -> None:
    assert all(header.strip() for header in headers)


def test_enriched_headers_include_evidence_slots() -> None:
    for header in scrape_headers(5):
        assert header in ENRICHED_HEADERS


@pytest.mark.parametrize(
    "model, headers",
    [
        (Lead, IG_LEADS_HEADERS),
        (DedupLead, DEDUP_HEADERS),
        (OutreachEntry, OUTREACH_HEADERS),
    ],
)
def test_model_aliases_are_a_subset_of_schema_headers(model, headers) -> None:
    aliases = {field.alias or name for name, field in model.model_fields.items()}
    assert aliases <= set(headers)


def test_model_roundtrip_uses_header_aliases() -> None:
    lead = Lead.model_validate({"leadId": "ld_1", "username": "a", "followerCount": "12"})
    dumped = lead.model_dump(by_alias=True)
    assert dumped["leadId"] == "ld_1"
    assert dumped["followerCount"] == 12


def test_enriched_keeps_unknown_evidence_columns() -> None:
    row = {
        "leadId": "ld_1",
        "username": "a",
        "scrape1Url": "https://example.com",
        "scrape1Text": "hello",
    }
    model = EnrichedLead.model_validate(row)
    dumped = model.model_dump(by_alias=True)
    assert dumped["scrape1Url"] == "https://example.com"
    assert dumped["scrape1Text"] == "hello"
