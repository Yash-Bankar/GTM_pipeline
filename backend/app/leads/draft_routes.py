"""HTTP routes for draft versions and manual outreach logging (V2-07).

Draft actions: Edit, Save, Mark reviewed, Copy, Export text, Generate new
version. Manual logging: Log sent and the outcome events (Replied, Interested,
Not interested, Follow up). No route sends a message.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app import constants
from app.config import get_settings
from app.dependencies import (
    get_draft_service,
    require_capture_key,
    require_operator_key,
)
from app.leads.drafts import (
    DraftNotFoundError,
    DraftService,
    FitGateError,
    GenerationUnavailableError,
    OutreachEventError,
)
from app.leads.schemas import (
    DraftGenerateRequest,
    DraftRevisionListOut,
    DraftRevisionOut,
    DraftSaveRequest,
    DraftTextOut,
    OutreachEventCreate,
    OutreachEventListOut,
    OutreachEventOut,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["drafts"],
)


def _ai_available() -> bool:
    """True when an explicit AI generation request can be accepted (V22)."""
    settings = get_settings()
    return bool(settings.ai_enabled and settings.gemini_api_key.strip())


@router.get(
    "/leads/{lead_id}/drafts",
    response_model=DraftRevisionListOut,
    summary="List saved draft versions (oldest first)",

    dependencies=[Depends(require_operator_key)],)
def list_drafts(
    lead_id: str,
    service: DraftService = Depends(get_draft_service),
) -> DraftRevisionListOut:
    rows = service.list_revisions(lead_id)
    return DraftRevisionListOut(
        items=[DraftRevisionOut.from_model(row) for row in rows],
        total=len(rows),
    )


@router.post(
    "/leads/{lead_id}/drafts",
    response_model=DraftRevisionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Save a draft as a new version (manual, no AI key required)",

    dependencies=[Depends(require_operator_key)],)
def save_draft(
    lead_id: str,
    payload: DraftSaveRequest,
    service: DraftService = Depends(get_draft_service),
) -> DraftRevisionOut:
    try:
        result = service.save_draft(
            lead_id,
            subject=payload.subject,
            body=payload.body,
            dm_body=payload.dm_body,
            channel=payload.channel,
            note=payload.note,
            contact_id=payload.contact_id,
            parent_revision_id=payload.parent_revision_id,
        )
    except DraftNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        ) from exc
    return DraftRevisionOut.from_model(result.revision)


@router.post(
    "/leads/{lead_id}/drafts/{revision_id}/review",
    response_model=DraftRevisionOut,
    summary="Mark a saved draft version as reviewed",

    dependencies=[Depends(require_operator_key)],)
def mark_draft_reviewed(
    lead_id: str,
    revision_id: str,
    service: DraftService = Depends(get_draft_service),
) -> DraftRevisionOut:
    try:
        result = service.mark_reviewed(lead_id, revision_id)
    except DraftNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No draft revision '{revision_id}'.",
        ) from exc
    return DraftRevisionOut.from_model(result.revision)


@router.get(
    "/leads/{lead_id}/drafts/{revision_id}/text",
    response_model=DraftTextOut,
    summary="Get the plain text of a draft version (copy/export never marks sent)",

    dependencies=[Depends(require_operator_key)],)
def get_draft_text(
    lead_id: str,
    revision_id: str,
    service: DraftService = Depends(get_draft_service),
) -> DraftTextOut:
    try:
        text = service.copy_text(lead_id, revision_id)
    except DraftNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No draft revision '{revision_id}'.",
        ) from exc
    return DraftTextOut(revision_id=revision_id, text=text)


@router.post(
    "/leads/{lead_id}/drafts/generate",
    response_model=DraftRevisionOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a new AI-generated draft version",

    dependencies=[Depends(require_operator_key)],)
def generate_draft(
    lead_id: str,
    payload: DraftGenerateRequest,
    service: DraftService = Depends(get_draft_service),
) -> DraftRevisionOut:
    """Request generation of a new version.

    The response is the *request* (accepted, not content): the worker writes a
    new revision when it succeeds. When AI is unavailable the request is
    rejected with 409 and **no** revision, job or orphan row is created (V22).
    """
    try:
        request = service.request_generation(
            lead_id,
            channel=payload.channel,
            ai_available=_ai_available(),
            parent_revision_id=payload.parent_revision_id,
            contact_id=payload.contact_id,
        )
    except GenerationUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": constants.ERROR_AI_UNAVAILABLE,
                "message": (
                    "AI is unavailable. Set AI_ENABLED=true and configure "
                    "GEMINI_API_KEY, then retry. Manual writing still works."
                ),
            },
        ) from exc
    except FitGateError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FIT_APPROVAL_REQUIRED",
                "message": (
                    "Shortlist this creator with current evidence before "
                    "requesting an AI-generated draft."
                ),
                "fit_status": exc.fit_status,
                "decision_currency": exc.decision_currency,
            },
        ) from exc
    except DraftNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lead with leadId '{lead_id}'.",
        ) from exc
    return DraftRevisionOut(
        revision_id=request.revision_id,
        lead_id=request.lead_id,
        channel=request.channel,
        status=request.status,
        method=constants.DRAFT_METHOD_AI,
        parent_revision_id=request.parent_revision_id,
        request_id=request.revision_id,
        created_at=request.created_at,
    )


@router.get(
    "/leads/{lead_id}/outreach-events",
    response_model=OutreachEventListOut,
    summary="List the manual outreach history (oldest first)",

    dependencies=[Depends(require_operator_key)],)
def list_outreach_events(
    lead_id: str,
    service: DraftService = Depends(get_draft_service),
) -> OutreachEventListOut:
    events = service.list_events(lead_id)
    latest = service.latest_event(lead_id)
    return OutreachEventListOut(
        items=[OutreachEventOut.from_model(event) for event in events],
        total=len(events),
        latest_outcome=latest.outcome if latest is not None else "",
    )


@router.post(
    "/leads/{lead_id}/outreach-events",
    response_model=OutreachEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log an outreach event manually (sent / replied / interested / ...)",

    dependencies=[Depends(require_operator_key)],)
def log_outreach_event(
    lead_id: str,
    payload: OutreachEventCreate,
    service: DraftService = Depends(get_draft_service),
) -> OutreachEventOut:
    try:
        result = service.log_event(
            lead_id,
            outcome=payload.outcome,
            channel=payload.channel,
            sent_at=payload.sent_at,
            revision_id=payload.revision_id,
            note=payload.note,
            corrects_event_id=payload.corrects_event_id,
        )
    except OutreachEventError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return OutreachEventOut.from_model(result.event)
