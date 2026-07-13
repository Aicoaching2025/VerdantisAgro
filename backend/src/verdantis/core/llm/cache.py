"""Redis-backed response cache for LLM classification calls (scope doc
Section 8: "Cost control: model routing... response caching..."). Wired
into scoring clients only (score_fit / score_lead), never drafting --
outreach copy is meant to read as freshly composed, and caching it risks
serving a stale draft after the dossier or fit reasons have changed.
Classification is a pure function of the dossier content, so caching it is
safe: any change to the input is automatically a cache miss.

Same Redis-coordination pattern as AdapterResilience -- state lives in
Redis, not in-process memory, so it's shared across worker replicas and
survives a process restart.
"""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis

# Long enough to absorb redundant re-scoring within a run or a checkpoint
# replay window; short enough that a same-day dossier update (new trade
# signals, a verification re-run) isn't masked by a stale cached score for
# long.
_DEFAULT_TTL_SECONDS = 6 * 60 * 60


class LLMResponseCache:
    def __init__(
        self, redis: Redis, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS
    ) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(*, model: str, system: str, user: str, max_tokens: int) -> str:
        digest = hashlib.sha256(
            f"{model}\n{max_tokens}\n{system}\n{user}".encode("utf-8")
        ).hexdigest()
        return f"llm:cache:{digest}"

    async def get(
        self, *, model: str, system: str, user: str, max_tokens: int
    ) -> str | None:
        value = await self._redis.get(
            self._key(model=model, system=system, user=user, max_tokens=max_tokens)
        )
        return value if isinstance(value, str) else None

    async def set(
        self, *, model: str, system: str, user: str, max_tokens: int, value: str
    ) -> None:
        await self._redis.set(
            self._key(model=model, system=system, user=user, max_tokens=max_tokens),
            value,
            ex=self._ttl_seconds,
        )
