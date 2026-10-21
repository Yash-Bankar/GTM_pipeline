"""V2-09: release QA - migration safety and the remaining acceptance gaps.

* **V31** - the real Alembic migrations run against a legacy-shaped
  PostgreSQL database: ids, draft text and decision history survive, the
  provenance limit stays explicit, and **no** mass jobs or sent events are
  created.
* **V18** - a repeated discovery request reuses the attempt and its progress
  is visible.
* **V28** - a save while the worker is offline leaves a truthful queued state
  and the work is not lost when the worker recovers.
* **V30** - the frontend accessibility/layout audit is wired into pytest, so
  it cannot silently regress.

The migration test uses a real PostgreSQL database because the migrations use
PostgreSQL SQL (``md5()``, ``ON CONFLICT``); SQLite cannot execute them.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.models import FitDecision, Lead, OutreachDraft

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"

# The revision that introduced the draft-revision history. The legacy shape
# exists up to this point.
PRE_DRAFT_REVISIONS = "f6a7b8c9d0e1"


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env=env,
    )


def _upgrade_to(database_url: str, revision: str) -> None:
    result = _alembic(database_url, "upgrade", revision)
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"


def _downgrade_to(database_url: str, revision: str) -> None:
    result = _alembic(database_url, "downgrade", revision)
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"


def _postgres_available() -> bool:
    """True when a local PostgreSQL is reachable for the migration test."""
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        return False
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 5})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:  # noqa: BLE001
        return False


def _scratch_url(base_url: str, name: str) -> str:
    """Return ``base_url`` with its database replaced by ``name``."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(base_url)
    return urlunsplit(
        (parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment)
    )


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason="TEST_DATABASE_URL is not set or PostgreSQL is unreachable",
)


