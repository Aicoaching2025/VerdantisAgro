# Testing, Deployment, and Next Steps

Where the system actually stands, how to test it locally, and what's left
before it can run in production. Written to be accurate to what's in the
repo today, not aspirational — gaps are called out explicitly rather than
glossed over.

## 1. Where things stand

All five build phases (scope doc §9) are merged to `main`:

- **Phase 0–1**: repo foundations, trade-intel adapter interface + a
  manual-CSV-export adapter, verification engine (corporate existence +
  sanctions + trade activity), dossier persistence with provenance.
- **Phase 2**: outbound discovery graph — discover → verify → score → draft
  → human approval → CRM sync.
- **Phase 3**: inbound intake graph — form submission → normalize → verify →
  score → route → dispatch → transactional ack.
- **Phase 4**: dashboard (FastAPI backend API + Next.js frontend), PII
  encryption + suppression list, eval loop (approve/reject → LangSmith
  feedback), LLM cost logging + response caching, Sentry/observability
  polish.

Every phase has passing tests and clean `ruff`/`mypy --strict` in CI. See
`docs/verdantis-lead-gen-scope.md` for the full build scope and
`docs/human-in-the-loop.md` for how the agents and the approval gate behave.

**What is not built yet** (see §4 for the full list): a real licensed
trade-data provider adapter (only the manual CSV importer exists), a
decision-maker enrichment provider connection (Clay/PDL — the interface
exists, nothing is wired to it), scheduled/cron outbound runs (today a run
is triggered on demand via CSV upload, not on a schedule), and a standalone
LangGraph Platform deployment (today the graphs run in-process inside the
FastAPI backend — see §3.3).

## 2. Testing

### 2.1 Backend — automated

```bash
cd backend
docker compose -f ../docker-compose.yml up -d   # Postgres (pgvector) + Redis
uv sync --extra dev
uv run alembic upgrade head
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src
uv run pytest --cov --cov-report=term-missing   # 150 tests as of this writing
```

Tests run against a real Postgres (not SQLite, not mocks — the schema
depends on pgvector, native enums, and partial unique indexes a fake
backend can't exercise honestly) and a real Redis, with every external
provider (OpenSanctions, OpenCorporates, HubSpot, Anthropic, Clerk,
LangSmith) faked or mocked. Coverage floor is 80% on `core/`; current
coverage is 88% overall.

Everything CI does is in `.github/workflows/ci.yml` — the same commands
above, run against Postgres/Redis service containers on every push and PR.

### 2.2 Frontend — automated

```bash
cd frontend
pnpm install
pnpm lint
pnpm exec tsc --noEmit
pnpm build
```

There is no frontend test suite (unit or e2e) yet — verification has been
manual browser testing against a live backend (see 2.3). If you want
automated frontend coverage, Playwright (already available in this
environment) against the built app would be the natural next addition.

### 2.3 Manual / end-to-end QA

This is how the dashboard has actually been verified so far, since no live
Clerk instance is configured yet:

1. **Seed data.** There's no committed seed script (deliberately — CLAUDE.md
   rule 2 means even fixtures must be synthetic, and a generic seed script
   risks looking like a real data-loading path). Insert a `Tenant` row with
   your commodity/region config, then a few `Company`/`Lead`/
   `TradeSignal`/`VerificationResult` rows through the ORM or a throwaway
   script — see any `tests/agents/*/test_graph.py` fixture builder for the
   shape.
2. **Run the backend** (`uv run uvicorn verdantis.api.main:app --reload`)
   and **frontend** (`pnpm dev`) locally.
3. **Auth, without a live Clerk key**: both `auth.protect()` (frontend) and
   the Clerk JWT verification (backend `core/auth/clerk.py`) fail closed —
   they 401/500 rather than silently allowing access. To drive the UI
   locally without live keys, override the backend's `get_current_user`
   FastAPI dependency the same way the test suite does
   (`app.dependency_overrides[get_current_user] = ...`, see
   `tests/api/routers/*.py` for the pattern), and temporarily bypass the
   frontend's `auth.protect()` call. **Revert both before committing** —
   this is a local-only workaround, not something that should ship.
