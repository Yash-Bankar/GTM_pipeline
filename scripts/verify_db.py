"""Database check: verify the schema and exercise a read/write round-trip.

Requires DATABASE_URL (see .env.example). Run from the repository root:

    .\\backend\\.venv\\Scripts\\python.exe scripts\\verify_db.py

It never prints credentials (the DATABASE_URL password is masked).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import sqlalchemy as sa  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.database import get_engine, get_session_factory  # noqa: E402
from app.db.repository import Repository  # noqa: E402

EXPECTED_TABLES = {
    "leads",
    "lead_posts",
    "website_pages",
    "dossiers",
    "outreach_drafts",
    "pipeline_jobs",
}


def _mask(url: str) -> str:
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", url)


def main() -> int:
    settings = get_settings()
    print(f"DATABASE_URL: {_mask(settings.database_url)}")

    engine = get_engine()
    try:
        tables = set(sa.inspect(engine).get_table_names())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not connect: {type(exc).__name__}: {exc}")
        return 1

    print(f"Tables: {', '.join(sorted(tables)) or '(none)'}")
    missing = EXPECTED_TABLES - tables
    if missing:
        print(f"ERROR: missing tables: {', '.join(sorted(missing))}. Run `alembic upgrade head`.")
        return 1

    with get_session_factory()() as session:
        repo = Repository(session)
        created, lead = repo.create_or_get_lead("synpo_db_test", source="integration-test")
        print(f"Lead: {lead.lead_id} (created={created})")
        repo.enqueue(
            "profile_fetch", lead.lead_id, lead.username, lead.username_normalized,
            on_duplicate="reenqueue",
        )
        jobs = repo.list_jobs(lead.lead_id)
        print(f"Jobs for lead: {len(jobs)}")
        print(f"Total leads: {repo.stats()['leads_total']}")

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
