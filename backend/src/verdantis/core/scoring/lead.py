"""LLM-backed inbound lead scoring: how promising a submitted inquiry is,
given both the verified dossier (if any prior signal exists for this
company) and what the submitter themselves stated (commodity, volume,
Incoterm, payment terms, message). Uses the cheap model per CLAUDE.md's
model-routing convention, same as outbound fit scoring — this is
classification, not drafting.

Reuses `FitScoreResult` / `FitScoreParseError` / `parse_score_response` from
`core.scoring.fit`: the response shape and parse-failure semantics are
identical, only the prompt differs.
"""

from __future__ import annotations

import json

from verdantis.core.llm.client import LLMClient
from verdantis.core.scoring.fit import (
    FitScoreParseError,
    FitScoreResult,
    parse_score_response,
)
from verdantis.db.enums import Incoterm, PaymentTerms
from verdantis.models.dossier import CompanyDossier

__all__ = ["FitScoreParseError", "FitScoreResult", "score_lead"]

_SYSTEM_PROMPT = (
    "You are scoring how promising an inbound buyer inquiry is for a "
    "commodity exporter, using the submitter's own stated intent plus any "
    "verified trade-intelligence already on file for their company. "
    'Respond with ONLY a JSON object: {"score": <float 0.0-1.0>, "reasons": '
    "[<string>, ...]}. Weigh: whether the requested commodity is one the "
    "exporter actually sells, plausibility of the stated volume, whether "
    "Incoterm/payment terms were given at all (vague or missing terms are a "
    "weaker signal), and any prior verified trade signals on file. Do not "
    "invent facts not present in the input."
)


async def score_lead(
    client: LLMClient,
    dossier: CompanyDossier,
    *,
    requested_commodity: str,
    requested_volume: str | None,
    incoterm: Incoterm | None,
    payment_terms: PaymentTerms,
    message: str | None,
) -> FitScoreResult:
    raw = await client.complete(
        system=_SYSTEM_PROMPT,
        user=_build_prompt(
            dossier,
            requested_commodity=requested_commodity,
            requested_volume=requested_volume,
            incoterm=incoterm,
            payment_terms=payment_terms,
            message=message,
        ),
        max_tokens=512,
    )
    return parse_score_response(raw)


def _build_prompt(
    dossier: CompanyDossier,
    *,
    requested_commodity: str,
    requested_volume: str | None,
    incoterm: Incoterm | None,
    payment_terms: PaymentTerms,
    message: str | None,
) -> str:
    payload = {
        "submission": {
            "requested_commodity": requested_commodity,
            "requested_volume": requested_volume,
            "incoterm": incoterm.value if incoterm else None,
            "payment_terms": payment_terms.value,
            "message": message,
        },
        "company": {
            "legal_name": dossier.legal_name,
            "country": dossier.country,
            "is_sanctioned": dossier.is_sanctioned,
        },
        "prior_trade_signals": [
            {
                "signal_type": s.signal_type.value,
                "commodity": s.commodity,
                "band": s.band.value if s.band else None,
            }
            for s in dossier.trade_signals
        ],
        "verification_results": [
            {"check_type": v.check_type.value, "verdict": v.verdict.value}
            for v in dossier.verification_results
        ],
    }
    return json.dumps(payload)
