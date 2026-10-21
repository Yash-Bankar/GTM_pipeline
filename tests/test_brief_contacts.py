"""V2-04: non-AI creator brief and incidental public contacts.

Proves the brief renders from raw evidence without AI, and that emails/phones
found by the website crawler are stored with provenance and visible immediately.
"""

from __future__ import annotations

from app.config import get_settings
from app.db.repository import Repository
from app.db.schemas import Contact
from app.db.util import contact_id
from app.worker.pipeline import WebsiteEnrichStage
from fakes import FakeCrawler, make_fetched_page


def _snapshot(**overrides):
    base = {
        "display_name": "Brief Creator",
        "is_verified": True,
        "bio": "Finance educator. hi@brief.org",
        "external_urls": ["https://brief.example/"],
        "followers": {"value": 12300, "display": "12.3K", "precision": "approximate"},
        "following": {"value": 100, "display": "100", "precision": "exact"},
        "post_count": {"value": 42, "display": "42", "precision": "exact"},
        "source_url": "https://www.instagram.com/brief.creator/",
        "captured_at": "2026-10-19T04:50:00Z",
        "parser_version": "1",
        "missing_fields": [],
    }
    base.update(overrides)
    return base


def _create_snapshot_lead(api_client, username: str) -> str:
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": username,
            "source": "extension",
            "request_id": f"v204-{username}",
            "profile_snapshot": _snapshot(),
        },
    )
    assert response.status_code == 201
    return response.json()["lead"]["lead_id"]


def test_brief_renders_without_ai(api_client, repo: Repository, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("AI_ENABLED", "false")
    get_settings.cache_clear()
    try:
        lead_id = _create_snapshot_lead(api_client, "brief.noai")
        repo.update_lead(
            lead_id,
            {"business_category_name": "Education", "external_url": "https://brief.example/"},
        )

        response = api_client.get(f"/api/v1/leads/{lead_id}/brief")

        assert response.status_code == 200
        brief = response.json()
        assert brief["username"] == "brief.noai"
        assert brief["bio"] == "Finance educator. hi@brief.org"
        assert brief["category"] == "Education"
        assert brief["follower_display"] == "12.3K"
        assert brief["follower_precision"] == "approximate"
        assert brief["observed_topics"] == ["Education"]
        assert brief["has_dossier"] is False
        assert brief["ai_status"] == "not_generated"
        assert any(site["url"] == "https://brief.example/" for site in brief["websites"])
        # No dossier/AI artifact was created just by reading the brief.
        assert repo.get_dossier(lead_id) is None
    finally:
        get_settings.cache_clear()


def test_incidental_contacts_are_extracted_with_provenance(api_client, repo: Repository) -> None:
    lead = repo.create_or_get_lead("contacts.creator")[1]
    repo.update_lead(
        lead.lead_id,
        {
            "external_url": "https://site.example/contact",
            "all_external_urls": "https://site.example/contact",
        },
    )
    repo.enqueue("website_enrich", lead.lead_id, lead.username, lead.username_normalized)
    job = repo.claim_next(worker_id="w1")

    crawler = FakeCrawler(
        pages=[
            make_fetched_page(
                "https://site.example/contact",
                emails=["hello@site.example"],
                phones=["+1 (415) 555-0199"],
            )
        ]
    )
    outcome = WebsiteEnrichStage(crawler).run(job, repo)

    assert outcome.ok is True
    contacts = repo.list_contacts(lead.lead_id)
    by_type = {contact.type: contact for contact in contacts}
    assert set(by_type) == {"email", "phone"}
    email = by_type["email"]
    assert email.value == "hello@site.example"
    assert email.method == "website_crawl"
    assert email.source_url == "https://site.example/contact"
    assert email.observed_at
    assert email.validation_state == "unverified"
    assert by_type["phone"].value == "+1 (415) 555-0199"

    # Visible immediately to the authenticated dashboard, with no shortlist gate.
    listing = api_client.get(f"/api/v1/leads/{lead.lead_id}/contacts")
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert all(item["provenance"] == "Public website" for item in listing.json()["items"])

    detail = api_client.get(f"/api/v1/leads/{lead.lead_id}/detail").json()
    assert len(detail["contacts"]) == 2
    assert detail["lead"]["fit_status"] == "not_reviewed"


def test_incidental_contacts_are_deduped_on_recrawl(api_client, repo: Repository) -> None:
    lead = repo.create_or_get_lead("contacts.recrawl")[1]
    repo.update_lead(lead.lead_id, {"external_url": "https://site.example/"})
    crawler = FakeCrawler(
        pages=[make_fetched_page("https://site.example/", emails=["hi@site.example"])]
    )

    for _ in range(2):
        repo.enqueue(
            "website_enrich",
            lead.lead_id,
            lead.username,
            lead.username_normalized,
            on_duplicate="reenqueue",
        )
        job = repo.claim_next(worker_id="w1")
        outcome = WebsiteEnrichStage(crawler).run(job, repo)
        assert outcome.ok is True
        repo.complete(job, outcome.result)

    contacts = repo.list_contacts(lead.lead_id)
    assert len(contacts) == 1
    assert contacts[0].value == "hi@site.example"


def test_legacy_contacts_are_labeled_source_unknown(api_client, repo: Repository) -> None:
    lead = repo.create_or_get_lead("legacy.contacts")[1]
    repo.update_lead(
        lead.lead_id,
        {"business_email": "old@legacy.example", "business_phone_number": "+44 20 7946 0958"},
    )
    for kind, value in (
        ("email", "old@legacy.example"),
        ("phone", "+44 20 7946 0958"),
    ):
        repo.upsert_contact(
            Contact(
                contact_id=contact_id(lead.lead_id, kind, value, ""),
                lead_id=lead.lead_id,
                type=kind,
                value=value,
                source_url="",
                observed_at="2026-10-01T00:00:00Z",
                method="legacy",
                validation_state="unverified",
            )
        )

    response = api_client.get(f"/api/v1/leads/{lead.lead_id}/contacts")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert all(item["provenance"] == "Legacy source unknown" for item in items)
    assert all(item["source_url"] == "" for item in items)
    # The legacy structured fields remain available.
    lead_payload = api_client.get(f"/api/v1/leads/{lead.lead_id}").json()
    assert lead_payload["business_email"] == "old@legacy.example"


def test_brief_includes_contacts_and_websites(api_client, repo: Repository) -> None:
    lead = repo.create_or_get_lead("brief.contacts")[1]
    repo.update_lead(
        lead.lead_id,
        {"external_url": "https://site.example/", "all_external_urls": "https://site.example/"},
    )
    crawler = FakeCrawler(
        pages=[make_fetched_page("https://site.example/", emails=["found@site.example"])]
    )
    repo.enqueue("website_enrich", lead.lead_id, lead.username, lead.username_normalized)
    job = repo.claim_next(worker_id="w1")
    WebsiteEnrichStage(crawler).run(job, repo)

    brief = api_client.get(f"/api/v1/leads/{lead.lead_id}/brief").json()

    assert brief["has_dossier"] is False
    assert [contact["value"] for contact in brief["contacts"]] == ["found@site.example"]
    assert any(site["url"].startswith("https://site.example/") for site in brief["websites"])


def test_phone_extraction_ignores_dates() -> None:
    from app.providers.emails import extract_phones

    assert extract_phones("posted 2026-10-19") == []
    assert extract_phones("call +1 (415) 555-0199") == ["+1 (415) 555-0199"]
