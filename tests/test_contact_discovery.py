"""V2-06: explicit contact discovery, idempotency, revocation, manual fallback.

Covers QA scenarios V17, V18, V19, and V20.
"""

from __future__ import annotations

from app.db.repository import Repository
from app.worker.pipeline import ContactDiscoveryStage
from fakes import FakeCrawler, make_fetched_page


def _snapshot(**overrides):
    base = {
        "display_name": "Discovery Creator",
        "is_verified": True,
        "bio": "Finance educator.",
        "external_urls": ["https://site.example/"],
        "followers": {"value": 2000, "display": "2K", "precision": "approximate"},
        "following": None,
        "post_count": None,
        "source_url": "https://www.instagram.com/discovery.creator/",
        "captured_at": "2026-10-19T04:50:00Z",
        "parser_version": "1",
        "missing_fields": ["following", "post_count"],
    }
    base.update(overrides)
    return base


def _shortlisted_lead(api_client, username: str = "discovery.creator") -> str:
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": username,
            "source": "extension",
            "request_id": f"v206-{username}",
            "profile_snapshot": _snapshot(),
        },
    )
    assert response.status_code == 201
    lead_id = response.json()["lead"]["lead_id"]
    fit = api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": "shortlist", "note": "Pursue"}
    )
    assert fit.status_code == 200
    assert fit.json()["fit_status"] == "shortlisted"
    return lead_id


def _request_contact(api_client, lead_id: str, **body):
    return api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json=body)


def _run(lead_id: str, repo: Repository, crawler) -> None:
    job = repo.find_job("contact_discovery", lead_id)
    assert job is not None
    outcome = ContactDiscoveryStage(crawler).run(job, repo)
    assert outcome.ok is True


# -- V17: gates ------------------------------------------------------------


def test_v17_contact_request_requires_current_shortlist(api_client, repo: Repository) -> None:
    lead_id = _shortlisted_lead(api_client, "v17.creator")

    repo.update_lead(lead_id, {"decision_currency": "review_needed"})
    stale = _request_contact(api_client, lead_id)
    assert stale.status_code == 403
    assert stale.json()["detail"]["decision_currency"] == "review_needed"

    repo.update_lead(lead_id, {"fit_status": "rejected"})
    rejected = _request_contact(api_client, lead_id)
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["fit_status"] == "rejected"


# -- V18: idempotency ------------------------------------------------------


def test_v18_repeated_click_reuses_the_existing_request(api_client, repo: Repository) -> None:
    lead_id = _shortlisted_lead(api_client, "v18.creator")

    first = _request_contact(api_client, lead_id)
    second = _request_contact(api_client, lead_id)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["request_id"] == second.json()["request_id"]
    assert first.json()["status"] == "queued"
    assert len(repo.list_contact_requests(lead_id)) == 1
    jobs = [
        job
        for job in repo.list_jobs(lead_id)
        if job.stage == "contact_discovery"
    ]
    assert len(jobs) == 1


def test_v18_search_again_creates_a_new_attempt(api_client, repo: Repository) -> None:
    lead_id = _shortlisted_lead(api_client, "v18.again")

    first = _request_contact(api_client, lead_id)
    second = _request_contact(api_client, lead_id, search_again=True)

    assert second.status_code == 201
    assert second.json()["request_id"] != first.json()["request_id"]
    assert len(repo.list_contact_requests(lead_id)) == 2
    job = repo.find_job("contact_discovery", lead_id)
    assert job is not None
    assert second.json()["request_id"] in job.payload


# -- V19: found / not found / blocked --------------------------------------


def test_v19_discovery_found_stores_contacts_and_scope(api_client, repo: Repository) -> None:
    lead_id = _shortlisted_lead(api_client, "v19.found")
    request_id = _request_contact(api_client, lead_id).json()["request_id"]
    crawler = FakeCrawler(
        pages=[
            make_fetched_page(
                "https://site.example/contact",
                emails=["hello@site.example"],
                phones=["+1 (415) 555-0199"],
            )
        ]
    )

    _run(lead_id, repo, crawler)

    request = repo.get_contact_request(request_id)
    assert request is not None
    assert request.status == "found"
    assert request.result_count == 2
    assert "searched" in request.searched_scope
    assert request.completed_at
    assert request.error == ""

    contacts = repo.list_contacts(lead_id)
    assert {contact.type for contact in contacts} == {"email", "phone"}
    assert all(contact.method == "contact_discovery" for contact in contacts)
    assert all(contact.source_url == "https://site.example/contact" for contact in contacts)
    assert all(contact.observed_at for contact in contacts)

    listing = api_client.get(f"/api/v1/leads/{lead_id}/contacts").json()
    assert listing["total"] == 2
    detail = api_client.get(f"/api/v1/leads/{lead_id}/detail").json()
    assert detail["contact_request"]["status"] == "found"


