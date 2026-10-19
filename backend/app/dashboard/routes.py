"""Dashboard HTTP routes: lead detail, retry, dossiers, outreach, stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app import constants
from app.config import get_settings
from app.dashboard.schemas import (
    DossierListOut,
    DossierOut,
    JobOut,
    LeadDetailOut,
    OutreachListOut,
    OutreachOut,
    OutreachUpdateRequest,
    PostOut,
    RetryAIOut,
    StatsOut,
    WebsitePageOut,
)
from app.dashboard.service import DashboardService
from app.dependencies import get_dashboard_service, require_api_key
from app.leads.schemas import LeadResponse

router = APIRouter(
    prefix="/api/v1",
    tags=["dashboard"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/leads/{lead_id}/detail", response_model=LeadDetailOut)
def lead_detail(
    lead_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> LeadDetailOut:
    detail = service.lead_detail(lead_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    return LeadDetailOut(
        lead=LeadResponse.from_lead(
            detail.lead, progress=detail.progress, remedy=detail.progress_remedy
        ),
        progress=detail.progress,
        progress_remedy=detail.progress_remedy,
        posts=[PostOut.from_model(post) for post in detail.posts],
        website_pages=[WebsitePageOut.from_model(page) for page in detail.website_pages],
        jobs=[JobOut.from_model(job) for job in detail.jobs],
    )


@router.post("/leads/{lead_id}/retry", response_model=JobOut)
def retry_lead(
    lead_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> JobOut:
    job = service.retry_lead(lead_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    return JobOut.from_model(job)


@router.post("/leads/{lead_id}/retry-ai", response_model=RetryAIOut)
def retry_ai(
    lead_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> RetryAIOut:
    """Re-queue the AI stages only (dossier + outreach).

    Rejected with ``409 AI_UNAVAILABLE`` before enqueue when AI is disabled or the
    Gemini key is missing (PRD T00 / A27). Existing reviewed drafts are preserved
    by the outreach stage, never overwritten.
    """
    settings = get_settings()
    if not (settings.ai_enabled and settings.gemini_api_key.strip()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": constants.ERROR_AI_UNAVAILABLE,
                "message": (
                    "AI is unavailable. Set AI_ENABLED=true and configure "
                    "GEMINI_API_KEY, then retry."
                ),
            },
        )

    jobs = service.retry_ai(lead_id)
    if jobs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    return RetryAIOut(lead_id=lead_id, jobs=[JobOut.from_model(job) for job in jobs])


@router.get("/dossiers", response_model=DossierListOut)
def list_dossiers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=200),
    service: DashboardService = Depends(get_dashboard_service),
) -> DossierListOut:
    rows, total = service.list_dossiers(limit=limit, offset=offset, search=q)
    return DossierListOut(
        items=[DossierOut.from_model(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/dossiers/{lead_id}", response_model=DossierOut)
def get_dossier(
    lead_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> DossierOut:
    dossier = service.get_dossier(lead_id)
    if dossier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No dossier for leadId '{lead_id}'.",
        )
    return DossierOut.from_model(dossier)


@router.get("/outreach", response_model=OutreachListOut)
def list_outreach(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status", max_length=50),
    service: DashboardService = Depends(get_dashboard_service),
) -> OutreachListOut:
    rows, total = service.list_outreach(limit=limit, offset=offset, status=status_filter)
    return OutreachListOut(
        items=[OutreachOut.from_model(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/outreach/{lead_id}", response_model=OutreachOut)
def get_outreach(
    lead_id: str,
    service: DashboardService = Depends(get_dashboard_service),
) -> OutreachOut:
    entry = service.get_outreach(lead_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No outreach for leadId '{lead_id}'.",
        )
    return OutreachOut.from_model(entry)


@router.patch("/outreach/{lead_id}", response_model=OutreachOut)
def update_outreach(
    lead_id: str,
    payload: OutreachUpdateRequest,
    service: DashboardService = Depends(get_dashboard_service),
) -> OutreachOut:
    try:
        entry = service.update_outreach(
            lead_id,
            status=payload.status,
            subject=payload.subject,
            body=payload.body,
            dm_body=payload.dm_body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No outreach for leadId '{lead_id}'.",
        )
    return OutreachOut.from_model(entry)


@router.get("/stats", response_model=StatsOut)
def stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> StatsOut:
    return StatsOut(**service.stats())
