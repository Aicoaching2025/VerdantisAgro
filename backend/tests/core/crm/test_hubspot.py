"""Contract tests for HubSpotClient against mocked batch-upsert responses.

No live access token is configured in this environment — these verify the
request/response mapping logic against the assumed API shape (see the NOTE
in hubspot.py), not the real HubSpot API itself.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from redis.asyncio import Redis

from verdantis.core.adapters.resilience import AdapterResilience
from verdantis.core.crm.hubspot import HubSpotClient, HubSpotNotConfiguredError

_BASE_URL = "https://hubspot.test"


def _client(redis_client: Redis) -> HubSpotClient:
    return HubSpotClient(
        access_token="test-token",
        resilience=AdapterResilience(redis_client, provider="hubspot-test"),
        client=httpx.AsyncClient(),
        base_url=_BASE_URL,
    )


def test_missing_access_token_raises_not_configured(redis_client: Redis) -> None:
    with pytest.raises(HubSpotNotConfiguredError):
        HubSpotClient(
            access_token=None,
            resilience=AdapterResilience(redis_client, provider="hubspot-noconf"),
            client=httpx.AsyncClient(),
        )


@respx.mock
async def test_upsert_company_returns_hubspot_id(redis_client: Redis) -> None:
    route = respx.post(f"{_BASE_URL}/crm/v3/objects/companies/batch/upsert").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"id": "12345", "properties": {"name": "Acme Trading Ltd"}}]
            },
        )
    )
    result = await _client(redis_client).upsert_company(
        legal_name="Acme Trading Ltd", properties={"fit_score": "0.85"}
    )
    assert result.object_type == "company"
    assert result.hubspot_id == "12345"

    request_body = route.calls[0].request.content
    assert b"Acme Trading Ltd" in request_body
    assert b"idProperty" in request_body
    assert b'"name"' in request_body


@respx.mock
async def test_upsert_contact_returns_hubspot_id(redis_client: Redis) -> None:
    respx.post(f"{_BASE_URL}/crm/v3/objects/contacts/batch/upsert").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": "67890", "properties": {"email": "buyer@example.com"}}
                ]
            },
        )
    )
    result = await _client(redis_client).upsert_contact(
        email="buyer@example.com", properties={"lifecyclestage": "lead"}
    )
    assert result.object_type == "contact"
    assert result.hubspot_id == "67890"
