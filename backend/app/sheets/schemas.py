"""Canonical tab schemas and username normalization.

The header row of each tab is the contract. Headers are declared here once and
consumed by the storage layer; models use the same names as aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from .models import DedupLead, EnrichedLead, Lead, OutreachEntry, SheetModel

# Logical schema keys (stable in code, independent of the tab display name).
KEY_IG_LEADS = "ig_leads"
KEY_DEDUP = "deduplicated_leads"
KEY_ENRICHED = "instagram_leads_enriched"
KEY_OUTREACH = "outreach"


def scrape_headers(max_slots: int = 5) -> list[str]:
    """Header names for the website-evidence slots (scrape1..scrapeN)."""
    headers: list[str] = []
    for index in range(1, max_slots + 1):
        headers.extend(
            [
                f"scrape{index}Url",
                f"scrape{index}Title",
                f"scrape{index}Text",
                f"scrape{index}Links",
            ]
        )
    return headers


# --- Canonical header rows -------------------------------------------------

IG_LEADS_HEADERS: tuple[str, ...] = (
    "leadId",
    "username",
    "usernameNormalized",
    "fullName",
    "instagramId",
    "followerCount",
    "followsCount",
    "businessCategoryName",
    "bio",
    "businessEmail",
    "businessPhoneNumber",
    "profileUrl",
    "externalUrl",
    "allExternalUrls",
    "engagementRate",
    "scrapedAt",
    "status",
    "source",
    "createdAt",
    "updatedAt",
    "lastError",
)

DEDUP_HEADERS: tuple[str, ...] = (
    "leadId",
    "username",
    "usernameNormalized",
    "status",
    "reason",
    "sourceLeadId",
    "createdAt",
    "updatedAt",
)

ENRICHED_HEADERS: tuple[str, ...] = (
    "leadId",
    "username",
    "usernameNormalized",
    "fullName",
    "instagramId",
    "followerCount",
    "followsCount",
    "businessCategoryName",
    "bio",
    "businessEmail",
    "businessPhoneNumber",
    "profileUrl",
    "externalUrl",
    "allExternalUrls",
    "engagementRate",
    "profileStatus",
    "websiteStatus",
    "profileScrapedAt",
    "websiteScrapedAt",
    "lastError",
    *scrape_headers(5),
    "createdAt",
    "updatedAt",
)

OUTREACH_HEADERS: tuple[str, ...] = (
    "leadId",
    "username",
    "usernameNormalized",
    "channel",
    "status",
    "subject",
    "body",
    "model",
    "generatedAt",
    "createdAt",
    "updatedAt",
    "lastError",
)


@dataclass(frozen=True)
class SheetSchema:
    """A tab's contract: display name, ordered headers, key column, model."""

    key: str
    default_tab: str
    headers: tuple[str, ...]
    key_header: str
    model: Type[SheetModel]

    def has_header(self, name: str) -> bool:
        return name in self.headers

    def index_of(self, name: str) -> int | None:
        try:
            return self.headers.index(name)
        except ValueError:
            return None


SCHEMAS: dict[str, SheetSchema] = {
    KEY_IG_LEADS: SheetSchema(
        key=KEY_IG_LEADS,
        default_tab="IG Leads",
        headers=IG_LEADS_HEADERS,
        key_header="leadId",
        model=Lead,
    ),
    KEY_DEDUP: SheetSchema(
        key=KEY_DEDUP,
        default_tab="Deduplicated Leads",
        headers=DEDUP_HEADERS,
        key_header="leadId",
        model=DedupLead,
    ),
    KEY_ENRICHED: SheetSchema(
        key=KEY_ENRICHED,
        default_tab="instagram_leads_enriched",
        headers=ENRICHED_HEADERS,
        key_header="leadId",
        model=EnrichedLead,
    ),
    KEY_OUTREACH: SheetSchema(
        key=KEY_OUTREACH,
        default_tab="Outreach",
        headers=OUTREACH_HEADERS,
        key_header="leadId",
        model=OutreachEntry,
    ),
}


def schema_for(key: str) -> SheetSchema:
    return SCHEMAS[key]


def normalize_username(raw: str | None) -> str:
    """Normalize an Instagram username for duplicate checks.

    Lowercases, strips whitespace, removes a leading ``@``, and extracts the
    handle from common URL forms (``instagram.com/<handle>``, optional trailing
    slash, query string or fragment).
    """
    value = (raw or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if "instagram.com/" in lowered:
        value = value.split("instagram.com/", 1)[1]
    value = value.split("?", 1)[0].split("#", 1)[0]
    value = value.strip("/")
    value = value.split("/", 1)[0]
    value = value.lstrip("@")
    return value.strip().lower()