4. Walk each dashboard page against the seeded data: Lead Inbox (filtering,
   pagination), Intake, Dossier detail (verify the sanctions banner renders
   for a flagged company), Approvals (approve/reject a pending lead),
   Admin (save tenant config, add/remove a suppression entry).
5. **CORS**: if testing the frontend and backend on different ports/hosts,
   set `CORS_ALLOW_ORIGINS` (comma-separated) on the backend to include the
   frontend's origin — there's no wildcard default.

### 2.4 Testing the agent graphs directly

Both graphs can be exercised without the API layer at all, which is the
fastest way to test a change to a node:

```python
from langgraph.checkpoint.memory import InMemorySaver
app = build_outbound_graph().compile(checkpointer=InMemorySaver())
result = await app.ainvoke(OutboundState(...), config={"configurable": {...}})
# result["__interrupt__"] holds the approval payload if it paused there
final = await app.ainvoke(Command(resume={"action": "approve"}), config=config)
```

This is exactly the pattern `tests/agents/*/test_graph.py` uses — real
Postgres for persistence, an in-memory checkpointer for graph state, fakes
for every external provider.

## 3. Deployment

### 3.1 What's already automated

CI (`.github/workflows/ci.yml`) runs on every push/PR: backend lint/
typecheck/test, frontend lint/build. **CI does not deploy anything** — no
Docker push, no Vercel deploy hook, no LangGraph Platform push. Deployment
today is a manual `fly deploy` / Vercel-on-push process (§3.3/§3.4), not a
CD pipeline — adding a GitHub Actions job that runs `fly deploy` on merge to
`main` is a reasonable next step once the manual path has been run
successfully at least once.

### 3.2 Secrets

Every credential comes from Doppler (or your secrets manager of choice) —
never committed, `.env*` is gitignored. The full list (see
`backend/src/verdantis/config/settings.py` for the authoritative set):

| Secret | Used for | Fails how if unset |
|---|---|---|
| `DATABASE_URL` | Postgres | Won't start |
| `REDIS_URL` | Redis (adapter resilience, rate limiting) | Won't start |
| `CLERK_SECRET_KEY` / `CLERK_PUBLISHABLE_KEY` / `CLERK_JWKS_URL` / `CLERK_ISSUER` | Dashboard auth | Every dashboard route 401s (fail closed) |
| `PII_ENCRYPTION_KEY` | Field-level PII encryption | Any write/read of PII raises rather than persisting plaintext |
| `OPENSANCTIONS_API_KEY` | Sanctions screening | The sanctions provider raises — since it's the compliance gate, nothing routes without it configured |
| `OPENCORPORATES_API_KEY` | Corporate existence checks | Verification degrades (corporate check fails) |
| `ANTHROPIC_API_KEY` | Fit/lead scoring, outreach drafting | Scoring/drafting nodes raise `AnthropicNotConfiguredError` |
| `HUBSPOT_ACCESS_TOKEN` | CRM sync | CRM sync is skipped (optional, not fail-closed) |
| `RESEND_API_KEY` | Inbound ack email | Ack is skipped (optional) |
| `LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true` | Tracing + eval feedback | Tracing/eval-feedback is a no-op (not fail-closed — observability, not compliance) |
| `SENTRY_DSN` | Error tracking | Sentry init is a no-op |
| `CORS_ALLOW_ORIGINS` | Dashboard ↔ API cross-origin fetches | Defaults to `http://localhost:3000` only — **must** be set to the real frontend origin(s) in production or every dashboard fetch will be blocked by the browser |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` (frontend) | Frontend Clerk SDK | Sign-in fails |
| `NEXT_PUBLIC_API_URL` | Frontend → backend base URL | Frontend can't reach the API |

### 3.3 Backend deploy (Fly.io)

CLAUDE.md's stated target is **LangGraph Platform** for the agents. That is
**not how the code is structured today** — worth being direct about, since
it's a real architectural decision, not something this Fly setup papers
over:

The outbound/inbound graphs are compiled and invoked *inside* the FastAPI
process (`build_outbound_graph().compile(...)` runs directly in
`api/routers/outbound.py`'s background tasks), sharing the same DB session
and Postgres checkpointer as the API. There is no `langgraph.json` in the
repo and nothing deploys the graphs as a separate LangGraph Platform
service. **That's fine for a first deploy** — it's one simpler deployable
unit — but worth revisiting before this needs to scale past one process. If
you do want the LangGraph Platform split later, that's a real refactor:
separating the graphs into their own deployable unit, having the API call
them via the LangGraph Platform client instead of compiling them in-process,
and deciding how the API and the platform-hosted graphs share the
checkpointer/DB.

What's actually in the repo now, all under Fly.io, no third-party DB/cache
vendor required:

| App | Config | Image |
|---|---|---|
| API (FastAPI + both graphs) | `backend/fly.toml` | Built from `backend/Dockerfile` |
| Postgres | `infra/fly/postgres/fly.toml` | Built from `infra/fly/postgres/Dockerfile` (`pgvector/pgvector:pg16` + the `vector` extension created on first boot) |
| Redis | `infra/fly/redis/fly.toml` | `redis:7-alpine` |

All three apps should live in the same Fly org so they can reach each other
over Fly's private network (`.flycast` / 6PN) — the DB and Redis are never
exposed publicly, only the API app has a public HTTPS endpoint.

**One-time setup, in order:**

```bash
# 1. Postgres
cd infra/fly/postgres
fly apps create verdantisagro-db                 # pick your own unique name
fly volumes create verdantisagro_db_data --region iad --size 10 -a verdantisagro-db
fly secrets set POSTGRES_PASSWORD="$(openssl rand -hex 24)" -a verdantisagro-db
fly deploy -a verdantisagro-db

