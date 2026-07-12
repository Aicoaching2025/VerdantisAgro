"""LLM-backed outreach draft generation. Uses the stronger model per
CLAUDE.md's model-routing convention — drafting is worth the better model,
unlike classification.

The draft this produces is NEVER sent automatically — it's exactly what a
human sees at the interrupt() approval node (rule 1). This module only
generates text; it has no send capability at all.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from verdantis.core.llm.client import LLMClient
from verdantis.models.dossier import CompanyDossier

_SYSTEM_PROMPT = (
    "You draft a first outreach email from a commodity exporter to a "
    "prospective buyer, based on verified trade-intelligence signals about "
    "that buyer. Write ONLY the email body (no subject line, no preamble, "
    "no signature block). Reference specific, verified signals from the "
    "dossier (commodity, shipment activity) — never invent facts not "
    "present in it. Keep it under 150 words, professional, no hard sell."
)


class OutreachDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    body: str


async def draft_outreach(
    client: LLMClient, dossier: CompanyDossier, *, fit_reasons: list[str]
) -> OutreachDraft:
    body = await client.complete(
        system=_SYSTEM_PROMPT,
        user=_build_prompt(dossier, fit_reasons),
        max_tokens=400,
    )
    return OutreachDraft(body=body.strip())


def _build_prompt(dossier: CompanyDossier, fit_reasons: list[str]) -> str:
    payload = {
        "legal_name": dossier.legal_name,
        "country": dossier.country,
        "fit_reasons": fit_reasons,
        "trade_signals": [
            {
                "signal_type": s.signal_type.value,
                "commodity": s.commodity,
                "band": s.band.value if s.band else None,
            }
            for s in dossier.trade_signals
        ],
    }
    return json.dumps(payload)
