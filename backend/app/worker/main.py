"""Autonomous worker: poll `Pipeline Jobs`, claim one, execute, repeat.

Single-instance by design (spreadsheet-backed MVP): one worker claims jobs under
a shared in-process write lock, so do not run multiple workers or API replicas
until a Sheets-based lease exists. No external messages are sent.

Run from the `backend` directory so the `app` package resolves:

    .\\.venv\\Scripts\\python.exe -m app.worker --drain
    .\\.venv\\Scripts\\python.exe -m app.worker --once
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading

from app.config import Settings, get_settings
from app.constants import STAGE_PROFILE_FETCH
from app.dependencies import SheetStores, build_sheet_stores
from app.providers import HikerAPIClient
from app.worker.pipeline import ProfileFetchStage, Stage, StageOutcome

logger = logging.getLogger("synpo.worker")


class Worker:
    """Single-threaded job runner."""

    def __init__(
        self,
        *,
        job_store: object,
        stages: dict[str, Stage],
        worker_id: str = "worker-1",
        poll_interval: float = 30.0,
        stale_minutes: int = 30,
        retry_backoff_base: float = 60.0,
        retry_backoff_max: float = 3600.0,
    ) -> None:
        self._job_store = job_store
        self._stages = dict(stages)
        self._worker_id = worker_id
        self._poll_interval = max(0.0, float(poll_interval))
        self._stale_minutes = stale_minutes
        self._retry_backoff_base = retry_backoff_base
        self._retry_backoff_max = retry_backoff_max

    def recover(self) -> int:
        """Return interrupted `running` jobs to `retry` (restart recovery)."""
        recovered = self._job_store.recover_stale_jobs(self._stale_minutes)
        if recovered:
            logger.info("Recovered %s stale job(s) from a previous run", recovered)
        return recovered

    def run(
        self,
        *,
        max_jobs: int | None = None,
        drain: bool = False,
        stop_event: threading.Event | None = None,
    ) -> int:
        """Process jobs until drained, ``max_jobs`` reached, or shutdown."""
        stop = stop_event or threading.Event()
        processed = 0
        self.recover()

        while not stop.is_set():
            if max_jobs is not None and processed >= max_jobs:
                break

            job = self._job_store.claim_next(worker_id=self._worker_id)
            if job is None:
                if drain or max_jobs is not None:
                    break
                if stop.wait(self._poll_interval):
                    break
                continue

            self.run_job(job)
            processed += 1

        return processed

    def run_job(self, job) -> StageOutcome:
        stage = self._stages.get(job.stage)
        if stage is None:
            outcome = StageOutcome(
                ok=False, error=f"no stage registered for '{job.stage}'", retryable=False
            )
        else:
            try:
                outcome = stage.run(job)
            except Exception as exc:  # noqa: BLE001 - surfaced as a job error
                logger.exception("Job %s crashed", job.job_id)
                outcome = StageOutcome(
                    ok=False, error=f"{type(exc).__name__}: {exc}"[:1000], retryable=True
                )

        if outcome.ok:
            self._job_store.complete(job, outcome.result)
            logger.info("Job %s (%s) done", job.job_id, job.stage)
        else:
            status = self._job_store.fail(
                job,
                outcome.error,
                retryable=outcome.retryable,
                backoff_base=self._retry_backoff_base,
                backoff_max=self._retry_backoff_max,
            )
            logger.warning(
                "Job %s (%s) -> %s: %s", job.job_id, job.stage, status, outcome.error
            )
        return outcome


def build_stages(stores: SheetStores, settings: Settings) -> dict[str, Stage]:
    hiker = HikerAPIClient.from_settings(settings)
    return {
        STAGE_PROFILE_FETCH: ProfileFetchStage(
            hiker, stores.lead_store, stores.enriched_store
        )
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synpo GTM Automation worker")
    parser.add_argument("--once", action="store_true", help="Process a single job and exit.")
    parser.add_argument(
        "--drain", action="store_true", help="Process until no eligible jobs remain, then exit."
    )
    parser.add_argument("--max-jobs", type=int, default=None, help="Stop after N jobs.")
    parser.add_argument("--poll-interval", type=float, default=None, help="Idle poll seconds.")
    parser.add_argument("--stale-minutes", type=int, default=None, help="Running-job stale age.")
    parser.add_argument("--worker-id", default="worker-1", help="Identifier recorded on jobs.")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = get_settings()
    if not settings.hikerapi_key.strip():
        logger.error("HIKERAPI_KEY is not set (see .env.example).")
        return 2

    stores = build_sheet_stores(settings)
    worker = Worker(
        job_store=stores.job_store,
        stages=build_stages(stores, settings),
        worker_id=args.worker_id,
        poll_interval=args.poll_interval if args.poll_interval is not None else settings.worker_poll_seconds,
        stale_minutes=args.stale_minutes if args.stale_minutes is not None else settings.worker_stale_minutes,
        retry_backoff_base=settings.pipeline_retry_backoff_base_seconds,
        retry_backoff_max=settings.pipeline_retry_backoff_max_seconds,
    )

    stop = threading.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Received signal %s - finishing current job then stopping.", signum)
        stop.set()

    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (AttributeError, ValueError):
        pass  # not available on all platforms

    max_jobs = 1 if args.once else args.max_jobs
    processed = worker.run(max_jobs=max_jobs, drain=args.drain, stop_event=stop)
    logger.info("Worker stopped after processing %s job(s).", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
