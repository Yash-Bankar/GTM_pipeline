"""Application settings loaded from environment variables.

Values are read from the process environment and, for local development, from a
`.env` file at the repository root. No secret is ever hardcoded here; see
`.env.example` for the full list of supported variables.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[0]=app, [1]=backend, [2]=repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    app_env: str = "development"
    log_level: str = "INFO"

    # Backend API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # When set, API requests must send a matching `x-api-key` header.
    api_key: str = ""
    # Comma-separated CORS origins for browser clients (e.g. the extension).
    cors_allow_origins: str = "*"

    # Instagram data provider (HikerAPI)
    hikerapi_base_url: str = "https://api.hikerapi.com/v2"
    hikerapi_key: str = ""
    hikerapi_timeout_seconds: float = 20.0
    hikerapi_max_attempts: int = 4
    hikerapi_backoff_base_seconds: float = 0.5
    hikerapi_backoff_max_seconds: float = 10.0

    # AI provider (Google Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    ai_enabled: bool = True
    ai_temperature: float = 0.4
    ai_max_output_tokens: int = 2048
    ai_timeout_seconds: float = 60.0
    ai_max_attempts: int = 3
    ai_rubric_json: str = ""
    ai_max_posts_evidence: int = 10
    ai_max_pages_evidence: int = 5
    ai_evidence_text_chars: int = 1500

    # Database (source of truth)
    # Sync SQLAlchemy URL. In Docker the host is the compose service `db`.
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/synpo"

    # Worker
    worker_poll_interval: int = 30
    worker_stale_minutes: int = 30

    # Profile media (recent posts/reels)
    media_max_posts: int = 12
    media_max_pages: int = 2

    # Website enrichment (crawl + SSRF-safe fetch)
    website_max_pages: int = 5
    website_max_links_per_page: int = 30
    website_timeout_seconds: float = 10.0
    website_max_bytes: int = 2_000_000
    website_max_attempts: int = 2
    website_user_agent: str = "SynpoGTM/0.1"

    # Pipeline job retries
    pipeline_max_attempts: int = 3
    pipeline_retry_backoff_base_seconds: float = 60.0
    pipeline_retry_backoff_max_seconds: float = 3600.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