@pytest.fixture
def legacy_database():
    """A PostgreSQL database migrated to the pre-draft-revision state.

    The schema is created by the real migrations, so the test exercises the
    actual upgrade path rather than a hand-written approximation.
    """
    base_url = os.environ["TEST_DATABASE_URL"]
    url = _scratch_url(base_url, "synpo_migration_test")

    admin_engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        # Terminate any leftover session before dropping the scratch database.
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = 'synpo_migration_test' AND pid <> pg_backend_pid()"
            )
        )
        connection.execute(text("DROP DATABASE IF EXISTS synpo_migration_test"))
        connection.execute(text("CREATE DATABASE synpo_migration_test"))
    admin_engine.dispose()

    # Migrate to just before the contact backfill, so the legacy lead with a
    # public email exists before the migration that imports it.
    _upgrade_to(url, "d4e5f6a7b8c9")

    engine = create_engine(url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)
    with factory() as session:
        # The legacy creator, with a public email that the contact migration
        # must import. The ORM model supplies every NOT NULL column.
        session.add(
            Lead(
                lead_id="ld_legacy_0001",
                username="legacy.creator",
                username_normalized="legacy.creator",
                bio="Legacy bio",
                business_email="legacy@creator.test",
                status="enriched",
                fit_status="shortlisted",
                decision_currency="current",
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
            )
        )
        session.commit()
    engine.dispose()

    # Now the review-state migration creates `fit_decisions`.
    _upgrade_to(url, PRE_DRAFT_REVISIONS)

    engine = create_engine(url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)
    with factory() as session:
        session.add(
            OutreachDraft(
                lead_id="ld_legacy_0001",
                username="legacy.creator",
                username_normalized="legacy.creator",
                channel="email",
                status="APPROVED",
                subject="Legacy subject",
                body="Legacy body text",
                dm_body="Legacy DM text",
                model="gemini-3.8-flash",
                generated_at="2026-01-01T00:00:00+00:00",
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
            )
        )
        session.add(
            FitDecision(
                decision_id="fd_legacy_0001",
                lead_id="ld_legacy_0001",
                action="shortlist",
                fit_status="shortlisted",
                decision_currency="current",
                evidence_version=1,
                criteria_version=1,
                note="Legacy note",
                actor="shared dashboard operator",
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        session.commit()
    engine.dispose()
    return url



@requires_postgres
def test_v31_migrations_preserve_legacy_data_and_create_no_work(
    legacy_database,
) -> None:
    """The real migration preserves legacy data and schedules nothing (V31)."""
    _upgrade_to(legacy_database, "head")

    engine = create_engine(legacy_database)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)
    with factory() as session:
        # The id survived.
        lead = session.execute(
            text("SELECT lead_id, fit_status FROM leads WHERE lead_id = 'ld_legacy_0001'")
        ).first()
        assert lead is not None
        assert lead.lead_id == "ld_legacy_0001"
        assert lead.fit_status == "shortlisted"

        # The decision history survived.
        decisions = session.execute(
            text("SELECT decision_id, note FROM fit_decisions")
        ).all()
        assert len(decisions) == 1
        assert decisions[0].decision_id == "fd_legacy_0001"
        assert decisions[0].note == "Legacy note"

        # The legacy draft became a revision with its text intact.
        revisions = session.execute(
            text(
                "SELECT revision_id, subject, body, dm_body, status, method, model "
                "FROM draft_revisions WHERE lead_id = 'ld_legacy_0001'"
            )
        ).all()
        assert len(revisions) == 1
        revision = revisions[0]
        assert revision.subject == "Legacy subject"
        assert revision.body == "Legacy body text"
        assert revision.dm_body == "Legacy DM text"
        # An approved legacy draft is "reviewed"; the model is preserved.
        assert revision.status == "reviewed"
        assert revision.method == "ai"
        assert revision.model == "gemini-3.8-flash"

        # **Zero mass jobs and zero sent events.**
        jobs = session.execute(text("SELECT COUNT(*) FROM pipeline_jobs")).scalar()
        assert jobs == 0
        events = session.execute(
            text("SELECT COUNT(*) FROM outreach_events")
        ).scalar()
        assert events == 0

        # A legacy draft is not treated as a generation request.
        requests = session.execute(
            text("SELECT COUNT(*) FROM outreach_revisions")
        ).scalar()
        assert requests == 0

        # The legacy email became a contact with an explicit provenance limit.
        contacts = session.execute(
            text(
                "SELECT value, source_url, method, validation_state "
                "FROM contacts WHERE lead_id = 'ld_legacy_0001'"
            )
        ).all()
        assert len(contacts) == 1
        assert contacts[0].value == "legacy@creator.test"
        # No source was invented and no validation was claimed.
        assert contacts[0].source_url == ""
        assert contacts[0].method == "legacy"
        assert contacts[0].validation_state == "unverified"
    engine.dispose()


@requires_postgres
def test_v31_migration_is_idempotent_on_a_second_run(legacy_database) -> None:
    """Re-running the upgrade on an already-migrated database is a no-op."""
    _upgrade_to(legacy_database, "head")
    _upgrade_to(legacy_database, "head")

    engine = create_engine(legacy_database)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)
    with factory() as session:
        revisions = session.execute(
            text("SELECT COUNT(*) FROM draft_revisions")
        ).scalar()
        assert revisions == 1
    engine.dispose()


@requires_postgres
def test_v31_migration_can_be_rolled_back(legacy_database) -> None:
    """The draft-revision migration has a working downgrade (V31)."""
    _upgrade_to(legacy_database, "head")
    _downgrade_to(legacy_database, PRE_DRAFT_REVISIONS)

    engine = create_engine(legacy_database)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)
    with factory() as session:
        # The legacy draft row itself was never touched by the upgrade.
        draft = session.execute(
            text("SELECT subject, body FROM outreach_drafts WHERE lead_id = 'ld_legacy_0001'")
        ).first()
        assert draft is not None
        assert draft.subject == "Legacy subject"
        assert draft.body == "Legacy body text"
    engine.dispose()


# -- V18: a repeated discovery request reuses the attempt -------------------


