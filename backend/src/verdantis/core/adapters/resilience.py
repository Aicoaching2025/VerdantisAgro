"""Redis-coordinated resilience wrapper for external adapter calls.

Every external provider call (trade-intel, sanctions, corporate registries)
goes through `AdapterResilience.call()`, never directly. State (rate-limit
counters, circuit-breaker status) lives in Redis, not in-process memory, so
it's coordinated across worker replicas and survives a LangGraph checkpoint
resume — a node retried after a crash doesn't get a fresh rate-limit budget
just because the process restarted.

Adapters signal "safe to retry" by raising `TransientAdapterError` (timeouts,
connection errors, 5xx). Anything else (4xx, parse errors) is not retried —
retrying a bad request or a bug doesn't fix it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from redis.asyncio import Redis
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")


class TransientAdapterError(Exception):
    """Raised by adapter code for a failure that's safe to retry."""


class RateLimitExceededError(Exception):
    def __init__(self, provider: str, retry_after: float) -> None:
        super().__init__(
            f"rate limit exceeded for {provider!r}, retry after {retry_after:.1f}s"
        )
        self.provider = provider
        self.retry_after = retry_after


class CircuitBreakerOpenError(Exception):
    def __init__(self, provider: str) -> None:
        super().__init__(f"circuit breaker open for {provider!r}")
        self.provider = provider


class AdapterResilience:
    """Rate limit + circuit breaker + retry + timeout for one provider.

    One instance per provider, constructed with a shared Redis client.
    Rate-limit and breaker state are keyed by `provider`, so multiple
    adapter instances for the same provider (e.g. across worker processes)
    coordinate correctly.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        provider: str,
        rate_limit: int = 60,
        rate_limit_window_seconds: int = 60,
        failure_threshold: int = 5,
        cooldown_seconds: int = 30,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
    ) -> None:
        self._redis = redis
        self._provider = provider
        self._rate_limit = rate_limit
        self._rate_limit_window_seconds = rate_limit_window_seconds
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    @property
    def _rate_limit_key(self) -> str:
        return f"adapter:{self._provider}:rate"

    @property
    def _breaker_key(self) -> str:
        return f"adapter:{self._provider}:breaker_open"

    @property
    def _failure_key(self) -> str:
        return f"adapter:{self._provider}:failures"

    async def _check_rate_limit(self) -> None:
        count = await self._redis.incr(self._rate_limit_key)
        if count == 1:
            await self._redis.expire(
                self._rate_limit_key, self._rate_limit_window_seconds
            )
        if count > self._rate_limit:
            ttl = await self._redis.ttl(self._rate_limit_key)
            raise RateLimitExceededError(self._provider, retry_after=max(ttl, 1))

    async def _check_circuit_breaker(self) -> None:
        if await self._redis.exists(self._breaker_key):
            raise CircuitBreakerOpenError(self._provider)

    async def _record_success(self) -> None:
        await self._redis.delete(self._failure_key)

    async def _record_failure(self) -> None:
        count = await self._redis.incr(self._failure_key)
        if count == 1:
            await self._redis.expire(self._failure_key, self._cooldown_seconds)
        if count >= self._failure_threshold:
            await self._redis.set(self._breaker_key, "1", ex=self._cooldown_seconds)

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Run `fn()` through the circuit breaker, rate limiter, timeout, and retry."""
        await self._check_circuit_breaker()

        result: T
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type(
                (RateLimitExceededError, TransientAdapterError)
            ),
            reraise=True,
        ):
            with attempt:
                await self._check_rate_limit()
                try:
                    result = await asyncio.wait_for(fn(), timeout=self._timeout_seconds)
                except TimeoutError:
                    await self._record_failure()
                    raise TransientAdapterError(
                        f"{self._provider} call timed out after {self._timeout_seconds}s"
                    ) from None
                except TransientAdapterError:
                    await self._record_failure()
                    raise
                else:
                    await self._record_success()
        return result
