"""Encrypts/decrypts the specific PII fields inbound leads carry in their
`intake` JSONB payload (`contact_name`, `contact_email`). Scoped narrowly to
those two structured fields — free-text fields like `message` are left as
entered, a deliberate scoping choice noted in the hardening PR rather than
encrypting everything indiscriminately.
"""

from __future__ import annotations

from typing import Any

from verdantis.core.security.encryption import decrypt_pii, encrypt_pii

_PII_KEYS = ("contact_name", "contact_email")


def encrypt_intake_pii(intake: dict[str, Any]) -> dict[str, Any]:
    result = dict(intake)
    for key in _PII_KEYS:
        value = result.get(key)
        if value is not None:
            result[key] = encrypt_pii(str(value))
    return result


def decrypt_intake_pii(intake: dict[str, Any]) -> dict[str, Any]:
    result = dict(intake)
    for key in _PII_KEYS:
        value = result.get(key)
        if value is not None:
            result[key] = decrypt_pii(str(value))
    return result
