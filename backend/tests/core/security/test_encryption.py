from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

import verdantis.core.security.encryption as encryption_module
from verdantis.config.settings import Settings
from verdantis.core.security.encryption import (
    DecryptionError,
    EncryptionNotConfiguredError,
    decrypt_pii,
    encrypt_pii,
)
from verdantis.core.security.pii import decrypt_intake_pii, encrypt_intake_pii


@pytest.fixture(autouse=True)
def _configured_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("utf-8")
    settings = Settings(pii_encryption_key=key)
    monkeypatch.setattr(encryption_module, "get_settings", lambda: settings)
    return key


def test_encrypt_then_decrypt_round_trips() -> None:
    ciphertext = encrypt_pii("jane@example.com")
    assert ciphertext != "jane@example.com"
    assert decrypt_pii(ciphertext) == "jane@example.com"


def test_raises_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicit None, not a bare Settings() -> conftest.py sets
    # PII_ENCRYPTION_KEY process-wide for the rest of the suite, which a
    # bare Settings() would still pick up from the environment.
    monkeypatch.setattr(
        encryption_module, "get_settings", lambda: Settings(pii_encryption_key=None)
    )
    with pytest.raises(EncryptionNotConfiguredError):
        encrypt_pii("jane@example.com")
    with pytest.raises(EncryptionNotConfiguredError):
        decrypt_pii("irrelevant")


def test_decrypt_with_wrong_key_raises_decryption_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ciphertext = encrypt_pii("jane@example.com")

    other_settings = Settings(pii_encryption_key=Fernet.generate_key().decode("utf-8"))
    monkeypatch.setattr(encryption_module, "get_settings", lambda: other_settings)

    with pytest.raises(DecryptionError):
        decrypt_pii(ciphertext)


def test_encrypt_intake_pii_only_touches_contact_fields() -> None:
    intake = {
        "contact_name": "Jane Buyer",
        "contact_email": "jane@example.com",
        "requested_volume": "1 container",
        "message": "Interested in a trial order",
    }
    encrypted = encrypt_intake_pii(intake)

    assert encrypted["contact_name"] != "Jane Buyer"
    assert encrypted["contact_email"] != "jane@example.com"
    assert encrypted["requested_volume"] == "1 container"
    assert encrypted["message"] == "Interested in a trial order"

    decrypted = decrypt_intake_pii(encrypted)
    assert decrypted["contact_name"] == "Jane Buyer"
    assert decrypted["contact_email"] == "jane@example.com"


def test_encrypt_intake_pii_handles_missing_keys() -> None:
    result = encrypt_intake_pii({"requested_volume": "1 container"})
    assert result == {"requested_volume": "1 container"}
