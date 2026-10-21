"""Campaign configuration routes (V2-03)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_campaign_service, require_operator_key

from .schemas import CampaignOut, CampaignUpdate
from .service import CampaignService

router = APIRouter(
    prefix="/api/v1",
    tags=["campaign"],
    # Campaign criteria drive fit decisions: operator-only (V2-09 / V27).
    dependencies=[Depends(require_operator_key)],
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
