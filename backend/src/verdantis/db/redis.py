"""Shared async Redis client. One client per process, built from Settings —
same pattern as db/session.py's engine. Used for AdapterResilience state and
for public-endpoint rate limiting (api/rate_limit.py).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from verdantis.config.settings import get_settings

_redis = Redis.from_url(get_settings().redis_url, decode_responses=True)


def get_redis_client() -> Redis:
    """The singleton client itself — for callers outside FastAPI's DI (e.g.
    a background task), which can't use the `get_redis` generator below."""
    return _redis


async def get_redis() -> AsyncGenerator[Redis, None]:
    yield _redis
