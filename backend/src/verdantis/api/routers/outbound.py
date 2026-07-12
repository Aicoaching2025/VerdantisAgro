"""Outbound discovery: admin-triggered runs and the human-approval queue.

Rule 1's core surface: nothing here sends anything on its own. `POST
.../runs` starts a discovery pass against an uploaded trade-data export
(the only concrete adapter that exists — `ManualExportAdapter`, per Phase
1's design). `GET .../approvals` reads the *live* interrupt() payload for
every PENDING_APPROVAL lead straight from the checkpointer — nothing about
a pending approval is duplicated into the Lead row beyond the thread_id
needed to look it up. `POST .../approvals/{lead_id}/decision` is the only
place a human's approve/reject resumes the graph, via
`Command(resume=...)`. All three require Clerk auth (see api/main.py).
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any, Literal

import sentry_sdk
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from verdantis.agents.outbound.graph import build_outbound_graph
from verdantis.agents.outbound.runtime import build_outbound_services
from verdantis.agents.outbound.state import OutboundState
from verdantis.agents.shared.checkpointer import get_checkpointer
from verdantis.agents.shared.run_config import build_run_config
from verdantis.api.deps import get_db
from verdantis.db.enums import LeadStatus
from verdantis.db.models import Lead, Tenant
from verdantis.db.redis import get_redis_client
from verdantis.db.session import session_scope
from verdantis.models.tenant_config import TenantConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_slug}/outbound", tags=["outbound"])


class OutboundRunResponse(BaseModel):
    thread_id: str
    status: str = "running"


class ApprovalItem(BaseModel):
    lead_id: uuid.UUID
    company_id: str
    legal_name: str
    country: str | None
    fit_score: float | None
    fit_reasons: list[str]
    credibility: dict[str, str]
    decision_maker_email: str | None
    draft_body: str | None


class ApprovalDecisionRequest(BaseModel):
    action: Literal["approve", "reject"]


async def _get_tenant(session: AsyncSession, tenant_slug: str) -> Tenant:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found"
        )
    return tenant


@router.post(
    "/runs", response_model=OutboundRunResponse, status_code=status.HTTP_202_ACCEPTED
)
async def trigger_outbound_run(
    tenant_slug: str,
    background_tasks: BackgroundTasks,
    export_file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
) -> OutboundRunResponse:
    tenant = await _get_tenant(session, tenant_slug)
    tenant_config = TenantConfig.from_raw(tenant.config)
    if not tenant_config.commodities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant has no commodities configured",
        )

    raw_bytes = await export_file.read()
    csv_text = raw_bytes.decode("utf-8")
    csv_source = export_file.filename or "manual-export"

    thread_id = str(uuid.uuid4())
    state = OutboundState(
        tenant_id=tenant.id,
        commodities=tenant_config.commodities,
        regions=tenant_config.regions,
        fit_threshold=tenant_config.outbound_fit_threshold,
    )

    background_tasks.add_task(
        _run_outbound_graph, state, thread_id, csv_text, csv_source
    )

    return OutboundRunResponse(thread_id=thread_id)


async def _run_outbound_graph(
    state: OutboundState, thread_id: str, csv_text: str, csv_source: str
) -> None:
    """Runs after the HTTP response is sent, on its own fresh session — same
    rule as the inbound background task."""
    try:
        async with session_scope() as session:
            services = build_outbound_services(
                session,
                redis=get_redis_client(),
                csv_file=io.StringIO(csv_text),
                csv_source=csv_source,
            )
            async with get_checkpointer() as checkpointer:
                app = build_outbound_graph().compile(checkpointer=checkpointer)
                config = build_run_config(
                    tenant_id=state.tenant_id,
                    capability="outbound",
                    thread_id=thread_id,
                    services=services,
                )
                await app.ainvoke(state, config=config)
    except Exception:
        logger.exception("outbound graph run failed for thread %s", thread_id)
        sentry_sdk.capture_exception()


@router.get("/approvals", response_model=list[ApprovalItem])
async def list_pending_approvals(
    tenant_slug: str,
    session: AsyncSession = Depends(get_db),
) -> list[ApprovalItem]:
    tenant = await _get_tenant(session, tenant_slug)
    leads = (
        (
            await session.execute(
                select(Lead).where(
                    Lead.tenant_id == tenant.id,
                    Lead.status == LeadStatus.PENDING_APPROVAL,
                    Lead.thread_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    items: list[ApprovalItem] = []
    async with get_checkpointer() as checkpointer:
        app = build_outbound_graph().compile(checkpointer=checkpointer)
        for lead in leads:
            snapshot = await app.aget_state(
                {"configurable": {"thread_id": lead.thread_id}}
            )
            payload = _extract_interrupt_payload(snapshot)
            if payload is None:
                # Thread already resumed/moved on since we listed the lead
                # (race with a concurrent decision) -> just omit it.
                continue
            items.append(
                ApprovalItem(
                    lead_id=lead.id,
                    company_id=payload["company_id"],
                    legal_name=payload["legal_name"],
                    country=payload["country"],
                    fit_score=payload["fit_score"],
                    fit_reasons=payload["fit_reasons"],
                    credibility=payload["credibility"],
                    decision_maker_email=payload["decision_maker_email"],
                    draft_body=payload["draft_body"],
                )
            )
    return items


def _extract_interrupt_payload(snapshot: Any) -> dict[str, Any] | None:
    for task in snapshot.tasks:
        for interrupt in task.interrupts:
            if isinstance(interrupt.value, dict):
                return interrupt.value
    return None


@router.post("/approvals/{lead_id}/decision", status_code=status.HTTP_202_ACCEPTED)
async def decide_approval(
    tenant_slug: str,
    lead_id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    tenant = await _get_tenant(session, tenant_slug)
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="lead not found"
        )
    if lead.status is not LeadStatus.PENDING_APPROVAL or not lead.thread_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="lead is not awaiting approval",
        )

    background_tasks.add_task(
        _resume_outbound_graph, lead.thread_id, payload.action, tenant.id
    )
    return {"status": "accepted"}


async def _resume_outbound_graph(
    thread_id: str, action: str, tenant_id: uuid.UUID
) -> None:
    try:
        async with session_scope() as session:
            # fetch_signals/persist_signals never re-run on resume (the
            # interrupt is past them in the graph), so an empty adapter
            # input is safe here — it will never be invoked.
            services = build_outbound_services(
                session,
                redis=get_redis_client(),
                csv_file=io.StringIO(""),
                csv_source="resume",
            )
            async with get_checkpointer() as checkpointer:
                app = build_outbound_graph().compile(checkpointer=checkpointer)
                config = build_run_config(
                    tenant_id=tenant_id,
                    capability="outbound",
                    thread_id=thread_id,
                    services=services,
                )
                await app.ainvoke(Command(resume={"action": action}), config=config)
    except Exception:
        logger.exception("outbound graph resume failed for thread %s", thread_id)
        sentry_sdk.capture_exception()
