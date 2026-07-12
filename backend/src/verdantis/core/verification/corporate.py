"""OpenCorporates-backed corporate existence verification.

A matching, active registry entry is PASS; a matching but dissolved/inactive
entry is FAIL; no matching entry at all is INCONCLUSIVE — OpenCorporates'
coverage is incomplete, so absence isn't proof a company doesn't exist.

NOTE: modeled on OpenCorporates' documented company-search API shape. This
has not been tested against the live API in this session — no api_token is
configured. Confirm the current API contract before pointing this at a real
token.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from verdantis.core.adapters.resilience import AdapterResilience, TransientAdapterError
from verdantis.core.verification.base import (
    CorporateExistenceProvider,
    VerificationOutcome,
)
from verdantis.db.enums import ProvenanceMethod, Verdict
from verdantis.db.provenance import Provenance

_ACTIVE_STATUSES = {"active", "good standing"}


class OpenCorporatesNotConfiguredError(Exception):
    """Raised when the corporate-existence provider is used without an api_token."""


class OpenCorporatesProvider(CorporateExistenceProvider):
    def __init__(
        self,
        *,
        api_token: str | None,
        resilience: AdapterResilience,
        client: httpx.AsyncClient,
        base_url: str = "https://api.opencorporates.com/v0.4",
    ) -> None:
        if not api_token:
            raise OpenCorporatesNotConfiguredError(
                "OpenCorporates API token is not configured"
            )
        self._api_token = api_token
        self._resilience = resilience
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def check(
        self, *, legal_name: str, country: str | None
    ) -> VerificationOutcome:
        async def _do_request() -> httpx.Response:
            params: dict[str, str] = {
                "q": legal_name,
                "api_token": self._api_token or "",
            }
            if country:
                params["jurisdiction_code"] = country.lower()
            try:
                response = await self._client.get(
                    f"{self._base_url}/companies/search", params=params
                )
            except httpx.TimeoutException as exc:
                raise TransientAdapterError(
                    f"OpenCorporates request timed out: {exc}"
                ) from exc
            except httpx.ConnectError as exc:
                raise TransientAdapterError(
                    f"OpenCorporates connection failed: {exc}"
                ) from exc
            if response.status_code >= 500:
                raise TransientAdapterError(
                    f"OpenCorporates returned {response.status_code}"
                )
            response.raise_for_status()
            return response

        response = await self._resilience.call(_do_request)
        payload = response.json()
        companies: list[dict[str, Any]] = [
            c["company"] for c in payload.get("results", {}).get("companies", [])
        ]

        if not companies:
            return VerificationOutcome(
                verdict=Verdict.INCONCLUSIVE,
                evidence={"query": legal_name, "match_count": 0},
                provenance=self._provenance(confidence=0.5),
            )

        best = companies[0]
        status = (best.get("current_status") or "").strip().lower()
        verdict = Verdict.PASS if status in _ACTIVE_STATUSES else Verdict.FAIL

        return VerificationOutcome(
            verdict=verdict,
            evidence={
                "company_number": best.get("company_number"),
                "jurisdiction_code": best.get("jurisdiction_code"),
                "current_status": best.get("current_status"),
                "name": best.get("name"),
            },
            provenance=self._provenance(confidence=0.85),
        )

    def _provenance(self, *, confidence: float) -> Provenance:
        return Provenance(
            source="opencorporates",
            retrieved_at=datetime.now(UTC),
            confidence=confidence,
            method=ProvenanceMethod.API,
        )
