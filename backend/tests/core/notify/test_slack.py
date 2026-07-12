"""Contract test for SlackWebhookNotifier against a mocked webhook endpoint.

No live webhook URL is configured in this environment.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from redis.asyncio import Redis

from verdantis.core.adapters.resilience import AdapterResilience
from verdantis.core.notify.slack import SlackNotConfiguredError, SlackWebhookNotifier

_WEBHOOK_URL = "https://hooks.slack.test/services/T00/B00/XXX"


def _notifier(redis_client: Redis) -> SlackWebhookNotifier:
    return SlackWebhookNotifier(
        webhook_url=_WEBHOOK_URL,
        resilience=AdapterResilience(redis_client, provider="slack-test"),
        client=httpx.AsyncClient(),
    )


def test_missing_webhook_url_raises_not_configured(redis_client: Redis) -> None:
    with pytest.raises(SlackNotConfiguredError):
        SlackWebhookNotifier(
            webhook_url=None,
            resilience=AdapterResilience(redis_client, provider="slack-noconf"),
            client=httpx.AsyncClient(),
        )


@respx.mock
async def test_notify_new_lead_posts_expected_text(redis_client: Redis) -> None:
    route = respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text="ok"))

    await _notifier(redis_client).notify_new_lead(
        legal_name="Acme Trading Ltd",
        country="DE",
        requested_commodity="cocoa",
        fit_score=0.87,
    )

    assert route.called
    body = route.calls[0].request.content
    assert b"Acme Trading Ltd" in body
    assert b"cocoa" in body
    assert b"0.87" in body
