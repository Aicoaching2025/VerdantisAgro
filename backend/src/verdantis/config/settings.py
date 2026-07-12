"""Application settings, read once from the environment.

`get_settings()` is the only sanctioned way to read config in this codebase —
no `os.getenv` scattered in modules. It's `lru_cache`d so the environment is
parsed exactly once per process; call it, don't instantiate `Settings()`
directly.

Values come from Doppler / injected env in every real environment. `.env` is
read locally only (gitignored) and never present in CI or production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"

    # Async driver (asyncpg) for the app runtime.
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/verdantis"
    )
    redis_url: str = "redis://localhost:6379/0"

    sentry_dsn: str | None = None

    langsmith_api_key: str | None = None
    langsmith_project: str = "verdantis-leadgen"
    langsmith_tracing: bool = False

    clerk_secret_key: str | None = None
    clerk_publishable_key: str | None = None

    # OpenSanctions self-hosted (yente) or hosted match API. Unset in dev —
    # the sanctions provider raises a clear error if called without one
    # rather than silently no-op'ing past a compliance-critical check.
    opensanctions_api_url: str = "https://api.opensanctions.org"
    opensanctions_api_key: str | None = None

    opencorporates_api_key: str | None = None

    # Model-routed per CLAUDE.md: cheap model for classification (fit
    # scoring), stronger model for drafting.
    anthropic_api_key: str | None = None
    anthropic_scoring_model: str = "claude-haiku-4-5-20251001"
    anthropic_drafting_model: str = "claude-sonnet-5"

    hubspot_access_token: str | None = None

    # Transactional ack email to inbound-form submitters (core.notify.email).
    # The Slack webhook URL and "from" address are per-tenant routing config
    # (Tenant.config / TenantConfig), not here — only Verdantis's own shared
    # provider credential belongs in global settings.
    resend_api_key: str | None = None

    @property
    def sync_database_url(self) -> str:
        """Sync driver (psycopg2) variant, for Alembic only.

        Alembic's migration runner is sync; the app runtime is async
        (asyncpg). Same database, same credentials — only the driver differs.
        """
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def psycopg_database_url(self) -> str:
        """psycopg3 conninfo variant, for the LangGraph Postgres checkpointer.

        AsyncPostgresSaver uses psycopg3, not asyncpg or psycopg2 — a third
        driver for the same database, same credentials.
        """
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
