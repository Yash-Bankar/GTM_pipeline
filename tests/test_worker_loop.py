from __future__ import annotations

import threading

from app.constants import JOB_DONE, JOB_RETRY
from app.sheets.schemas import KEY_JOBS
from app.worker.main import Worker
from fakes import RecordingStage


def _enqueue(job_store, lead_id: str):
    return job_store.enqueue("profile_fetch", lead_id, lead_id, lead_id)[1]


def test_drain_processes_all_jobs(job_store) -> None:
    for index in range(3):
        _enqueue(job_store, f"ld_{index}")

    stage = RecordingStage("profile_fetch")
    worker = Worker(job_store=job_store, stages={stage.name: stage}, poll_interval=0)

    processed = worker.run(drain=True)

    assert processed == 3
    assert len(stage.ran) == 3
    assert all(row.values["status"] == JOB_DONE for row in job_store.read_rows(KEY_JOBS))


def test_max_jobs_bounds_processing(job_store) -> None:
    for index in range(4):
        _enqueue(job_store, f"ld_{index}")

    stage = RecordingStage("profile_fetch")
    worker = Worker(job_store=job_store, stages={stage.name: stage}, poll_interval=0)

    processed = worker.run(drain=True, max_jobs=2)
    assert processed == 2


def test_pre_set_stop_event_processes_nothing(job_store) -> None:
    _enqueue(job_store, "ld_0")
    stop = threading.Event()
    stop.set()
    stage = RecordingStage("profile_fetch")
    worker = Worker(job_store=job_store, stages={stage.name: stage}, poll_interval=0)

    processed = worker.run(stop_event=stop)
    assert processed == 0


def test_graceful_shutdown_finishes_current_job(job_store) -> None:
    for index in range(3):
        _enqueue(job_store, f"ld_{index}")

    stop = threading.Event()

    def outcome_factory(job):
        stop.set()  # request shutdown while the first job is running
        return None

    stage = RecordingStage("profile_fetch", outcome_factory)
    worker = Worker(job_store=job_store, stages={stage.name: stage}, poll_interval=0)

    processed = worker.run(stop_event=stop)

    assert processed == 1  # finished the in-flight job, then stopped


def test_restart_recovery_requeues_and_processes(job_store) -> None:
    _enqueue(job_store, "ld_stale")
    _enqueue(job_store, "ld_ok")

    stale = job_store.claim_next(worker_id="w1")
    assert stale is not None and stale.lead_id == "ld_stale"
    # Simulate a crash: leave it running with an old lock.
    job_store.update_by_key(KEY_JOBS, stale.job_id, {"lockedAt": "2000-01-01T00:00:00+00:00"})

    stage = RecordingStage("profile_fetch")
    worker = Worker(job_store=job_store, stages={stage.name: stage}, poll_interval=0, stale_minutes=30)

    processed = worker.run(drain=True)

    assert processed == 2  # recovered stale job + the queued one
    assert len(stage.ran) == 2
    assert all(row.values["status"] == JOB_DONE for row in job_store.read_rows(KEY_JOBS))

def test_poll_interval_has_minimum_floor(job_store) -> None:
    stage = RecordingStage("profile_fetch")
    worker = Worker(job_store=job_store, stages={stage.name: stage}, poll_interval=0.0)
    assert worker._poll_interval >= 5.0


def test_poll_interval_default_is_at_least_floor(job_store) -> None:
    stage = RecordingStage("profile_fetch")
    worker = Worker(job_store=job_store, stages={stage.name: stage})
    assert worker._poll_interval >= 5.0
