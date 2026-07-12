"""Verifies get_checkpointer's Postgres path actually works against a real
database — setup() creates the schema, and a checkpoint written through the
factory can be read back through a fresh saver instance (proving it's really
Postgres-backed, not accidentally in-memory).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from verdantis.agents.shared.checkpointer import get_checkpointer


class _CountState(BaseModel):
    count: int = 0


async def _increment(state: _CountState) -> dict[str, int]:
    return {"count": state.count + 1}


def _build_graph() -> StateGraph[_CountState]:
    graph = StateGraph(_CountState)
    graph.add_node("increment", _increment)
    graph.set_entry_point("increment")
    graph.add_edge("increment", END)
    return graph


async def test_postgres_checkpointer_persists_across_saver_instances() -> None:
    config = {"configurable": {"thread_id": "test-thread-checkpointer"}}

    async with get_checkpointer(use_memory=False) as saver:
        app = _build_graph().compile(checkpointer=saver)
        result = await app.ainvoke(_CountState(count=0), config=config)
        assert result["count"] == 1

    # Fresh saver instance, same thread_id -> state must come from Postgres,
    # not from anything held in the first saver's process memory.
    async with get_checkpointer(use_memory=False) as saver:
        app = _build_graph().compile(checkpointer=saver)
        state = await app.aget_state(config)
        assert state.values["count"] == 1


async def test_in_memory_checkpointer_works_without_postgres() -> None:
    config = {"configurable": {"thread_id": "test-thread-memory"}}
    async with get_checkpointer(use_memory=True) as saver:
        app = _build_graph().compile(checkpointer=saver)
        result = await app.ainvoke(_CountState(count=0), config=config)
        assert result["count"] == 1
