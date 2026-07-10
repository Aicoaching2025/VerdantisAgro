"""FastAPI dependency functions. Thin wiring only — no business logic.

Routers import from here, not from db/ or core/ directly, so request-scoped
dependencies (DB session today; tenant/auth context once Clerk is wired in)
have one place to live and one place for tests to override.
"""

from __future__ import annotations

from verdantis.db.session import get_session as get_db

__all__ = ["get_db"]
