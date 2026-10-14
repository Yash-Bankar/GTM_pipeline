from __future__ import annotations

from app.constants import JOB_ERROR, LEAD_STATUS_ENRICHED, LEAD_STATUS_NOT_FOUND
from app.db.repository import Repository
from app.providers.errors import HikerAPINotFoundError, HikerAPIQuotaError
from app.worker.main import Worker
from app.worker.pipeline import ProfileFetchStage
from fakes import FakeHikerClient, make_profile


def _raising(exc: BaseException):
    def handler(_username):
        raise exc

    return handler


def _claim(repo: Repository, name: str, stage: str = "profile_fetch"):
    lead = repo.create_or_get_lead(name)[1]
    repo.enqueue(stage, lead.lead_id, lead.username, lead.username_normalized, max_attempts=2)
    return lead, repo.claim_next(worker_id="w1")


def test_profile_fetch_success(repo: Repository) -> None:
    lead, job = _claim(repo, "creator.one")
    stage = ProfileFetchStage(FakeHikerClient(lambda _u: make_profile("creator.one")))

    outcome = stage.run(job, repo)

    assert outcome.ok
    updated = repo.get_lead(lead.lead_id)
    assert updated.status == LEAD_STATUS_ENRICHED
    assert updated.follower_count == 5000
    assert updated.business_email == "hi@creator.example.org"


def test_profile_fetch_not_found_is_terminal(repo: Repository) -> None:
    lead, job = _claim(repo, "ghost")
    stage = ProfileFetchStage(FakeHikerClient(_raising(HikerAPINotFoundError("nf"))))
    outcome = stage.run(job, repo)
    assert outcome.ok is False
    assert outcome.retryable is False
    assert repo.get_lead(lead.lead_id).status == LEAD_STATUS_NOT_FOUND


def test_profile_fetch_quota_is_retryable(repo: Repository) -> None:
    _lead, job = _claim(repo, "quota")
    stage = ProfileFetchStage(FakeHikerClient(_raising(HikerAPIQuotaError("no balance"))))
    outcome = stage.run(job, repo)
    assert outcome.ok is False
    assert outcome.retryable is True


def test_profile_fetch_enqueues_followups(repo: Repository) -> None:
    lead, job = _claim(repo, "enqueue.me")
    profile = make_profile("enqueue.me", instagram_id="555", external_url="https://example.org")
    stage = ProfileFetchStage(FakeHikerClient(lambda _u: profile), enable_ai=True)

    stage.run(job, repo)

    assert repo.find_job("profile_media", lead.lead_id) is not None
    assert repo.find_job("website_enrich", lead.lead_id) is not None
    assert repo.find_job("ai_dossier", lead.lead_id) is not None


def test_worker_unknown_stage_errors(repo: Repository, session_factory) -> None:
    lead = repo.create_or_get_lead("orphan")[1]
    repo.enqueue("mystery_stage", lead.lead_id, lead.username, lead.username_normalized)
    worker = Worker(session_factory=session_factory, stages={}, poll_interval=0)
    assert worker.run(drain=True) == 1
    assert repo.find_job("mystery_stage", lead.lead_id).status == JOB_ERROR


def test_worker_retries_then_errors(repo: Repository, session_factory) -> None:
    lead = repo.create_or_get_lead("flaky")[1]
    repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized, max_attempts=2)
    stage = ProfileFetchStage(FakeHikerClient(_raising(HikerAPIQuotaError("no balance"))))
    worker = Worker(
        session_factory=session_factory, stages={stage.name: stage}, poll_interval=0, retry_backoff_base=0.0
    )
    processed = worker.run(drain=True)
    assert processed == 2  # first retry, then terminal error
    assert repo.find_job("profile_fetch", lead.lead_id).status == JOB_ERROR
