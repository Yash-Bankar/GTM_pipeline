"""Error types for the Google Sheets storage layer."""

from __future__ import annotations


class SheetsError(RuntimeError):
    """Base class for all Google Sheets storage errors."""


class SheetsConfigError(SheetsError):
    """Missing or invalid configuration (spreadsheet id, credentials, ...)."""


class SheetsAuthError(SheetsError):
    """Authentication failed (HTTP 401)."""


class SheetsPermissionError(SheetsError):
    """The service account lacks access (HTTP 403, not quota related)."""


class SheetsQuotaError(SheetsError):
    """Quota or rate limit exceeded (HTTP 429, or 403 quota errors)."""


class SheetsNetworkError(SheetsError):
    """Transport-level failure (timeout, DNS, connection reset)."""


class SheetsNotFoundError(SheetsError):
    """The spreadsheet, tab, or range was not found (HTTP 404)."""


class SheetTabMissingError(SheetsNotFoundError):
    """A configured tab does not exist in the spreadsheet."""


class SchemaError(SheetsError):
    """A tab is missing required headers or has no usable header row."""


class DuplicateLeadError(SheetsError):
    """A lead with the same normalized username already exists."""


class SheetsApiError(SheetsError):
    """Any other non-retryable Google Sheets API error."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status
