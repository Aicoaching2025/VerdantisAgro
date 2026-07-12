# CLAUDE.md — Verdantis Buy-Side Lead-Gen

Repo conventions and coding standards for Claude Code. Read this before editing. The
**what** lives in `docs/verdantis-lead-gen-scope.md` (the build scope) — read it once per
feature. This file is the **how**.

## Non-negotiable rules (these are code rules, not guidelines)

1. **No autonomous outbound sends.** Every outbound message passes through a LangGraph
   `interrupt()` human-approval node. No code path sends without an approved decision.
2. **No raw licensed records persisted — ever.** Customs/BoL data
   (ImportYeti/Panjiva/ImportGenius/Tendata) is licensed. Persist derived signals only
   (counts, bands, recency, scores). This applies to test fixtures too — fixtures are
   synthetic, never real captured records.
3. **Provenance by construction.** No derived signal is written except through the dossier
   helper that requires `source`, `retrieved_at`, `confidence`, `method`. If you can
   persist a signal without provenance, the code is wrong.
4. **Sanctions screening is a blocking gate.** OpenSanctions check runs before any routing
   or outreach. A hit short-circuits to discard/hold. Never add a bypass, even
   "temporarily."
5. **No LinkedIn scraping.** Decision-maker enrichment goes through approved providers
   (Clay / PDL) only.
6. **No secrets in code or git.** Secrets come from Doppler / injected env. `.env*` is
   gitignored. Never commit a key, even a "test" one.
7. **Tenant config is never hardcoded.** Commodity set, regions, ICP thresholds, routing
   rules live in the tenant-scoped config object. One tenant today; code assumes N.

If a task seems to require breaking one of these, stop and flag it rather than working
around it.

## Stack (operative versions)

- **Python 3.12+**, managed with **uv**. Async-first.
- **LangGraph 1.x** (agents), **FastAPI** (API), **Pydantic v2** (models), **SQLAlchemy
  2.x + Alembic** (DB), **PostgreSQL + pgvector**, **Redis**.
- **LangSmith** (tracing + evals), **Sentry** (errors).
- **Next.js** (App Router) + **TypeScript** + **shadcn/ui** + **Tailwind**, **TanStack
  Query** (server state), **Zod** (validation).
- **Ruff** (lint+format), **mypy --strict** (types), **pytest** (tests). Frontend: ESLint
  + Prettier.
- Deploy: **LangGraph Platform** (agents), **Vercel** (web), **Docker** for local + CI.

## Directory structure

```
verdantis-leadgen/
├── CLAUDE.md
├── docs/
│   └── verdantis-lead-gen-scope.md
├── docker-compose.yml          # local: postgres, redis
├── .github/workflows/ci.yml
├── backend/
│   ├── pyproject.toml          # uv-managed
│   ├── Dockerfile
│   ├── alembic/                # migrations (source of truth for schema)
│   ├── langgraph.json          # LangGraph Platform deploy config
│   ├── src/verdantis/
│   │   ├── api/                # FastAPI: routers/, deps.py, schemas/ (request/response DTOs)
│   │   ├── agents/
│   │   │   ├── outbound/       # graph.py, nodes.py, state.py
│   │   │   ├── inbound/        # graph.py, nodes.py, state.py
│   │   │   └── shared/         # checkpointer factory, interrupt helpers
│   │   ├── core/                # THE shared trade-intel + verification core
│   │   │   ├── adapters/       # trade-data providers behind one interface
│   │   │   ├── verification/   # corp existence, AML, activity
│   │   │   ├── enrichment/     # decision-maker resolution (ToS-safe)
│   │   │   └── dossier/        # dossier store + provenance helpers
│   │   ├── models/             # Pydantic domain models (not DB models)
│   │   ├── db/                 # SQLAlchemy models, session, repositories
│   │   ├── config/             # settings.py (env), tenant.py (tenant config)
│   │   └── observability/      # logging, tracing, sentry init
│   └── tests/                  # mirrors src/ layout
└── frontend/
    ├── app/                    # routes: inbox, dossier/[id], approvals, intake, admin
    ├── components/             # ui/ (shadcn), feature components
    ├── lib/                    # api client, query hooks, zod schemas
    └── package.json
```

Boundaries: `core/` never imports from `agents/` or `api/`. Agents consume `core/` as a
service. `api/` orchestrates; it holds no business logic. Domain models (`models/`) are
Pydantic and DB-agnostic; DB models (`db/`) are SQLAlchemy — never leak SQLAlchemy objects
above the repository layer.

## Python conventions

- **Type everything.** `mypy --strict` passes. No bare `Any` without a `# reason:`
  comment.
- **Async by default** for anything touching I/O (DB, HTTP, LLM). No sync calls inside
  async paths.
- **Pydantic v2** for all boundary data (API, agent state, adapter output). Validate at
  the boundary; trust internally.
- **Errors:** typed exceptions in `core/`; map to HTTP at the API layer. Never swallow
  exceptions silently — log with context or re-raise.
- **Config:** `pydantic-settings` reads env once into a `Settings` singleton. No
  `os.getenv` scattered in modules.
