"""LLM-backed fit scoring: how well a discovered company matches a tenant's
ICP, using the already-verified dossier as context. Uses the cheap model per
CLAUDE.md's model-routing convention — classification, not drafting.

A malformed LLM response raises FitScoreParseError rather than guessing a
default score — the caller (the graph node) routes that to human triage
instead of silently treating an unparseable response as a low or high score.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from verdantis.core.llm.client import LLMClient
from verdantis.models.dossier import CompanyDossier

_SYSTEM_PROMPT = (
    "You are scoring how well a company fits as a buyer lead for a "
    "commodity exporter, based on verified trade-intelligence signals. "
    'Respond with ONLY a JSON object: {"score": <float 0.0-1.0>, "reasons": '
    "[<string>, ...]}. Base the score on shipment volume/frequency bands, "
    "recency, and verification status in the dossier. Do not invent facts "
    "not present in the dossier."
)


class FitScoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str]


class FitScoreParseError(Exception):
    """Raised when the LLM's fit-score response can't be parsed."""


async def score_fit(client: LLMClient, dossier: CompanyDossier) -> FitScoreResult:
    raw = await client.complete(
        system=_SYSTEM_PROMPT, user=_build_prompt(dossier), max_tokens=512
    )
    return parse_score_response(raw)


def _build_prompt(dossier: CompanyDossier) -> str:
    payload = {
        "legal_name": dossier.legal_name,
        "country": dossier.country,
        "is_sanctioned": dossier.is_sanctioned,
        "trade_signals": [
            {
                "signal_type": s.signal_type.value,
                "commodity": s.commodity,
                "band": s.band.value if s.band else None,
                "numeric_value": s.numeric_value,
            }
            for s in dossier.trade_signals
        ],
        "verification_results": [
            {"check_type": v.check_type.value, "verdict": v.verdict.value}
            for v in dossier.verification_results
        ],
    }
    return json.dumps(payload)


def parse_score_response(raw: str) -> FitScoreResult:
    """Shared {"score", "reasons"} JSON parser — used by both fit scoring
    (outbound) and lead scoring (inbound), which return the same shape."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FitScoreParseError(
            f"could not parse fit-score response: {raw!r}"
        ) from exc
    if not isinstance(data, dict):
        raise FitScoreParseError(f"fit-score response was not a JSON object: {raw!r}")
    try:
        return FitScoreResult(score=data["score"], reasons=data["reasons"])
    except (KeyError, TypeError, ValidationError) as exc:
        raise FitScoreParseError(
            f"fit-score response missing/invalid fields: {raw!r}"
        ) from exc
