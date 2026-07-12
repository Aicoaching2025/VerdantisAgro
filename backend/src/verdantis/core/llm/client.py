"""Anthropic-backed LLM client, wrapped in the same resilience pattern as
every other external provider call (rate limit, circuit breaker, retry,
timeout).

`LLMClient` is the interface scoring/drafting code depends on — a Protocol,
not an ABC, since anything with a matching `complete()` method satisfies it
(a fake in tests, a different provider later) without needing to inherit
from anything.
"""

from __future__ import annotations

from typing import Protocol

import anthropic

from verdantis.core.adapters.resilience import AdapterResilience, TransientAdapterError


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
    ) -> None:
        if not api_key:
            raise AnthropicNotConfiguredError("Anthropic API key is not configured")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._resilience = resilience
        self._model = model

    async def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
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
        return "".join(block.text for block in message.content if block.type == "text")
