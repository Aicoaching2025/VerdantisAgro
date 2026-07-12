"""FastAPI dependency functions. Thin wiring only — no business logic.

Routers import from here, not from db/ or core/ directly, so request-scoped
dependencies (DB session, Clerk auth context) have one place to live and one
place for tests to override.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from verdantis.core.auth.clerk import (
    ClerkNotConfiguredError,
    ClerkUser,
    InvalidSessionTokenError,
    verify_session_token,
)
from verdantis.db.session import get_session as get_db

__all__ = ["get_current_user", "get_db"]

_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> ClerkUser:
    """Guards every dashboard route. The public inbound-submission endpoint
    does not depend on this. Fails closed (401) if Clerk isn't configured —
    an unconfigured auth provider must never behave like "no auth required."
    """
    try:
        return await verify_session_token(credentials.credentials)
    except (ClerkNotConfiguredError, InvalidSessionTokenError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing session token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
