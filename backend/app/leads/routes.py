"""HTTP routes for leading capture and retrieval."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.dependencies import get_lead_service, require_api_key
from app.leads.schemas import (
    ContactRequestCreate,
    ContactRequestOut,
    DraftRequestCreate,
    FitDecisionListOut,
    FitDecisionOut,
    FitDecisionRequest,
    LeadCreateRequest,
    LeadListResponse,
    LeadResponse,
    LeadSubmissionResponse,
    OutreachRevisionListOut,
    OutreachRevisionOut,
)
from app.leads.service import FitNotApprovedError, LeadService, RequestIdConflictError

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
    try:
        submission = service.submit(payload)
    except RequestIdConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "REQUEST_ID_CONFLICT",
                "message": (
                    f"Request id '{exc.request_id}' was already used with a "
                    "different payload."
                ),
            },
        ) from exc
    if not submission.created:
        response.status_code = status.HTTP_200_OK
    return LeadSubmissionResponse(
        created=submission.created,
        lead=LeadResponse.from_lead(
            submission.lead, progress=submission.progress, remedy=submission.remedy
        ),
        outcome=submission.outcome,
        missing_fields=submission.missing_fields,
        research_queued=submission.research_queued,
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


@router.patch(
    "/leads/{lead_id}/fit",
    response_model=LeadResponse,
    summary="Record a manual fit decision (T08)",
)
def decide_fit(
    lead_id: str,
    payload: FitDecisionRequest,
    service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    try:
        lead = service.decide_fit(lead_id, action=payload.action, note=payload.note)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    context = service.get(lead_id)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    lead, progress, remedy = context
    return LeadResponse.from_lead(lead, progress=progress, remedy=remedy)


@router.post(
    "/leads/{lead_id}/contact-requests",
    response_model=ContactRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request public contact details (requires approved fit)",
)
def request_contact(
    lead_id: str,
    payload: ContactRequestCreate | None = None,
    service: LeadService = Depends(get_lead_service),
) -> ContactRequestOut:
    try:
        request = service.request_contact(lead_id, note=payload.note if payload else "")
    except FitNotApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FIT_APPROVAL_REQUIRED",
                "message": (
                    "Shortlist this creator with current evidence before requesting "
                    "contact details."
                ),
                "fit_status": exc.fit_status,
                "decision_currency": exc.decision_currency,
            },
        ) from exc
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    return ContactRequestOut.from_model(request)


@router.post(
    "/leads/{lead_id}/draft-requests",
    response_model=OutreachRevisionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request a new outreach draft revision (requires approved fit)",
)
def request_draft(
    lead_id: str,
    payload: DraftRequestCreate,
    service: LeadService = Depends(get_lead_service),
) -> OutreachRevisionOut:
    try:
        revision = service.request_draft(lead_id, channel=payload.channel)
    except FitNotApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FIT_APPROVAL_REQUIRED",
                "message": (
                    "Shortlist this creator with current evidence before requesting "
                    "an outreach draft."
                ),
                "fit_status": exc.fit_status,
                "decision_currency": exc.decision_currency,
            },
        ) from exc
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    return OutreachRevisionOut.from_model(revision)


@router.get(
    "/leads/{lead_id}/draft-requests",
    response_model=OutreachRevisionListOut,
    summary="List outreach draft revision history (T08)",
)
def list_draft_requests(
    lead_id: str,
    service: LeadService = Depends(get_lead_service),
) -> OutreachRevisionListOut:
    if service.get(lead_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    rows = service.list_draft_revisions(lead_id)
    return OutreachRevisionListOut(
        items=[OutreachRevisionOut.from_model(row) for row in rows],
        total=len(rows),
    )


@router.get(
    "/leads/{lead_id}/fit-decisions",
    response_model=FitDecisionListOut,
    summary="List fit decision history (V2-03)",
)
def list_fit_decisions(
    lead_id: str,
    service: LeadService = Depends(get_lead_service),
) -> FitDecisionListOut:
    if service.get(lead_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        )
    rows = service.list_fit_decisions(lead_id)
    return FitDecisionListOut(
        items=[FitDecisionOut.from_model(row) for row in rows],
        total=len(rows),
    )
