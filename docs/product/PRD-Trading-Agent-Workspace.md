# PRD: Trading Agent Workspace

Status: decision_required
Owner: Trading Agent Workspace Feature Coordinator
Feature Registry row: `Trading Agent Workspace`
Last updated: 2026-07-23

## Product Intent

Add a first-class browser workspace after Command Workbench that learns from
TradingAgents' role-based investment-research process while using the Owner's
existing ChatGPT subscription through Codex CLI. The user selects an
instrument and clicks Start Research; the cloud queues, runs, monitors, and
retains the result without asking for an LLM API key.

This is a separate workflow. It is not Daily Market Brief, Weekly Review,
Command Workbench, an existing `research_job`, or an automatic portfolio
action.

## Owner Decision Required

The original request can support two materially different V1 outcomes. Product
must not choose silently.

| Choice | Workflow result | Included stages | Still prohibited |
|---|---|---|---|
| A — Research stance only | Evidence-backed bullish, neutral, bearish, or insufficient-evidence stance | Evidence analysts, bull/bear debate, neutral risk chair | Orders, position sizing against real holdings, broker calls, and cross-feature writes |
| B — Simulated Trader and Portfolio decision | Choice A plus a hypothetical trade proposal and a Portfolio Manager accept/modify/reject decision | Evidence analysts, bull/bear debate, simulated Trader proposal, risk review, simulated Portfolio Manager decision | Orders, broker calls, reading or changing real holdings, and all cross-feature writes |

Choice B better matches the original request for the complete TradingAgents
business flow and provides more learning value. It remains simulation only.
The Owner must explicitly choose A or B before Gate A or Development.

## Source And Provenance

- Reference: `TauricResearch/TradingAgents`
- Local source: `/Users/lishaocheng/code/TradingAgents`
- Verified ref: `a33fd4c0f134485a43553a2c23a63cb14adbd88f`
- License: Apache License 2.0
- `NOTICE`: none at the verified ref

| Source evidence | V1 use |
|---|---|
| Analyst, researcher, risk, Trader, and Portfolio Manager graph | Workflow and role-design evidence |
| Typed agent state and reporting tree | Versioned handoff and progress concepts |
| LLM clients, LangGraph runtime, prompts, and memory | Do not copy or import |
| Data vendor stack | Do not copy; reuse this repository's provider-neutral read contracts or clean-room adapters |
| CLI, UI, schemas, and assets | Do not copy |

Any future copied material requires an explicit license/attribution review.
The current design is clean-room.

## Goals

- Add `/trading-agent` after `/command` in primary navigation.
- Start a durable cloud run from one typed browser action.
- Use ChatGPT-authenticated Codex CLI with no `OPENAI_API_KEY` fallback.
- Run at most five Trading Agent runs concurrently; queue later valid runs.
- Show independent status, stages, cancellation, timeout, retry lineage, and
  results for each run.
- Ground analysis in a trusted, read-only evidence snapshot and allow native
  web search only for enrichment.
- Keep all run state and artifacts isolated from existing product workflows.
- Produce research/simulation output only, never an executed trade.

## Non-Goals

- No broker connection, order placement, real portfolio sizing, or automated
  execution.
- No writes to holdings, snapshots, transactions, trades, Weekly Review,
  Daily Brief, existing research jobs/artifacts, knowledge, sources, insights,
  code, Git, deployment, or Ops state.
- No automatic import/export into another feature.
- No new Trading-specific browser token, LLM API key, or product-managed
  model credential.
- No upstream TradingAgents runtime, prompt, schema, vendor, memory, or UI
  import.
- No model-local shell, filesystem, patch, MCP, app, browser-control,
  computer-control, or connector tool.

## Request Contract

