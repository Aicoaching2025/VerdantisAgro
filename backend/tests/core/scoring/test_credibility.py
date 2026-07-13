"""Unit tests for the deterministic composite credibility score. No I/O --
VerificationSummary is a plain dataclass, so these run without Postgres."""

from __future__ import annotations

import uuid

from verdantis.core.scoring.credibility import compute_credibility_score
from verdantis.core.verification.engine import VerificationSummary
from verdantis.db.enums import Verdict


def _summary(
    *,
    blocked: bool = False,
    corporate: Verdict | None = Verdict.PASS,
    activity: Verdict | None = Verdict.PASS,
) -> VerificationSummary:
    return VerificationSummary(
        company_id=uuid.uuid4(),
        sanctions_verdict=Verdict.FAIL if blocked else Verdict.PASS,
        corporate_verdict=corporate,
        activity_verdict=activity,
        is_sanctioned=blocked,
        blocked=blocked,
    )


def test_blocked_scores_zero_regardless_of_other_verdicts() -> None:
    summary = _summary(blocked=True, corporate=None, activity=None)
    assert compute_credibility_score(summary) == 0.0


def test_both_pass_scores_one() -> None:
    summary = _summary(corporate=Verdict.PASS, activity=Verdict.PASS)
    assert compute_credibility_score(summary) == 1.0


def test_both_fail_scores_zero() -> None:
    summary = _summary(corporate=Verdict.FAIL, activity=Verdict.FAIL)
    assert compute_credibility_score(summary) == 0.0


def test_mixed_verdicts_average() -> None:
    summary = _summary(corporate=Verdict.PASS, activity=Verdict.FAIL)
    assert compute_credibility_score(summary) == 0.5


def test_inconclusive_counts_as_half_weight() -> None:
    summary = _summary(corporate=Verdict.INCONCLUSIVE, activity=Verdict.PASS)
    assert compute_credibility_score(summary) == 0.75
