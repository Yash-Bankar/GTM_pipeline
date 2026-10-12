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


def make_profile(username: str = "creator", **overrides: object):
    """Build a normalized HikerProfile for tests."""
    from app.providers.models import HikerProfile

    data: dict[str, object] = {
        "username": username,
        "instagram_id": "123",
        "full_name": "A Creator",
        "biography": "finance educator hi@creator.example.org",
        "follower_count": 5000,
        "following_count": 120,
        "media_count": 42,
        "external_url": "https://example.org",
        "bio_links": ["https://example.org"],
        "emails": ["hi@creator.example.org"],
        "phone": "",
        "category": "Education",
        "is_private": False,
        "is_verified": False,
        "is_business": True,
    }
    data.update(overrides)
    return HikerProfile(**data)


class FakeHikerClient:
    """Stand-in for HikerAPIClient: ``handler(username)`` returns a profile or raises."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls = 0

    def fetch_profile(self, username: str):
        self.calls += 1
        return self._handler(username)


def make_post(post_id: str = "1001", **overrides: object):
    """Build a normalized HikerPost for tests."""
    from app.providers.models import HikerPost

    data: dict[str, object] = {
        "post_id": post_id,
        "short_code": f"SC{post_id}",
        "media_type": "2",
        "product_type": "clips",
        "caption": "hello world",
        "like_count": 10,
        "comment_count": 2,
        "play_count": 100,
        "taken_at": "1700000000",
        "url": f"https://www.instagram.com/p/SC{post_id}/",
    }
    data.update(overrides)
    return HikerPost(**data)


def make_fetched_page(url: str, *, status: str = "done", **overrides: object):
    """Build a FetchedPage for tests."""
    from app.providers.website import FetchedPage

    data: dict[str, object] = {
        "url": url,
        "resolved_url": url,
        "domain": "example.org",
        "title": "Example",
        "text": "contact us hello@example.org",
        "links": [],
        "emails": ["hello@example.org"],
        "http_status": 200 if status == "done" else 0,
        "status": status,
        "error": "" if status == "done" else f"{status} reason",
    }
    data.update(overrides)
    return FetchedPage(**data)


class FakeMediaClient:
    """Stand-in for a media fetcher."""

    def __init__(self, posts=None, error: BaseException | None = None) -> None:
        self._posts = list(posts or [])
        self._error = error
        self.calls = 0

    def fetch_recent_posts(self, user_id: str, *, limit: int, max_pages: int):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._posts[:limit]


class FakeCrawler:
    """Stand-in for WebsiteCrawler."""

    def __init__(self, pages=None, emails=None) -> None:
        self._pages = list(pages or [])
        self._emails = list(emails or [])
        self.calls = 0

    def crawl(self, start_urls):
        self.calls += 1
        return list(self._pages), list(self._emails)


class RecordingStage:
    """A trivial stage that records jobs and returns a configured outcome."""

    def __init__(self, name: str, outcome_factory=None) -> None:
        self.name = name
        self.ran: list[str] = []
        self._outcome_factory = outcome_factory or (lambda job: None)

    def run(self, job):
        from app.worker.pipeline import StageOutcome

        self.ran.append(job.job_id)
        outcome = self._outcome_factory(job)
        return outcome if outcome is not None else StageOutcome(ok=True, result="ok")




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

