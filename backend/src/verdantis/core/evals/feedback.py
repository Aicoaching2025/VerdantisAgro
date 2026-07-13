"""Feeds the outbound approval queue's approve/reject decisions back to
LangSmith as labels on the `score_fit` trace that produced the lead (scope
doc Section 8: "Add an annotation queue so the human's approve/reject
decisions feed back as labels"). No separate annotation-queue UI -- the
existing approval decision *is* the label; this just ships it.

Best-effort and non-blocking: a feedback-submission failure must never
affect the approval flow itself (the lead is already approved/rejected by
the time this runs), so failures are logged and swallowed, not raised. This
mirrors Sentry/tracing's posture, not the compliance-critical fail-closed
posture of sanctions/encryption -- eval labeling is observability, not a
correctness or compliance gate.
"""

from __future__ import annotations

import logging

from langsmith import Client

from verdantis.config.settings import get_settings

logger = logging.getLogger(__name__)


def record_approval_feedback(run_id: str | None, *, approved: bool) -> None:
    settings = get_settings()
    if not run_id or not settings.langsmith_tracing or not settings.langsmith_api_key:
        return
    try:
        Client(api_key=settings.langsmith_api_key).create_feedback(
            run_id,
            key="human_decision",
            score=1.0 if approved else 0.0,
            value="approve" if approved else "reject",
        )
    except Exception:
        logger.exception("failed to record approval feedback for run %s", run_id)
