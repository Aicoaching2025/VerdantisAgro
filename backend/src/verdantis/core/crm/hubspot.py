"""HubSpot CRM sync.

Upserts a Company (and, if a decision-maker was resolved, a Contact)
representing an approved lead, using HubSpot's CRM v3 batch-upsert API.
This only runs after a human has approved the outbound send (rule 1) — it's
the sync_crm node's job, never triggered independently.

NOTE: modeled on HubSpot's documented CRM v3 batch-upsert API shape
(POST /crm/v3/objects/{type}/batch/upsert). This has not been tested against
the live API in this session — no access token is configured. Confirm the
current API contract before pointing this at a real token.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from verdantis.core.adapters.resilience import AdapterResilience, TransientAdapterError


class HubSpotNotConfiguredError(Exception):
    """Raised when the HubSpot client is used without an access token."""


class HubSpotSyncResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    object_type: str
    hubspot_id: str


class CrmSyncClient(Protocol):
    """What the outbound graph's sync_crm node depends on — a Protocol, not
    the concrete HubSpotClient, so a fake satisfies it in tests without
    inheriting from anything (same pattern as core.llm.client.LLMClient)."""

    async def upsert_company(
        self, *, legal_name: str, properties: dict[str, Any]
    ) -> HubSpotSyncResult: ...

    async def upsert_contact(
        self, *, email: str, properties: dict[str, Any]
    ) -> HubSpotSyncResult: ...


class HubSpotClient:
    def __init__(
        self,
        *,
        access_token: str | None,
        resilience: AdapterResilience,
        client: httpx.AsyncClient,
        base_url: str = "https://api.hubapi.com",
    ) -> None:
        if not access_token:
            raise HubSpotNotConfiguredError("HubSpot access token is not configured")
        self._access_token = access_token
        self._resilience = resilience
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def upsert_company(
        self, *, legal_name: str, properties: dict[str, Any]
    ) -> HubSpotSyncResult:
        response = await self._resilience.call(
            lambda: self._batch_upsert(
                "companies",
                id_property="name",
                id_value=legal_name,
                properties={"name": legal_name, **properties},
            )
        )
        return _parse_batch_upsert_result(response, object_type="company")

    async def upsert_contact(
        self, *, email: str, properties: dict[str, Any]
    ) -> HubSpotSyncResult:
        response = await self._resilience.call(
            lambda: self._batch_upsert(
                "contacts",
                id_property="email",
                id_value=email,
                properties={"email": email, **properties},
            )
        )
        return _parse_batch_upsert_result(response, object_type="contact")

    async def _batch_upsert(
        self,
        object_type: str,
        *,
        id_property: str,
        id_value: str,
        properties: dict[str, Any],
    ) -> httpx.Response:
        payload = {
            "inputs": [
                {"idProperty": id_property, "id": id_value, "properties": properties}
            ]
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/crm/v3/objects/{object_type}/batch/upsert",
                headers={"Authorization": f"Bearer {self._access_token}"},
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise TransientAdapterError(f"HubSpot request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise TransientAdapterError(f"HubSpot connection failed: {exc}") from exc
        if response.status_code >= 500:
            raise TransientAdapterError(f"HubSpot returned {response.status_code}")
        response.raise_for_status()
        return response


def _parse_batch_upsert_result(
    response: httpx.Response, *, object_type: str
) -> HubSpotSyncResult:
    data = response.json()
    result = data["results"][0]
    return HubSpotSyncResult(object_type=object_type, hubspot_id=result["id"])
