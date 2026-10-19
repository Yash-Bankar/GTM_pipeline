"""HTTP routes for leading capture and retrieval."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.dependencies import get_lead_service, require_api_key
from app.leads.schemas import (
    LeadCreateRequest,
    LeadListResponse,
    LeadResponse,
    LeadSubmissionResponse,
)
from app.leads.service import LeadService

router = APIRouter(
    prefix="/api/v1",
    tags=["leads"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "/leads",
    response_model=LeadSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a lead (idempotent by normalized username)",
)
def submit_lead(
    payload: LeadCreateRequest,
    response: Response,
    service: LeadService = Depends(get_lead_service),
) -> LeadSubmissionResponse:
    submission = service.submit(payload)
    if not submission.created:
        response.status_code = status.HTTP_200_OK
    return LeadSubmissionResponse(
        created=submission.created,
        lead=LeadResponse.from_lead(
            submission.lead, progress=submission.progress, remedy=submission.remedy
        ),
        outcome=submission.outcome,
        missing_fields=submission.missing_fields,
    )


@router.get(
    "/leads",
    response_model=LeadListResponse,
    summary="List leads with pagination and optional search/status filter",
)
def list_leads(
    limit: int = Query(50, ge=1, le=500, description="Page size."),
    offset: int = Query(0, ge=0, description="Number of leads to skip."),
    q: str | None = Query(None, max_length=200, description="Search text."),
    status_filter: str | None = Query(
        None, alias="status", max_length=50, description="Filter by lead status."
    ),
    service: LeadService = Depends(get_lead_service),
) -> LeadListResponse:
    rows, total = service.list(
        limit=limit, offset=offset, search=q, status=status_filter
    )
    return LeadListResponse(
        items=[
            LeadResponse.from_lead(lead, progress=progress, remedy=remedy)
            for lead, progress, remedy in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/leads/{lead_id}",
    response_model=LeadResponse,
    summary="Fetch a single lead by its stable leadId",
)
def get_lead(
    lead_id: str,
    service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    result = service.get(lead_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    lead, progress, remedy = result
    return LeadResponse.from_lead(lead, progress=progress, remedy=remedy)
