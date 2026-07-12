"""Contract tests for OpenCorporatesProvider against mocked HTTP responses.

No live api_token is configured in this environment — these verify the
response mapping logic against the assumed API shape (see the NOTE in
corporate.py), not the real OpenCorporates API itself.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from redis.asyncio import Redis

from verdantis.core.adapters.resilience import AdapterResilience
from verdantis.core.verification.corporate import (
    OpenCorporatesNotConfiguredError,
    OpenCorporatesProvider,
)
from verdantis.db.enums import Verdict

_BASE_URL = "https://corporates.test/v0.4"


def _provider(redis_client: Redis) -> OpenCorporatesProvider:
    return OpenCorporatesProvider(
        api_token="test-token",
        resilience=AdapterResilience(redis_client, provider="opencorporates-test"),
        client=httpx.AsyncClient(),
        base_url=_BASE_URL,
    )


def test_missing_api_token_raises_not_configured(redis_client: Redis) -> None:
    with pytest.raises(OpenCorporatesNotConfiguredError):
        OpenCorporatesProvider(
            api_token=None,
            resilience=AdapterResilience(redis_client, provider="opencorp-noconf"),
            client=httpx.AsyncClient(),
        )


@respx.mock
async def test_active_company_found_is_pass(redis_client: Redis) -> None:
    respx.get(f"{_BASE_URL}/companies/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": {
                    "companies": [
                        {
                            "company": {
                                "name": "Acme Trading Ltd",
                                "company_number": "12345",
                                "jurisdiction_code": "de",
                                "current_status": "Active",
                            }
                        }
                    ]
                }
            },
        )
    )
    outcome = await _provider(redis_client).check(
        legal_name="Acme Trading Ltd", country="DE"
    )
    assert outcome.verdict is Verdict.PASS
    assert outcome.evidence is not None
    assert outcome.evidence["company_number"] == "12345"


@respx.mock
async def test_dissolved_company_is_fail(redis_client: Redis) -> None:
    respx.get(f"{_BASE_URL}/companies/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": {
                    "companies": [
                        {
                            "company": {
                                "name": "Defunct Co",
                                "company_number": "999",
                                "current_status": "Dissolved",
                            }
                        }
                    ]
                }
            },
        )
    )
    outcome = await _provider(redis_client).check(legal_name="Defunct Co", country=None)
    assert outcome.verdict is Verdict.FAIL


@respx.mock
async def test_no_results_is_inconclusive(redis_client: Redis) -> None:
    respx.get(f"{_BASE_URL}/companies/search").mock(
        return_value=httpx.Response(200, json={"results": {"companies": []}})
    )
    outcome = await _provider(redis_client).check(
        legal_name="Totally Unknown Entity", country=None
    )
    assert outcome.verdict is Verdict.INCONCLUSIVE
