"""Campaign configuration service (V2-03)."""

from __future__ import annotations

import json

from app import constants
from app.db.repository import Repository
from app.db.schemas import Campaign, FitDecision
from app.db.util import new_job_id, utc_now_iso_precise

from .schemas import CampaignOut, CampaignUpdate


class CampaignService:
    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def get(self) -> CampaignOut:
        campaign = self._repo.get_active_campaign()
        if campaign is None:
            return CampaignOut()
        return CampaignOut.from_model(campaign)

    def update(self, payload: CampaignUpdate) -> CampaignOut:
        """Replace the active campaign, increment its version, and invalidate
        current shortlists because campaign criteria are material evidence."""
        existing = self._repo.get_active_campaign()
        campaign = Campaign(
            campaign_id=existing.campaign_id if existing else new_job_id("cmp"),
            name=payload.name,
            description=payload.description,
            target_topics=json.dumps(payload.target_topics),
            language=payload.language,
            follower_min=payload.follower_min,
            follower_max=payload.follower_max,
            version=(existing.version + 1) if existing else 1,
            is_active=True,
        )
        saved = self._repo.upsert_campaign(campaign)
        self._invalidate_shortlists(saved)
        return CampaignOut.from_model(saved)

    def _invalidate_shortlists(self, campaign: Campaign) -> None:
        reason = "Campaign criteria changed"
        for lead in self._repo.list_shortlisted_leads():
            if lead.decision_currency == constants.DECISION_CURRENCY_REVIEW_NEEDED:
                continue
            self._repo.set_fit_decision(
                lead.lead_id,
                status=constants.FIT_STATUS_SHORTLISTED,
                note=lead.fit_note,
                decided_at=lead.fit_decided_at,
                currency=constants.DECISION_CURRENCY_REVIEW_NEEDED,
                currency_reason=reason,
            )
            self._repo.create_fit_decision(
                FitDecision(
                    decision_id=new_job_id("fd"),
                    lead_id=lead.lead_id,
                    action="review_needed",
                    fit_status=constants.FIT_STATUS_SHORTLISTED,
                    decision_currency=constants.DECISION_CURRENCY_REVIEW_NEEDED,
                    evidence_version=lead.evidence_version,
                    criteria_version=campaign.version,
                    note=reason,
                    actor=constants.FIT_ACTOR_SYSTEM,
                    created_at=utc_now_iso_precise(),
                )
            )
