"""ManualExportAdapter tests against a synthetic (never real) shipment CSV.

Expected values below are hand-computed against the fixture data so this
verifies the actual derivation math (bands, recency, trend), not just that
the adapter runs without crashing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

from verdantis.core.adapters.manual_export import ManualExportAdapter
from verdantis.db.enums import ProvenanceMethod, SignalBand, SignalType

_CSV = """company_name,country,commodity,shipment_date,volume_kg
Acme Trading Ltd,DE,cocoa,2025-01-15,5000
Acme Trading Ltd,DE,cocoa,2025-03-10,8000
Acme Trading Ltd,DE,cocoa,2025-05-20,12000
Acme Trading Ltd,DE,sesame,2025-02-01,500
Beta Imports GmbH,FR,cocoa,2025-06-01,50000
"""

_RETRIEVED_AT = datetime(2025, 7, 1, tzinfo=UTC)


def _adapter(csv_text: str = _CSV) -> ManualExportAdapter:
    return ManualExportAdapter(
        StringIO(csv_text),
        source="manual_export:test_provider_2025Q2",
        export_retrieved_at=_RETRIEVED_AT,
        confidence=0.9,
    )


async def test_derives_expected_signals_for_acme_cocoa() -> None:
    signals = await _adapter().fetch_signals(commodities=["cocoa"])
    acme = [s for s in signals if s.company_legal_name == "Acme Trading Ltd"]
    by_type = {s.signal_type: s for s in acme}

    assert set(by_type) == {
        SignalType.COMMODITY_MATCH,
        SignalType.SHIPMENT_VOLUME,
        SignalType.SHIPMENT_FREQUENCY,
        SignalType.RECENCY,
        SignalType.TREND,
    }

    volume = by_type[SignalType.SHIPMENT_VOLUME]
    assert volume.numeric_value == 25000
    assert volume.band == SignalBand.HIGH

    frequency = by_type[SignalType.SHIPMENT_FREQUENCY]
    assert frequency.numeric_value == 3
    assert frequency.band == SignalBand.MEDIUM

    recency = by_type[SignalType.RECENCY]
    assert recency.numeric_value == 42  # days between 2025-05-20 and 2025-07-01
    assert recency.band == SignalBand.HIGH

    trend = by_type[SignalType.TREND]
    assert trend.numeric_value is not None
    assert trend.numeric_value < 0
    assert trend.details is not None
    assert trend.details["direction"] == "decreasing"

    for signal in acme:
        assert signal.commodity == "cocoa"
        assert signal.company_country == "DE"
        assert signal.period_start.isoformat() == "2025-01-15"
        assert signal.period_end.isoformat() == "2025-05-20"


async def test_derives_signals_for_single_shipment_company() -> None:
    signals = await _adapter().fetch_signals(commodities=["cocoa"])
    beta = [s for s in signals if s.company_legal_name == "Beta Imports GmbH"]
    by_type = {s.signal_type: s for s in beta}

    assert by_type[SignalType.SHIPMENT_VOLUME].numeric_value == 50000
    assert by_type[SignalType.SHIPMENT_VOLUME].band == SignalBand.HIGH
    assert by_type[SignalType.SHIPMENT_FREQUENCY].numeric_value == 1
    assert by_type[SignalType.SHIPMENT_FREQUENCY].band == SignalBand.LOW
    assert by_type[SignalType.RECENCY].numeric_value == 30
    assert (
        by_type[SignalType.RECENCY].band == SignalBand.VERY_HIGH
    )  # threshold inclusive


async def test_filters_out_commodities_not_requested() -> None:
    signals = await _adapter().fetch_signals(commodities=["cocoa"])
    assert all(s.commodity != "sesame" for s in signals)

    signals_with_sesame = await _adapter().fetch_signals(
        commodities=["cocoa", "sesame"]
    )
    assert any(s.commodity == "sesame" for s in signals_with_sesame)


async def test_filters_by_region() -> None:
    signals = await _adapter().fetch_signals(commodities=["cocoa"], regions=["DE"])
    companies = {s.company_legal_name for s in signals}
    assert companies == {"Acme Trading Ltd"}


async def test_provenance_is_stamped_from_constructor_args() -> None:
    signals = await _adapter().fetch_signals(commodities=["cocoa"])
    assert signals
    for signal in signals:
        assert signal.provenance.source == "manual_export:test_provider_2025Q2"
        assert signal.provenance.retrieved_at == _RETRIEVED_AT
        assert signal.provenance.confidence == 0.9
        assert signal.provenance.method is ProvenanceMethod.DERIVED
