"""Shared research-progress derivation (PRD section 10, tickets T01/V2-03).

The displayed research state is derived from persisted jobs plus the lead, never
from the raw ``lead.status`` alone, so a terminal job failure is shown as
``blocked`` instead of a misleading "Queued / Awaiting the worker".

States: ``needs_data``, ``queued``, ``running``, ``complete``, ``blocked``.
"""

from __future__ import annotations

from collections.abc import Iterable

from app import constants

from .schemas import PipelineJob

__all__ = ["derive_research_status", "research_remedy"]


def _research_jobs(jobs: Iterable[PipelineJob]) -> list[PipelineJob]:
    return [job for job in jobs if job.stage in constants.RESEARCH_STAGES]


def derive_research_status(lead_status: str, jobs: Iterable[PipelineJob]) -> str:
    """Derive the effective research state for a lead.

    Precedence (a terminal error always wins over a queued label):
    1. a required-stage terminal error -> ``blocked``
    2. any research job running -> ``running``
    3. any research job queued/retry -> ``queued``
    4. profile research succeeded -> ``complete``
    5. lead marked not_found/error -> ``blocked``
    6. an optional-stage error with no successful profile -> ``blocked``
    7. otherwise -> ``needs_data``
    """
    research = _research_jobs(jobs)
    status_value = (lead_status or "").lower()

    if any(
        job.status == constants.JOB_ERROR and job.stage in constants.REQUIRED_RESEARCH_STAGES
        for job in research
    ):
        return constants.RESEARCH_BLOCKED
    if any(job.status == constants.JOB_RUNNING for job in research):
        return constants.RESEARCH_RUNNING
    if any(job.status in constants.JOB_ACTIVE_STATUSES for job in research):
        return constants.RESEARCH_QUEUED
    if status_value == constants.LEAD_STATUS_ENRICHED:
        return constants.RESEARCH_COMPLETE
    if status_value in (constants.LEAD_STATUS_NOT_FOUND, constants.LEAD_STATUS_ERROR):
        return constants.RESEARCH_BLOCKED
    if any(job.status == constants.JOB_ERROR for job in research):
        return constants.RESEARCH_BLOCKED
    return constants.RESEARCH_NEEDS_DATA


def research_remedy(lead_status: str, jobs: Iterable[PipelineJob]) -> str:
    """Human-readable remedy when research is blocked, else an empty string."""
    research = _research_jobs(jobs)
    errored = [job for job in research if job.status == constants.JOB_ERROR]

    if not errored:
        if (lead_status or "").lower() == constants.LEAD_STATUS_NOT_FOUND:
            return "Profile not found on Instagram - verify the handle."
        return ""

    # Surface the most actionable error first (required stages before optional).
    for stage in constants.REQUIRED_RESEARCH_STAGES + (
        constants.STAGE_PROFILE_MEDIA,
        constants.STAGE_WEBSITE_ENRICH,
    ):
        for job in errored:
            if job.stage == stage:
                return _remedy_for(job)
    return f"Processing blocked: {errored[0].last_error or 'unknown error'}"


def _remedy_for(job: PipelineJob) -> str:
    error = (job.last_error or "").lower()

    if job.stage == constants.STAGE_PROFILE_FETCH:
        if any(marker in error for marker in ("auth", "401", "403", "rejected the api key")):
            return "Profile source rejected credentials - check HIKERAPI_KEY in Settings."
        if "not found" in error or "notfound" in error:
            return "Profile not found on Instagram - verify the handle."
        if "quota" in error or "rate" in error:
            return "Profile source rate-limited - retry later."
        return f"Profile research failed: {job.last_error}"
    if job.stage == constants.STAGE_AI_DOSSIER:
        return "AI generation failed - check GEMINI_API_KEY / GEMINI_MODEL, then retry."
    if job.stage == constants.STAGE_WEBSITE_ENRICH:
        return "Website research failed - the profile may have no reachable public site."
    return f"{job.stage} failed: {job.last_error}"
