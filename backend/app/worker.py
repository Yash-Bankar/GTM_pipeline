"""Background worker entrypoint.

Foundation only: a runnable stub. The worker will poll Google Sheets for pending
work and run the enrichment/generation stages in later phases (see
docs/architecture.md).

Concurrency: run exactly **one** worker instance. Job state lives in Google
Sheets, and there is no concurrent job claimer in the MVP; multiple workers would
race on the same rows. A Sheets-based lease is a later phase.
"""

from __future__ import annotations

import argparse
import logging

from app import __version__

logger = logging.getLogger("synpo.worker")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synpo GTM Automation worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll cycle and exit instead of looping.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def run_once() -> None:
    """Run a single poll cycle.

    No jobs are implemented yet; this is a placeholder that later phases replace
    with Sheets polling and pipeline stage execution.
    """
    logger.info("poll cycle: no jobs implemented yet")


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info("synpo-gtm worker starting (version %s)", __version__)
    run_once()
    logger.info("synpo-gtm worker finished")


if __name__ == "__main__":
    main()
