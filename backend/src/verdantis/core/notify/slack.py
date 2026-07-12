"""Slack notification for high-confidence inbound leads.

Internal-only message to the sales team's Slack channel via an incoming
webhook — it never reaches an external party, so it isn't gated by the
outbound-send approval rule (CLAUDE.md rule 1's inbound exception covers
internal routing explicitly). Routed through the same AdapterResilience
wrapper as every other external call.

NOTE: modeled on Slack's documented incoming-webhook API (POST <webhook_url>
with a {"text": ...} payload). No webhook URL is configured in this
environment — contract-tested against a mocked endpoint only.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from verdantis.core.adapters.resilience import AdapterResilience, TransientAdapterError


class SlackNotConfiguredError(Exception):
    """Raised when the Slack notifier is used without a webhook URL."""


class SlackNotifier(Protocol):
    async def notify_new_lead(
        self,
        *,
        legal_name: str,
        country: str | None,
        requested_commodity: str,
        fit_score: float,
    ) -> None: ...


class SlackWebhookNotifier:
    def __init__(
        self,
        *,
        webhook_url: str | None,
        resilience: AdapterResilience,
        client: httpx.AsyncClient,
    ) -> None:
        if not webhook_url:
            raise SlackNotConfiguredError("Slack webhook URL is not configured")
        self._webhook_url = webhook_url
        self._resilience = resilience
        self._client = client

    async def notify_new_lead(
        self,
        *,
        legal_name: str,
        country: str | None,
        requested_commodity: str,
        fit_score: float,
    ) -> None:
        text = (
            f":seedling: New inbound lead: *{legal_name}* "
            f"({country or 'country unknown'}) — wants {requested_commodity}. "
            f"Fit score: {fit_score:.2f}"
        )
        await self._resilience.call(lambda: self._post(text))

    async def _post(self, text: str) -> httpx.Response:
        try:
            response = await self._client.post(self._webhook_url, json={"text": text})
        except httpx.TimeoutException as exc:
            raise TransientAdapterError(f"Slack webhook timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise TransientAdapterError(
                f"Slack webhook connection failed: {exc}"
            ) from exc
        if response.status_code >= 500:
            raise TransientAdapterError(
                f"Slack webhook returned {response.status_code}"
            )
        response.raise_for_status()
        return response
