from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.dashboard.service import DashboardService, _worker_state
from app.db.repository import Repository
from app.worker.main import Worker


def _status(api_client) -> dict:
    response = api_client.get("/api/v1/integrations/status")
    assert response.status_code == 200
    return response.json()


def test_status_is_secret_free_and_disabled_by_default(api_client, monkeypatch) -> None:
    monkeypatch.setenv("HIKERAPI_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()

    body = _status(api_client)

    assert set(body) == {
        "database",
        "worker",
        "gemini",
        "hikerapi",
        "worker_last_beat_at",
    }
    assert body["database"] == "healthy"
    assert body["worker"] == "stopped"
    assert body["worker_last_beat_at"] == ""
    assert body["gemini"] == "disabled"
    assert body["hikerapi"] == "disabled"
    serialized = json.dumps(body).lower()
    assert "key" not in serialized
    assert "secret" not in serialized


def test_status_reports_configured_providers(api_client, monkeypatch) -> None:
    monkeypatch.setenv("HIKERAPI_KEY", "hik-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-test-key")
    monkeypatch.setenv("AI_ENABLED", "true")
    get_settings.cache_clear()

    body = _status(api_client)

    assert body["gemini"] == "configured"
    assert body["hikerapi"] == "configured"
    # Secrets are never echoed back.
    assert "hik-test-key" not in json.dumps(body)
    assert "gem-test-key" not in json.dumps(body)


def test_worker_heartbeat_active_then_stale(api_client, repo: Repository, monkeypatch) -> None:
    monkeypatch.setenv("HIKERAPI_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()

    assert _status(api_client)["worker"] == "stopped"

    repo.touch_heartbeat("w1")
    active = _status(api_client)
    assert active["worker"] == "active"
    assert active["worker_last_beat_at"]

    old = (datetime.now(timezone.utc) - timedelta(seconds=120)).replace(microsecond=0).isoformat()
    repo.touch_heartbeat("w1", beat_at=old)
    stale = _status(api_client)
    assert stale["worker"] == "stale"
    assert stale["worker_last_beat_at"] == old


def test_worker_state_helper() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    stale = (datetime.now(timezone.utc) - timedelta(seconds=61)).replace(microsecond=0).isoformat()
    assert _worker_state("") == "stopped"
    assert _worker_state("not-a-date") == "stopped"
    assert _worker_state(now) == "active"
    assert _worker_state(stale) == "stale"


def test_worker_loop_touches_heartbeat(repo: Repository, session_factory) -> None:
    worker = Worker(session_factory=session_factory, stages={}, poll_interval=0)
    worker.run(drain=True)

    heartbeat = repo.get_heartbeat()
    assert heartbeat is not None
    assert heartbeat.worker_id == "worker-1"
    assert heartbeat.beat_at


def test_database_unreachable_is_reported_not_raised(monkeypatch) -> None:
    monkeypatch.setenv("HIKERAPI_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()

    class _BoomSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("database down")

    class _BoomRepo:
        session = _BoomSession()

        def get_heartbeat(self):  # pragma: no cover - not reached
            raise RuntimeError("database down")

    status = DashboardService(_BoomRepo()).integrations_status()

    assert status["database"] == "unreachable"
    assert status["worker"] == "stopped"
    assert status["gemini"] == "disabled"
    assert status["hikerapi"] == "disabled"
