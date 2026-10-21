"""Saved creator views for the review workspace (V2-08).

The Creators page presents **saved views** rather than a single additive
funnel: a creator can appear in an operational view (blocked work) *and* in a
decision view (shortlisted, research more, ...). Counters are therefore
labelled per view, never summed (PRD 6.2).

View semantics:

``to_review`` (default)
    Not reviewed, plus shortlisters whose evidence changed and need a
    reconfirmation. Rejected creators are **excluded**.
``all``
    Every captured creator.
``research_more``
    Operators asked for more research.
``shortlisted``
    Current shortlists, whatever their decision currency.
``rejected``
    Rejected creators, kept for dedupe and history.
``attention``
    Blocked system work that needs a remedy.
"""

from __future__ import annotations

from app import constants
from app.db.schemas import Lead

# The saved views offered by the Creators page, in display order.
SAVED_VIEWS: tuple[str, ...] = (
    "to_review",
    "all",
    "research_more",
    "shortlisted",
    "rejected",
    "attention",
)

DEFAULT_VIEW = "to_review"

# Human labels for the view switcher.
VIEW_LABELS: dict[str, str] = {
    "to_review": "To review",
    "all": "All creators",
    "research_more": "Research more",
    "shortlisted": "Shortlisted",
    "rejected": "Rejected",
    "attention": "Needs attention",
}

# Views that describe operator intent (a decision), as opposed to system work.
DECISION_VIEWS: frozenset[str] = frozenset(
    {"to_review", "research_more", "shortlisted", "rejected"}
)


def normalize_view(view: str | None) -> str:
    """Map a requested view to a known one, falling back to the default."""
    value = (view or "").strip().lower()
    return value if value in SAVED_VIEWS else DEFAULT_VIEW


def matches_view(lead: Lead, progress: str, view: str) -> bool:
    """True when ``lead`` belongs to ``view``."""
    view = normalize_view(view)
    if view == "all":
        return True
    if view == "to_review":
        if lead.fit_status == constants.FIT_STATUS_NOT_REVIEWED:
            return True
        return (
            lead.fit_status == constants.FIT_STATUS_SHORTLISTED
            and lead.decision_currency == constants.DECISION_CURRENCY_REVIEW_NEEDED
        )
    if view == "research_more":
        return lead.fit_status == constants.FIT_STATUS_RESEARCH_MORE
    if view == "shortlisted":
        return lead.fit_status == constants.FIT_STATUS_SHORTLISTED
    if view == "rejected":
        return lead.fit_status == constants.FIT_STATUS_REJECTED
    if view == "attention":
        return (progress or "").lower() == constants.RESEARCH_BLOCKED
    return True


def view_counts(
    rows: list[tuple[Lead, str, str]], contacts: dict[str, set[str]]
) -> dict[str, int]:
    """Count creators per saved view.

    The counts are **labelled per view**, not a single additive funnel: the
    same creator may be counted in "To review" and in "Needs attention".
    """
    counts = {view: 0 for view in SAVED_VIEWS}
    for lead, progress, _remedy in rows:
        for view in SAVED_VIEWS:
            if matches_view(lead, progress, view):
                counts[view] += 1
    return counts


def sort_rows(
    rows: list[tuple[Lead, str, str]], sort: str | None, view: str
) -> list[tuple[Lead, str, str]]:
    """Order the rows for a view.

    The review queue is **oldest unreviewed first** so nothing is starved;
    other views default to newest first.
    """
    value = (sort or "").strip().lower()
    if value == "oldest":
        return sorted(rows, key=lambda row: (row[0].created_at, row[0].lead_id))
    if value == "newest":
        return sorted(
            rows, key=lambda row: (row[0].created_at, row[0].lead_id), reverse=True
        )
    if value in ("", None) and normalize_view(view) == "to_review":
        # Oldest unreviewed first: creators that have waited longest come first,
        # with decided creators after them.
        return sorted(
            rows,
            key=lambda row: (
                0 if row[0].fit_status == constants.FIT_STATUS_NOT_REVIEWED else 1,
                row[0].created_at,
                row[0].lead_id,
            ),
        )
    return sorted(rows, key=lambda row: (row[0].created_at, row[0].lead_id), reverse=True)
