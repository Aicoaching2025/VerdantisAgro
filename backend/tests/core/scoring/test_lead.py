from __future__ import annotations

import json
import uuid

import pytest

from verdantis.core.scoring.fit import FitScoreParseError
from verdantis.core.scoring.lead import score_lead
from verdantis.db.enums import PaymentTerms
from verdantis.models.dossier import CompanyDossier


class _FakeLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_user: str | None = None

    async def complete(self, *, system: str, user: str, max_tokens: int = 1024) -> str:
        self.last_user = user
        return self.response


def _dossier() -> CompanyDossier:
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
        trade_signals=[],
        verification_results=[],
    )


async def test_parses_valid_response() -> None:
    client = _FakeLLMClient(
        json.dumps({"score": 0.7, "reasons": ["Requested commodity matches"]})
    )
    result = await score_lead(
        client,
        _dossier(),
        requested_commodity="cocoa",
        requested_volume="1 container",
        incoterm=None,
        payment_terms=PaymentTerms.LC,
        message="Interested in a trial order",
    )
    assert result.score == 0.7
    assert result.reasons == ["Requested commodity matches"]


async def test_prompt_includes_submission_fields() -> None:
    client = _FakeLLMClient(json.dumps({"score": 0.5, "reasons": []}))
    await score_lead(
        client,
        _dossier(),
        requested_commodity="cocoa",
        requested_volume="1 container",
        incoterm=None,
        payment_terms=PaymentTerms.LC,
        message="Interested in a trial order",
    )
    assert client.last_user is not None
    assert "cocoa" in client.last_user
    assert "Interested in a trial order" in client.last_user
    assert "LC" in client.last_user


async def test_malformed_json_raises_parse_error() -> None:
    client = _FakeLLMClient("not json")
    with pytest.raises(FitScoreParseError):
        await score_lead(
            client,
            _dossier(),
            requested_commodity="cocoa",
            requested_volume=None,
            incoterm=None,
            payment_terms=PaymentTerms.OTHER,
            message=None,
        )
