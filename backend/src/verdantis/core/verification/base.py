"""Verification provider interfaces.

Every verification check that calls an external provider (corporate
existence, sanctions/AML) implements one of these ABCs. App code depends on
the interface, never a concrete provider — same pattern as
core/adapters/base.py. Composite orchestration (which checks run, in what
order, and the sanctions-blocks-routing gate) lives in engine.py, not here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from verdantis.db.enums import Verdict
from verdantis.db.provenance import Provenance


class VerificationOutcome(BaseModel):
    """Result of one verification check, ready to persist via
    `db.provenance.record_verification_result`."""

    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    evidence: dict[str, Any] | None = None
    provenance: Provenance


class CorporateExistenceProvider(ABC):
    @abstractmethod
    async def check(
        self, *, legal_name: str, country: str | None
    ) -> VerificationOutcome:
        raise NotImplementedError


class SanctionsProvider(ABC):
    @abstractmethod
    async def check(
        self, *, legal_name: str, country: str | None
    ) -> VerificationOutcome:
        raise NotImplementedError
