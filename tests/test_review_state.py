"""V2-03: review state, campaign criteria, material-change invalidation, history.

Covers QA scenarios V13, V14, V15, and V16.
"""

from __future__ import annotations


def _snapshot(**overrides):
    base = {
        "display_name": "Review Creator",
        "is_verified": True,
        "bio": "Finance educator.",
        "external_urls": ["https://one.example/"],
        "followers": {"value": 2000, "display": "2K", "precision": "approximate"},
        "following": {"value": 100, "display": "100", "precision": "exact"},
        "post_count": {"value": 50, "display": "50", "precision": "exact"},
        "source_url": "https://www.instagram.com/review.creator/",
        "captured_at": "2026-10-19T04:50:00Z",
        "parser_version": "1",
        "missing_fields": [],
    }
    base.update(overrides)
    return base


def _create_lead(api_client, username: str) -> str:
    response = api_client.post("/api/v1/leads", json={"username": username})
    assert response.status_code == 201
    return response.json()["lead"]["lead_id"]


def _post_snapshot(api_client, username: str, request_id: str, snapshot: dict):
    return api_client.post(
        "/api/v1/leads",
        json={
            "username": username,
            "source": "extension",
            "request_id": request_id,
            "profile_snapshot": snapshot,
        },
    )


def _fit(api_client, lead_id: str, action: str, note: str = ""):
    return api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": action, "note": note}
    )


def _decisions(api_client, lead_id: str) -> list[dict]:
    response = api_client.get(f"/api/v1/leads/{lead_id}/fit-decisions")
    assert response.status_code == 200
    return response.json()["items"]


def _campaign(api_client, **payload):
    return api_client.put("/api/v1/campaign", json=payload)


# -- V13: transitions ------------------------------------------------------


def test_v13_research_more_reject_reopen_and_shortlist(api_client) -> None:
    lead_id = _create_lead(api_client, "v13.creator")

    research = _fit(api_client, lead_id, "research_more", "Need topic evidence")
    assert research.status_code == 200
    assert research.json()["fit_status"] == "research_more"

    no_note = _fit(api_client, lead_id, "reject")
    assert no_note.status_code == 422

    rejected = _fit(api_client, lead_id, "reject", "Not a fit")
    assert rejected.status_code == 200
    assert rejected.json()["fit_status"] == "rejected"

    # A rejected creator cannot be shortlisted directly.
    blocked_shortlist = _fit(api_client, lead_id, "shortlist")
    assert blocked_shortlist.status_code == 422

    reopened = _fit(api_client, lead_id, "reopen")
    assert reopened.status_code == 200
    assert reopened.json()["fit_status"] == "not_reviewed"

    shortlisted = _fit(api_client, lead_id, "shortlist", "Good fit")
    assert shortlisted.status_code == 200
    assert shortlisted.json()["fit_status"] == "shortlisted"

    rows = _decisions(api_client, lead_id)
    assert [row["action"] for row in rows] == [
        "research_more",
        "reject",
        "reopen",
        "shortlist",
    ]
    assert all(row["actor"] == "shared dashboard operator" for row in rows)


def test_v13_legacy_action_aliases_still_work(api_client) -> None:
    lead_id = _create_lead(api_client, "v13.alias")
    response = _fit(api_client, lead_id, "approve", "Legacy caller")
    assert response.status_code == 200
    assert response.json()["fit_status"] == "shortlisted"


# -- V14: material changes -------------------------------------------------


def test_v14_bio_change_marks_review_needed_and_blocks_gates(api_client) -> None:
    lead_id = _post_snapshot(
        api_client, "v14.bio", "v14-bio-1", _snapshot()
    ).json()["lead"]["lead_id"]
    assert _fit(api_client, lead_id, "shortlist").json()["fit_status"] == "shortlisted"

    updated = _post_snapshot(
        api_client,
        "v14.bio",
        "v14-bio-2",
        _snapshot(bio="Completely different bio", captured_at="2026-10-20T00:00:00Z"),
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["outcome"] == "updated"
    assert body["lead"]["decision_currency"] == "review_needed"
    assert "Bio changed" in body["lead"]["decision_currency_reason"]

    # Gated work is blocked until reconfirmed.
    contact = api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json={})
    assert contact.status_code == 403
    assert contact.json()["detail"]["decision_currency"] == "review_needed"

    rows = _decisions(api_client, lead_id)
    assert rows[-1]["action"] == "review_needed"
    assert rows[-1]["actor"] == "system"
    assert rows[-1]["evidence_version"] == 2


def test_v14_external_domain_change_marks_review_needed(api_client) -> None:
    lead_id = _post_snapshot(
        api_client, "v14.domain", "v14-dom-1", _snapshot()
    ).json()["lead"]["lead_id"]
    _fit(api_client, lead_id, "shortlist")

    body = _post_snapshot(
        api_client,
        "v14.domain",
        "v14-dom-2",
        _snapshot(
            external_urls=["https://two.example/"],
            captured_at="2026-10-20T00:00:00Z",
        ),
    ).json()

    assert body["lead"]["decision_currency"] == "review_needed"
    assert "External domain changed" in body["lead"]["decision_currency_reason"]


