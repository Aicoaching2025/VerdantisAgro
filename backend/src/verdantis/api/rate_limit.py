"""Per-IP fixed-window rate limiting for public, unauthenticated endpoints.

Same INCR+EXPIRE idiom as `core.adapters.resilience.AdapterResilience`'s
provider rate limiter, but this guards our own public surface against abuse
rather than coordinating calls to a metered third-party API, so it lives
here rather than in core/adapters/.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from redis.asyncio import Redis


class RateLimitExceeded(HTTPException):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


async def enforce_rate_limit(
    redis: Redis, *, key: str, limit: int, window_seconds: int
) -> None:
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > limit:
        ttl = await redis.ttl(key)
        raise RateLimitExceeded(retry_after=max(int(ttl), 1))