| Field | Contract |
|---|---|
| Market | Required: `CN`, `HK`, `US`, or `KR` |
| Symbol | Required uppercase-safe identifier, 1-32 characters |
| Instrument name | Optional, maximum 120 characters |
| As-of date | Optional; defaults to server date; never future |
| Research focus | Optional, maximum 500 characters |
| Time horizon | `1-4 weeks`, `3-6 months` (default), or `6-12 months` |
| Source policy | `official_only`, `official_first` (default), or `broad_search` |

Provider, model, worker, priority, credentials, paths, and prompts are not
browser fields.

The browser creates a UUID `Idempotency-Key` per deliberate Start action and
reuses it after transport uncertainty. A replay returns the original run.

## Evidence Acquisition

Before Codex starts, trusted application code builds
`trading_evidence_snapshot.v1` through provider-neutral, read-only contracts:

- market bars and locally computed deterministic indicators;
- official financial facts and market snapshot where supported;
- official/company filings and bounded news/event evidence;
- source identity, source URL where applicable, as-of date, fetched time,
  freshness, coverage, and typed provider failures.

The builder may reuse `investment_knowledge_mcp.data_sources` contracts,
`market_bars`, and valuation/official-source adapters. Missing capability is a
typed `unavailable` or `partial` section, not a reason to fabricate data.
Clean-room adapters may fill a genuine market gap. The builder imports no
repository write interface and does not read existing feature records.

Codex receives only the normalized snapshot and the typed request. Native web
search may enrich or update evidence under the selected source policy; every
new material claim still requires a source and date.

## Browser Experience

### Navigation And Access

- `Trading Agent` appears immediately after Command Workbench.
- `/trading-agent` is a public recovery shell; all run data and mutations use
  protected APIs.
- V1 creates no Trading-specific token or credential prompt.
- It reuses the shared browser-persisted InvestmentKnowledge access state
  already used by protected surfaces. Navigation from an authorized
  `/command` session must work without re-entry.
- If shared access is absent, the page uses the one canonical recovery/setup
  journey. It never asks for a second token or displays a token value.

### Start And Progress

1. Validate the typed form and focus the first invalid field.
2. On Start Research, disable only the submit control and show `Starting…`.
3. Return and select a durable run:
   - `Research started — N of 5 running`, or
   - `Research queued — position N; five runs are currently running`.
4. Show known stages and elapsed time, never invented percentages.
5. Poll only non-terminal runs; pause while hidden and preserve focus.
6. Treat a browser request timeout as unknown status, not worker failure.

Run states are `queued`, `running`, `cancel_requested`, `completed`, `failed`,
`timed_out`, and `cancelled`.

### Cancellation, Retry, And Results

- Queued cancellation is immediate.
- Running cancellation remains `cancel_requested` until the executor/Codex
  process group is terminated and lease-guarded finalization succeeds.
- A whole-run deadline terminates the process group and records `timed_out`.
- Retry creates a new linked run and preserves the original.
- Results show normalized evidence, sources, debate, decision, confidence,
  invalidation conditions, unknowns, limitations, and the research-only
  disclaimer.
- Choice B additionally shows the simulated proposal and simulated Portfolio
  Manager decision. It must say that no order was created.

Raw paths, prompts, JSONL, worker logs, provider exceptions, authorization
values, and credentials are never browser fields.

## Execution And Isolation

The existing `investment-research-agent-worker` daemon is conditionally reused
only as scheduler. It does not reuse the existing `research_jobs` schema or
unsafe Codex handler.

Each running Trading Agent run uses:

- one short-lived executor under a dedicated OS account;
- the trusted pre-model snapshot builder inside that executor, with only
  admitted read-only provider configuration;
- a PostgreSQL role with no direct table DML and only fixed-search-path
  lifecycle functions for Trading Agent tables;
- one UUID-derived artifact directory; and
- at most one nested Codex CLI process at a time.

The nested Codex environment has the executor-owned ChatGPT login but no
database, application, browser-access, Git, deploy, broker, or API-key
credential. The model sees native web search as its only tool. `read-only`
sandboxing is defense in depth, not the secret boundary.

