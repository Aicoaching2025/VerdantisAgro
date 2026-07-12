"""Inbound intake graph.

    (ingest_submission runs synchronously in the API layer, not as a graph
     node -- see nodes.py's docstring. company_id/lead_id already exist by
     the time this graph starts.)

    normalize_fields -> verify -+-> discard -> END (sanctions hit)
                                 |
                                 v
                            score_lead
                            /         \\
                       fit>=thr      fit<thr
                          |               |
                      dispatch         triage
                          |               |
                          +-------+-------+
                                  v
                            ack_submitter -> END

Sanctions runs inside `verify` (core.verification.engine) before scoring or
any dispatch — a blocked submission never reaches score_lead, CRM sync,
Slack, or the ack email (CLAUDE.md rule 4). `dispatch` (CRM/Slack/ack) and
`triage` (ack only, no CRM/Slack) both route the lead and send the fixed
ack email; only `discard` skips the ack entirely. Per CLAUDE.md rule 1's
inbound exception, none of this is gated by interrupt() — the submitter
initiated contact, the ack is a fixed non-marketing template, and
low-confidence submissions still fall through to human triage rather than
auto-dispatching.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from verdantis.agents.inbound.nodes import (
    dispatch_node,
    discard_node,
    normalize_fields,
    score_lead_node,
    triage_node,
    verify,
)
from verdantis.agents.inbound.state import InboundState


def _route_after_verify(state: InboundState) -> str:
    return "discard" if state.blocked else "score_lead"


def _route_after_score_lead(state: InboundState) -> str:
    if state.fit_score is not None and state.fit_score >= state.fit_threshold:
        return "dispatch"
    return "triage"


def build_inbound_graph() -> StateGraph[InboundState]:
    graph: StateGraph[InboundState] = StateGraph(InboundState)

    graph.add_node("normalize_fields", normalize_fields)
    graph.add_node("verify", verify)
    graph.add_node("score_lead", score_lead_node)
    graph.add_node("dispatch", dispatch_node)
    graph.add_node("triage", triage_node)
    graph.add_node("discard", discard_node)

    graph.set_entry_point("normalize_fields")
    graph.add_edge("normalize_fields", "verify")
    graph.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"discard": "discard", "score_lead": "score_lead"},
    )
    graph.add_conditional_edges(
        "score_lead",
        _route_after_score_lead,
        {"dispatch": "dispatch", "triage": "triage"},
    )
    graph.add_edge("dispatch", END)
    graph.add_edge("triage", END)
    graph.add_edge("discard", END)

    return graph
