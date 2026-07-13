"""Outbound discovery graph state.

Minimal and serializable — IDs and derived values, not large blobs, not live
clients, not secrets (per CLAUDE.md's LangGraph state conventions). The
dossier, verification history, and draft text all live in Postgres via the
persistence layer already; state carries only what's needed to route
between nodes and what the human sees at the interrupt.

One graph run processes a batch of companies sequentially — `pending_*`
tracks the queue, `current_*` tracks whichever company is being processed
right now. A company is fully handled (verified, scored, drafted, approved
or rejected, synced or discarded) before the next one starts, so there is
never more than one pending human-approval decision per run.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from verdantis.core.adapters.base import TradeSignalRecord

ApprovalDecision = Literal["approved", "rejected"]
# "approved" — not "sent": this graph never sends anything itself (rule 1).
# It's the human's approval decision plus a CRM sync, full stop.
Outcome = Literal["discarded_sanctions", "discarded_low_fit", "approved", "rejected"]


class OutboundState(BaseModel):
    tenant_id: uuid.UUID
    commodities: list[str]
    regions: list[str] | None = None
    fit_threshold: float = 0.6

    # Transient: populated by fetch_signals, consumed and cleared by
    # persist_signals in the same superstep pair. Not carried through the
    # rest of the run — kept out of state once it's in Postgres.
    fetched_signals: list[TradeSignalRecord] = Field(default_factory=list)

    pending_company_ids: list[uuid.UUID] = Field(default_factory=list)
    processed_company_ids: list[uuid.UUID] = Field(default_factory=list)

    current_company_id: uuid.UUID | None = None
    current_lead_id: uuid.UUID | None = None
    current_blocked: bool = False
    current_fit_score: float | None = None
    current_fit_reasons: list[str] = Field(default_factory=list)
    # LangSmith run id for the score_fit call, if tracing is enabled -- lets
    # record_decision_node feed the human's decision back as a label
    # (core.evals.feedback). None when tracing is off; never real without it.
    current_fit_score_run_id: str | None = None
    current_decision_maker_email: str | None = None
    current_draft_body: str | None = None
    current_approval_decision: ApprovalDecision | None = None
    current_outcome: Outcome | None = None

    outcomes: dict[str, Outcome] = Field(default_factory=dict)
