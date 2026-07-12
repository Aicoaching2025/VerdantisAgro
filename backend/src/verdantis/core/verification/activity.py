"""Genuine trade-activity verification — derived from a company's already-
ingested TradeSignal rows, not a live external call.

Per the scope doc: a company with real recent import volume of the relevant
commodity is simultaneously the hottest lead and the strongest credibility
signal — discovery and verification consume the same data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from verdantis.core.verification.base import VerificationOutcome
from verdantis.db.enums import ProvenanceMethod, SignalBand, SignalType, Verdict
from verdantis.db.models import TradeSignal
from verdantis.db.provenance import Provenance

_STRONG_BANDS = {SignalBand.HIGH, SignalBand.VERY_HIGH}
_WEAK_RECENCY_BANDS = {SignalBand.LOW}


def assess_trade_activity(signals: list[TradeSignal]) -> VerificationOutcome:
    """Compute a TRADE_ACTIVITY verdict from a company's existing TradeSignal rows.

    PASS: recent (non-LOW recency) shipment activity at HIGH/VERY_HIGH volume
    or frequency for at least one commodity.
    INCONCLUSIVE: some trade signals exist but don't clear that bar.
    FAIL: no trade signals at all — no evidence of genuine import activity.
    """
    if not signals:
        return VerificationOutcome(
            verdict=Verdict.FAIL,
            evidence={"signal_count": 0},
            provenance=_provenance(confidence=1.0),
        )

    by_commodity: dict[str | None, list[TradeSignal]] = {}
    for signal in signals:
        by_commodity.setdefault(signal.commodity, []).append(signal)

    qualifying_commodities = []
    for commodity, commodity_signals in by_commodity.items():
        recency = _latest(commodity_signals, SignalType.RECENCY)
        volume = _latest(commodity_signals, SignalType.SHIPMENT_VOLUME)
        frequency = _latest(commodity_signals, SignalType.SHIPMENT_FREQUENCY)

        recent_enough = recency is not None and recency.band not in _WEAK_RECENCY_BANDS
        strong_volume = volume is not None and volume.band in _STRONG_BANDS
        strong_frequency = frequency is not None and frequency.band in _STRONG_BANDS

        if recent_enough and (strong_volume or strong_frequency):
            qualifying_commodities.append(commodity)

    verdict = Verdict.PASS if qualifying_commodities else Verdict.INCONCLUSIVE

    return VerificationOutcome(
        verdict=verdict,
        evidence={
            "signal_count": len(signals),
            "qualifying_commodities": qualifying_commodities,
        },
        provenance=_provenance(confidence=0.9),
    )


def _latest(signals: list[TradeSignal], signal_type: SignalType) -> TradeSignal | None:
    matching = [s for s in signals if s.signal_type == signal_type]
    if not matching:
        return None
    return max(matching, key=lambda s: s.created_at)


def _provenance(*, confidence: float) -> Provenance:
    return Provenance(
        source="derived:trade_signals",
        retrieved_at=datetime.now(UTC),
        confidence=confidence,
        method=ProvenanceMethod.DERIVED,
    )
