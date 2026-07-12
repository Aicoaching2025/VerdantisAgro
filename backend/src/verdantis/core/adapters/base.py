"""Trade-data adapter interface.

Every trade-intelligence provider — a live API integration or a manual
licensed-export ingestion — implements `TradeDataAdapter`. App code depends
on this interface, never a concrete provider, so a provider swap or a terms
change touches one module (see docs/verdantis-lead-gen-scope.md §7.3).

Adapters return normalized `TradeSignalRecord`s — derived intelligence only,
ready to persist via `db.provenance.record_trade_signal`. They never return
or persist a raw shipment/customs record: that's licensed data this system
is not permitted to store verbatim (rule 2). Adapters don't write to the
database themselves — fetching and persisting are separate concerns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from verdantis.db.enums import SignalBand, SignalType
from verdantis.db.provenance import Provenance


class TradeSignalRecord(BaseModel):
    """One normalized, derived trade signal for one company."""

    model_config = ConfigDict(frozen=True)

    company_legal_name: str
    company_country: str | None = None

    signal_type: SignalType
    commodity: str | None = None
    band: SignalBand | None = None
    numeric_value: float | None = None
    period_start: date | None = None
    period_end: date | None = None
    details: dict[str, Any] | None = None

    provenance: Provenance


class TradeDataAdapter(ABC):
    """Interface every trade-intelligence provider implements."""

    @abstractmethod
    async def fetch_signals(
        self, *, commodities: list[str], regions: list[str] | None = None
    ) -> list[TradeSignalRecord]:
        """Return normalized signals for companies importing `commodities`,
        optionally restricted to `regions`. Never returns raw licensed
        records — only derived intelligence (counts, bands, recency)."""
        raise NotImplementedError