# 2. Redis
cd ../redis
fly apps create verdantisagro-redis
fly volumes create verdantisagro_redis_data --region iad --size 1 -a verdantisagro-redis
fly deploy -a verdantisagro-redis

# 3. API — from backend/, after editing fly.toml's `app`/`primary_region`
#    and CORS_ALLOW_ORIGINS to match what you used above and your Vercel URL
cd ../../../backend
fly apps create verdantisagro-api
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://postgres:<the POSTGRES_PASSWORD above>@verdantisagro-db.flycast:5432/verdantis" \
  REDIS_URL="redis://verdantisagro-redis.flycast:6379/0" \
  CLERK_SECRET_KEY="..." \
  CLERK_PUBLISHABLE_KEY="..." \
  CLERK_JWKS_URL="..." \
  CLERK_ISSUER="..." \
  PII_ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  OPENSANCTIONS_API_KEY="..." \
  OPENCORPORATES_API_KEY="..." \
  ANTHROPIC_API_KEY="..." \
  -a verdantisagro-api
fly deploy -a verdantisagro-api
```

`fly deploy` runs `[deploy].release_command` (`alembic upgrade head`, wired
in `backend/fly.toml`) against the new image *before* cutting traffic over —
schema changes land before any request can hit code that expects them, and
a failed migration fails the deploy instead of shipping a broken release.

Optional secrets (§3.2 lists what happens if each is skipped):
`HUBSPOT_ACCESS_TOKEN`, `RESEND_API_KEY`, `LANGSMITH_API_KEY` +
`LANGSMITH_TRACING=true`, `SENTRY_DSN`.

**Every subsequent deploy** is just `fly deploy -a verdantisagro-api` from
`backend/` — the release command re-runs the migration automatically, so a
PR that adds a new Alembic revision doesn't need a separate manual step.

Verify it worked: `fly status -a verdantisagro-api` should show the machine
healthy against the `/healthz` check wired in `fly.toml`; `curl
https://verdantisagro-api.fly.dev/healthz` should return
`{"status":"ok"}`.

### 3.4 Frontend deploy

Standard Next.js on Vercel — no `vercel.json` exists because none is
needed for the default App Router setup:

1. Import the `frontend/` directory as a Vercel project (set the root
   directory if deploying from this monorepo).
