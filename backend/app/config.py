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
BACKEND_DIR = Path(__file__).resolve().parents[1]
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

    # Instagram data provider (HikerAPI)
    hikerapi_base_url: str = "https://api.hikerapi.com/v2"
    hikerapi_key: str = ""

    # AI provider (Google Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Google Sheets (source of truth)
    google_sheets_spreadsheet_id: str = ""
    google_sheets_ig_leads_tab: str = "IG Leads"
    google_sheets_dedup_tab: str = "Deduplicated Leads"
    google_sheets_enriched_tab: str = "instagram_leads_enriched"
    google_sheets_outreach_tab: str = "Outreach"
    google_application_credentials: str = ""

    # Google Sheets client behaviour
    google_sheets_request_timeout_seconds: int = 30
    google_sheets_max_attempts: int = 5
    google_sheets_backoff_base_seconds: float = 0.5
    google_sheets_backoff_max_seconds: float = 30.0

    def credentials_path(self) -> Path | None:
        """Resolve the service account JSON path.

        Absolute paths are used as-is. Relative paths are resolved against the
        repository root first, then the backend directory, so both
        ``secrets/service-account.json`` and ``backend/secrets/service-account.json``
        (relative to the repo root) work.
        """
        raw = self.google_application_credentials.strip()
        if not raw:
            return None
        path = Path(raw)
        if path.is_absolute():
            return path
        for base in (REPO_ROOT, BACKEND_DIR):
            candidate = (base / path).resolve()
            if candidate.exists():
                return candidate
        return (REPO_ROOT / path).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
