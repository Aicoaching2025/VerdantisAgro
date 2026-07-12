"""Inbound intake graph state.

`company_id`/`lead_id` are populated before this graph ever runs —
`agents.inbound.nodes.ingest_submission` is a plain function the API layer
calls directly (with its own short-lived session) to mint both rows fast
enough for the HTTP response, before the rest of intake (normalize -> verify
-> score -> route -> dispatch) runs as a background task through the
compiled graph. See agents/inbound/graph.py's docstring for why.

Deliberately excludes contact_name/contact_email: the checkpointer persists
this whole state to Postgres after every node, so anything encrypted at
rest on the Lead row would still leak in plaintext through the checkpoint
blobs if it also lived here. Nodes that need the contact's real name/email
(ack_submitter, CRM contact sync) load the Lead and decrypt on demand
instead — see nodes.py's `_load_decrypted_contact`.
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
