"""Tests for Clerk session-token verification against a mocked JWKS
endpoint — a real RSA keypair signs a real JWT, verified through the same
code path production uses, just with a fake JWKS URL. No live Clerk
instance is configured anywhere in this environment.
"""

from __future__ import annotations

import json
import time
import uuid

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import verdantis.core.auth.clerk as clerk_module
from verdantis.config.settings import Settings
from verdantis.core.auth.clerk import (
    ClerkNotConfiguredError,
    InvalidSessionTokenError,
    verify_session_token,
)


def _keypair(kid: str) -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private_key, jwk


def _sign(
    private_key: rsa.RSAPrivateKey, *, kid: str, claims: dict[str, object]
) -> str:
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def _configured_settings(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    jwks_url = f"https://clerk.test/{uuid.uuid4().hex}/.well-known/jwks.json"
    issuer = "https://clerk.test/issuer"
    settings = Settings(clerk_jwks_url=jwks_url, clerk_issuer=issuer)
    monkeypatch.setattr(clerk_module, "get_settings", lambda: settings)
    clerk_module._jwks_cache.pop(jwks_url, None)
    return jwks_url, issuer


async def test_raises_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clerk_module, "get_settings", lambda: Settings())
    with pytest.raises(ClerkNotConfiguredError):
        await verify_session_token("irrelevant-token")


@respx.mock
async def test_valid_token_returns_clerk_user(
    _configured_settings: tuple[str, str],
) -> None:
    jwks_url, issuer = _configured_settings
    private_key, jwk = _keypair("key-1")
    respx.get(jwks_url).mock(return_value=httpx.Response(200, json={"keys": [jwk]}))
    token = _sign(
        private_key,
        kid="key-1",
        claims={
            "sub": "user_abc123",
            "iss": issuer,
            "exp": int(time.time()) + 3600,
        },
    )

    async with httpx.AsyncClient() as client:
        user = await verify_session_token(token, client=client)

    assert user.user_id == "user_abc123"
    assert user.claims["iss"] == issuer


@respx.mock
async def test_expired_token_raises_invalid(
    _configured_settings: tuple[str, str],
) -> None:
    jwks_url, issuer = _configured_settings
    private_key, jwk = _keypair("key-1")
    respx.get(jwks_url).mock(return_value=httpx.Response(200, json={"keys": [jwk]}))
    token = _sign(
        private_key,
        kid="key-1",
        claims={
            "sub": "user_abc123",
            "iss": issuer,
            "exp": int(time.time()) - 3600,
        },
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(InvalidSessionTokenError):
            await verify_session_token(token, client=client)


@respx.mock
async def test_wrong_signing_key_raises_invalid(
    _configured_settings: tuple[str, str],
) -> None:
    jwks_url, issuer = _configured_settings
    _real_key, real_jwk = _keypair("key-1")
    attacker_key, _attacker_jwk = _keypair("key-1")  # same kid, different key
    respx.get(jwks_url).mock(
        return_value=httpx.Response(200, json={"keys": [real_jwk]})
    )
    forged_token = _sign(
        attacker_key,
        kid="key-1",
        claims={
            "sub": "user_abc123",
            "iss": issuer,
            "exp": int(time.time()) + 3600,
        },
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(InvalidSessionTokenError):
            await verify_session_token(forged_token, client=client)


@respx.mock
async def test_unknown_kid_refetches_jwks_once_then_raises(
    _configured_settings: tuple[str, str],
) -> None:
    jwks_url, issuer = _configured_settings
    private_key, jwk = _keypair("key-current")
    route = respx.get(jwks_url).mock(
        return_value=httpx.Response(200, json={"keys": [jwk]})
    )
    token = _sign(
        private_key,
        kid="key-rotated-out",
        claims={"sub": "user_abc123", "iss": issuer, "exp": int(time.time()) + 3600},
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(InvalidSessionTokenError):
            await verify_session_token(token, client=client)

    assert route.call_count == 2  # initial fetch + one forced refresh
