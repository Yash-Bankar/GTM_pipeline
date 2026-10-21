"""V2-08: saved creator views and the review workspace contract.

Covers the PRD 6.2 saved views and the QA scenarios behind V29/V30:

* the default "To review" view shows Not reviewed plus shortlisters with
  Review needed, and **excludes** Rejected;
* the other views (All creators, Research more, Shortlisted, Rejected,
  Needs attention) select the right rows;
* counters are labelled per view, not a single additive funnel;
* an unknown view falls back to the default instead of erroring.
"""

from __future__ import annotations

from app.db.repository import Repository
from app.leads.service import LeadService
from app.leads.views import (
    DEFAULT_VIEW,
    SAVED_VIEWS,
    VIEW_LABELS,
    matches_view,
    normalize_view,
    view_counts,
)


def _seed(repo: Repository, username: str, *, fit: str, currency: str = "current") -> str:
    _created, lead = repo.create_or_get_lead(username)
    repo.update_lead(
        lead.lead_id,
        {"fit_status": fit, "decision_currency": currency},
    )
    return lead.lead_id


def test_default_view_is_to_review() -> None:
    assert DEFAULT_VIEW == "to_review"
    assert normalize_view(None) == "to_review"
    assert normalize_view("") == "to_review"
    assert normalize_view("nonsense") == "to_review"
    assert normalize_view("all") == "all"
    assert SAVED_VIEWS[0] == "to_review"


def test_every_view_has_a_label() -> None:
    for view in SAVED_VIEWS:
        assert VIEW_LABELS[view]
    # The PRD names these five plus the default.
    assert set(SAVED_VIEWS) == {
        "to_review",
        "all",
        "research_more",
        "shortlisted",
        "rejected",
        "attention",
    }


def test_to_review_includes_not_reviewed_and_review_needed(
    repo: Repository,
) -> None:
    service = LeadService(repo)
    _seed(repo, "view.unreviewed", fit="not_reviewed")
    _seed(repo, "view.reviewneeded", fit="shortlisted", currency="review_needed")

    rows, total = service.list(limit=50, offset=0)

    usernames = {lead.username for lead, _p, _r in rows}
    assert total == 2
    assert "view.unreviewed" in usernames
    assert "view.reviewneeded" in usernames


def test_to_review_excludes_rejected(repo: Repository) -> None:
    service = LeadService(repo)
    _seed(repo, "view.rejected", fit="rejected")
    _seed(repo, "view.ok", fit="not_reviewed")

    rows, total = service.list(limit=50, offset=0)

    usernames = {lead.username for lead, _p, _r in rows}
    assert "view.rejected" not in usernames
    assert total == 1


def test_each_view_selects_the_right_rows(repo: Repository) -> None:
    service = LeadService(repo)
    _seed(repo, "v.all.unreviewed", fit="not_reviewed")
    _seed(repo, "v.all.research", fit="research_more")
    _seed(repo, "v.all.shortlisted", fit="shortlisted")
    _seed(repo, "v.all.rejected", fit="rejected")

    def usernames(view: str) -> set[str]:
        rows, _total = service.list(limit=50, offset=0, view=view)
        return {lead.username for lead, _p, _r in rows}

    assert usernames("all") == {
        "v.all.unreviewed",
        "v.all.research",
        "v.all.shortlisted",
        "v.all.rejected",
    }
    assert usernames("research_more") == {"v.all.research"}
    assert usernames("shortlisted") == {"v.all.shortlisted"}
    assert usernames("rejected") == {"v.all.rejected"}


def test_view_counts_are_labelled_not_additive(repo: Repository) -> None:
    service = LeadService(repo)
    _seed(repo, "c.notreviewed", fit="not_reviewed")
    _seed(repo, "c.rejected", fit="rejected")

    counts = service.saved_view_counts()

    assert counts["to_review"] == 1
    assert counts["all"] == 2
    assert counts["rejected"] == 1
    # A creator can sit in an operational view *and* a decision view, so the
    # counters are not a single additive funnel.
    assert sum(counts.values()) >= counts["all"]


def test_matches_view_is_pure(repo: Repository) -> None:
    _created, lead = repo.create_or_get_lead("pure.lead")
    assert matches_view(lead, "complete", "all") is True
    assert matches_view(lead, "complete", "to_review") is True
    # Blocked system work belongs to the "attention" view only.
    assert matches_view(lead, "blocked", "attention") is True
    assert matches_view(lead, "complete", "attention") is False


def test_review_order_is_oldest_unreviewed_first(repo: Repository) -> None:
    service = LeadService(repo)
    first = _seed(repo, "order.first", fit="not_reviewed")
    second = _seed(repo, "order.second", fit="not_reviewed")
    repo.update_lead(first, {"created_at": "2026-01-01T00:00:00+00:00"})
    repo.update_lead(second, {"created_at": "2026-06-01T00:00:00+00:00"})

    rows, _total = service.list(limit=50, offset=0, view="to_review")

    assert [lead.username for lead, _p, _r in rows] == ["order.first", "order.second"]


def test_contact_indicator_is_reported_per_lead(repo: Repository) -> None:
    from app.db.schemas import Contact
    from app.db.util import contact_id

    service = LeadService(repo)
    lead_id = _seed(repo, "contact.lead", fit="not_reviewed")
    repo.upsert_contact(
        Contact(
            contact_id=contact_id(lead_id, "email", "a@b.test", "https://x.test"),
            lead_id=lead_id,
            type="email",
            value="a@b.test",
            source_url="https://x.test",
            observed_at="2026-01-01T00:00:00+00:00",
            method="manual",
            validation_state="unverified",
        )
    )

    types = service.contact_types_by_lead()

    assert types[lead_id] == {"email"}
