"""Checkpointer factory: Postgres in every environment except unit tests.

Build every graph's checkpointer through `get_checkpointer()` — never
instantiate a saver directly in a graph module — so environment-appropriate
selection, and the Postgres setup/schema step, live in exactly one place.

`use_memory` is explicit rather than inferred from Settings().environment:
graph tests opt into the in-memory saver deliberately when compiling the
graph for testing, rather than relying on env-var detection that's easy to
get wrong silently.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from verdantis.config.settings import get_settings


@asynccontextmanager
async def get_checkpointer(
    *, use_memory: bool = False
) -> AsyncIterator[BaseCheckpointSaver[str]]:
    """Yields the checkpointer to use for this environment.

    `use_memory=True` (unit tests only) skips Postgres entirely. Otherwise
    connects to `Settings().psycopg_database_url` and ensures the checkpoint
    tables exist (`.setup()` is idempotent — safe to call every time).
    """
    if use_memory:
        yield InMemorySaver()
        return

    conninfo = get_settings().psycopg_database_url
    async with AsyncPostgresSaver.from_conn_string(conninfo) as saver:
        await saver.setup()
        yield saver
