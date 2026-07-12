from __future__ import annotations

from datetime import UTC, datetime

from verdantis.core.verification.activity import assess_trade_activity
from verdantis.db.enums import ProvenanceMethod, SignalBand, SignalType, Verdict
from verdantis.db.models import TradeSignal


def _signal(
    signal_type: SignalType,
    band: SignalBand | None,
    *,
    commodity: str = "cocoa",
    created_at: datetime = datetime(2025, 1, 1, tzinfo=UTC),
) -> TradeSignal:
    return TradeSignal(
        signal_type=signal_type,
        band=band,
        commodity=commodity,
        source="test",
        retrieved_at=created_at,
        confidence=0.9,
        method=ProvenanceMethod.DERIVED,
        created_at=created_at,
    )


def test_no_signals_is_fail() -> None:
    outcome = assess_trade_activity([])
    assert outcome.verdict is Verdict.FAIL
    assert outcome.evidence == {"signal_count": 0}


def test_strong_volume_and_recent_is_pass() -> None:
    signals = [
        _signal(SignalType.RECENCY, SignalBand.HIGH),
        _signal(SignalType.SHIPMENT_VOLUME, SignalBand.HIGH),
    ]
    outcome = assess_trade_activity(signals)
    assert outcome.verdict is Verdict.PASS
    assert outcome.evidence is not None
    assert outcome.evidence["qualifying_commodities"] == ["cocoa"]


def test_strong_frequency_and_recent_is_pass() -> None:
    signals = [
        _signal(SignalType.RECENCY, SignalBand.VERY_HIGH),
        _signal(SignalType.SHIPMENT_FREQUENCY, SignalBand.VERY_HIGH),
    ]
    outcome = assess_trade_activity(signals)
    assert outcome.verdict is Verdict.PASS


def test_weak_volume_is_inconclusive() -> None:
    signals = [
        _signal(SignalType.RECENCY, SignalBand.HIGH),
        _signal(SignalType.SHIPMENT_VOLUME, SignalBand.LOW),
    ]
    outcome = assess_trade_activity(signals)
    assert outcome.verdict is Verdict.INCONCLUSIVE


def test_stale_recency_is_inconclusive_even_with_strong_volume() -> None:
    signals = [
        _signal(SignalType.RECENCY, SignalBand.LOW),
        _signal(SignalType.SHIPMENT_VOLUME, SignalBand.VERY_HIGH),
    ]
    outcome = assess_trade_activity(signals)
    assert outcome.verdict is Verdict.INCONCLUSIVE


def test_latest_signal_wins_when_duplicates_exist() -> None:
    # An older HIGH recency signal superseded by a newer LOW one should not
    # qualify — assess_trade_activity must use the latest, not just any.
    signals = [
        _signal(
            SignalType.RECENCY,
            SignalBand.HIGH,
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
        ),
        _signal(
            SignalType.RECENCY,
            SignalBand.LOW,
            created_at=datetime(2025, 6, 1, tzinfo=UTC),
        ),
        _signal(SignalType.SHIPMENT_VOLUME, SignalBand.VERY_HIGH),
    ]
    outcome = assess_trade_activity(signals)
    assert outcome.verdict is Verdict.INCONCLUSIVE


def test_qualifying_commodity_is_independent_of_non_qualifying_one() -> None:
    signals = [
        _signal(SignalType.RECENCY, SignalBand.HIGH, commodity="cocoa"),
        _signal(SignalType.SHIPMENT_VOLUME, SignalBand.HIGH, commodity="cocoa"),
        _signal(SignalType.RECENCY, SignalBand.LOW, commodity="sesame"),
        _signal(SignalType.SHIPMENT_VOLUME, SignalBand.VERY_HIGH, commodity="sesame"),
    ]
    outcome = assess_trade_activity(signals)
    assert outcome.verdict is Verdict.PASS
    assert outcome.evidence is not None
    assert outcome.evidence["qualifying_commodities"] == ["cocoa"]
