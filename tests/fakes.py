"""In-memory fake implementing the SheetsClient interface.

Used by unit tests as the "mocked Google Sheets client" so the storage layer can
be exercised without network access or credentials.
"""

from __future__ import annotations

from googleapiclient.errors import HttpError
from httplib2 import Response

from app.sheets.client import SheetsClient
from app.sheets.errors import SheetsApiError


def make_http_error(status: int, message: str = "error") -> HttpError:
    """Build a real googleapiclient HttpError with the given status code."""
    return HttpError(Response({"status": status}), message.encode("utf-8"))



class FakeSheetsClient(SheetsClient):
    def __init__(self, tabs: dict[str, list[list[str]]] | None = None) -> None:
        self.tabs: dict[str, list[list[str]]] = {}
        for name, rows in (tabs or {}).items():
            self.tabs[name] = [list(row) for row in rows]
        self.append_calls = 0
        self.update_calls = 0
        self.created_tabs: list[str] = []

    def _require(self, tab: str) -> None:
        if tab not in self.tabs:
            raise SheetsApiError(f"tab not found: {tab}")

    def list_tab_titles(self) -> list[str]:
        return list(self.tabs.keys())

    def read_tab(self, tab: str) -> list[list[str]]:
        self._require(tab)
        return [list(row) for row in self.tabs[tab]]

    def read_tabs(self, tabs: list[str]) -> dict[str, list[list[str]]]:
        return {tab: self.read_tab(tab) for tab in tabs}

    def read_row(self, tab: str, row_number: int) -> list[str]:
        self._require(tab)
        rows = self.tabs[tab]
        if 1 <= row_number <= len(rows):
            return list(rows[row_number - 1])
        return []

    def append_rows(self, tab: str, rows: list[list[str]]) -> None:
        self._require(tab)
        self.append_calls += 1
        self.tabs[tab].extend([list(row) for row in rows])

    def update_cells(self, tab: str, updates: list[tuple[int, int, str]]) -> None:
        self._require(tab)
        self.update_calls += 1
        rows = self.tabs[tab]
        for row_number, column, value in updates:
            while len(rows) < row_number:
                rows.append([])
            row = rows[row_number - 1]
            while len(row) <= column:
                row.append("")
            row[column] = value

    def create_tab(self, title: str) -> None:
        if title in self.tabs:
            raise SheetsApiError(f"tab already exists: {title}")
        self.tabs[title] = []
        self.created_tabs.append(title)


class RaisingSheetsClient(SheetsClient):
    """A client whose every call raises a configured exception.

    Used to verify that storage failures surface as clear HTTP responses.
    """

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def _raise(self) -> None:
        raise self._exc

    def list_tab_titles(self) -> list[str]:
        self._raise()

    def read_tab(self, tab: str) -> list[list[str]]:
        self._raise()

    def read_tabs(self, tabs: list[str]) -> dict[str, list[list[str]]]:
        self._raise()

    def read_row(self, tab: str, row_number: int) -> list[str]:
        self._raise()

    def append_rows(self, tab: str, rows: list[list[str]]) -> None:
        self._raise()

    def update_cells(self, tab: str, updates: list[tuple[int, int, str]]) -> None:
        self._raise()

    def create_tab(self, title: str) -> None:
        self._raise()

