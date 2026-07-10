# Verdantis Buy-Side Lead Generation & Qualification System — Build Scope

> Purpose of this document: Directive build specification for Claude Code. It defines
> *what* to build, *how* it must be architected for production, and *what is explicitly
> out of scope*. Treat every "MUST" as a hard requirement and every "SHOULD" as a strong
> default that requires justification to override.

## 1. Objective

Build a **production-grade, deployable** AI agent system for **Verdantis Agro Produce**
(Lagos-based agro-commodity exporter — cocoa/palm-kernel by-products, sesame, hibiscus,
gum arabic, shea, cashew, soybeans, ginger, cassava, charcoal briquettes, oils, processed
goods) that:

1. **Discovers** international buyers actively importing Verdantis's commodities.
2. **Verifies** buyer credibility before any human time is spent.
3. **Captures, qualifies, and routes** inbound website leads to the right person.

**Buy-side only.** The seller-side marketplace ("connect other sellers to buyers") is
explicitly out of scope.

The build is single-tenant (Verdantis) but MUST keep tenant-scoped configuration and the
trade-intelligence/verification core cleanly separable, so generalization into a
multi-tenant SaaS later is a configuration change, not a rewrite.

## 2. Scope Boundaries

### In scope (v1)

- Outbound buyer-discovery agent (trade-intelligence driven).
- Shared buyer-verification service (corporate existence + sanctions/AML + genuine-
  trade-activity signal).
- Inbound intake agent (form capture → qualification → routing).
- Human approval queue for all outbound messages.
- Per-company trade dossier (derived, sourced, timestamped signals).
- Dashboard: lead inbox, dossier view, approval/outreach view, intake view,
  admin/settings.
- Observability + eval harness for the classifiers.

### Out of scope (v1)

- Seller-side / two-sided marketplace.
- Autonomous sending without human approval.
- Full multi-tenancy (build the seam, not the feature).
- Storing verbatim licensed customs records (see §7.3).
- Automated contract/negotiation handling.
- Payment/LC processing.

## 3. Core Capabilities

### 3.1 Outbound Buyer Discovery

Reframed from "social listening" — commodity buyers do **not** post intent on Reddit/IG.
Intent lives in **customs/bill-of-lading data** and **B2B trade platforms**. The agent:

- Ingests trade signals for Verdantis's commodity set across target regions (EU, North
  America, Asia, Africa).
- Identifies companies **currently importing** matching commodities, with volume and
  recency.
- Enriches the buying organization and resolves a decision-maker (ToS-compliant
  enrichment only).
- Scores fit and produces an outreach angle + draft — **queued for human approval, never
  sent autonomously.**

### 3.2 Buyer Verification (Shared Service)

A standalone module both agents call. Verification is not a form field — in commodity
trade it is the fraud firewall (fake buyers, broker-as-principal, advance-fee/LC fraud).
Three checks:

- **Corporate existence:** registries (OpenCorporates), EU VAT (VIES), EORI, D-U-N-S.
- **Sanctions/AML:** OFAC SDN, EU consolidated, UN — via OpenSanctions. **Hard gate: a
  sanctions hit blocks routing and outreach.**
- **Genuine trade activity:** shipment history from customs/BoL data. A company with real
  recent import volume of the relevant commodity is simultaneously the hottest lead and
  the strongest credibility signal — **discovery and verification consume the same
  data.**

### 3.3 Inbound Intake & Routing

- Embeddable form on the WordPress site (and other owned channels).
- Structured qualification using the schema Verdantis already publishes: product
  specification, volume, origin, delivery terms (Incoterms), inspection requirements,
  payment structure (LC/TT).
- Runs the shared verification service on the submitter.
- Scores and routes to sales / Organica (trade/documentation) / support, with the
  dossier attached.
- Trust-friction aware: surfaces Verdantis's own credibility signals (certs, batch
  traceability, inspection) in acknowledgements.

## 4. System Architecture

Design invariants:

- The core is a **shared service**, not code duplicated across the two agents.

```
 ┌─────────────────────────────────────────────┐
 │       TRADE-INTELLIGENCE + VERIFICATION      │
 │              CORE (shared)                   │
 │  • Data-source adapters (customs/BoL, B2B)    │
 │  • Verification engine (corp / AML / activity)│
 │  • Dossier store (derived signals + provenance)│
 └───────────────┬───────────────┬───────────────┘
                  │               │
   ┌──────────────┘               └──────────────┐
   ▼                                              ▼
 ┌────────────────────┐              ┌────────────────────┐
 │ OUTBOUND DISCOVERY  │              │  INBOUND INTAKE    │
 │  (LangGraph graph)  │              │  (LangGraph graph) │
 │ discover→enrich→    │              │ capture→qualify→   │
 │ score→draft→[HITL]  │              │ verify→score→route │
 └─────────┬───────────┘              └─────────┬──────────┘
           │                                     │
           ▼                                     ▼
 ┌──────────────┐        ┌────────────────┐   ┌─────────────┐
 │  APPROVAL     │───────▶│ CRM (HubSpot)  │◀──│  ROUTER     │
 │  QUEUE (HITL) │        │ + notifications│   │             │
 └──────────────┘        └────────────────┘   └─────────────┘
```