def test_v19_discovery_not_found_reports_searched_scope(api_client, repo: Repository) -> None:
    lead_id = _shortlisted_lead(api_client, "v19.none")
    request_id = _request_contact(api_client, lead_id).json()["request_id"]
    crawler = FakeCrawler(
        pages=[
            make_fetched_page(
                "https://site.example/", text="no contacts here", emails=[], phones=[]
            )
        ]
    )

    _run(lead_id, repo, crawler)

    request = repo.get_contact_request(request_id)
    assert request is not None
    assert request.status == "not_found"
    assert request.result_count == 0
    assert "source(s)" in request.searched_scope
    assert request.completed_at
    assert repo.list_contacts(lead_id) == []


def test_v19_discovery_blocked_sources_fail(api_client, repo: Repository) -> None:
    lead_id = _shortlisted_lead(api_client, "v19.blocked")
    request_id = _request_contact(api_client, lead_id).json()["request_id"]
    crawler = FakeCrawler(
        pages=[
            make_fetched_page(
                "https://site.example/", status="blocked", emails=[], phones=[]
            )
        ]
    )

    _run(lead_id, repo, crawler)

    request = repo.get_contact_request(request_id)
    assert request is not None
    assert request.status == "failed"
    assert "blocked" in request.error.lower()
    assert repo.list_contacts(lead_id) == []


# -- V20: revocation -------------------------------------------------------


def test_v20_revocation_before_run_cancels_without_contacts(
    api_client, repo: Repository
) -> None:
    lead_id = _shortlisted_lead(api_client, "v20.before")
    request_id = _request_contact(api_client, lead_id).json()["request_id"]
    repo.update_lead(lead_id, {"fit_status": "rejected"})
    crawler = FakeCrawler(
        pages=[make_fetched_page("https://site.example/", emails=["leak@site.example"])]
    )

    _run(lead_id, repo, crawler)

    request = repo.get_contact_request(request_id)
    assert request is not None
    assert request.status == "cancelled"
    assert "revoked" in request.error.lower()
    assert crawler.calls == 0
    assert repo.list_contacts(lead_id) == []


class _RevokingCrawler:
    def __init__(self, repo: Repository, lead_id: str) -> None:
        self._repo = repo
        self._lead_id = lead_id
        self.calls = 0

    def crawl(self, start_urls):
        self.calls += 1
        self._repo.update_lead(self._lead_id, {"decision_currency": "review_needed"})
        return [
            make_fetched_page("https://site.example/", emails=["leak@site.example"])
        ], []


def test_v20_revocation_during_run_does_not_publish(api_client, repo: Repository) -> None:
    lead_id = _shortlisted_lead(api_client, "v20.during")
    request_id = _request_contact(api_client, lead_id).json()["request_id"]
    crawler = _RevokingCrawler(repo, lead_id)

    _run(lead_id, repo, crawler)

    request = repo.get_contact_request(request_id)
    assert request is not None
    assert request.status == "cancelled"
    assert "during search" in request.error.lower()
    assert crawler.calls == 1
    assert repo.list_contacts(lead_id) == []


# -- Manual fallback -------------------------------------------------------


def test_manual_contact_with_source_is_saved(api_client, repo: Repository) -> None:
    # No fit gate for manual contact entry.
    response = api_client.post(
        "/api/v1/leads",
        json={"username": "manual.creator"},
    )
    lead_id = response.json()["lead"]["lead_id"]

    added = api_client.post(
        f"/api/v1/leads/{lead_id}/contacts",
        json={
            "type": "email",
            "value": "typed@manual.example",
            "source_url": "https://manual.example/contact",
        },
    )

    assert added.status_code == 201
    assert added.json()["value"] == "typed@manual.example"
    assert added.json()["provenance"] == "Public website"
    contacts = repo.list_contacts(lead_id)
    assert len(contacts) == 1
    assert contacts[0].method == "manual"
    assert contacts[0].source_url == "https://manual.example/contact"


def test_manual_contact_requires_valid_source_and_type(api_client) -> None:
    lead_id = api_client.post("/api/v1/leads", json={"username": "manual.invalid"}).json()[
        "lead"
    ]["lead_id"]

    bad_source = api_client.post(
        f"/api/v1/leads/{lead_id}/contacts",
        json={"type": "email", "value": "x@y.example", "source_url": "not-a-url"},
    )
    assert bad_source.status_code == 422

    bad_type = api_client.post(
        f"/api/v1/leads/{lead_id}/contacts",
        json={"type": "carrier_pigeon", "value": "x", "source_url": "https://x.example/"},
    )
    assert bad_type.status_code == 422
