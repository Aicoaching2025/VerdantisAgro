"""Manual-export adapter: ingests a licensed provider's data via a human-
exported CSV rather than a live API call.

This is the licensing-safe ingestion pattern for trade-intel providers
(ImportYeti/Panjiva/ImportGenius/Tendata) until/unless a specific provider's
terms are confirmed to permit automated querying. A licensed analyst pulls
shipment-level data through the provider's own sanctioned export feature;
this adapter aggregates those rows into derived signals. It never returns
the raw per-shipment rows — only the aggregates (rule 2).

Expected CSV columns, one row per shipment: company_name, country (ISO-3166
alpha-2 or free text), commodity, shipment_date (ISO 8601), volume_kg.

`regions` filtering is a simple case-insensitive match against the `country`
column — this adapter does not attempt EU/APAC-style region bucketing.
Callers wanting region-group filtering should pass explicit country values.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from io import TextIOBase
from typing import TypedDict, Unpack

from verdantis.core.adapters.base import TradeDataAdapter, TradeSignalRecord
from verdantis.db.enums import ProvenanceMethod, SignalBand, SignalType
from verdantis.db.provenance import Provenance

# (upper bound inclusive, band). The last band is used for anything above
# the highest threshold.
_VOLUME_KG_BANDS: tuple[tuple[float, SignalBand], ...] = (
    (1_000, SignalBand.LOW),
    (10_000, SignalBand.MEDIUM),
    (100_000, SignalBand.HIGH),
)
_FREQUENCY_BANDS: tuple[tuple[float, SignalBand], ...] = (
    (2, SignalBand.LOW),
    (6, SignalBand.MEDIUM),
    (12, SignalBand.HIGH),
)
# Days since last shipment -> recency band. Lower is more recent = higher band.
_RECENCY_DAYS_BANDS: tuple[tuple[float, SignalBand], ...] = (
    (30, SignalBand.VERY_HIGH),
    (90, SignalBand.HIGH),
    (180, SignalBand.MEDIUM),
)


def _band_for(
    value: float,
    thresholds: tuple[tuple[float, SignalBand], ...],
    above_highest: SignalBand,
) -> SignalBand:
    for threshold, band in thresholds:
        if value <= threshold:
            return band
    return above_highest


class _CommonFields(TypedDict):
    company_legal_name: str
    company_country: str | None
    commodity: str
    period_start: date
    period_end: date
    provenance: Provenance


@dataclass(frozen=True)
class _ShipmentRow:
    company_name: str
    country: str | None
    commodity: str
    shipment_date: date
    volume_kg: float


class ManualExportAdapter(TradeDataAdapter):
    """Aggregates a human-exported shipment CSV into derived TradeSignalRecords."""

    def __init__(
        self,
        csv_file: TextIOBase,
        *,
        source: str,
        export_retrieved_at: datetime,
        confidence: float = 0.9,
    ) -> None:
        self._csv_file = csv_file
        self._source = source
        self._export_retrieved_at = export_retrieved_at
        self._confidence = confidence

    async def fetch_signals(
        self, *, commodities: list[str], regions: list[str] | None = None
    ) -> list[TradeSignalRecord]:
        rows = self._parse_rows(commodities=commodities, regions=regions)

        grouped: dict[tuple[str, str | None, str], list[_ShipmentRow]] = defaultdict(
            list
        )
        for row in rows:
            grouped[(row.company_name, row.country, row.commodity)].append(row)

        signals: list[TradeSignalRecord] = []
        for (company_name, country, commodity), company_rows in grouped.items():
            signals.extend(
                self._signals_for_company_commodity(
                    company_name, country, commodity, company_rows
                )
            )
        return signals

    def _parse_rows(
        self, *, commodities: list[str], regions: list[str] | None
    ) -> list[_ShipmentRow]:
        wanted_commodities = {c.lower() for c in commodities}
        wanted_regions = {r.lower() for r in regions} if regions else None

        reader = csv.DictReader(self._csv_file)
        rows: list[_ShipmentRow] = []
        for raw in reader:
            commodity = raw["commodity"].strip()
            if commodity.lower() not in wanted_commodities:
                continue
            country = (raw.get("country") or "").strip() or None
            if wanted_regions is not None and (
                country is None or country.lower() not in wanted_regions
            ):
                continue
            rows.append(
                _ShipmentRow(
                    company_name=raw["company_name"].strip(),
                    country=country,
                    commodity=commodity,
                    shipment_date=date.fromisoformat(raw["shipment_date"].strip()),
                    volume_kg=float(raw["volume_kg"]),
                )
            )
        return rows

    def _provenance(self) -> Provenance:
        return Provenance(
            source=self._source,
            retrieved_at=self._export_retrieved_at,
            confidence=self._confidence,
            method=ProvenanceMethod.DERIVED,
        )

    def _signals_for_company_commodity(
        self,
        company_name: str,
        country: str | None,
        commodity: str,
        rows: list[_ShipmentRow],
    ) -> list[TradeSignalRecord]:
        rows_sorted = sorted(rows, key=lambda r: r.shipment_date)
        period_start = rows_sorted[0].shipment_date
        period_end = rows_sorted[-1].shipment_date
        total_volume = sum(r.volume_kg for r in rows_sorted)
        shipment_count = len(rows_sorted)
        days_since_last = (self._export_retrieved_at.date() - period_end).days
        provenance = self._provenance()

        common: _CommonFields = {
            "company_legal_name": company_name,
            "company_country": country,
            "commodity": commodity,
            "period_start": period_start,
            "period_end": period_end,
            "provenance": provenance,
        }

        signals = [
            TradeSignalRecord(
                signal_type=SignalType.COMMODITY_MATCH,
                numeric_value=None,
                band=None,
                details={"shipment_count": shipment_count},
                **common,
            ),
            TradeSignalRecord(
                signal_type=SignalType.SHIPMENT_VOLUME,
                numeric_value=total_volume,
                band=_band_for(total_volume, _VOLUME_KG_BANDS, SignalBand.VERY_HIGH),
                details={"total_volume_kg": total_volume},
                **common,
            ),
            TradeSignalRecord(
                signal_type=SignalType.SHIPMENT_FREQUENCY,
                numeric_value=float(shipment_count),
                band=_band_for(shipment_count, _FREQUENCY_BANDS, SignalBand.VERY_HIGH),
                details={"shipment_count": shipment_count},
                **common,
            ),
            TradeSignalRecord(
                signal_type=SignalType.RECENCY,
                numeric_value=float(days_since_last),
                band=_band_for(days_since_last, _RECENCY_DAYS_BANDS, SignalBand.LOW),
                details={"days_since_last_shipment": days_since_last},
                **common,
            ),
            self._trend_signal(rows_sorted, **common),
        ]
        return signals

    def _trend_signal(
        self, rows_sorted: list[_ShipmentRow], **common: Unpack[_CommonFields]
    ) -> TradeSignalRecord:
        period_start = common["period_start"]
        period_end = common["period_end"]
        midpoint = period_start + (period_end - period_start) / 2

        first_half = sum(
            r.volume_kg for r in rows_sorted if r.shipment_date <= midpoint
        )
        second_half = sum(
            r.volume_kg for r in rows_sorted if r.shipment_date > midpoint
        )

        if first_half > 0:
            pct_change = ((second_half - first_half) / first_half) * 100
            direction = (
                "increasing"
                if pct_change > 5
                else "decreasing"
                if pct_change < -5
                else "flat"
            )
        else:
            pct_change = None
            direction = "flat" if second_half == 0 else "increasing"

        return TradeSignalRecord(
            signal_type=SignalType.TREND,
            numeric_value=pct_change,
            band=None,
            details={
                "direction": direction,
                "first_half_volume_kg": first_half,
                "second_half_volume_kg": second_half,
            },
            **common,
        )
