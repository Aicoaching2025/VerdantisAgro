"""Outbound discovery graph.

    fetch_signals -> persist_signals -> next_company -+-> END (queue empty)
                                              |        |
                                              v        |
                                           verify      |
                                          /       \\    |
                                  blocked          ok  |
                                     |               \\ |
                                     v                score_fit
                                  discard            /         \\
                                     |          fit>=thr      fit<thr
                                     |               |            |
                                     |     resolve_decision_maker  |
                                     |               |             |
                                     |         draft_outreach       |
                                     |               |               |
                                     |        human_approval (interrupt)
                                     |               |
                                     |       record_decision
                                     |          /          \\
                                     |    approved        rejected
                                     |       |                |
                                     |    sync_crm             |
                                     |       |                |
                                     +-------+----------------+
                                             |
                                             v
                                       next_company (loop)

Sanctions runs inside `verify` (core.verification.engine) before anything
else — a blocked company never reaches score_fit, drafting, or the
human-approval interrupt. Nothing before human_approval can send anything;
nothing after it runs without an explicit human decision (rule 1).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from verdantis.agents.outbound.nodes import (
    discard_node,
    draft_outreach_node,
    fetch_signals,
    human_approval_node,
    next_company,
    persist_signals,
    record_decision_node,
    resolve_decision_maker_node,
    score_fit_node,
    sync_crm_node,
    verify,
)
from verdantis.agents.outbound.state import OutboundState


def _route_after_next_company(state: OutboundState) -> str:
    return "verify" if state.current_company_id is not None else END


def _route_after_verify(state: OutboundState) -> str:
    return "discard" if state.current_blocked else "score_fit"


def _route_after_score_fit(state: OutboundState) -> str:
    if (
        state.current_fit_score is not None
        and state.current_fit_score >= state.fit_threshold
    ):
        return "resolve_decision_maker"
    return "discard"


def _route_after_record_decision(state: OutboundState) -> str:
    return (
        "sync_crm" if state.current_approval_decision == "approved" else "next_company"
    )


def build_outbound_graph() -> StateGraph[OutboundState]:
    graph: StateGraph[OutboundState] = StateGraph(OutboundState)

    graph.add_node("fetch_signals", fetch_signals)
    graph.add_node("persist_signals", persist_signals)
    graph.add_node("next_company", next_company)
    graph.add_node("verify", verify)
    graph.add_node("score_fit", score_fit_node)
    graph.add_node("resolve_decision_maker", resolve_decision_maker_node)
    graph.add_node("draft_outreach", draft_outreach_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("record_decision", record_decision_node)
    graph.add_node("sync_crm", sync_crm_node)
    graph.add_node("discard", discard_node)

    graph.set_entry_point("fetch_signals")
    graph.add_edge("fetch_signals", "persist_signals")
    graph.add_edge("persist_signals", "next_company")

    graph.add_conditional_edges(
        "next_company", _route_after_next_company, {"verify": "verify", END: END}
    )
    graph.add_conditional_edges(
        "verify", _route_after_verify, {"discard": "discard", "score_fit": "score_fit"}
    )
    graph.add_conditional_edges(
        "score_fit",
        _route_after_score_fit,
        {"resolve_decision_maker": "resolve_decision_maker", "discard": "discard"},
    )
    graph.add_edge("resolve_decision_maker", "draft_outreach")
    graph.add_edge("draft_outreach", "human_approval")
    graph.add_edge("human_approval", "record_decision")
    graph.add_conditional_edges(
        "record_decision",
        _route_after_record_decision,
        {"sync_crm": "sync_crm", "next_company": "next_company"},
    )
    graph.add_edge("sync_crm", "next_company")
    graph.add_edge("discard", "next_company")

    return graph
