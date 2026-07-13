"""Contract test for AnthropicClient against a mocked Anthropic API response.

No live API key is configured in this environment — this verifies the
resilience wrapping and response-text extraction, not the real API.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from redis.asyncio import Redis

from verdantis.core.adapters.resilience import AdapterResilience
from verdantis.core.llm.cache import LLMResponseCache
from verdantis.core.llm.client import AnthropicClient, AnthropicNotConfiguredError


def test_missing_api_key_raises_not_configured(redis_client: Redis) -> None:
    with pytest.raises(AnthropicNotConfiguredError):
        AnthropicClient(
            api_key=None,
            resilience=AdapterResilience(redis_client, provider="anthropic-noconf"),
            model="claude-haiku-4-5-20251001",
        )


@respx.mock
async def test_complete_extracts_text_from_response(redis_client: Redis) -> None:
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5-20251001",
                "content": [{"type": "text", "text": "Hello from Claude"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
    )
    client = AnthropicClient(
        api_key="test-key",
        resilience=AdapterResilience(redis_client, provider="anthropic-test"),
        model="claude-haiku-4-5-20251001",
    )
    result = await client.complete(system="You are a test.", user="Say hello.")
    assert result == "Hello from Claude"


@respx.mock
async def test_complete_serves_repeat_calls_from_cache(redis_client: Redis) -> None:
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5-20251001",
                "content": [{"type": "text", "text": "Hello from Claude"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
    )
    client = AnthropicClient(
        api_key="test-key",
        resilience=AdapterResilience(redis_client, provider="anthropic-test-cache"),
        model="claude-haiku-4-5-20251001",
        cache=LLMResponseCache(redis_client),
    )

    first = await client.complete(system="You are a test.", user="Say hello.")
    second = await client.complete(system="You are a test.", user="Say hello.")

    assert first == second == "Hello from Claude"
    assert route.call_count == 1  # second call served from cache, not the API
