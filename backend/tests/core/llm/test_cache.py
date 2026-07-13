from __future__ import annotations

from redis.asyncio import Redis

from verdantis.core.llm.cache import LLMResponseCache


async def test_miss_then_hit(redis_client: Redis) -> None:
    cache = LLMResponseCache(redis_client)
    assert (
        await cache.get(
            model="claude-haiku-4-5-20251001", system="sys", user="usr", max_tokens=512
        )
        is None
    )

    await cache.set(
        model="claude-haiku-4-5-20251001",
        system="sys",
        user="usr",
        max_tokens=512,
        value="cached response",
    )

    assert (
        await cache.get(
            model="claude-haiku-4-5-20251001", system="sys", user="usr", max_tokens=512
        )
        == "cached response"
    )


async def test_different_inputs_are_different_keys(redis_client: Redis) -> None:
    cache = LLMResponseCache(redis_client)
    await cache.set(
        model="m", system="sys", user="usr-a", max_tokens=512, value="response-a"
    )
    await cache.set(
        model="m", system="sys", user="usr-b", max_tokens=512, value="response-b"
    )

    assert (
        await cache.get(model="m", system="sys", user="usr-a", max_tokens=512)
        == "response-a"
    )
    assert (
        await cache.get(model="m", system="sys", user="usr-b", max_tokens=512)
        == "response-b"
    )
