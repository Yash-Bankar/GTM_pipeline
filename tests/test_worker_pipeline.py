from __future__ import annotations

from app.constants import JOB_ERROR, LEAD_STATUS_ENRICHED, LEAD_STATUS_NOT_FOUND
from app.providers.errors import HikerAPINotFoundError, HikerAPIQuotaError
from app.sheets.schemas import KEY_ENRICHED, KEY_IG_LEADS, KEY_JOBS
from app.worker.main import Worker
from app.worker.pipeline import ProfileFetchStage
from fakes import FakeHikerClient, make_profile


def _enqueue(store, lead):
    created, job = store.jobs.enqueue(
        "profile_fetch", lead.lead_id, lead.username, lead.username_normalized, max_attempts=2
    )
    return job


def test_profile_fetch_success_writes_enriched_and_updates_lead(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("creator.one")
    job = _enqueue(worker_stores, lead)
    claimed = worker_stores.jobs.claim_next(worker_id="w1")
    assert claimed is not None

    stage = ProfileFetchStage(
        FakeHikerClient(lambda username: make_profile("creator.one")),
        worker_stores.lead,
        worker_stores.enriched,
    )
    outcome = stage.run(claimed)

    assert outcome.ok

    enriched = worker_stores.enriched.read_rows(KEY_ENRICHED)
    assert len(enriched) == 1
    assert enriched[0].values["leadId"] == lead.lead_id
    assert enriched[0].values["profileStatus"] == "done"
    assert enriched[0].values["followerCount"] == "5000"
    assert enriched[0].values["businessEmail"] == "hi@creator.example.org"

    updated_lead = worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id)
    assert updated_lead is not None
    assert updated_lead.values["status"] == LEAD_STATUS_ENRICHED
    assert updated_lead.values["followerCount"] == "5000"


def test_profile_fetch_is_idempotent(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("creator.two")
    job = _enqueue(worker_stores, lead)
    stage = ProfileFetchStage(
        FakeHikerClient(lambda username: make_profile("creator.two")),
        worker_stores.lead,
        worker_stores.enriched,
    )

    claimed1 = worker_stores.jobs.claim_next(worker_id="w1")
    stage.run(claimed1)
    first = worker_stores.enriched.read_rows(KEY_ENRICHED)
    assert len(first) == 1
    created_at = first[0].values["createdAt"]

    # Re-run the same job (e.g. after a retry).
    worker_stores.jobs.update_by_key(KEY_JOBS, job.job_id, {"status": "queued"})
    claimed2 = worker_stores.jobs.claim_next(worker_id="w1")
    stage.run(claimed2)

    second = worker_stores.enriched.read_rows(KEY_ENRICHED)
    assert len(second) == 1  # no duplicate row
    assert second[0].values["createdAt"] == created_at  # createdAt preserved


def test_profile_fetch_not_found_is_terminal(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("ghost")
    _enqueue(worker_stores, lead)
    claimed = worker_stores.jobs.claim_next(worker_id="w1")

    def handler(username):
        raise HikerAPINotFoundError("profile not found")

    stage = ProfileFetchStage(FakeHikerClient(handler), worker_stores.lead, worker_stores.enriched)
    outcome = stage.run(claimed)

    assert outcome.ok is False
    assert outcome.retryable is False
    assert worker_stores.lead.find_row(KEY_IG_LEADS, lead.lead_id).values["status"] == LEAD_STATUS_NOT_FOUND


def test_profile_fetch_quota_is_retryable(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("quota.hit")
    _enqueue(worker_stores, lead)
    claimed = worker_stores.jobs.claim_next(worker_id="w1")

    def handler(username):
        raise HikerAPIQuotaError("no balance")

    stage = ProfileFetchStage(FakeHikerClient(handler), worker_stores.lead, worker_stores.enriched)
    outcome = stage.run(claimed)
    assert outcome.ok is False
    assert outcome.retryable is True


def test_worker_marks_retry_then_error(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("flaky")

    def handler(username):
        raise HikerAPIQuotaError("no balance")

    stage = ProfileFetchStage(FakeHikerClient(handler), worker_stores.lead, worker_stores.enriched)
    worker = Worker(
        job_store=worker_stores.jobs,
        stages={stage.name: stage},
        poll_interval=0,
        retry_backoff_base=0.0,
    )
    worker._job_store.enqueue(
        "profile_fetch", lead.lead_id, lead.username, lead.username_normalized, max_attempts=2
    )

    processed = worker.run(drain=True)
    assert processed == 2  # first retry, then terminal error
    job = worker_stores.jobs.find_job("profile_fetch", lead.lead_id)
    assert job.status == JOB_ERROR


def test_worker_unknown_stage_errors(worker_stores) -> None:
    lead = worker_stores.lead.create_lead("orphan")
    worker_stores.jobs.enqueue("mystery_stage", lead.lead_id, lead.username, lead.username_normalized)
    worker = Worker(job_store=worker_stores.jobs, stages={}, poll_interval=0)

    processed = worker.run(drain=True)
    assert processed == 1
    assert worker_stores.jobs.find_job("mystery_stage", lead.lead_id).status == JOB_ERROR