- Both agents are LangGraph `StateGraph`s with Postgres-backed checkpointers.
- All outbound-send transitions pass through a LangGraph `interrupt` (human approval).
- Every persisted signal carries provenance (source, timestamp, confidence).

## 5. Technology Stack (authoritative — do not substitute without cause)

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph 1.x (`StateGraph`, conditional edges, `interrupt` for HITL) |
| Runtime / deployment | LangGraph Platform — Hybrid tier (self-hosted data plane; cron, background runs, durable execution, autoscale) |
| Observability + eval | LangSmith (tracing + eval datasets + annotation queues) |
| State + app DB | PostgreSQL (Neon or Supabase) with pgvector |
| Cache / rate coordination | Redis |
| Web extraction | Firecrawl |
| Trade-intel sources | ImportYeti / Panjiva / ImportGenius / Tendata behind a provider-agnostic adapter interface |
| Sanctions / AML | OpenSanctions (self-hostable API) |
| Corporate identity | OpenCorporates, EU VIES (VAT), EORI, D&B D-U-N-S |
| Contact enrichment | Clay / People Data Labs (ToS-safe; no LinkedIn scraping) |
| Backend API | FastAPI (Python) |
| Frontend | Next.js + shadcn/ui + Tailwind on Vercel |
| Auth | Clerk (RBAC-ready) |
| CRM / routing sink | HubSpot |
| Secrets | Doppler (or cloud Secret Manager) |
| Error tracking | Sentry |
| CI/CD | GitHub Actions, Docker-containerized |
| LLM | Model-routed: cheap model for classification/enrichment, stronger model for verification synthesis and outreach drafting (route via LangSmith LLM Gateway) |

## 6. Agent Graph Design (LangGraph specifics)

### 6.1 Shared conventions

- **Checkpointer:** Postgres in all environments except unit tests. Validate that every
  state field is serializable (Pydantic models; no raw client objects in state).
- **State:** typed Pydantic `TypedDict`/`BaseModel`. Keep state minimal — IDs and derived
  values, not large blobs. Store large artifacts in Postgres and reference by ID.
- **Durability:** discovery and verification are long-running and API-bound — rely on
  durable execution so runs resume after interruption rather than restarting.
- **Idempotency:** every node that hits an external API MUST be idempotent and safe to
  replay on checkpoint resume.

### 6.2 Outbound discovery graph

```
seed_query → fetch_trade_signals (adapters) → dedup/match_commodities →
build/update_dossier → verify (core) → score_fit → resolve_decision_maker →
draft_outreach → INTERRUPT(human_approval) → send_or_discard → sync_crm
```

- `verify` reuses the shared verification service; a sanctions hit short-circuits to
  `discard`.
- `INTERRUPT` presents: dossier summary, fit score + reasons, credibility verdict +
  evidence, draft message. Human approves / edits / rejects.

### 6.3 Inbound intake graph

```
ingest_submission → normalize_fields (Incoterms/payment schema) → verify (core) →
score_lead → route_decision → dispatch (CRM/email/Slack) → ack_submitter
```

- Runs synchronously enough for a fast acknowledgement; verification enrichment can
  complete async and update the dossier.

### 6.4 Human-in-the-loop

- **All outbound sends require approval.** Non-negotiable — it is the ToS/CAN-SPAM/GDPR
  liability firewall, not a UX preference.
- Inbound routing MAY be auto-dispatched, but a low-confidence score routes to a human
  triage lane.

## 7. Data Model, Persistence & Provenance

### 7.1 Trade dossier (per company)

Persistent, updated over time. Stores derived signals, not raw records:

