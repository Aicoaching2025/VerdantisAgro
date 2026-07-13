"""Composite credibility score (scope doc Section 7.1: "Verification
results: corporate-existence status, sanctions/AML status, activity
verdict, composite credibility score"). Deterministic, not LLM-scored — a
straight rollup of the three verification verdicts already computed by
`VerificationEngine`, each of which already carries its own provenance.
This score is a denormalized derivative of already-provenanced data (same
category as `Company.is_sanctioned`), not a new independent signal, so it
does not go through the provenance-write path (CLAUDE.md rule 3).

A sanctions hit is scored 0.0 outright — sanctioned companies have zero
credibility regardless of anything else on file, and the verification
engine never runs the other checks once sanctions fails (the gate), so
there is nothing else to weigh anyway.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from verdantis.db.enums import Verdict

if TYPE_CHECKING:
    # Deferred to avoid a circular import -- engine.py imports this module
    # to persist the score it computes from its own VerificationSummary.
    from verdantis.core.verification.engine import VerificationSummary

_VERDICT_WEIGHT: dict[Verdict, float] = {
    Verdict.PASS: 1.0,
    Verdict.INCONCLUSIVE: 0.5,
    Verdict.FAIL: 0.0,
}


def compute_credibility_score(summary: VerificationSummary) -> float:
    if summary.blocked:
        return 0.0

    # The engine always runs (and sets) both once sanctions has passed --
    # blocked is the only case where they're absent, handled above.
    assert summary.corporate_verdict is not None
    assert summary.activity_verdict is not None
    return (
        _VERDICT_WEIGHT[summary.corporate_verdict]
        + _VERDICT_WEIGHT[summary.activity_verdict]
    ) / 2
