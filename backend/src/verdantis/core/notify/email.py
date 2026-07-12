"""Transactional acknowledgment email to inbound-form submitters.

Fixed, non-marketing template only — CLAUDE.md rule 1's inbound exception is
scoped exactly to this: a "we received your inquiry" receipt, never
LLM-drafted, never carrying sales copy. `render_inquiry_ack` is the only
place that produces the subject/body; nothing else in this module composes
message content. Uses Resend's REST API behind an `EmailSender` Protocol, so
swapping providers (SES, Postmark) only touches this module.

NOTE: modeled on Resend's documented API (POST https://api.resend.com/emails).
No API key is configured in this environment — contract-tested against a
mocked endpoint only.
"""

from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from verdantis.core.adapters.resilience import AdapterResilience, TransientAdapterError


class EmailNotConfiguredError(Exception):
    """Raised when the email sender is used without an API key."""


class EmailSendResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    message_id: str


class EmailSender(Protocol):
    async def send(
        self, *, to: str, from_email: str, from_name: str, subject: str, body: str
    ) -> EmailSendResult: ...


def render_inquiry_ack(*, contact_name: str, legal_name: str) -> tuple[str, str]:
    """Returns (subject, body). Fixed template — see module docstring."""
    subject = "We received your inquiry - Verdantis Agro Produce"
    body = (
        f"Hi {contact_name},\n\n"
        f"Thanks for reaching out to Verdantis Agro Produce on behalf of "
        f"{legal_name}. We've received your inquiry and a member of our team "
        f"will follow up shortly.\n\n"
        f"- Verdantis Agro Produce"
    )
    return subject, body


class ResendEmailClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        resilience: AdapterResilience,
        client: httpx.AsyncClient,
        base_url: str = "https://api.resend.com",
    ) -> None:
        if not api_key:
            raise EmailNotConfiguredError("Resend API key is not configured")
        self._api_key = api_key
        self._resilience = resilience
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def send(
        self, *, to: str, from_email: str, from_name: str, subject: str, body: str
    ) -> EmailSendResult:
        response = await self._resilience.call(
            lambda: self._post(
                to=to,
                from_email=from_email,
                from_name=from_name,
                subject=subject,
                body=body,
            )
        )
        data = response.json()
        return EmailSendResult(message_id=data["id"])

    async def _post(
        self, *, to: str, from_email: str, from_name: str, subject: str, body: str
    ) -> httpx.Response:
        payload = {
            "from": f"{from_name} <{from_email}>",
            "to": [to],
            "subject": subject,
            "text": body,
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise TransientAdapterError(f"Resend request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise TransientAdapterError(f"Resend connection failed: {exc}") from exc
        if response.status_code >= 500:
            raise TransientAdapterError(f"Resend returned {response.status_code}")
        response.raise_for_status()
        return response