- Company identity (name, country, registry IDs, VAT/EORI/D-U-N-S where resolved).
- Commodity-match signals (which of Verdantis's products they import).
- Trade-activity signals: shipment count, volume band, recency, trend — derived, with
  source + retrieval timestamp + confidence per signal.
- Verification results: corporate-existence status, sanctions/AML status, activity
  verdict, composite credibility score.
- Fit score, engagement history, routing history.

### 7.2 Provenance (mandatory)

Every derived signal and every verification verdict MUST carry: `source`,
`retrieved_at`, `confidence`, and `method`. The dashboard MUST be able to show *why* a
buyer was rated credible — the evidence trail, not just the score. This is required for
human trust now and for defensibility if this becomes a SaaS.

### 7.3 Licensing constraint (hard requirement)

Customs/BoL data from ImportYeti/Panjiva/ImportGenius/Tendata is **licensed** and
generally **cannot be stored verbatim or redistributed**. Therefore:

- Persist derived signals and metadata (counts, bands, recency, scores) — never raw
  verbatim records.
- Design the dossier schema so it holds *intelligence*, not scraped originals.
- Verify each provider's terms before the POC hardens into a product. Isolate all
  provider access behind the adapter interface so a terms change touches one module.

## 8. Production-Grade Requirements (non-functional)

These are what make it "deployable production grade," not a prototype. All MUST.

- **Security:** all secrets in Doppler/Secret Manager, never in code or env files
  committed to git. Least-privilege API keys. Encrypt PII at rest.
- **Compliance:**
  - Sanctions/AML screening is a blocking gate before routing or outreach.
  - Outbound respects CAN-SPAM (identification, opt-out) and GDPR (lawful basis,
    data-subject handling) — enforced by the human-approval gate + suppression list.
  - No LinkedIn scraping. Enrichment via compliant providers only.
- **Observability:** every LangGraph node traced in LangSmith; app errors in Sentry;
  structured logs with correlation IDs across API → graph → adapters.
- **Evaluation (do not skip):** build LangSmith eval datasets for the fit classifier and
  the credibility classifier from annotated real traces. Track precision explicitly —
  false positives (surfacing junk leads / mis-vetting fraud) are the failure mode that
  kills adoption. Add an annotation queue so the human's approve/reject decisions feed
  back as labels.
- **Rate limiting & resilience:** every external adapter has rate limiting
  (Redis-coordinated), exponential-backoff retries, timeouts, and circuit-breaking.
  Metered trade-data APIs must not be hammered on checkpoint replay.
- **Cost control:** model routing (cheap-vs-strong), response caching, and awareness
  that LangGraph Platform bills per node execution — keep graphs tight, avoid gratuitous
  nodes.
- **Scalability:** stateless API workers; all state in Postgres/Redis; discovery runs as
  scheduled background jobs via LangGraph cron, not synchronous requests.
- **Testing:** unit tests for adapters/verification logic with mocked externals;
  integration tests for each graph with an in-memory checkpointer; contract tests for
  external API schemas.
- **Multi-tenant seam:** all tenant-specific config (commodity set, target regions,
  routing rules, ICP thresholds) lives in a tenant-scoped config object, never
  hardcoded. One tenant now; the code path assumes N.

## 9. Build Phases

- **Phase 0 — Foundations.** Repo, Docker, CI, Postgres + pgvector, Redis, secrets,
  LangSmith project, Clerk auth, base FastAPI + Next.js skeletons.
- **Phase 1 — Core.** Trade-intel adapter interface + first adapter; verification engine
  (corp existence + OpenSanctions + activity signal); dossier schema with provenance;
  licensing-safe persistence.
- **Phase 2 — Outbound graph.** Discovery → dossier → verify → score → draft → HITL
  interrupt → approval queue UI → HubSpot sync. Trace + first eval dataset.
- **Phase 3 — Inbound graph.** Embeddable form → normalize (Incoterms/payment) → verify
  → score → route → dispatch → ack. Triage lane for low-confidence.
- **Phase 4 — Dashboard + hardening.** Lead inbox, dossier/evidence view,
  approval/outreach view, intake view, admin/settings. Rate limiting, retries, circuit
  breakers, eval loop wired to approve/reject labels, cost controls, observability
  polish.

## 10. Dashboard Sections (frontend)

- **Lead Inbox:** unified queue of discovered + inbound leads, sortable by
  fit/credibility/recency.
- **Dossier View:** company profile, derived trade signals, provenance/evidence trail,
  verification verdict with reasons.
- **Approval / Outreach View:** draft message + context; approve / edit / reject;
  suppression controls.
- **Inbound Intake View:** submissions with normalized commodity-trade fields and
  routing status.
- **Admin / Settings:** tenant config (commodity set, regions, ICP thresholds, routing
  rules), API/adapter status, user/RBAC.

## 11. Key Risks & Constraints

- **Classifier precision** is where the system earns or loses value — over-surfacing
  junk buries the human. Instrument and eval from day one.
- **Trade-data licensing** — derived-only persistence; verify terms per provider;
  adapter isolation.
- **Fraud/credibility** — sanctions gate is blocking; treat broker-as-principal and
  advance-fee patterns as explicit negative signals.
- **Trust tax** — Nigerian agro-export carries a credibility discount internationally;
  outreach and intake must front-load verification signals.
- **LangGraph persistence footgun** — Postgres checkpointer, validated state
  serialization, idempotent nodes.
- **Platform naming** — "LangGraph Platform" is now officially "LangSmith Deployment";
  expect both names in docs.

## 12. Definition of Done (v1)

- Discovery agent produces verified, scored buyer leads with dossiers and draft
  outreach, gated by human approval.
- Verification service returns corporate-existence + sanctions + activity verdicts with
  evidence, and blocks on sanctions hits.
- Inbound form captures, qualifies on the commodity-trade schema, verifies, and routes
  with the dossier attached.
- Every derived signal and verdict is traceable to source/timestamp/confidence in the
  UI.
- No raw licensed records persisted. No autonomous sends. No LinkedIn scraping.
- LangSmith traces + eval datasets live for both classifiers; approve/reject decisions
  feed labels.
