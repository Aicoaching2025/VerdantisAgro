from __future__ import annotations

from verdantis.core.llm.pricing import estimate_cost_usd


def test_known_model_uses_its_own_rates() -> None:
    cost = estimate_cost_usd(
        "claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000
    )
    assert cost == 1.00 + 5.00


def test_unknown_model_falls_back_to_conservative_rate() -> None:
    cost = estimate_cost_usd(
        "some-future-model", input_tokens=1_000_000, output_tokens=0
    )
    assert cost == 3.00


def test_zero_tokens_cost_nothing() -> None:
    assert estimate_cost_usd("claude-sonnet-5", input_tokens=0, output_tokens=0) == 0.0
