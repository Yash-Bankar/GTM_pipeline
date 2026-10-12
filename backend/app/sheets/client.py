"""Google Sheets client.

Two layers:

* ``SheetsClient`` - a narrow, storage-oriented interface (tabs, rows, cells).
  The repository depends on this, so tests can substitute a mock/fake.
* ``GoogleSheetsClient`` - the real implementation on top of the Google Sheets
  v4 API, adding request timeouts, batch calls and exponential backoff.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

import httplib2
from google.oauth2 import service_account
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import Settings

from .errors import (
    SheetsApiError,
    SheetsAuthError,
    SheetsConfigError,
    SheetsNetworkError,
    SheetsNotFoundError,
    SheetsPermissionError,
    SheetsQuotaError,
)
from .retry import TRANSPORT_ERRORS, call_with_retry, http_status, is_retryable

logger = logging.getLogger(__name__)

SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


def column_letter(index: int) -> str:
    """Convert a 0-based column index to an A1 column letter (0 -> A)."""
    if index < 0:
        raise ValueError("column index must be >= 0")
    letters = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _quote_tab(tab: str) -> str:
    return "'" + tab.replace("'", "''") + "'"


def _tab_range(tab: str) -> str:
    return _quote_tab(tab)


def cell_range(tab: str, row: int, column: int) -> str:
    """A1 range for a single cell. ``row`` is 1-based, ``column`` is 0-based."""
    return f"{_quote_tab(tab)}!{column_letter(column)}{row}"


class SheetsClient(ABC):
    """Storage-oriented interface over a spreadsheet."""

    @abstractmethod
    def list_tab_titles(self) -> list[str]:
        ...

    @abstractmethod
    def read_tab(self, tab: str) -> list[list[str]]:
        """Return all values of a tab (rows of cells)."""

    @abstractmethod
    def read_tabs(self, tabs: list[str]) -> dict[str, list[list[str]]]:
        """Batch-read several tabs at once."""

    @abstractmethod
    def read_row(self, tab: str, row_number: int) -> list[str]:
        """Return a single row (1-based)."""

    @abstractmethod
    def append_rows(self, tab: str, rows: list[list[str]]) -> None:
        """Append rows after the last row of the tab, inserting rows as needed."""

    @abstractmethod
    def update_cells(self, tab: str, updates: list[tuple[int, int, str]]) -> None:
        """Batch-update cells given as ``(row_1based, column_0based, value)``."""

    @abstractmethod
    def create_tab(self, title: str) -> None:
        """Create a new tab."""


class GoogleSheetsClient(SheetsClient):
    """Concrete Google Sheets v4 client with retries and timeouts."""

    def __init__(
        self,
        service: Any,
        spreadsheet_id: str,
        *,
        max_attempts: int = 5,
        backoff_base: float = 0.5,
        backoff_max: float = 30.0,
        sleeper: Callable[[float], None] | None = None,
        retryable: Callable[[BaseException], bool] = is_retryable,
    ) -> None:
        if not spreadsheet_id.strip():
            raise SheetsConfigError("GOOGLE_SHEETS_SPREADSHEET_ID is not set")
        self._service = service
        self._spreadsheet_id = spreadsheet_id.strip()
        self._max_attempts = max(1, int(max_attempts))
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._retryable = retryable

        import time as _time

        self._sleeper = sleeper or _time.sleep

    # -- construction -------------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Settings) -> "GoogleSheetsClient":
        service = build_sheets_service(settings)
        return cls(
            service,
            settings.google_sheets_spreadsheet_id,
            max_attempts=settings.google_sheets_max_attempts,
            backoff_base=settings.google_sheets_backoff_base_seconds,
            backoff_max=settings.google_sheets_backoff_max_seconds,
        )

    # -- low-level execution ------------------------------------------------

    def _run(self, build_request: Callable[[], Any]) -> Any:
        """Execute an API request, retrying transient failures with backoff."""

        def _attempt() -> Any:
            return build_request().execute()

        def _on_retry(attempt: int, delay: float, exc: BaseException) -> None:
            logger.warning(
                "Google Sheets call failed (attempt %s/%s), retrying in %.2fs: %s",
                attempt,
                self._max_attempts,
                delay,
                type(exc).__name__,
            )

        try:
            return call_with_retry(
                _attempt,
                max_attempts=self._max_attempts,
                backoff_base=self._backoff_base,
                backoff_max=self._backoff_max,
                sleeper=self._sleeper,
                retryable=self._retryable,
                on_retry=_on_retry,
            )
        except HttpError as exc:
            raise _map_http_error(exc) from exc
        except TRANSPORT_ERRORS as exc:
            raise SheetsNetworkError(
                f"Google Sheets request failed: {type(exc).__name__}: {exc}"
            ) from exc

    # -- interface ----------------------------------------------------------

    def list_tab_titles(self) -> list[str]:
        def _request() -> Any:
            return (
                self._service.spreadsheets()
                .get(spreadsheetId=self._spreadsheet_id, fields="sheets.properties.title")
            )

        payload = self._run(_request)
        titles: list[str] = []
        for sheet in payload.get("sheets", []) or []:
            title = (sheet.get("properties") or {}).get("title")
            if title:
                titles.append(title)
        return titles

    def read_tab(self, tab: str) -> list[list[str]]:
        def _request() -> Any:
            return (
                self._service.spreadsheets()
                .values()
                .get(spreadsheetId=self._spreadsheet_id, range=_tab_range(tab))
            )

        payload = self._run(_request)
        return payload.get("values", []) or []

    def read_tabs(self, tabs: list[str]) -> dict[str, list[list[str]]]:
        if not tabs:
            return {}
        ranges = [_tab_range(tab) for tab in tabs]

        def _request() -> Any:
            return (
                self._service.spreadsheets()
                .values()
                .batchGet(spreadsheetId=self._spreadsheet_id, ranges=ranges)
            )

        payload = self._run(_request)
        result: dict[str, list[list[str]]] = {}
        for value_range in payload.get("valueRanges", []) or []:
            raw_range = value_range.get("range", "")
            tab = raw_range.split("!", 1)[0].strip("'").replace("''", "'")
            result[tab] = value_range.get("values", []) or []
        return result

    def read_row(self, tab: str, row_number: int) -> list[str]:
        a1 = f"{_quote_tab(tab)}!{row_number}:{row_number}"

        def _request() -> Any:
            return (
                self._service.spreadsheets()
                .values()
                .get(spreadsheetId=self._spreadsheet_id, range=a1)
            )

        payload = self._run(_request)
        values = payload.get("values", []) or []
        return values[0] if values else []

    def append_rows(self, tab: str, rows: list[list[str]]) -> None:
        if not rows:
            return
        body = {"values": rows}

        def _request() -> Any:
            return (
                self._service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self._spreadsheet_id,
                    range=_tab_range(tab),
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
            )

        self._run(_request)

    def update_cells(self, tab: str, updates: list[tuple[int, int, str]]) -> None:
        if not updates:
            return
        data = [
            {"range": cell_range(tab, row, column), "values": [[value]]}
            for row, column, value in updates
        ]

        def _request() -> Any:
            return (
                self._service.spreadsheets()
                .values()
                .batchUpdate(
                    spreadsheetId=self._spreadsheet_id,
                    body={"valueInputOption": "RAW", "data": data},
                )
            )

        self._run(_request)

    def create_tab(self, title: str) -> None:
        body = {"requests": [{"addSheet": {"properties": {"title": title}}}]}

        def _request() -> Any:
            return self._service.spreadsheets().batchUpdate(
                spreadsheetId=self._spreadsheet_id, body=body
            )

        self._run(_request)


def _map_http_error(exc: HttpError) -> Exception:
    """Translate a Google HttpError into a typed storage error."""
    status = http_status(exc)
    message = str(exc)
    preview = message.replace("\n", " ").strip()[:300]
    lowered = message.lower()

    if status == 401:
        return SheetsAuthError("Google Sheets authentication failed (401).")
    if status == 403:
        if any(marker in lowered for marker in ("quota", "rate limit", "userratelimitexceeded")):
            return SheetsQuotaError("Google Sheets quota/rate limit exceeded (403).")
        return SheetsPermissionError(
            "Access denied by Google Sheets (403). Share the spreadsheet with the service account."
        )
    if status == 404:
        return SheetsNotFoundError(
            "Google Sheets resource not found (404). Check the spreadsheet id and tab names."
        )
    if status == 429:
        return SheetsQuotaError("Google Sheets quota/rate limit exceeded (429).")
    return SheetsApiError(
        f"Google Sheets API error {status or '?'}: {preview}", status=status or None
    )


def build_sheets_service(settings: Settings) -> Any:
    """Build an authorized Sheets v4 service from server-side credentials.

    Credentials come from a service account JSON file referenced by
    ``GOOGLE_APPLICATION_CREDENTIALS``. The file's contents are never logged.
    """
    credentials_path = settings.credentials_path()
    if credentials_path is None:
        raise SheetsConfigError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set (path to a service account JSON)."
        )
    if not credentials_path.exists():
        raise SheetsConfigError(
            f"Service account credentials file not found at '{credentials_path}'."
        )

    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=list(SHEETS_SCOPES)
    )
    http = AuthorizedHttp(
        credentials,
        http=httplib2.Http(timeout=settings.google_sheets_request_timeout_seconds),
    )
    return build("sheets", "v4", http=http, cache_discovery=False)
