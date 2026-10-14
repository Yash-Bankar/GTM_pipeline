from __future__ import annotations

import threading

from app.constants import JOB_DONE, JOB_RETRY
from app.db.models import PipelineJob as JobORM
from app.db.repository import Repository
from app.worker.main import Worker
from fakes import RecordingStage


def _lead(repo: Repository, name: str):
    return repo.create_or_get_lead(name)[1]


def _enqueue(repo: Repository, lead):
    return repo.enqueue("profile_fetch", lead.lead_id, lead.username, lead.username_normalized)[1]


def test_drain_processes_all_jobs(repo, session_factory) -> None:
    leads = [_lead(repo, f"loop.{index}") for index in range(3)]
    for lead in leads:
        _enqueue(repo, lead)

    stage = RecordingStage("profile_fetch")
    worker = Worker(session_factory=session_factory, stages={stage.name: stage}, poll_interval=0)

    processed = worker.run(drain=True)

    assert processed == 3
    assert len(stage.ran) == 3
    assert all(repo.find_job("profile_fetch", lead.lead_id).status == JOB_DONE for lead in leads)


def test_max_jobs_bounds_processing(repo, session_factory) -> None:
    for index in range(4):
        _enqueue(repo, _lead(repo, f"max.{index}"))
    stage = RecordingStage("profile_fetch")
    worker = Worker(session_factory=session_factory, stages={stage.name: stage}, poll_interval=0)
    assert worker.run(drain=True, max_jobs=2) == 2


def test_pre_set_stop_event_processes_nothing(repo, session_factory) -> None:
    _enqueue(repo, _lead(repo, "stop.0"))
    stop = threading.Event()
    stop.set()
    stage = RecordingStage("profile_fetch")
    worker = Worker(session_factory=session_factory, stages={stage.name: stage}, poll_interval=0)
    assert worker.run(stop_event=stop) == 0


def test_graceful_shutdown_finishes_current_job(repo, session_factory) -> None:
    for index in range(3):
        _enqueue(repo, _lead(repo, f"grace.{index}"))
    stop = threading.Event()

    def outcome_factory(job):
        stop.set()
        return None

    stage = RecordingStage("profile_fetch", outcome_factory)
    worker = Worker(session_factory=session_factory, stages={stage.name: stage}, poll_interval=0)
    assert worker.run(stop_event=stop) == 1


def test_restart_recovery_requeues_and_processes(repo, session_factory) -> None:
    stale_lead = _lead(repo, "stale.0")
    _enqueue(repo, stale_lead)
    other_lead = _lead(repo, "stale.1")
    _enqueue(repo, other_lead)

    claimed = repo.claim_next(worker_id="w1")
    row = repo.session.get(JobORM, claimed.job_id)
    row.locked_at = "2000-01-01T00:00:00+00:00"
    repo.session.commit()

    stage = RecordingStage("profile_fetch")
    worker = Worker(session_factory=session_factory, stages={stage.name: stage}, poll_interval=0, stale_minutes=30)
    processed = worker.run(drain=True)

    assert processed == 2
    assert repo.find_job("profile_fetch", stale_lead.lead_id).status == JOB_DONE
    assert repo.find_job("profile_fetch", other_lead.lead_id).status == JOB_DONE


def test_poll_interval_has_minimum_floor(repo, session_factory) -> None:
    stage = RecordingStage("profile_fetch")
    worker = Worker(session_factory=session_factory, stages={stage.name: stage}, poll_interval=0.0)
    assert worker._poll_interval >= 5.0
