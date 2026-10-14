"""Test doubles for providers and worker stages (database layer uses SQLite)."""

from __future__ import annotations


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


class FakeHikerClient:
    """Stand-in for HikerAPIClient: ``handler(username)`` returns a profile or raises."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls = 0

    def fetch_profile(self, username: str):
        self.calls += 1
        return self._handler(username)


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


class FakeAIProvider:
    """Stand-in for an AIProvider; returns configured schema instances or raises."""

    def __init__(self, *, dossier=None, outreach=None, error: BaseException | None = None) -> None:
        self._dossier = dossier
        self._outreach = outreach
        self._error = error
        self.calls = 0
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def generate_structured(self, *, prompt: str, system: str, schema):
        self.calls += 1
        self.prompts.append(prompt)
        self.systems.append(system)
        if self._error is not None:
            raise self._error
        if schema.__name__ == "DossierDraft":
            return self._dossier if self._dossier is not None else schema()
        if schema.__name__ == "OutreachDraft":
            return self._outreach if self._outreach is not None else schema()
        return schema()


class RecordingStage:
    """A trivial stage that records jobs and returns a configured outcome."""

    def __init__(self, name: str, outcome_factory=None) -> None:
        self.name = name
        self.ran: list[str] = []
        self._outcome_factory = outcome_factory or (lambda job: None)

    def run(self, job, repo=None):
        from app.worker.pipeline import StageOutcome

        self.ran.append(job.job_id)
        outcome = self._outcome_factory(job)
        return outcome if outcome is not None else StageOutcome(ok=True, result="ok")
