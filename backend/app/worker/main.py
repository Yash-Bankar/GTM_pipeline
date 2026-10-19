"""Autonomous worker: poll `pipeline_jobs`, claim one, execute, repeat.

Single-instance by design: the queue lives in PostgreSQL. One worker is
recommended; the DB now provides row-level safety but a cross-process lease is a
later phase. No external messages are sent.

Run from the `backend` directory so the `app` package resolves:

    .\\.venv\\Scripts\\python.exe -m app.worker --drain
    .\\.venv\\Scripts\\python.exe -m app.worker --once
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading

from app.ai import AIService, DEFAULT_RUBRIC, parse_rubric
from app.config import Settings, get_settings
from app.constants import (
    STAGE_AI_DOSSIER,
    STAGE_AI_OUTREACH,
    STAGE_PROFILE_FETCH,
    STAGE_PROFILE_MEDIA,
    STAGE_WEBSITE_ENRICH,
)
from app.db.database import get_session_factory
from app.db.repository import Repository
from app.providers import HikerAPIClient
from app.providers.ai import GeminiProvider
from app.providers.website import WebsiteCrawler
from app.worker.pipeline import (
    AIDossierStage,
    AIOutreachStage,
    ProfileFetchStage,
    ProfileMediaStage,
    Stage,
    StageOutcome,
    WebsiteEnrichStage,
)

logger = logging.getLogger("synpo.worker")

# Never poll faster than this, even if configured lower.
MIN_POLL_INTERVAL_SECONDS = 5.0


class Worker:
    """Single-threaded job runner over a PostgreSQL session factory."""

    def __init__(
        self,
        *,
        session_factory,
        stages: dict[str, Stage],
        worker_id: str = "worker-1",
        poll_interval: float = 30.0,
        stale_minutes: int = 30,
        retry_backoff_base: float = 60.0,
        retry_backoff_max: float = 3600.0,
    ) -> None:
        self._session_factory = session_factory
        self._stages = dict(stages)
        self._worker_id = worker_id
        self._poll_interval = max(MIN_POLL_INTERVAL_SECONDS, float(poll_interval))
        self._stale_minutes = stale_minutes
        self._retry_backoff_base = retry_backoff_base
        self._retry_backoff_max = retry_backoff_max

    def recover(self) -> int:
        """Return interrupted `running` jobs to `retry` (restart recovery)."""
        with self._session_factory() as session:
            recovered = Repository(session).recover_stale_jobs(self._stale_minutes)
        if recovered:
            logger.info("Recovered %s stale job(s) from a previous run", recovered)
        return recovered

    def _touch_heartbeat(self) -> None:
        """Record liveness for the readiness endpoint (T09). Never fatal."""
        try:
            with self._session_factory() as session:
                Repository(session).touch_heartbeat(self._worker_id)
        except Exception:  # noqa: BLE001 - a heartbeat failure must not stop work
            logger.warning("Could not update the worker heartbeat", exc_info=True)

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

            self._touch_heartbeat()
            with self._session_factory() as session:
                job = Repository(session).claim_next(worker_id=self._worker_id)
            if job is None:
                if drain or max_jobs is not None:
                    break
                if stop.wait(self._poll_interval):
                    break
                continue

            self.run_job(job)
            self._touch_heartbeat()
            processed += 1

        return processed

    def run_job(self, job) -> StageOutcome:
        with self._session_factory() as session:
            repo = Repository(session)
            stage = self._stages.get(job.stage)
            if stage is None:
                outcome = StageOutcome(
                    ok=False, error=f"no stage registered for '{job.stage}'", retryable=False
                )
            else:
                try:
                    outcome = stage.run(job, repo)
                except Exception as exc:  # noqa: BLE001 - surfaced as a job error
                    logger.exception("Job %s crashed", job.job_id)
                    outcome = StageOutcome(
                        ok=False, error=f"{type(exc).__name__}: {exc}"[:1000], retryable=True
                    )

            if outcome.deferred:
                repo.defer(job, outcome.defer_seconds)
                logger.info("Job %s (%s) deferred: %s", job.job_id, job.stage, outcome.result)
            elif outcome.ok:
                repo.complete(job, outcome.result)
                logger.info("Job %s (%s) done", job.job_id, job.stage)
            else:
                status = repo.fail(
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


def build_stages(settings: Settings) -> dict[str, Stage]:
    hiker_enabled = bool(settings.hikerapi_key.strip())
    hiker = HikerAPIClient.from_settings(settings) if hiker_enabled else None
    if not hiker_enabled:
        logger.warning(
            "HIKERAPI_KEY is not set; profile_fetch will use captured snapshots only."
        )
    crawler = WebsiteCrawler(
        timeout=settings.website_timeout_seconds,
        max_pages=settings.website_max_pages,
        max_links_per_page=settings.website_max_links_per_page,
        max_bytes=settings.website_max_bytes,
        max_attempts=settings.website_max_attempts,
        user_agent=settings.website_user_agent,
    )
    ai_enabled = bool(settings.ai_enabled and settings.gemini_api_key.strip())
    if settings.ai_enabled and not ai_enabled:
        logger.warning("AI_ENABLED is true but GEMINI_API_KEY is unset; AI stages disabled.")

    stages: dict[str, Stage] = {
        STAGE_PROFILE_FETCH: ProfileFetchStage(
            hiker,
            followup_max_attempts=settings.pipeline_max_attempts,
            enable_ai=ai_enabled,
            hiker_enabled=hiker_enabled,
        ),
        STAGE_PROFILE_MEDIA: ProfileMediaStage(
            hiker,
            max_posts=settings.media_max_posts,
            max_pages=settings.media_max_pages,
        ),
        STAGE_WEBSITE_ENRICH: WebsiteEnrichStage(crawler),
    }

    if ai_enabled:
        rubric = parse_rubric(settings.ai_rubric_json) or DEFAULT_RUBRIC
        service = AIService(GeminiProvider.from_settings(settings), rubric)
        evidence_kwargs = {
            "max_posts": settings.ai_max_posts_evidence,
            "max_pages": settings.ai_max_pages_evidence,
            "text_chars": settings.ai_evidence_text_chars,
        }
        stages[STAGE_AI_DOSSIER] = AIDossierStage(
            service,
            model_name=settings.gemini_model,
            followup_max_attempts=settings.pipeline_max_attempts,
            **evidence_kwargs,
        )
        stages[STAGE_AI_OUTREACH] = AIOutreachStage(
            service,
            model_name=settings.gemini_model,
            **evidence_kwargs,
        )
    return stages


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
        logger.warning(
            "HIKERAPI_KEY is not set; the worker will process captured snapshots only "
            "(handle-only leads stay needs_data)."
        )

    worker = Worker(
        session_factory=get_session_factory(),
        stages=build_stages(settings),
        worker_id=args.worker_id,
        poll_interval=args.poll_interval if args.poll_interval is not None else settings.worker_poll_interval,
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
        pass

    max_jobs = 1 if args.once else args.max_jobs
    processed = worker.run(max_jobs=max_jobs, drain=args.drain, stop_event=stop)
    logger.info("Worker stopped after processing %s job(s).", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