- **No business logic in routers or nodes.** Routers call services; nodes call `core/`.
  Logic lives in `core/`.

## LangGraph conventions

- **One graph per capability** (`outbound`, `inbound`), each in its own module with
  `state.py`, `nodes.py`, `graph.py`.
- **State is a Pydantic model, minimal and serializable.** Store IDs and derived values —
  not large blobs, not live clients, not secrets. Large artifacts go to Postgres;
  reference by ID. Validate serialization: if it can't round-trip through the
  checkpointer, it doesn't belong in state.
- **Checkpointer:** Postgres in every environment except unit tests (in-memory saver
  there). Build it via the shared factory in `agents/shared/`.
- **Nodes are `async def node(state) -> dict`** returning partial state updates. Keep
  them single-responsibility and named for what they do.
- **Nodes MUST be idempotent** — safe to replay on checkpoint resume. Guard external
  side-effects (sends, CRM writes) with idempotency keys so a resume never double-fires.
- **HITL via `interrupt()`** in the approval node. The interrupt payload carries
  everything the human needs: dossier summary, scores + reasons, credibility verdict +
  evidence, draft message.
- **Routing via conditional edges** — e.g. sanctions hit routes to `discard`, low
  confidence routes to human triage.
- **Tenant scoping via `RunnableConfig` `configurable`** — never read tenant config from
  globals inside a node.

## Data & persistence

- **Alembic is the schema source of truth.** Every model change ships with a migration.
  No auto-create in app code.
- **Repository pattern:** DB access behind repository classes in `db/`. Services depend
  on repositories, not sessions.
- **Provenance helper is the only write path for signals** (see rule 3). Signature
  enforces `source`, `retrieved_at`, `confidence`, `method`.
- **pgvector** for dossier semantic match/dedup — keep embeddings in Postgres; don't add
  a separate vector store for v1.
- **PII encrypted at rest.** Maintain a suppression list checked before any send.

## External adapters (trade data, enrichment, verification)

- Every provider sits behind an ABC (`TradeDataAdapter`, `EnrichmentProvider`, etc.) in
  `core/`. App code depends on the interface, never a concrete provider.
- Every adapter call has: Redis-coordinated rate limiting, exponential-backoff retry,
  timeout, and a circuit breaker. Metered APIs must not be hammered on replay.
- Adapters return normalized derived signals, never raw licensed records (rule 2).
- Tests mock adapters with synthetic fixtures. Contract-test the schema mapping so an
  upstream change is caught, not silently absorbed.

## Testing

- pytest, async tests via `pytest-asyncio`. Mirror `src/` in `tests/`.
- Graph tests use the in-memory checkpointer and mocked `core/` services; assert node
  transitions and interrupt behavior.
- Unit tests for verification logic and adapter mapping with mocked externals.
- Contract tests for each external API's response schema.
- Coverage floor enforced in CI (start at 80% on `core/`). New logic ships with tests.

## Observability

- LangSmith tracing on via env; every node is traced. Tag runs with tenant + capability.
- Structured JSON logs with a `correlation_id` propagated API → graph → adapter. One
  request/run is followable end to end.
- Sentry captures unhandled exceptions with correlation context.
- Evals live in the repo: LangSmith datasets for the fit and credibility classifiers; the
  approval-queue approve/reject decisions feed back as labels. Precision is the metric
  that matters — don't let it regress silently.

## Frontend conventions

- App Router, Server Components by default; client components only where interactivity
  requires.
- TanStack Query for all server state — no manual fetch-in-effect. Zod validates API
  responses at the boundary.
- shadcn/ui + Tailwind; no ad-hoc CSS files. Compose primitives.
- Types generated from / shared with backend DTOs — don't hand-redefine API shapes; keep
  one source of truth.
- Auth via Clerk; guard routes with middleware, not per-component checks.

## Git, CI, commands

Conventional Commits (`feat:`, `fix:`, `chore:`…). Short-lived branches, PR into `main`,
no direct commits to `main`. CI must pass before merge.

CI gates: `ruff check` + `ruff format --check`, `mypy --strict`, `pytest`, frontend
`lint` + `build`.

```bash
# Backend (from backend/)
uv sync                                          # install
uv run uvicorn verdantis.api.main:app --reload   # run API
uv run langgraph dev                             # run graphs locally with Studio
uv run pytest                                    # test
uv run ruff check . && uv run mypy src           # lint + types
uv run alembic upgrade head                      # apply migrations
uv run alembic revision --autogenerate -m "msg"  # new migration

# Frontend (from frontend/)
pnpm install && pnpm dev
pnpm lint && pnpm build

# Local infra
docker compose up -d                             # postgres + redis
```

**Windows note:** create `.env` with an editor, not the shell, and confirm the real
filename is `.env` (not `.env.txt` — Explorer hides extensions). Prefer `uv run …` and
`docker compose` over activating a venv to sidestep PowerShell execution-policy friction.

## When you're unsure

Prefer asking over guessing on: schema changes, a new external provider, anything
touching the approval gate, sanctions logic, or persistence of provider data. These are
the places where a wrong default is expensive. Everywhere else, follow the conventions
above and move.
