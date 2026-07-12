from __future__ import annotations

import uuid
from datetime import UTC, datetime

from verdantis.core.outreach.draft import draft_outreach
from verdantis.db.enums import SignalBand, SignalType
from verdantis.models.dossier import CompanyDossier, TradeSignalView


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
        verification_results=[],
    )


async def test_returns_stripped_body() -> None:
    client = _FakeLLMClient("  Hello, we noticed your cocoa imports...  \n")
    draft = await draft_outreach(client, _dossier(), fit_reasons=["high volume"])
    assert draft.body == "Hello, we noticed your cocoa imports..."


async def test_prompt_includes_dossier_and_fit_reasons() -> None:
    client = _FakeLLMClient("draft body")
    await draft_outreach(client, _dossier(), fit_reasons=["strong recent activity"])
    assert client.last_user is not None
    assert "cocoa" in client.last_user
    assert "strong recent activity" in client.last_user
    assert "Acme Trading Ltd" in client.last_user