def test_v14_follower_threshold_crossing_marks_review_needed(api_client) -> None:
    campaign = _campaign(
        api_client,
        name="Finance",
        description="Finance creators",
        target_topics=["finance"],
        follower_min=1000,
        follower_max=5000,
    )
    assert campaign.status_code == 200
    assert campaign.json()["version"] == 1

    lead_id = _post_snapshot(
        api_client, "v14.threshold", "v14-thr-1", _snapshot()
    ).json()["lead"]["lead_id"]
    _fit(api_client, lead_id, "shortlist")

    body = _post_snapshot(
        api_client,
        "v14.threshold",
        "v14-thr-2",
        _snapshot(
            followers={"value": 9000, "display": "9K", "precision": "approximate"},
            captured_at="2026-10-20T00:00:00Z",
        ),
    ).json()

    assert body["lead"]["decision_currency"] == "review_needed"
    assert "campaign threshold" in body["lead"]["decision_currency_reason"].lower()


# -- V15: non-material recaptures -----------------------------------------


def test_v15_timestamp_only_and_unchanged_recaptures_do_not_invalidate(api_client) -> None:
    lead_id = _post_snapshot(
        api_client, "v15.creator", "v15-a", _snapshot()
    ).json()["lead"]["lead_id"]
    _fit(api_client, lead_id, "shortlist")

    timestamp_only = _post_snapshot(
        api_client,
        "v15.creator",
        "v15-b",
        _snapshot(captured_at="2026-10-20T00:00:00Z"),
    ).json()
    assert timestamp_only["outcome"] == "unchanged"
    assert timestamp_only["lead"]["decision_currency"] == "current"

    identical = _post_snapshot(
        api_client, "v15.creator", "v15-c", _snapshot(captured_at="2026-10-20T00:00:00Z")
    ).json()
    assert identical["outcome"] == "unchanged"
    assert identical["lead"]["decision_currency"] == "current"

    actions = [row["action"] for row in _decisions(api_client, lead_id)]
    assert "review_needed" not in actions


# -- V16: rejected + new evidence -----------------------------------------


def test_v16_rejected_creator_gains_new_evidence_flag_without_reopening(
    api_client,
) -> None:
    lead_id = _post_snapshot(
        api_client, "v16.creator", "v16-a", _snapshot()
    ).json()["lead"]["lead_id"]
    assert _fit(api_client, lead_id, "reject", "Not a fit").status_code == 200

    body = _post_snapshot(
        api_client,
        "v16.creator",
        "v16-b",
        _snapshot(bio="New evidence", captured_at="2026-10-20T00:00:00Z"),
    ).json()

    assert body["outcome"] == "updated"
    assert body["lead"]["fit_status"] == "rejected"
    assert body["lead"]["new_evidence_available"] is True
    assert body["lead"]["decision_currency"] == "current"

    actions = [row["action"] for row in _decisions(api_client, lead_id)]
    assert actions[-1] == "new_evidence"

    # Still blocked from contact/draft work while rejected.
    contact = api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json={})
    assert contact.status_code == 403
    assert contact.json()["detail"]["fit_status"] == "rejected"

    reopened = _fit(api_client, lead_id, "reopen")
    assert reopened.status_code == 200
    assert reopened.json()["fit_status"] == "not_reviewed"
    assert reopened.json()["new_evidence_available"] is False


# -- Campaign configuration ------------------------------------------------


def test_campaign_configuration_roundtrip_and_invalidates_shortlists(api_client) -> None:
    initial = api_client.get("/api/v1/campaign")
    assert initial.status_code == 200
    assert initial.json()["version"] == 0

    first = _campaign(
        api_client,
        name="Finance partnerships",
        description="Finance creators",
        target_topics=["finance", "investing"],
        language="en",
        follower_min=1000,
        follower_max=100000,
    )
    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert first.json()["target_topics"] == ["finance", "investing"]

    lead_id = _create_lead(api_client, "campaign.creator")
    assert _fit(api_client, lead_id, "shortlist").status_code == 200

    second = _campaign(
        api_client,
        name="Finance partnerships",
        description="Finance creators",
        target_topics=["finance", "investing"],
        language="en",
        follower_min=5000,
        follower_max=100000,
    )
    assert second.status_code == 200
    assert second.json()["version"] == 2

    lead = api_client.get(f"/api/v1/leads/{lead_id}").json()
    assert lead["decision_currency"] == "review_needed"
    assert "Campaign criteria changed" in lead["decision_currency_reason"]

    rows = _decisions(api_client, lead_id)
    assert rows[-1]["action"] == "review_needed"
    assert rows[-1]["criteria_version"] == 2


def test_campaign_rejects_unknown_fields(api_client) -> None:
    response = api_client.put(
        "/api/v1/campaign", json={"name": "X", "unexpected": True}
    )
    assert response.status_code == 422
