"""Google Sheets storage layer (source of truth for the MVP).

Public API::

    from app.sheets import LeadStore, SheetStore, normalize_username

    store = LeadStore.from_settings(get_settings())
    lead = store.create_lead("some.creator", source="chrome-extension")

No database is used: all operational state lives in Google Sheets.
"""

from __future__ import annotations

from .client import GoogleSheetsClient, SheetsClient, build_sheets_service, column_letter
from .errors import (
    DuplicateLeadError,
    SchemaError,
    SheetTabMissingError,
    SheetsApiError,
    SheetsAuthError,
    SheetsConfigError,
    SheetsError,
    SheetsNetworkError,
    SheetsNotFoundError,
    SheetsPermissionError,
    SheetsQuotaError,
)
from .models import DedupLead, EnrichedLead, Lead, OutreachEntry, PipelineJob, SheetModel
from .repository import (
    JobStore,
    LeadStore,
    RowRecord,
    SchemaReport,
    SheetStore,
    TabLayout,
    tab_names_from_settings,
)
from .schemas import (
    DEDUP_HEADERS,
    ENRICHED_HEADERS,
    IG_LEADS_HEADERS,
    KEY_DEDUP,
    KEY_ENRICHED,
    KEY_IG_LEADS,
    KEY_JOBS,
    KEY_OUTREACH,
    OUTREACH_HEADERS,
    PIPELINE_JOBS_HEADERS,
    SCHEMAS,
    SheetSchema,
    normalize_username,
    scrape_headers,
)
from .util import new_job_id, new_lead_id, stringify, utc_now_iso

__all__ = [
    "DEDUP_HEADERS",
    "DedupLead",
    "DuplicateLeadError",
    "ENRICHED_HEADERS",
    "EnrichedLead",
    "GoogleSheetsClient",
    "IG_LEADS_HEADERS",
    "JobStore",
    "KEY_DEDUP",
    "KEY_ENRICHED",
    "KEY_IG_LEADS",
    "KEY_JOBS",
    "KEY_OUTREACH",
    "Lead",
    "LeadStore",
    "OUTREACH_HEADERS",
    "OutreachEntry",
    "PIPELINE_JOBS_HEADERS",
    "PipelineJob",
    "RowRecord",
    "SCHEMAS",
    "SchemaError",
    "SchemaReport",
    "SheetModel",
    "SheetSchema",
    "SheetStore",
    "SheetTabMissingError",
    "SheetsApiError",
    "SheetsAuthError",
    "SheetsClient",
    "SheetsConfigError",
    "SheetsError",
    "SheetsNetworkError",
    "SheetsNotFoundError",
    "SheetsPermissionError",
    "SheetsQuotaError",
    "TabLayout",
    "build_sheets_service",
    "column_letter",
    "new_job_id",
    "new_lead_id",
    "normalize_username",
    "scrape_headers",
    "stringify",
    "tab_names_from_settings",
    "utc_now_iso",
]