The executor drops provider configuration before launching Codex. No model
prompt or result can invoke the trusted evidence builder.

## Concurrency And Lifecycle

- At most five Trading Agent rows are `running` or `cancel_requested`.
- A sixth valid run remains queued.
- Five active runs mean at most five executor process groups and five Codex
  processes.
- A shared global scheduler cap includes legacy research work; legacy load may
  reduce temporarily available Trading slots.
- Claims use FIFO selection, `FOR UPDATE SKIP LOCKED`, lease token, attempt,
  slot identity, heartbeat, and lease-guarded final writes.
- One stale worker attempt may be requeued; model/business/schema failures are
  not automatically retried.
- Default stage deadline is 20 minutes and default run deadline is 60 minutes.
- Admission defaults are 100 queued runs and 10 creates per minute for the
  shared protected identity. These are operational defaults, not immutable
  product promises.

## Run State And Artifacts

Separate Trading Agent tables store the request, idempotency hash, workflow
version, status/stage, lease state, retry lineage, safe summaries, artifact
manifest, and bounded events.

Artifacts contain the normalized request, evidence snapshot, stage outputs,
citations, and final report under:

`drafts/trading_agent_runs/<server-generated-uuid>/`

V1 defaults are 90-day terminal artifact retention, 20 MiB per run, 20 GiB
root usage, 5 GiB free-space admission floor, and opportunistic cleanup no
more often than every six hours. These are configurable implementation
defaults. Acceptance requires bounded writes, safe capacity failure, and
cleanup confined to the Trading Agent root; the exact default values must not
delay the first end-to-end usable slice.

## Acceptance Criteria

Common criteria:

1. Trading Agent is a distinct destination immediately after Command.
2. An already authorized browser can navigate from Command without credential
   re-entry; absent access uses only the canonical shared recovery journey.
3. Start Research creates one durable idempotent run and gives immediate
   queued/running feedback.
4. Five independent runs may execute and a sixth queues.
5. A trusted snapshot supplies fixture-verified CN/HK/US/KR evidence with
   source, as-of/freshness, coverage, and explicit missing-data behavior.
6. Codex receives the snapshot plus native search, uses ChatGPT login only,
   exposes no other model tool, and cannot read a local canary.
7. Stages, events, elapsed time, cancellation, timeout, retry, and terminal
   state are truthful and independent.
8. Executor permission-negative tests prove no forbidden feature, database,
   artifact, code, Git, or deploy write.
9. Results contain evidence, opposing thesis, risk/decision reasoning,
   citations, invalidation conditions, unknowns, and limitations.
10. Public shells and protected DTOs expose no secret, path, prompt, raw log,
    or provider exception.
11. Bounded artifact and queue behavior fails safely under configured limits.
12. Desktop and 390-pixel browser journeys pass accessibility and interaction
    checks.
13. Local, cloud, five-run, mixed-load, cancellation, timeout, restart, and
    independent L3 acceptance pass before Owner acceptance.

Choice-dependent criterion:

- Choice A: the final research stance is one of bullish, neutral, bearish, or
  insufficient evidence.
- Choice B: the simulated Trader proposal and simulated Portfolio Manager
  accept/modify/reject decision are visible, and no real order, holding read,
  or portfolio write occurs.

## Quality And Release State

Quality route: `L3`.

`AT-2026-07-23-001` remains `not_required` because no implementation or
release candidate exists. It becomes pending only after implementation,
deployment readiness, and an approved protected browser session/fixture.

No runtime, ECS, database, deploy, or production action is authorized by this
document.

## Next Decision

Owner chooses:

- `A` — research stance only; or
- `B` — simulated Trader proposal plus simulated Portfolio Manager decision.

After that decision, Global PM reviews the corresponding stage contract. Only
then may this Feature Coordinator run non-mutating ECS Gate A. Development
remains prohibited until both gates pass.
