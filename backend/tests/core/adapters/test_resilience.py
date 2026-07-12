"""Exercises AdapterResilience against a real Redis instance: rate limiting,
circuit breaker trip/cooldown, and retry-then-succeed on transient failures.
"""

from __future__ import annotations

import asyncio

import pytest
from redis.asyncio import Redis

from verdantis.core.adapters.resilience import (
    AdapterResilience,
    CircuitBreakerOpenError,
    RateLimitExceededError,
    TransientAdapterError,
)


async def test_calls_within_rate_limit_succeed(redis_client: Redis) -> None:
    resilience = AdapterResilience(redis_client, provider="test-rl-ok", rate_limit=3)

    for _ in range(3):
        result = await resilience.call(lambda: _ok("fine"))
    assert result == "fine"


async def test_rate_limit_exceeded_raises(redis_client: Redis) -> None:
    resilience = AdapterResilience(
        redis_client,
        provider="test-rl-exceeded",
        rate_limit=2,
        max_attempts=1,  # don't let retry mask the rate-limit error
    )

    await resilience.call(lambda: _ok("1"))
    await resilience.call(lambda: _ok("2"))

    with pytest.raises(RateLimitExceededError):
        await resilience.call(lambda: _ok("3"))


async def test_circuit_breaker_opens_after_threshold_failures(
    redis_client: Redis,
) -> None:
    resilience = AdapterResilience(
        redis_client,
        provider="test-cb-open",
        rate_limit=100,
        failure_threshold=2,
        max_attempts=1,  # each call() is one attempt at the underlying fn
        cooldown_seconds=30,
    )

    with pytest.raises(TransientAdapterError):
        await resilience.call(_always_fails)
    with pytest.raises(TransientAdapterError):
        await resilience.call(_always_fails)

    # Third call: breaker should be open now, short-circuiting before fn runs.
    with pytest.raises(CircuitBreakerOpenError):
        await resilience.call(_always_fails)


async def test_success_resets_failure_count(redis_client: Redis) -> None:
    resilience = AdapterResilience(
        redis_client,
        provider="test-cb-reset",
        rate_limit=100,
        failure_threshold=2,
        max_attempts=1,
        cooldown_seconds=30,
    )

    with pytest.raises(TransientAdapterError):
        await resilience.call(_always_fails)

    # One success between failures should reset the counter...
    await resilience.call(lambda: _ok("recovered"))

    # ...so this failure alone shouldn't trip the breaker (threshold is 2).
    with pytest.raises(TransientAdapterError):
        await resilience.call(_always_fails)

    # Breaker still closed: a normal call goes through.
    result = await resilience.call(lambda: _ok("still closed"))
    assert result == "still closed"


async def test_retries_transient_failure_then_succeeds(redis_client: Redis) -> None:
    resilience = AdapterResilience(
        redis_client,
        provider="test-retry",
        rate_limit=100,
        failure_threshold=10,
        max_attempts=3,
    )

    attempts = {"count": 0}

    async def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise TransientAdapterError("simulated transient failure")
        return "eventually ok"

    result = await resilience.call(flaky)
    assert result == "eventually ok"
    assert attempts["count"] == 2


async def test_timeout_is_retried_as_transient(redis_client: Redis) -> None:
    resilience = AdapterResilience(
        redis_client,
        provider="test-timeout",
        rate_limit=100,
        failure_threshold=10,
        max_attempts=2,
        timeout_seconds=0.05,
    )

    async def too_slow() -> str:
        await asyncio.sleep(1)
        return "never gets here"

    with pytest.raises(TransientAdapterError):
        await resilience.call(too_slow)


async def _ok(value: str) -> str:
    return value


async def _always_fails() -> str:
    raise TransientAdapterError("simulated permanent-for-this-test failure")
