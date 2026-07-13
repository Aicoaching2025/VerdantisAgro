"""Per-model token pricing, for cost-control visibility (scope doc Section 8:
"model routing... and awareness that... billing" — this is the "awareness"
half). USD per million tokens, input/output priced separately since output
is materially more expensive on every current Anthropic model.

Not tenant config (CLAUDE.md rule 7 doesn't apply here): pricing is a
property of the model itself, identical for every tenant, and changes only
when Anthropic reprices a model — a code constant, not something a tenant
would ever configure.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_million_usd: float
    output_per_million_usd: float


# Prices as of this writing; update alongside ANTHROPIC_SCORING_MODEL /
# ANTHROPIC_DRAFTING_MODEL in config/settings.py if the routed models change.
_PRICING: dict[str, ModelPricing] = {
    "claude-haiku-4-5-20251001": ModelPricing(
        input_per_million_usd=1.00, output_per_million_usd=5.00
    ),
    "claude-sonnet-5": ModelPricing(
        input_per_million_usd=3.00, output_per_million_usd=15.00
    ),
}

# Applied when a model isn't in the table (e.g. a tenant config override we
# don't have pricing for yet) so cost estimates degrade to a conservative
# guess instead of silently reporting zero.
_FALLBACK_PRICING = ModelPricing(
    input_per_million_usd=3.00, output_per_million_usd=15.00
)


def estimate_cost_usd(model: str, *, input_tokens: int, output_tokens: int) -> float:
    pricing = _PRICING.get(model, _FALLBACK_PRICING)
    return (
        input_tokens * pricing.input_per_million_usd / 1_000_000
        + output_tokens * pricing.output_per_million_usd / 1_000_000
    )
