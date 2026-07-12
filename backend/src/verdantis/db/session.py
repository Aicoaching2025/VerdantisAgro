"""Async engine + session factory. One engine per process, built from Settings."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from verdantis.config.settings import get_settings

_engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A fresh session for callers outside FastAPI's DI (e.g. a background
    task), which can't use the `get_session` generator above."""
    async with _session_factory() as session:
        yield session