2. Set the frontend env vars from §3.2 in Vercel's project settings.
3. Set `CORS_ALLOW_ORIGINS` on the **backend** to the Vercel deployment's
   URL (and any preview-deployment domains you want to allow).
4. Vercel's own CI (or your GitHub integration) builds and deploys on push
   — this repo's own CI only lints/builds, it doesn't trigger a Vercel
   deploy itself.

### 3.5 Rollout order

1. Deploy Postgres and Redis on Fly (§3.3, steps 1–2).
2. Create the real Clerk application; get its secret/publishable keys and
   JWKS URL/issuer.
3. Deploy the API on Fly with every secret set (§3.3, step 3) — the release
   command applies migrations before traffic cuts over.
4. Verify `/healthz` (§3.3's last paragraph) before moving on.
5. Deploy the frontend to Vercel, pointed at the Fly API's real URL
   (`NEXT_PUBLIC_API_URL`).
6. Set `CORS_ALLOW_ORIGINS` on the Fly API app to the Vercel deployment's
   real origin (`fly secrets set CORS_ALLOW_ORIGINS=https://... -a
   verdantisagro-api && fly deploy -a verdantisagro-api` — it's in
   `[env]` in `fly.toml` by default, but a secret takes precedence and is
   the cleaner way to change it post-deploy without editing the file).
7. Smoke-test end to end: sign in through the real Clerk flow, view an
   empty Lead Inbox, submit the inbound form, confirm sanctions screening
   and the approval gate both behave as documented in
   `docs/human-in-the-loop.md`.

## 4. Known gaps / next steps, roughly in priority order

1. **No live Clerk instance has been tested.** Every auth path has been
   verified via its fail-closed behavior (401/500 when unconfigured), not
   against a real signed session token. This is the highest-priority item
   before any real user touches the dashboard.
2. **No live LangSmith backend has been tested.** Tracing and the
   approve/reject eval-feedback loop are verified against the SDK's own
   contract and a mocked client, not a real LangSmith project. Low risk if
   wrong (it's observability, fails soft) but worth a real check.
3. **CORS allow-list defaults to localhost only** — `backend/fly.toml` has
   a placeholder that must be changed to the real Vercel origin before the
   dashboard will work in any deployed environment (see §3.3 step 3 and
   §3.5 step 6).
4. **No real trade-data provider adapter.** Outbound discovery only
   ingests a manually uploaded CSV export today. Getting real ongoing
   discovery running means building a second adapter against a licensed
   provider (ImportYeti/Panjiva/ImportGenius/Tendata) behind the existing
   `TradeDataAdapter` interface, respecting the licensing constraint
   (derived signals only, never raw records — rule 2).
5. **No decision-maker enrichment provider connected.** The interface
   exists (`core/enrichment/base.py`); no Clay/PDL credential is wired in,
   so `resolve_decision_maker_node` is currently a no-op.
6. **Outbound runs are on-demand, not scheduled.** The scope doc calls for
   discovery to run as scheduled background jobs; today it's triggered by
   an admin uploading a CSV via the dashboard/API. Needs a scheduler
   (cron, or the LangGraph Platform's own cron support if §3.3's platform
   migration happens).
7. **No RBAC.** Any authenticated Clerk user has full dashboard access —
   there's no role distinction (e.g., sales vs. admin) despite the scope
   doc listing "user/RBAC" under Admin/Settings. Worth deciding whether
   Clerk's own organization/role features cover this before building
   something custom.
8. **No "API/adapter status" panel.** Also scoped for Admin/Settings,
   not built — there's currently no dashboard visibility into whether
   OpenSanctions/OpenCorporates/HubSpot/etc. are configured and healthy
   short of checking logs/Sentry.
9. **No automated frontend tests.** Coverage today is backend pytest (150
   tests, 88%) plus manual browser QA. Consider Playwright if the frontend
   grows past what manual QA can reliably catch.
10. **Load/security review** before real volume: rate limits on the
    inbound public endpoint have been built and unit-tested but not load
    tested; a proper security review (dependency audit, secret rotation
    plan, Clerk RBAC decision above) is worth doing before this handles
    real prospect data at scale.
