from __future__ import annotations

from app import constants
from app.db.progress import derive_research_status, research_remedy
from app.db.repository import Repository
from app.db.schemas import PipelineJob


def _job(stage: str, status: str, error: str = "") -> PipelineJob:
    return PipelineJob(
        job_id=f"j_{stage}_{status}",
        stage=stage,
        lead_id="ld_x",
        status=status,
        attempt_count=1,
        max_attempts=3,
        last_error=error,
    )


def test_required_profile_error_is_blocked_with_credential_remedy() -> None:
    jobs = [
        _job(
            constants.STAGE_PROFILE_FETCH,
            constants.JOB_ERROR,
            "HikerAPIAuthError: HikerAPI rejected the API key (HTTP 401).",
        )
    ]
    assert derive_research_status("queued", jobs) == constants.RESEARCH_BLOCKED
    assert "HIKERAPI_KEY" in research_remedy("queued", jobs)


def test_terminal_error_overrides_queued_label() -> None:
    jobs = [
        _job(constants.STAGE_PROFILE_FETCH, constants.JOB_ERROR, "boom"),
        _job(constants.STAGE_WEBSITE_ENRICH, constants.JOB_QUEUED),
    ]
    assert derive_research_status("queued", jobs) == constants.RESEARCH_BLOCKED


def test_running_and_queued_states() -> None:
    assert (
        derive_research_status("queued", [_job(constants.STAGE_PROFILE_FETCH, constants.JOB_RUNNING)])
        == constants.RESEARCH_RUNNING
    )
    assert (
        derive_research_status("queued", [_job(constants.STAGE_PROFILE_FETCH, constants.JOB_QUEUED)])
        == constants.RESEARCH_QUEUED
    )
    assert (
        derive_research_status("queued", [_job(constants.STAGE_PROFILE_FETCH, constants.JOB_RETRY)])
        == constants.RESEARCH_QUEUED
    )


def test_ready_when_enriched_and_done() -> None:
    jobs = [_job(constants.STAGE_PROFILE_FETCH, constants.JOB_DONE)]
    assert derive_research_status("enriched", jobs) == constants.RESEARCH_READY


def test_optional_website_error_still_ready() -> None:
    jobs = [
        _job(constants.STAGE_PROFILE_FETCH, constants.JOB_DONE),
        _job(constants.STAGE_WEBSITE_ENRICH, constants.JOB_ERROR, "HTTP 500"),
    ]
    assert derive_research_status("enriched", jobs) == constants.RESEARCH_READY


def test_dossier_error_blocks_research() -> None:
    jobs = [
        _job(constants.STAGE_PROFILE_FETCH, constants.JOB_DONE),
        _job(constants.STAGE_AI_DOSSIER, constants.JOB_ERROR, "AIModelError: 503 UNAVAILABLE"),
    ]
    assert derive_research_status("enriched", jobs) == constants.RESEARCH_BLOCKED
    assert "GEMINI" in research_remedy("enriched", jobs)


def test_needs_data_without_jobs() -> None:
    assert derive_research_status("new", []) == constants.RESEARCH_NEEDS_DATA
    assert derive_research_status("queued", []) == constants.RESEARCH_NEEDS_DATA


def test_not_found_lead_is_blocked() -> None:
    assert derive_research_status("not_found", []) == constants.RESEARCH_BLOCKED
    assert "not found" in research_remedy("not_found", []).lower()


def test_outreach_jobs_do_not_affect_research() -> None:
    jobs = [
        _job(constants.STAGE_PROFILE_FETCH, constants.JOB_DONE),
        _job(constants.STAGE_AI_OUTREACH, constants.JOB_QUEUED),
    ]
    assert derive_research_status("enriched", jobs) == constants.RESEARCH_READY


def test_stats_and_rows_agree_on_derived_blocked(repo: Repository) -> None:
    _, lead = repo.create_or_get_lead("blocked.creator", status="queued")
    repo.enqueue(constants.STAGE_PROFILE_FETCH, lead.lead_id, lead.username, lead.username_normalized)
    claimed = repo.claim_next(worker_id="w1")
    repo.fail(
        claimed,
        "HikerAPIAuthError: HikerAPI rejected the API key (HTTP 401).",
        retryable=False,
    )

    progress, remedy = repo.lead_progress(lead.lead_id)
    assert progress == constants.RESEARCH_BLOCKED
    assert "HIKERAPI_KEY" in remedy

    rows = repo.list_leads_with_progress()
    assert rows[0][1] == constants.RESEARCH_BLOCKED
    assert repo.stats()["leads_by_progress"].get("blocked") == 1
