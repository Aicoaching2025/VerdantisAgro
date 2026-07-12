"""Field-level encryption for PII at rest, per CLAUDE.md/scope-doc Section 8:
"PII encrypted at rest." Symmetric (Fernet — AES-128-CBC + HMAC), key from
Settings, Doppler-injected in every real environment like every other
secret.

Fails closed: encrypting or decrypting without a configured key raises
rather than silently persisting plaintext or returning garbage. This
mirrors the sanctions-provider pattern (OpenSanctionsProvider) — an
unconfigured compliance-critical dependency must be a loud error, not a
silent no-op.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from verdantis.config.settings import get_settings


class EncryptionNotConfiguredError(Exception):
    """Raised when PII encryption is attempted without PII_ENCRYPTION_KEY."""


class DecryptionError(Exception):
    """Raised when a ciphertext can't be decrypted (wrong/rotated key, corrupt data)."""


def _fernet() -> Fernet:
    key = get_settings().pii_encryption_key
    if not key:
        raise EncryptionNotConfiguredError(
            "PII_ENCRYPTION_KEY is not configured; refusing to persist PII "
            "without encryption"
        )
    return Fernet(key.encode("utf-8"))


def encrypt_pii(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_pii(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError("failed to decrypt PII value") from exc
