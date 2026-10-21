"""Campaign configuration schemas (V2-03)."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from app.db.schemas import Campaign


class CampaignOut(BaseModel):
    campaign_id: str = ""
    name: str = ""
    description: str = ""
    target_topics: list[str] = Field(default_factory=list)
    language: str = ""
    follower_min: int = 0
    follower_max: int = 0
    version: int = 0
    updated_at: str = ""

    @classmethod
    def from_model(cls, campaign: Campaign) -> "CampaignOut":
        try:
            topics = json.loads(campaign.target_topics) if campaign.target_topics else []
        except ValueError:
            topics = []
        return cls(
            campaign_id=campaign.campaign_id,
            name=campaign.name,
            description=campaign.description,
            target_topics=[str(topic) for topic in topics if str(topic).strip()],
            language=campaign.language,
            follower_min=campaign.follower_min,
            follower_max=campaign.follower_max,
            version=campaign.version,
            updated_at=campaign.updated_at,
        )


class CampaignUpdate(BaseModel):
    """Criteria for the single active campaign.

    ``follower_min``/``follower_max`` of 0 mean "no bound".
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=4000)
    target_topics: list[str] = Field(default_factory=list, max_length=50)
    language: str = Field(default="", max_length=32)
    follower_min: int = Field(default=0, ge=0)
    follower_max: int = Field(default=0, ge=0)
