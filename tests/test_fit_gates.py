from __future__ import annotations

from app.db.repository import Repository


def _create_lead(api_client, username: str) -> str:
    response = api_client.post("/api/v1/leads", json={"username": username})
    assert response.status_code == 201
    return response.json()["lead"]["lead_id"]


def _approve(api_client, lead_id: str) -> None:
    response = api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": "shortlist", "note": "Good fit"}
    )
    assert response.status_code == 200
    assert response.json()["fit_status"] == "shortlisted"


def test_approve_fit_records_status_note_and_timestamp(api_client) -> None:
    lead_id = _create_lead(api_client, "fit.approve")
    response = api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": "shortlist", "note": "Strong finance fit"}
    )
    assert response.status_code == 200
    lead = response.json()
    assert lead["fit_status"] == "shortlisted"
    assert lead["fit_note"] == "Strong finance fit"
    assert lead["fit_decided_at"]


def test_need_evidence_sets_status(api_client) -> None:
    lead_id = _create_lead(api_client, "fit.more")
    response = api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": "research_more"}
    )
    assert response.status_code == 200
    assert response.json()["fit_status"] == "research_more"


def test_reject_requires_a_note(api_client) -> None:
    lead_id = _create_lead(api_client, "fit.reject.note")
    response = api_client.patch(f"/api/v1/leads/{lead_id}/fit", json={"action": "reject"})
    assert response.status_code == 422
    assert "note" in response.text.lower()


def test_reject_with_note_sets_status(api_client) -> None:
    lead_id = _create_lead(api_client, "fit.reject")
    response = api_client.patch(
        f"/api/v1/leads/{lead_id}/fit",
        json={"action": "reject", "note": "Outside target niche"},
    )
    assert response.status_code == 200
    assert response.json()["fit_status"] == "rejected"
    assert response.json()["fit_note"] == "Outside target niche"


def test_fit_decision_invalid_action_is_422(api_client) -> None:
    lead_id = _create_lead(api_client, "fit.invalid")
    response = api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": "maybe"}
    )
    assert response.status_code == 422


def test_fit_decision_missing_lead_is_404(api_client) -> None:
    response = api_client.patch(
        "/api/v1/leads/ld_nope/fit", json={"action": "shortlist"}
    )
    assert response.status_code == 404


def test_contact_request_blocked_until_approved(api_client) -> None:
    lead_id = _create_lead(api_client, "contact.gate")

    blocked = api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json={})
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "FIT_APPROVAL_REQUIRED"
    assert blocked.json()["detail"]["fit_status"] == "not_reviewed"

    _approve(api_client, lead_id)
    allowed = api_client.post(
        f"/api/v1/leads/{lead_id}/contact-requests", json={"note": "Find public email"}
    )
    assert allowed.status_code == 201
    body = allowed.json()
    assert body["lead_id"] == lead_id
    assert body["status"] == "requested"
    assert body["note"] == "Find public email"


def test_contact_request_blocked_after_rejection(api_client) -> None:
    lead_id = _create_lead(api_client, "contact.rejected")
    api_client.patch(
        f"/api/v1/leads/{lead_id}/fit",
        json={"action": "reject", "note": "No"},
    )
    response = api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json={})
    assert response.status_code == 403
    assert response.json()["detail"]["fit_status"] == "rejected"


def test_draft_request_blocked_until_approved(api_client) -> None:
    lead_id = _create_lead(api_client, "draft.gate")
    blocked = api_client.post(
        f"/api/v1/leads/{lead_id}/draft-requests", json={"channel": "email"}
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "FIT_APPROVAL_REQUIRED"


def test_draft_request_creates_history(api_client, repo: Repository) -> None:
    lead_id = _create_lead(api_client, "draft.history")
    _approve(api_client, lead_id)

    first = api_client.post(
        f"/api/v1/leads/{lead_id}/draft-requests", json={"channel": "email"}
    )
    second = api_client.post(
        f"/api/v1/leads/{lead_id}/draft-requests", json={"channel": "instagram_dm"}
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["revision_id"] != second.json()["revision_id"]
    assert first.json()["channel"] == "email"
    assert second.json()["channel"] == "instagram_dm"
    assert first.json()["status"] == "requested"
    assert first.json()["requested_at"]

    revisions = repo.list_outreach_revisions(lead_id)
    assert [row.channel for row in revisions] == ["email", "instagram_dm"]


def test_draft_request_invalid_channel_is_422(api_client) -> None:
    lead_id = _create_lead(api_client, "draft.channel")
    _approve(api_client, lead_id)
    response = api_client.post(
        f"/api/v1/leads/{lead_id}/draft-requests", json={"channel": "carrier_pigeon"}
    )
    assert response.status_code == 422


def test_draft_revision_history_is_listed(api_client) -> None:
    lead_id = _create_lead(api_client, "draft.list")
    _approve(api_client, lead_id)
    api_client.post(f"/api/v1/leads/{lead_id}/draft-requests", json={"channel": "email"})
    api_client.post(
        f"/api/v1/leads/{lead_id}/draft-requests", json={"channel": "instagram_dm"}
    )

    response = api_client.get(f"/api/v1/leads/{lead_id}/draft-requests")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["channel"] for item in body["items"]] == ["email", "instagram_dm"]


def test_draft_revision_history_missing_lead_is_404(api_client) -> None:
    response = api_client.get("/api/v1/leads/ld_nope/draft-requests")
    assert response.status_code == 404


def test_draft_request_missing_lead_is_404(api_client) -> None:
    response = api_client.post(
        "/api/v1/leads/ld_nope/draft-requests", json={"channel": "email"}
    )
    assert response.status_code == 404


def test_contact_request_missing_lead_is_404(api_client) -> None:
    response = api_client.post("/api/v1/leads/ld_nope/contact-requests", json={})
    assert response.status_code == 404


def test_fit_status_defaults_to_not_reviewed(api_client) -> None:
    lead_id = _create_lead(api_client, "fit.default")
    lead = api_client.get(f"/api/v1/leads/{lead_id}").json()
    assert lead["fit_status"] == "not_reviewed"
    assert lead["fit_note"] == ""
    assert lead["fit_decided_at"] == ""
