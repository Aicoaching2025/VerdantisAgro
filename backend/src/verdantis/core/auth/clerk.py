"""Clerk session-token verification.

Guards every dashboard endpoint (CLAUDE.md: "Auth via Clerk; guard routes
with middleware, not per-component checks"). Verifies the RS256-signed
session JWT Clerk issues against Clerk's own JWKS — no shared secret, no
call back to Clerk per request beyond fetching (and caching) its public
keys. Implemented with a plain async httpx fetch + in-memory cache rather
than PyJWT's built-in `PyJWKClient`, which does a blocking (sync) HTTP call
that would stall the event loop if used from an async path.

NOTE: no live Clerk instance is configured in this environment
(CLERK_JWKS_URL / CLERK_ISSUER unset). `ClerkNotConfiguredError` makes that
failure explicit and fail-closed — every dashboard request 401s — rather
than silently accepting any token. Confirm the real JWKS URL/issuer against
a live Clerk instance before pointing this at production.
"""

from __future__ import annotations

from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel, ConfigDict

from verdantis.config.settings import get_settings

_default_client = httpx.AsyncClient()
_jwks_cache: dict[str, list[dict[str, Any]]] = {}


class ClerkNotConfiguredError(Exception):
    """Raised when session verification is attempted without CLERK_JWKS_URL."""


class InvalidSessionTokenError(Exception):
    """Raised when a session token fails signature/claim verification."""


class ClerkUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    claims: dict[str, Any]


async def _fetch_jwks(
    jwks_url: str, *, client: httpx.AsyncClient, force_refresh: bool = False
) -> list[dict[str, Any]]:
    if not force_refresh:
        cached = _jwks_cache.get(jwks_url)
        if cached is not None:
            return cached
    response = await client.get(jwks_url)
    response.raise_for_status()
    keys: list[dict[str, Any]] = response.json()["keys"]
    _jwks_cache[jwks_url] = keys
    return keys


async def verify_session_token(
    token: str, *, client: httpx.AsyncClient | None = None
) -> ClerkUser:
    settings = get_settings()
    if not settings.clerk_jwks_url:
        raise ClerkNotConfiguredError(
            "CLERK_JWKS_URL is not configured; refusing to verify session "
            "tokens without a configured JWKS endpoint"
        )
    http_client = client or _default_client

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise InvalidSessionTokenError(f"invalid token header: {exc}") from exc
    kid = unverified_header.get("kid")

    keys = await _fetch_jwks(settings.clerk_jwks_url, client=http_client)
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None:
        # Key rotated since our cache was populated -> refetch once before
        # giving up, rather than caching a false negative forever.
        keys = await _fetch_jwks(
            settings.clerk_jwks_url, client=http_client, force_refresh=True
        )
        jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None:
        raise InvalidSessionTokenError("no matching JWKS key for token")

    public_key = RSAAlgorithm.from_jwk(jwk)
    try:
        claims = jwt.decode(
            token,
            public_key,  # type: ignore[arg-type]
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={
                "require": ["exp", "sub"],
                "verify_iss": bool(settings.clerk_issuer),
            },
        )
    except jwt.PyJWTError as exc:
        raise InvalidSessionTokenError(f"invalid session token: {exc}") from exc

    return ClerkUser(user_id=claims["sub"], claims=claims)
