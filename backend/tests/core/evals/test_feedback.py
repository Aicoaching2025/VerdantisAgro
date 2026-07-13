"""record_approval_feedback is best-effort: it must never raise, and must
no-op whenever there's nothing real to attach feedback to (no run id, or
LangSmith isn't configured) -- see core.evals.feedback's module docstring
for why this isn't fail-closed like sanctions/encryption."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from verdantis.config.settings import Settings
from verdantis.core.evals import feedback as feedback_module
from verdantis.core.evals.feedback import record_approval_feedback


def _configured_settings() -> Settings:
    return Settings(langsmith_tracing=True, langsmith_api_key="test-key")


def test_noop_when_run_id_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feedback_module, "get_settings", _configured_settings)
    fake_client = MagicMock()
    monkeypatch.setattr(feedback_module, "Client", lambda **_: fake_client)

    record_approval_feedback(None, approved=True)

    fake_client.create_feedback.assert_not_called()


def test_noop_when_tracing_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        feedback_module,
        "get_settings",
        lambda: Settings(langsmith_tracing=False, langsmith_api_key="test-key"),
    )
    fake_client = MagicMock()
    monkeypatch.setattr(feedback_module, "Client", lambda **_: fake_client)

    record_approval_feedback("run-123", approved=True)

    fake_client.create_feedback.assert_not_called()


def test_noop_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        feedback_module,
        "get_settings",
        lambda: Settings(langsmith_tracing=True, langsmith_api_key=None),
    )
    fake_client = MagicMock()
    monkeypatch.setattr(feedback_module, "Client", lambda **_: fake_client)

    record_approval_feedback("run-123", approved=True)

    fake_client.create_feedback.assert_not_called()


def test_submits_feedback_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feedback_module, "get_settings", _configured_settings)
    fake_client = MagicMock()
    monkeypatch.setattr(feedback_module, "Client", lambda **_: fake_client)

    record_approval_feedback("run-123", approved=True)

    fake_client.create_feedback.assert_called_once_with(
        "run-123", key="human_decision", score=1.0, value="approve"
    )


def test_rejection_submits_zero_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feedback_module, "get_settings", _configured_settings)
    fake_client = MagicMock()
    monkeypatch.setattr(feedback_module, "Client", lambda **_: fake_client)

    record_approval_feedback("run-123", approved=False)

    fake_client.create_feedback.assert_called_once_with(
        "run-123", key="human_decision", score=0.0, value="reject"
    )


def test_client_error_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feedback_module, "get_settings", _configured_settings)

    def _raise(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network down")

    fake_client = MagicMock()
    fake_client.create_feedback.side_effect = _raise
    monkeypatch.setattr(feedback_module, "Client", lambda **_: fake_client)

    record_approval_feedback("run-123", approved=True)  # must not raise
