"""Shared pytest fixtures.

Tests run against a real Postgres + pgvector database (verdantis_test) — not
SQLite, not mocks — because the schema depends on Postgres-specific features
(pgvector, partial unique indexes, native enums) that a fake backend can't
exercise honestly. The database itself is provisioned by docker-compose
locally and by the CI workflow; these fixtures assume it already exists and
has the `vector` extension enabled.

Schema is applied via the real `alembic upgrade head` (not
`Base.metadata.create_all`) once per test session, so a migration-authoring
bug — like the enum create_type=False bug found during review — fails the
test suite instead of only surfacing when someone runs the migration by hand.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Must happen before any `verdantis.config.settings` import (transitively,
# db/session.py and db/redis.py call get_settings() at module-import time) —
# PII encryption is mandatory, not optional, so every test that touches
# inbound ingestion needs a real key present from the start, not patched in
# ad hoc per test.
os.environ.setdefault("PII_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))

BACKEND_ROOT = Path(__file__).resolve().parents[1]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/verdantis_test",
)
TEST_DATABASE_URL_SYNC = TEST_DATABASE_URL.replace("+asyncpg", "+psycopg2")

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")

_TABLES = (
    "tenants, companies, trade_signals, verification_results, leads, "
    "suppression_entries"
)


def _run_migrations() -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL_SYNC)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    _run_migrations()


@pytest_asyncio.fixture
async def db_session(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """A session against a clean schema. Truncates after use.

    Tests exercising provenance.py commit mid-test (matching real usage), so
    a plain rollback isn't enough for isolation — truncate is what actually
    resets state between tests.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """A Redis client against an isolated logical DB (15), flushed after use."""
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()
