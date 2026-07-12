from __future__ import annotations

import json

import pytest

from verdantis.core.scoring.fit import FitScoreParseError, score_fit
from verdantis.db.enums import CheckType, SignalBand, SignalType, Verdict
from verdantis.models.dossier import (
    CompanyDossier,
    TradeSignalView,
    VerificationVerdictView,
)


class _FakeLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        self.last_system = system
        self.last_user = user
        return self.response


def _dossier() -> CompanyDossier:
    import uuid
    from datetime import UTC, datetime

    return CompanyDossier(
        company_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        legal_name="Acme Trading Ltd",
        display_name=None,
        country="DE",
        vat_number=None,
        eori_number=None,
        duns_number=None,
        is_sanctioned=False,
        sanctions_review_suggested=False,
        credibility_score=None,
        trade_signals=[
            TradeSignalView(
                signal_type=SignalType.SHIPMENT_VOLUME,
                commodity="cocoa",
                band=SignalBand.HIGH,
                numeric_value=25000,
                period_start=None,
                period_end=None,
                details=None,
                source="test",
                retrieved_at=datetime.now(UTC),
                confidence=0.9,
            )
        ],
        verification_results=[
            VerificationVerdictView(
                check_type=CheckType.SANCTIONS_AML,
                verdict=Verdict.PASS,
                evidence=None,
                source="test",
                retrieved_at=datetime.now(UTC),
                confidence=0.95,
            )
        ],
    )


async def test_parses_valid_response() -> None:
    client = _FakeLLMClient(
        json.dumps(
            {"score": 0.85, "reasons": ["High cocoa volume", "Clean sanctions check"]}
        )
    )
    result = await score_fit(client, _dossier())
    assert result.score == 0.85
    assert result.reasons == ["High cocoa volume", "Clean sanctions check"]


async def test_prompt_includes_dossier_signals() -> None:
    client = _FakeLLMClient(json.dumps({"score": 0.5, "reasons": []}))
    await score_fit(client, _dossier())
    assert client.last_user is not None
    assert "cocoa" in client.last_user
    assert "Acme Trading Ltd" in client.last_user


async def test_malformed_json_raises_parse_error() -> None:
    client = _FakeLLMClient("not json at all")
    with pytest.raises(FitScoreParseError):
        await score_fit(client, _dossier())


async def test_missing_fields_raises_parse_error() -> None:
    client = _FakeLLMClient(json.dumps({"score": 0.5}))  # no "reasons"
    with pytest.raises(FitScoreParseError):
        await score_fit(client, _dossier())


async def test_out_of_range_score_raises_parse_error() -> None:
    client = _FakeLLMClient(json.dumps({"score": 1.5, "reasons": ["bad"]}))
    with pytest.raises(FitScoreParseError):
        await score_fit(client, _dossier())
