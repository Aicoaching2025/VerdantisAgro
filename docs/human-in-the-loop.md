# Human-in-the-Loop & Agent Responsibilities

Who (or what) is allowed to do what, and where the human decision points are.
This is the reference for anyone auditing the system's compliance posture —
sales, legal, or a customer's security review — not just engineers.

## 1. The core rule

**No autonomous outbound message ever leaves the system without a human
clicking Approve.** This is CLAUDE.md's rule 1, enforced in code, not just
policy:

- The outbound discovery graph cannot reach its CRM-sync / send step without
  passing through a LangGraph `interrupt()` node. The graph literally pauses
  execution and persists its state to Postgres at that point — there is no
  code path around it, because the node that would come next does not run
  until a human decision resumes the graph.
- Any LLM-drafted sales or marketing copy is subject to the same gate. The
  agent drafts; it never sends.

The one narrow exception is described in §3.

## 2. What each agent is responsible for

### Outbound discovery agent (`agents/outbound/`)

| Step | Who | What happens |
|---|---|---|
| Fetch trade signals | Agent | Reads an uploaded trade-data export (CSV), extracts derived signals only — never raw licensed records (rule 2). |
| Resolve / create company | Agent | Entity resolution against existing companies by normalized name. |
| Sanctions + corporate + activity verification | Agent | Calls OpenSanctions / OpenCorporates, computes a composite credibility score. **Sanctions screening blocks everything downstream on a hit** — no human step needed to catch this, it's a hard gate. |
| Fit scoring | Agent (LLM) | Scores ICP fit (0–1) with reasons, using the cheap/classification model. |
| Decision-maker resolution | Agent | Looks up a contact via an approved enrichment provider (Clay/PDL) — never LinkedIn scraping (rule 5). Currently unconfigured (no live provider key), so this step is a no-op until wired up. |
| Draft outreach | Agent (LLM) | Drafts a message using the stronger/drafting model. **This is a draft only.** |
| **Human approval** | **Human** | Reviews the dossier, fit score + reasons, credibility verdict + evidence, and the draft in the dashboard's Approval/Outreach queue. Approves or rejects. Nothing before this point can send anything; nothing after it runs without this explicit decision. |
| CRM sync + routing | Agent | Only on approval: syncs the company/contact to HubSpot and marks the lead routed. On rejection: the lead is marked rejected and the flow stops — no CRM write, no send. |

The human's decision also feeds back as a label on the LLM trace that
produced the fit score (LangSmith), building the eval dataset used to
measure and improve classifier precision over time — see §5.

### Inbound intake agent (`agents/inbound/`)

| Step | Who | What happens |
|---|---|---|
| Submission received | Human (external) | A prospective buyer submits Verdantis's own intake form. **They initiated contact** — this is the basis for the scoped exception in §3. |
| Normalize | Agent | Parses commodity, Incoterm, payment terms, volume into the structured schema. |
| Sanctions + verification | Agent | Same blocking gate as outbound. A hit discards the submission — no ack, no routing, no further action (§4). |
| Lead scoring | Agent (LLM) | Scores how promising the inquiry is, using the submitter's own stated intent plus any prior trade signals on file. |
| Routing decision | Agent | High-confidence submissions route directly (CRM sync + Slack ping to sales). **Low-confidence submissions route to a human triage lane instead of auto-dispatching** — this is the inbound graph's human checkpoint, functionally equivalent to the outbound approval gate but for qualification confidence rather than a drafted message. |
| Transactional acknowledgment | Agent | Sends a **fixed, non-marketing** "we received your inquiry" email. Never LLM-drafted, never carries sales copy. This is the one send this system makes without a human clicking Approve — see §3 for exactly why that's safe. |

### Verification engine (shared by both graphs)

Not really an "agent" in the LLM sense — a deterministic service both graphs
call. Produces three verdicts (sanctions/AML, corporate existence, trade
activity) each with mandatory provenance (`source`, `retrieved_at`,
`confidence`, `method`), and a composite credibility score derived from
them. Sanctions always runs first and gates everything else. No LLM
involvement, no human step — this is the part of the system that has to be
boringly deterministic.

## 3. The one thing that sends without a human click — and why it's safe

Rule 1 has exactly one scoped exception, written into CLAUDE.md deliberately
narrowly:

> The inbound graph's transactional acknowledgment to someone who submitted
> Verdantis's own intake form, plus the internal-only routing that
> submission triggers (CRM sync, Slack ping to the sales team), are not
> gated by `interrupt()`.

Why this doesn't violate the spirit of rule 1:

- **The submitter initiated contact.** This isn't outreach to a stranger;
  it's a receipt for something someone just did on Verdantis's own form.
- **The ack is fixed, not generated.** It is never LLM-drafted and never
  carries sales or marketing copy — it's a static "we got your inquiry"
  notice. There's no drafted content for a human to review because nothing
  is being composed.
- **Low confidence still stops it.** A submission that scores
  low-confidence skips auto-dispatch and routes to human triage instead —
  the *routing* decision still has a human checkpoint even though the ack
  email doesn't.
- **A sanctions hit skips the ack entirely.** Discard means discard —
  nothing further happens, not even the receipt email.
- **The exception is narrow by construction, not by discipline.** If that
  ack template ever becomes LLM-generated or grows marketing content, it
  re-enters the `interrupt()` gate. There's no code path today where it
  could drift into being sales copy without someone deliberately changing
  the node that sends it.

## 4. What "blocked" actually means

When the compliance gate fires (sanctions hit, either graph), the system
does not quietly file the lead away — it stops:

- No routing.
- No CRM sync.
- No outreach draft (outbound never gets there).
- No acknowledgment email (inbound — discard is unconditional, see §3).
- The lead is persisted with a `DISQUALIFIED` / `DISCARDED` status, visible
  in the dashboard's Dossier view with the sanctions verdict and its
  evidence, so a human can see *why* it was blocked — but nothing further
  happens automatically.

## 5. How the human's decisions make the system better over time

Every outbound fit-score call is traced (LangSmith). When a human approves
or rejects a lead in the dashboard, that decision is submitted back as
feedback on the exact trace that produced the fit score — not a separate
manual annotation step, the approval decision *is* the label. Over time
this builds the evaluation dataset CLAUDE.md's observability section calls
for, and lets precision (the rate of correctly surfaced vs. junk leads) be
tracked explicitly rather than assumed. This is currently unverified against
a live LangSmith backend — see `docs/testing-and-deployment.md`'s "known
gaps" section.

## 6. Quick answer key

| Question | Answer |
|---|---|
| Can the agent send a cold email on its own? | No. Never, under any status. |
| Can the agent send a marketing message to someone who already contacted us? | No — only a fixed, non-marketing receipt. Anything with sales copy still needs approval. |
| What happens on a sanctions hit? | Everything stops. No routing, no CRM sync, no send, no ack. |
| Who decides if a drafted outreach message actually goes out? | A human, every time, in the dashboard's Approval/Outreach queue. |
| What if the human doesn't respond? | The graph stays paused at the `interrupt()` — LangGraph's Postgres checkpointer holds that state indefinitely. Nothing times out into an auto-send. |
| Can a low-confidence inbound submission auto-route to sales? | No — it goes to a human triage lane instead. |
