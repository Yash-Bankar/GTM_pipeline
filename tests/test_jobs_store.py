from __future__ import annotations

from app.constants import JOB_DONE, JOB_ERROR, JOB_RETRY, JOB_RUNNING
from app.sheets.schemas import KEY_JOBS


def test_enqueue_creates_queued_job(job_store) -> None:
    created, job = job_store.enqueue("profile_fetch", "ld_1", "creator", "creator")

    assert created is True
    assert job.job_id.startswith("job_")
    assert job.status == "queued"
    assert job.attempt_count == 0
    assert job.created_at and job.updated_at
    assert len(job_store.read_rows(KEY_JOBS)) == 1


def test_enqueue_is_idempotent_per_stage_and_lead(job_store) -> None:
    first_created, first = job_store.enqueue("profile_fetch", "ld_1", "creator", "creator")
    second_created, second = job_store.enqueue("profile_fetch", "ld_1", "creator", "creator")

    assert first_created is True
    assert second_created is False
    assert second.job_id == first.job_id
    assert len(job_store.read_rows(KEY_JOBS)) == 1


def test_different_stage_is_a_separate_job(job_store) -> None:
    job_store.enqueue("profile_fetch", "ld_1", "creator", "creator")
    created, _ = job_store.enqueue("website_enrich", "ld_1", "creator", "creator")
    assert created is True
    assert len(job_store.read_rows(KEY_JOBS)) == 2


def test_claim_marks_running_and_increments_attempt(job_store) -> None:
    job_store.enqueue("profile_fetch", "ld_1", "creator", "creator")

    claimed = job_store.claim_next(worker_id="w1")
    assert claimed is not None
    assert claimed.status == JOB_RUNNING
    assert claimed.attempt_count == 1
    assert claimed.locked_by == "w1"
    assert claimed.locked_at

    # No other eligible job.
    assert job_store.claim_next(worker_id="w1") is None


def test_claim_respects_run_after(job_store) -> None:
    _, job = job_store.enqueue("profile_fetch", "ld_1", "creator", "creator")
    job_store.update_by_key(KEY_JOBS, job.job_id, {"runAfter": "2999-01-01T00:00:00+00:00"})

    assert job_store.claim_next(worker_id="w1") is None

    job_store.update_by_key(KEY_JOBS, job.job_id, {"runAfter": "2000-01-01T00:00:00+00:00"})
    assert job_store.claim_next(worker_id="w1") is not None


def test_complete_marks_done(job_store) -> None:
    _, job = job_store.enqueue("profile_fetch", "ld_1", "creator", "creator")
    claimed = job_store.claim_next(worker_id="w1")
    assert claimed is not None

    job_store.complete(claimed, "result-body")
    row = job_store.find_job("profile_fetch", "ld_1")
    assert row is not None
    assert row.status == JOB_DONE
    assert row.result == "result-body"


def test_fail_retries_then_errors_when_exhausted(job_store) -> None:
    job_store.enqueue("profile_fetch", "ld_1", "creator", "creator", max_attempts=2)

    claimed = job_store.claim_next(worker_id="w1")
    assert claimed is not None
    status = job_store.fail(claimed, "boom", retryable=True, backoff_base=0.0)
    assert status == JOB_RETRY
    retried = job_store.find_job("profile_fetch", "ld_1")
    assert retried is not None and retried.status == JOB_RETRY

    claimed2 = job_store.claim_next(worker_id="w1")
    assert claimed2 is not None
    status2 = job_store.fail(claimed2, "boom again", retryable=True, backoff_base=0.0)
    assert status2 == JOB_ERROR
    errored = job_store.find_job("profile_fetch", "ld_1")
    assert errored is not None
    assert errored.status == JOB_ERROR
    assert "boom again" in errored.last_error


def test_fail_terminal_goes_straight_to_error(job_store) -> None:
    job_store.enqueue("profile_fetch", "ld_1", "creator", "creator", max_attempts=5)
    claimed = job_store.claim_next(worker_id="w1")
    assert claimed is not None

    status = job_store.fail(claimed, "not found", retryable=False)
    assert status == JOB_ERROR


def test_recover_stale_jobs(job_store) -> None:
    job_store.enqueue("profile_fetch", "ld_old", "old", "old")
    job_store.enqueue("profile_fetch", "ld_new", "new", "new")

    old = job_store.claim_next(worker_id="w1")
    assert old is not None
    job_store.update_by_key(KEY_JOBS, old.job_id, {"lockedAt": "2000-01-01T00:00:00+00:00"})

    # Re-queue the second then claim it so it is fresh/running.
    job_store.update_by_key(KEY_JOBS, job_store.find_job("profile_fetch", "ld_new").job_id, {"status": "queued"})
    fresh = job_store.claim_next(worker_id="w1")
    assert fresh is not None
    assert fresh.lead_id == "ld_new"

    recovered = job_store.recover_stale_jobs(stale_after_minutes=30)
    assert recovered == 1
    assert job_store.find_job("profile_fetch", "ld_old").status == JOB_RETRY
    assert job_store.find_job("profile_fetch", "ld_new").status == JOB_RUNNING
