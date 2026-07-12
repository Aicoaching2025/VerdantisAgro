"""Contract tests for OpenSanctionsProvider against mocked HTTP responses.

No live API key is configured in this environment — these verify the
request/response mapping logic against the assumed API shape (see the
NOTE in sanctions.py), not the real OpenSanctions API itself.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from redis.asyncio import Redis

from verdantis.core.adapters.resilience import AdapterResilience, TransientAdapterError
from verdantis.core.verification.sanctions import (
    OpenSanctionsNotConfiguredError,
    OpenSanctionsProvider,
)
from verdantis.db.enums import ProvenanceMethod, Verdict

_API_URL = "https://sanctions.test"


def _provider(redis_client: Redis) -> OpenSanctionsProvider:
    return OpenSanctionsProvider(
        api_url=_API_URL,
        api_key="test-key",
        resilience=AdapterResilience(redis_client, provider="opensanctions-test"),
        client=httpx.AsyncClient(),
    )


def test_missing_api_key_raises_not_configured(redis_client: Redis) -> None:
    with pytest.raises(OpenSanctionsNotConfiguredError):
        OpenSanctionsProvider(
            api_url=_API_URL,
            api_key=None,
            resilience=AdapterResilience(redis_client, provider="opensanctions-noconf"),
            client=httpx.AsyncClient(),
        )


@respx.mock
async def test_no_match_is_pass(redis_client: Redis) -> None:
    respx.post(f"{_API_URL}/match/default").mock(
        return_value=httpx.Response(200, json={"responses": {"q1": {"results": []}}})
    )
    outcome = await _provider(redis_client).check(
        legal_name="Acme Trading Ltd", country="DE"
    )
    assert outcome.verdict is Verdict.PASS
    assert outcome.evidence == {"dataset": "default", "match_count": 0, "matches": []}
    assert outcome.provenance.method is ProvenanceMethod.API


@respx.mock
async def test_strong_match_is_fail(redis_client: Redis) -> None:
    respx.post(f"{_API_URL}/match/default").mock(
        return_value=httpx.Response(
            200,
            json={
                "responses": {
                    "q1": {
                        "results": [
                            {
                                "id": "Q123",
                                "caption": "Sanctioned Entity LLC",
                                "match": True,
                                "score": 0.93,
                                "datasets": ["us_ofac_sdn"],
                            }
                        ]
                    }
                }
            },
        )
    )
    outcome = await _provider(redis_client).check(
        legal_name="Sanctioned Entity LLC", country=None
    )
    assert outcome.verdict is Verdict.FAIL
    assert outcome.evidence is not None
    assert outcome.evidence["match_count"] == 1
    assert outcome.evidence["matches"][0]["id"] == "Q123"
    assert outcome.provenance.confidence == 0.93


@respx.mock
async def test_below_threshold_match_is_pass(redis_client: Redis) -> None:
    respx.post(f"{_API_URL}/match/default").mock(
        return_value=httpx.Response(
            200,
            json={
                "responses": {
                    "q1": {
                        "results": [
                            {
                                "id": "Q999",
                                "caption": "Loosely Similar Name Inc",
                                "match": True,
                                "score": 0.4,
                            }
                        ]
                    }
                }
            },
        )
    )
    outcome = await _provider(redis_client).check(
        legal_name="Acme Trading Ltd", country="DE"
    )
    assert outcome.verdict is Verdict.PASS


@respx.mock
async def test_server_error_raises_transient_after_retries(redis_client: Redis) -> None:
    route = respx.post(f"{_API_URL}/match/default").mock(
        return_value=httpx.Response(500)
    )
    provider = OpenSanctionsProvider(
        api_url=_API_URL,
        api_key="test-key",
        resilience=AdapterResilience(
            redis_client, provider="opensanctions-500", max_attempts=2
        ),
        client=httpx.AsyncClient(),
    )
    with pytest.raises(TransientAdapterError):
        await provider.check(legal_name="Acme Trading Ltd", country="DE")
    assert route.call_count == 2
