"""Anthropic-backed LLM client, wrapped in the same resilience pattern as
every other external provider call (rate limit, circuit breaker, retry,
timeout).

`LLMClient` is the interface scoring/drafting code depends on — a Protocol,
not an ABC, since anything with a matching `complete()` method satisfies it
(a fake in tests, a different provider later) without needing to inherit
from anything.
"""

from __future__ import annotations

import logging
from typing import Protocol

import anthropic
from langsmith import traceable

from verdantis.core.adapters.resilience import AdapterResilience, TransientAdapterError
from verdantis.core.llm.cache import LLMResponseCache
from verdantis.core.llm.pricing import estimate_cost_usd

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    async def complete(
        self, *, system: str, user: str, max_tokens: int = 1024
    ) -> str: ...


class AnthropicNotConfiguredError(Exception):
    """Raised when the LLM client is used without an API key."""


class AnthropicClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        resilience: AdapterResilience,
        model: str,
        cache: LLMResponseCache | None = None,
    ) -> None:
        if not api_key:
            raise AnthropicNotConfiguredError("Anthropic API key is not configured")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._resilience = resilience
        self._model = model
        self._cache = cache

    @traceable(run_type="llm", name="anthropic_complete")
    async def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        if self._cache is not None:
            cached = await self._cache.get(
                model=self._model, system=system, user=user, max_tokens=max_tokens
            )
            if cached is not None:
                logger.info("llm_cache_hit", extra={"llm_model": self._model})
                return cached

        async def _do_request() -> anthropic.types.Message:
            try:
                return await self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
            except anthropic.APITimeoutError as exc:
                raise TransientAdapterError(
                    f"Anthropic request timed out: {exc}"
                ) from exc
            except anthropic.APIConnectionError as exc:
                raise TransientAdapterError(
                    f"Anthropic connection failed: {exc}"
                ) from exc
            except anthropic.InternalServerError as exc:
                raise TransientAdapterError(
                    f"Anthropic returned a server error: {exc}"
                ) from exc

        message = await self._resilience.call(_do_request)
        self._log_usage(message.usage)
        result = "".join(
            block.text for block in message.content if block.type == "text"
        )
        if self._cache is not None:
            await self._cache.set(
                model=self._model,
                system=system,
                user=user,
                max_tokens=max_tokens,
                value=result,
            )
        return result

    def _log_usage(self, usage: anthropic.types.Usage) -> None:
        # Structured, not persisted (rule 2/3 don't apply -- this is
        # operational telemetry, not a derived trade signal). Gives the cost
        # visibility scope doc Section 8 asks for without a new DB write path.
        cost_usd = estimate_cost_usd(
            self._model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        logger.info(
            "llm_call",
            extra={
                "llm_model": self._model,
                "llm_input_tokens": usage.input_tokens,
                "llm_output_tokens": usage.output_tokens,
                "llm_estimated_cost_usd": round(cost_usd, 6),
            },
        )
