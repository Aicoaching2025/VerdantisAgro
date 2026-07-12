"""Inbound intake graph state.

`company_id`/`lead_id` are populated before this graph ever runs —
`agents.inbound.nodes.ingest_submission` is a plain function the API layer
calls directly (with its own short-lived session) to mint both rows fast
enough for the HTTP response, before the rest of intake (normalize -> verify
-> score -> route -> dispatch) runs as a background task through the
compiled graph. See agents/inbound/graph.py's docstring for why.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from verdantis.db.enums import Incoterm, PaymentTerms, RoutingTarget

Outcome = Literal["discarded_sanctions", "dispatched", "needs_triage"]


class InboundState(BaseModel):
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    lead_id: uuid.UUID

    legal_name: str
    country: str | None = None
    contact_name: str
    contact_email: str
    requested_commodity: str
    requested_volume: str | None = None
    incoterm_raw: str | None = None
    payment_terms_raw: str | None = None
    message: str | None = None

    fit_threshold: float = 0.5

    incoterm: Incoterm | None = None
    payment_terms: PaymentTerms | None = None

    blocked: bool = False
    fit_score: float | None = None
    fit_reasons: list[str] = Field(default_factory=list)
    routing_target: RoutingTarget | None = None
    outcome: Outcome | None = None
