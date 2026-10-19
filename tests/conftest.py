from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Make the tests directory importable (for `fakes`) in addition to `backend`
# (which pytest adds via pythonpath in pytest.ini).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app.db.models  # noqa: E402,F401  (register ORM models)
from app.config import get_settings  # noqa: E402
from app.db.database import Base  # noqa: E402
from app.db.repository import Repository  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Keep tests independent of a developer's local .env.

    Forces no API key and no Gemini key so AI-unavailable paths are deterministic;
    tests that need auth or AI set these themselves (and clear the cache).
    """
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def engine():
    """A fresh in-memory SQLite database per test."""
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session_factory(engine):
    # expire_on_commit=True so post-commit reads see other sessions' writes.
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=True)


@pytest.fixture
def session(session_factory):
    db = session_factory()
    yield db
    db.close()


@pytest.fixture
def repo(session) -> Repository:
    return Repository(session)


@pytest.fixture
def api_client(session_factory):
    """FastAPI TestClient bound to the test database."""
    from fastapi.testclient import TestClient

    from app.db.database import get_db
    from app.main import app

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
