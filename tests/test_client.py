from __future__ import annotations

import pytest

from app.sheets.client import (
    GoogleSheetsClient,
    _map_http_error,
    cell_range,
    column_letter,
)
from app.sheets.errors import (
    SheetsApiError,
    SheetsAuthError,
    SheetsNotFoundError,
    SheetsPermissionError,
    SheetsQuotaError,
)
from fakes import make_http_error


@pytest.mark.parametrize(
    ("index", "letter"),
    [(0, "A"), (1, "B"), (25, "Z"), (26, "AA"), (27, "AB"), (51, "AZ"), (52, "BA"), (701, "ZZ"), (702, "AAA")],
)
def test_column_letter(index: int, letter: str) -> None:
    assert column_letter(index) == letter


def test_column_letter_rejects_negative() -> None:
    with pytest.raises(ValueError):
        column_letter(-1)


def test_cell_range_quotes_and_escapes_tab() -> None:
    assert cell_range("IG Leads", 2, 3) == "'IG Leads'!D2"
    assert cell_range("O'Brien", 1, 0) == "'O''Brien'!A1"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, SheetsAuthError),
        (403, SheetsPermissionError),
        (404, SheetsNotFoundError),
        (429, SheetsQuotaError),
        (400, SheetsApiError),
    ],
)
def test_map_http_error_types(status: int, expected: type[Exception]) -> None:
    assert isinstance(_map_http_error(make_http_error(status)), expected)


def test_map_http_error_quota_403() -> None:
    assert isinstance(_map_http_error(make_http_error(403, "quota exceeded")), SheetsQuotaError)


class _Request:
    def __init__(self, result: object) -> None:
        self._result = result

    def execute(self) -> object:
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


class _ValuesResource:
    def __init__(self, sequence: list[object]) -> None:
        self._sequence = sequence
        self._index = 0

    def get(self, **_kwargs: object) -> _Request:
        item = self._sequence[self._index]
        self._index += 1
        return _Request(item)


class _SpreadsheetsResource:
    def __init__(self, values: _ValuesResource) -> None:
        self._values = values

    def values(self) -> _ValuesResource:
        return self._values


class _FakeService:
    def __init__(self, values: _ValuesResource) -> None:
        self._values = values

    def spreadsheets(self) -> _SpreadsheetsResource:
        return _SpreadsheetsResource(self._values)


def test_client_retries_transient_then_succeeds() -> None:
    service = _FakeService(_ValuesResource([make_http_error(503), {"values": [["header"]]}]))
    client = GoogleSheetsClient(
        service, "spreadsheet-id", max_attempts=3, backoff_base=0, sleeper=lambda _: None
    )
    assert client.read_tab("IG Leads") == [["header"]]


def test_client_raises_mapped_error_without_retry() -> None:
    service = _FakeService(_ValuesResource([make_http_error(404)]))
    client = GoogleSheetsClient(
        service, "spreadsheet-id", max_attempts=3, backoff_base=0, sleeper=lambda _: None
    )
    with pytest.raises(SheetsNotFoundError):
        client.read_tab("IG Leads")


def test_client_requires_spreadsheet_id() -> None:
    with pytest.raises(Exception):
        GoogleSheetsClient(_FakeService(_ValuesResource([])), "  ")
