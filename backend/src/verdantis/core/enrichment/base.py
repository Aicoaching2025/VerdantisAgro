"""Decision-maker enrichment provider interface.

Resolves a contact (name, title, email) for a discovered buying
organization. ToS-safe providers only (Clay / PDL) — never LinkedIn
scraping (rule 5).

No concrete implementation exists yet — no provider contract or credentials
are configured. This is deliberately just the interface: the outbound
graph's resolve_decision_maker node accepts `EnrichmentProvider | None` and
treats `None` as "enrichment unavailable, continue without a resolved
contact." Unlike sanctions, missing enrichment is not a blocking gate — it's
surfaced as a gap in the human-approval payload, not a reason to halt.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from verdantis.db.provenance import Provenance


class DecisionMaker(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None
    title: str | None
    email: str | None
    provenance: Provenance


class EnrichmentProvider(ABC):
    @abstractmethod
    async def resolve_decision_maker(
        self, *, company_legal_name: str, country: str | None
    ) -> DecisionMaker | None:
        """Return the best-matching decision-maker contact, or None if the
        provider found nothing."""
        raise NotImplementedError
