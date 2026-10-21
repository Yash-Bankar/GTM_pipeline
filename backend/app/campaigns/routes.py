"""Campaign configuration routes (V2-03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_campaign_service, require_api_key

from .schemas import CampaignOut, CampaignUpdate
from .service import CampaignService

router = APIRouter(
    prefix="/api/v1",
    tags=["campaign"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/campaign", response_model=CampaignOut)
def get_campaign(service: CampaignService = Depends(get_campaign_service)) -> CampaignOut:
    return service.get()


@router.put("/campaign", response_model=CampaignOut)
def update_campaign(
    payload: CampaignUpdate,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignOut:
    return service.update(payload)