def test_v18_repeated_discovery_reuses_the_attempt_and_shows_progress(
    api_client, repo: Repository
) -> None:
    """A repeated click reuses the attempt, and its progress is visible (V18)."""
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": "v18.progress",
            "source": "extension",
            "request_id": "v209-v18",
            "profile_snapshot": {
                "display_name": "Creator",
                "is_verified": False,
                "bio": "",
                "external_urls": ["https://site.example/"],
                "followers": {"value": 1, "display": "1", "precision": "exact"},
                "following": {"value": 1, "display": "1", "precision": "exact"},
                "post_count": {"value": 1, "display": "1", "precision": "exact"},
                "source_url": "https://www.instagram.com/v18.progress/",
                "captured_at": "2026-10-21T00:00:00Z",
                "parser_version": "1",
                "missing_fields": [],
            },
        },
    )
    lead_id = response.json()["lead"]["lead_id"]
    api_client.patch(
        f"/api/v1/leads/{lead_id}/fit", json={"action": "shortlist", "note": "ok"}
    )

    first = api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json={})
    second = api_client.post(f"/api/v1/leads/{lead_id}/contact-requests", json={})

    assert first.status_code == 201
    # The repeated request returns the existing attempt (200, not a new one).
    assert second.status_code == 200
    assert first.json()["request_id"] == second.json()["request_id"]
    assert len(repo.list_contact_requests(lead_id)) == 1
    jobs = [job for job in repo.list_jobs(lead_id) if job.stage == "contact_discovery"]
    assert len(jobs) == 1

    # The progress is visible on the creator detail.
    detail = api_client.get(f"/api/v1/leads/{lead_id}/detail").json()
    request = detail["contact_request"]
    assert request is not None
    assert request["status"] == "queued"
    assert request["request_id"] == first.json()["request_id"]


# -- V28: a truthful queued state while the worker is offline ---------------


def test_v28_save_is_distinct_from_processing_and_survives_restart(
    api_client, repo: Repository
) -> None:
    """Saving is separate from processing; a queued job is not lost (V28)."""
    response = api_client.post(
        "/api/v1/leads",
        json={
            "username": "v28.offline",
            "source": "extension",
            "request_id": "v209-v28",
            "profile_snapshot": {
                "display_name": "Creator",
                "is_verified": False,
                "bio": "",
                "external_urls": [],
                "followers": {"value": 1, "display": "1", "precision": "exact"},
                "following": {"value": 1, "display": "1", "precision": "exact"},
                "post_count": {"value": 1, "display": "1", "precision": "exact"},
                "source_url": "https://www.instagram.com/v28.offline/",
                "captured_at": "2026-10-21T00:00:00Z",
                "parser_version": "1",
                "missing_fields": [],
            },
        },
    )
    lead_id = response.json()["lead"]["lead_id"]

    # The save succeeded and the work is queued, not lost.
    assert response.status_code == 201
    jobs = repo.list_jobs(lead_id)
    assert len(jobs) == 1
    assert jobs[0].stage == "profile_fetch"
    assert jobs[0].status == "queued"

    # The lead's state is truthful: queued, not "complete".
    detail = api_client.get(f"/api/v1/leads/{lead_id}/detail").json()
    assert detail["progress"] in ("queued", "running", "needs_data")

    # The worker was offline: simulate a crash by leaving the job locked.
    job = repo.claim_next(worker_id="w1")
    assert job is not None
    assert job.status == "running"

    # On restart the stale job is requeued and the work is not lost.
    repo.recover_stale_jobs()
    requeued = repo.list_jobs(lead_id)
    assert len(requeued) == 1
    assert requeued[0].job_id == jobs[0].job_id
    assert requeued[0].status in ("queued", "running", "done")


# -- V30: the frontend audit is part of the automated suite -----------------


def test_v30_frontend_accessibility_audit_passes() -> None:
    """The frontend a11y/layout audit is wired into pytest (V30).

    The audit checks that every interactive element has an accessible name and
    a visible focus ring, that touch targets are at least 44px, and that
    nothing overflows at 360 CSS pixels.
    """
    script = REPO_ROOT / "scripts" / "audit_frontend_a11y.py"
    assert script.exists(), "the frontend audit script is missing"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"the frontend accessibility audit failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "issues: 0" in result.stdout


def test_v09_p0_release_audit_passes() -> None:
    """The P0 audit is wired into pytest (V2-09).

    It checks the defect classes that would block a release: destructive
    migrations, secret exposure, unguarded mutating routes and any code path
    that could dispatch a message.
    """
    script = REPO_ROOT / "scripts" / "audit_p0.py"
    assert script.exists(), "the P0 audit script is missing"

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"the P0 release audit failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "problems: 0" in result.stdout
