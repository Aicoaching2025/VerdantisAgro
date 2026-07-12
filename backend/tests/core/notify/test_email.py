"""Contract test for ResendEmailClient against a mocked Resend endpoint, and
a test for the fixed ack template.

No live Resend API key is configured in this environment.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from redis.asyncio import Redis

from verdantis.core.adapters.resilience import AdapterResilience
from verdantis.core.notify.email import (
    EmailNotConfiguredError,
    ResendEmailClient,
    render_inquiry_ack,
)

_BASE_URL = "https://resend.test"


def _client(redis_client: Redis) -> ResendEmailClient:
    return ResendEmailClient(
        api_key="test-key",
        resilience=AdapterResilience(redis_client, provider="resend-test"),
        client=httpx.AsyncClient(),
        base_url=_BASE_URL,
    )


def test_missing_api_key_raises_not_configured(redis_client: Redis) -> None:
    with pytest.raises(EmailNotConfiguredError):
        ResendEmailClient(
            api_key=None,
            resilience=AdapterResilience(redis_client, provider="resend-noconf"),
            client=httpx.AsyncClient(),
        )


@respx.mock
async def test_send_returns_message_id(redis_client: Redis) -> None:
    route = respx.post(f"{_BASE_URL}/emails").mock(
        return_value=httpx.Response(200, json={"id": "msg-123"})
    )

    result = await _client(redis_client).send(
        to="buyer@example.com",
        from_email="leads@verdantisagro.com",
        from_name="Verdantis Agro Produce",
        subject="We received your inquiry",
        body="Thanks for reaching out.",
    )

    assert result.message_id == "msg-123"
    request_body = route.calls[0].request.content
    assert b"buyer@example.com" in request_body
    assert b"Verdantis Agro Produce" in request_body


def test_render_inquiry_ack_is_fixed_non_marketing_template() -> None:
    subject, body = render_inquiry_ack(
        contact_name="Jane Buyer", legal_name="Acme Trading Ltd"
    )
    assert "received your inquiry" in subject.lower()
    assert "Jane Buyer" in body
    assert "Acme Trading Ltd" in body
