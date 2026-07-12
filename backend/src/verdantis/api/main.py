"""FastAPI app factory.

No business logic lives here — routers call services, services call core/.
This module only wires up middleware, routers, and startup/shutdown hooks.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from verdantis.api.deps import get_current_user
from verdantis.api.routers import admin, health, inbound, leads, outbound, suppression
from verdantis.observability import configure_observability, set_correlation_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        set_correlation_id(correlation_id)
        response = await call_next(request)
        response.headers["x-correlation-id"] = correlation_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_observability()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Verdantis Buy-Side Lead-Gen API", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health.router)
    # Public, unauthenticated — the embeddable form's backend (rate-limited
    # instead; see api/rate_limit.py).
    app.include_router(inbound.router)
    # Dashboard surface: every route here requires a verified Clerk session.
    auth_dep = [Depends(get_current_user)]
    app.include_router(outbound.router, dependencies=auth_dep)
    app.include_router(leads.router, dependencies=auth_dep)
    app.include_router(admin.router, dependencies=auth_dep)
    app.include_router(suppression.router, dependencies=auth_dep)
    return app


app = create_app()
