"""OpenSanctions-backed sanctions/AML screening.

A sanctions hit (`match: true` on any result at or above the match
threshold) is Verdict.FAIL — this is the rule-4 blocking gate. A provider
error propagates rather than defaulting to PASS: an unreachable sanctions
API is a reason to hold for human review, never a reason to wave a buyer
through silently.

NOTE: the request/response shape below is modeled on OpenSanctions'
documented yente match API (POST /match/{dataset}). This has not been tested
against the live API in this session — no API key is configured. Confirm
the current OpenSanctions API contract before pointing this at a real key
and production sanctions data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from verdantis.core.adapters.resilience import AdapterResilience, TransientAdapterError
from verdantis.core.verification.base import SanctionsProvider, VerificationOutcome
from verdantis.db.enums import ProvenanceMethod, Verdict
from verdantis.db.provenance import Provenance

_MATCH_THRESHOLD = 0.7


class OpenSanctionsNotConfiguredError(Exception):
    """Raised when the sanctions provider is used without an API key.

    Deliberately loud rather than a silent no-op: a misconfigured sanctions
    check must fail closed, not silently skip the blocking gate (rule 4).
    """


class OpenSanctionsProvider(SanctionsProvider):
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str | None,
        resilience: AdapterResilience,
        client: httpx.AsyncClient,
        dataset: str = "default",
    ) -> None:
        if not api_key:
            raise OpenSanctionsNotConfiguredError(
                "OpenSanctions API key is not configured; refusing to run "
                "sanctions screening without a configured provider"
            )
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._resilience = resilience
        self._client = client
        self._dataset = dataset

    async def check(
        self, *, legal_name: str, country: str | None
    ) -> VerificationOutcome:
        async def _do_request() -> httpx.Response:
            properties: dict[str, list[str]] = {"name": [legal_name]}
            if country:
                properties["country"] = [country]
            try:
                response = await self._client.post(
                    f"{self._api_url}/match/{self._dataset}",
                    headers={"Authorization": f"ApiKey {self._api_key}"},
                    json={
                        "queries": {
                            "q1": {"schema": "Company", "properties": properties}
                        }
                    },
                )
            except httpx.TimeoutException as exc:
                raise TransientAdapterError(
                    f"OpenSanctions request timed out: {exc}"
                ) from exc
            except httpx.ConnectError as exc:
                raise TransientAdapterError(
                    f"OpenSanctions connection failed: {exc}"
                ) from exc
            if response.status_code >= 500:
                raise TransientAdapterError(
                    f"OpenSanctions returned {response.status_code}"
                )
            response.raise_for_status()
            return response

        response = await self._resilience.call(_do_request)
        payload = response.json()
        results: list[dict[str, Any]] = (
            payload.get("responses", {}).get("q1", {}).get("results", [])
        )

        hits = [
            r
            for r in results
            if r.get("match") and r.get("score", 0) >= _MATCH_THRESHOLD
        ]
        verdict = Verdict.FAIL if hits else Verdict.PASS
        confidence = min(max((h.get("score", 0.0) for h in hits), default=0.95), 1.0)

        return VerificationOutcome(
            verdict=verdict,
            evidence={
                "dataset": self._dataset,
                "match_count": len(hits),
                "matches": [
                    {
                        "id": h.get("id"),
                        "caption": h.get("caption"),
                        "score": h.get("score"),
                        "datasets": h.get("datasets"),
                    }
                    for h in hits
                ],
            },
            provenance=Provenance(
                source=f"opensanctions:{self._dataset}",
                retrieved_at=datetime.now(UTC),
                confidence=confidence,
                method=ProvenanceMethod.API,
            ),
        )
