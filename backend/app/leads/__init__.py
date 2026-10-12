"""Lead capture API package."""

from __future__ import annotations

from .schemas import (
    LeadCreateRequest,
    LeadListResponse,
    LeadResponse,
    LeadSubmissionResponse,
)
from .service import LeadService, LeadSubmission
from .validation import InvalidLeadInput, ParsedLeadInput, parse_lead_input

__all__ = [
    "InvalidLeadInput",
    "LeadCreateRequest",
    "LeadListResponse",
    "LeadResponse",
    "LeadService",
    "LeadSubmission",
    "LeadSubmissionResponse",
    "ParsedLeadInput",
    "parse_lead_input",
]
