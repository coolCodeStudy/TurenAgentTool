# PRD: Trading Agent Workspace

Status: ready
Owner: Trading Agent Workspace Feature Coordinator
Feature Registry row: `Trading Agent Workspace`
Last updated: 2026-07-23

## Background

The Owner wants a new first-class browser workspace that learns from the
role-based research flow in TradingAgents while using the Owner's existing
ChatGPT subscription through Codex CLI. The user should start a run in the
browser and let the cloud queue, execute, monitor, cancel, and retain the
result. The product must not require an OpenAI API key or import
TradingAgents' LLM-provider and market-data stack.

This is a separate product workflow. It appears after Command Workbench in the
primary navigation and does not become another Command Workbench action,
Weekly Review section, Daily Market Brief section, or existing stock-research
job.

## User Problem

The existing product can run bounded stock-research jobs and expose command
workflows, but it does not provide a dedicated, inspectable research board
that:

- makes distinct evidence, challenge, and risk-decision stages visible;
- runs automatically in the cloud after one browser action;
- uses subscription-backed Codex CLI instead of product-managed LLM API keys;
- supports several independent runs without mixing their status or artifacts;
- stops safely on cancellation or timeout; and
- leaves the existing portfolio, review, research, knowledge, code, and deploy
  systems unchanged.

## Product Judgment

V1 should adopt TradingAgents' workflow ideas, not its runtime framework.

The product will implement a clean-room three-stage research board:

1. `evidence_panel`: market/technical, fundamentals/valuation, and
   news/catalyst/sentiment perspectives.
2. `thesis_debate`: explicit bull and bear cases grounded in the evidence
   panel.
3. `risk_decision`: a neutral risk chair that weighs the evidence and
   counter-case and produces a research stance.

Each stage has a versioned structured-output contract and a human-readable
report. These are research opinions, not orders. V1 does not place trades,
size positions, or update any other product workflow.

This three-stage design is preferred over a one-shot prompt because progress
and failures are inspectable, and preferred over eleven separate upstream-style
agents because it preserves the core workflow with bounded runtime,
concurrency, latency, and operational complexity.

## Source And Provenance

The source reference used for product and technical design is:

- Project: `TauricResearch/TradingAgents`
- Local source: `/Users/lishaocheng/code/TradingAgents`
- Verified ref: `a33fd4c0f134485a43553a2c23a63cb14adbd88f`
- License: Apache License 2.0
- License file: `/Users/lishaocheng/code/TradingAgents/LICENSE`
- `NOTICE`: no `NOTICE` file exists at the verified ref

| Upstream evidence | Concept consulted | V1 disposition |
|---|---|---|
| `README.md`, `tradingagents/graph/setup.py` | Specialist analysis, debate, risk review, final synthesis | Adopt the abstract staged workflow |
| `tradingagents/agents/utils/agent_states.py` | Named handoff state | Create independent versioned stage schemas |
| `tradingagents/agents/schemas.py` | Typed decisions plus readable rendering | Create new fields, wording, schemas, and renderers |
| `tradingagents/agents/researchers/` | Opposing bull and bear theses | Adopt the challenge pattern; do not copy prompts |
| `tradingagents/agents/risk_mgmt/` | Multiple risk viewpoints | Collapse into one neutral V1 risk chair |
| `tradingagents/reporting.py`, `cli/main.py` | Visible progress and report artifacts | Adopt the product concept; do not copy CLI/UI code |
| `tradingagents/llm_clients/` | Direct LLM provider clients | Do not copy or depend on |
| `tradingagents/dataflows/` | Embedded market-data vendors | Do not copy or depend on |
| `tradingagents/graph/trading_graph.py` memory and state logs | Cross-run memory and automatic state writes | Do not adopt in V1 |

V1 is clean-room and does not copy upstream Python, prompts, schemas, images,
UI text, or report templates. The source/ref/license mapping stays in this PRD
and the technical plan. If future implementation copies upstream material,
that change must include Apache-2.0 redistribution obligations, modified-file
notices, applicable attribution notices, and a new license review.

## Goals

- Add `/trading-agent` as a first-class browser destination after
  `/command`.
- Let an authenticated browser user create a run and immediately receive a
  durable run ID and status.
- Execute the research workflow through Codex CLI authenticated with the
  Owner's ChatGPT subscription.
- Support at most five running Trading Agent runs; valid later requests remain
  queued in FIFO order.
- Give every run independent lifecycle state, stage state, cancellation,
  timeout, retry lineage, events, and artifacts.
- Present structured evidence, bull/bear challenge, risk decision, citations,
  limitations, and a readable final report.
- Keep the short-lived Trading Agent executor and its Codex child unable to
  read unrelated application data or mutate application code, Git, forbidden
  database state, existing artifacts, or deployment state.
- Make missing/expired Codex login, unavailable web-search capability,
  resource limits, cancellation, timeout, and partial results visible through
  typed product states.

## Non-Goals

- No trade placement, broker connection, order proposal, or automated
  execution.
- No writes to holdings, positions, account snapshots, transactions, trade
  records, Weekly Review, Daily Market Brief, existing `research_jobs`,
  knowledge items, sources, candidate insights, user insights, code, Git, or
  deployment state.
- No automatic import or export into another product feature.
- No use of `OPENAI_API_KEY` or another LLM API key.
- No direct reuse of TradingAgents' LangGraph runtime, prompts, schemas, LLM
  clients, data-vendor adapters, memory store, CLI, or images.
- No arbitrary artifact filesystem browser or raw worker-log viewer.
- No new long-lived ECS service in V1 unless the design review or runtime
  readiness gate proves the existing research-worker host cannot satisfy the
  isolation contract.
- No automatic retry of a model/business failure, because that can consume
  subscription capacity twice without user intent.
- No model-local shell, unified execution, patch, filesystem, MCP, app,
  browser-control, computer-control, or other connector tool in V1. The model
  receives only the stage input and native public web search.

## User Stories

- As the Owner, I can start research for one instrument without writing a
  command or configuring an LLM API key.
- As the Owner, I can see whether my run is queued, which stage is active, and
  how many of five execution slots are in use.
- As the Owner, I can inspect the evidence, counter-case, risk decision,
  citations, and limitations instead of seeing only a final answer.
- As the Owner, I can cancel a queued or running run and see the difference
  between "cancellation requested" and "cancelled."
- As the Owner, I can retry a failed or timed-out run as a new linked run
  without losing the original evidence.
- As the Owner, I can trust that a Trading Agent run cannot silently update my
  portfolio, reviews, knowledge base, code, or deployment.

## V1 Request Contract

The Start Research form is typed and separate from Command Workbench parsing.

| Field | Requirement |
|---|---|
| Market | Required enum: `CN`, `HK`, `US`, or `KR` |
| Symbol | Required, normalized uppercase instrument identifier, 1-32 safe characters |
| Instrument name | Optional, 1-120 display characters |
| As-of date | Optional; defaults to the current server date and may not be in the future |
| Research focus | Optional, maximum 500 characters |
| Time horizon | Required enum with default `3-6 months`; choices `1-4 weeks`, `3-6 months`, `6-12 months` |
| Source policy | Required enum with default `official_first`; choices `official_only`, `official_first`, `broad_search` |

Provider, model, worker, priority, credentials, import behavior, filesystem
paths, and raw prompts are not browser fields.

## Browser Experience

### Navigation And Access

- Add `Trading Agent` after `Command Workbench` in the primary navigation.
  The existing Daily, Weekly, and Command relative order remains unchanged.
- `GET /trading-agent` and `GET /assets/trading-agent.js` return only a public
  recovery shell so top-level navigation works before browser access is
  available.
- Every run list, detail, create, cancel, retry, event, and artifact API is
  protected by the canonical bearer-access contract.
- The page must not embed run data, artifacts, prompts, or credentials in the
  public shell.

### Start Research

1. The user fills the typed form and selects `Start Research`.
2. Client validation focuses the first invalid field.
3. Submission immediately disables only the submit control, changes its copy
   to `Starting…`, marks the form busy, and shows a polite live status.
4. The browser sends one random UUID `Idempotency-Key` and retains it until a
   definitive create response; a transport retry reuses that key.
5. A valid response selects the new run:
   - `Research started — N of 5 running`, or
   - `Research queued — position N; five runs are currently running`.
6. The sixth and later valid run is queued, not rejected.
7. Persistent safety copy states: `Creates a research opinion. It cannot place
   or modify trades.`

### Workspace

- Desktop: Start Research panel, then a run list and selected-run detail.
- Compact layout: form, run list, and detail in that source order, with no
  page-level horizontal overflow at 390 pixels.
- The run list retains terminal history and selection. Refreshes must not move
  keyboard focus.
- Poll only non-terminal runs. The selected run uses a two-second normal
  cadence, backs off after failures, pauses while the document is hidden, and
  refreshes on return.
- A browser request timeout means status is temporarily unknown; it does not
  mean the cloud run failed.

### Progress States

The UI uses known stages and elapsed time, never invented percentages:

`Queued → Preparing → Evidence panel → Thesis debate → Risk decision → Complete`

Run lifecycle states:

- `queued`
- `running`
- `cancel_requested`
- `completed`
- `failed`
- `timed_out`
- `cancelled`

The API may store `timed_out` as a dedicated terminal state or a typed failure
code, but the browser contract must render it distinctly.

### Cancellation And Retry

- Cancelling a queued run terminalizes it immediately.
- Cancelling a running run first records `cancel_requested`, disables repeated
  cancellation, and continues polling.
- The worker must terminate the active Codex process group and win a
  lease-guarded finalization before the browser shows `cancelled`.
- A whole-run deadline terminates the process group and records `timed_out`
  with a safe explanation.
- Retry creates a new queued run with `retry_of_run_id`; it never mutates or
  deletes the original run.

### Results

The selected run presents:

- instrument, market, as-of date, horizon, source policy, timestamps, stage,
  and terminal state;
- evidence-panel report with source URLs;
- bull thesis and bear/failure-mode thesis;
- risk and decision chair result;
- final stance, confidence, horizon, invalidation triggers, material unknowns,
  and limitations;
- citations and source dates;
- an escaped/read-only Markdown report; and
- a structured-output view for auditability.

Raw artifact paths, arbitrary local filenames, worker logs, prompts, provider
exceptions, database errors, authorization values, and credentials are never
browser DTO fields.

V1 supports one execution backend:

- Codex CLI authenticated by ChatGPT subscription/device login.
- No `OPENAI_API_KEY` fallback.
- The daemon never starts an interactive login.
- Missing or expired login returns typed `auth_unavailable` health/run state
  with an operator device-login action; the Owner is never asked for token
  values.

Every stage runs with:

- `codex exec`
- `--ephemeral`
- `--ignore-user-config`
- `--ignore-rules`
- an explicit empty MCP configuration
- explicit disabling of shell, unified execution, apps, plugins, and other
  local/connector capabilities
- native `--search` as the only model tool
- `--sandbox read-only`
- `--skip-git-repo-check`
- a run/stage-specific `--cd`
- a versioned `--output-schema`
- an exact wrapper-controlled `--output-last-message`
- `--json` captured by the trusted executor for bounded progress events

The existing worker remains the long-lived scheduler, but it does not execute
Trading Agent business logic in its privileged process. Each running Trading
Agent uses a short-lived executor process under a dedicated OS account. That
executor receives a PostgreSQL role restricted to the new Trading Agent tables
and an isolated artifact root. Its nested Codex process receives neither
database credentials nor filesystem/local tools. The only credential visible
to the Codex CLI process is the ChatGPT authentication store needed by the CLI
itself; the model has no local tool with which to inspect it.

Local design probes on `codex-cli 0.145.0-alpha.30` verified:

- ChatGPT login without an API key;
- ephemeral structured output under both `workspace-write` and `read-only`;
- wrapper-controlled output capture under `read-only`;
- ordinary `curl` DNS is blocked inside `workspace-write`; and
- native `--search` can reach an official IANA source while `shell_tool` is
  disabled and a local canary file remains unread.

The same probe also showed that `--ignore-user-config` alone is insufficient:
the current Codex app context still exposed managed non-web tools. Therefore
V1 does not infer safety from `read-only` or local success. A pre-development
ECS probe must show that the exact production invocation exposes only native
web search and cannot read a non-secret local canary. If the deployed CLI or
managed policy cannot provide that tool allowlist, shared-host execution is
rejected and Development remains blocked pending a stronger execution
surface. V1 never falls back to danger-full-access or unsandboxed shell
network.

## Isolation Boundary

| System/data | Trading Agent read | Trading Agent write |
|---|---|---|
| New Trading Agent run, event, and admission-window state | Authorized Web, scheduler, and restricted executor functions only | Typed Web admission and lease-guarded executor lifecycle only |
| New run artifact root | Authorized allowlisted DTOs; isolated executor filesystem | Restricted executor only |
| Public web sources | Codex native web search only | No |
| Holdings, snapshots, transactions, trades | No | No |
| Weekly Review and Daily Market Brief | No | No |
| Existing `research_jobs` and research artifacts | No | No |
| Knowledge, source, insight tables | No | No |
| Application checkout and `.git` | Executor may read its immutable installed code; model has no filesystem tool | No |
| Deploy state, Ops API, GitHub | No | No |
| Codex authentication store | CLI process authentication only | No model-local tool; negative canary gate required |

Run workspaces use server-generated UUIDs only. User input never becomes a
directory component. The executor receives immutable input and prior-stage
data selected by the trusted scheduler; the Codex model receives those values
in its prompt, not through a filesystem tool. Structured output is written
only to the executor-selected file. Browser APIs expose an allowlisted
manifest, never a caller-supplied path.

## Concurrency Semantics

- At most five Trading Agent runs have execution state `running`.
- Queued rows do not count as running. V1 accepts up to 100 queued rows and 10
  create attempts per protected access identity per minute.
- V1 derives one rate-limit identity as
  `HMAC-SHA256(APP_ACCESS_TOKEN, "trading-agent-rate-limit:v1")` and stores
  only that value in a Trading-Agent-only admission window. It introduces no
  new secret and never persists the bearer.
- Each running run occupies one shared worker slot until it reaches a terminal
  state.
- Each run executes one Codex stage at a time. Five running runs imply at most
  five short-lived executor process groups and five nested Codex CLI
  processes.
- The shared host uses a global worker cap across legacy research and Trading
  Agent handlers. Legacy work may temporarily reduce available Trading Agent
  slots, but the Trading Agent-specific cap remains five.
- Queue selection is work-conserving and fair; a slot is refilled when it
  completes rather than waiting for a batch.
- Claims use `FOR UPDATE SKIP LOCKED`, lease tokens, worker/slot identity,
  attempt count, heartbeats, and lease-guarded final writes.
- A sixth Trading Agent run remains queued until a shared slot is available.
- When the 100-row queue bound or rate limit is reached, creation returns
  typed HTTP `429` with `queue_capacity_reached` or `rate_limited`. The UI
  distinguishes this admission limit from the normal five-running queue.

Five-process production execution is a release gate, not a static assumption.
Before enabling it, the cloud owner must prove Codex subscription behavior,
host CPU/memory/disk headroom, cancellation cleanup, and no orphaned child
processes under a five-run synthetic load.

## Run State And Artifacts

Each run has:

- server-generated UUID and numeric database ID;
- normalized request, request fingerprint, and durable submission-key hash;
- workflow/schema/policy versions;
- status, stage, queue position, timestamps, whole-run deadline;
- lease token, worker and slot identity, attempt count, heartbeat;
- cancellation timestamp and safe terminal failure code;
- retry lineage;
- stage summaries and allowlisted artifact manifest; and
- isolated Trading Agent events.

One separate Trading-Agent-only admission-window record stores only the
HMAC-derived V1 access identity, minute bucket, bounded counter, and
timestamps. It contains no bearer value or run artifact and is deleted after
24 hours. Token rotation starts a new rate-limit identity; old windows remain
unusable until cleanup.

Artifact root:

```text
drafts/trading_agent_runs/<run_uuid>/
  manifest.json
  input/request.json
  stages/evidence_panel/result.json
  stages/evidence_panel/events.jsonl
  stages/thesis_debate/result.json
  stages/thesis_debate/events.jsonl
  stages/risk_decision/result.json
  stages/risk_decision/events.jsonl
  final/report.md
  final/citations.json
```

V1 retains stage/event/report artifacts for 90 days after terminal completion
and retains run metadata for auditability. Exact storage limits are 2 MiB per
structured stage result, 5 MiB per stage event stream, 2 MiB for the final
report, 2 MiB for citations, and 20 MiB total per run. The isolated executor
performs a symlink-rejecting cleanup under the Trading Agent root. The
long-lived scheduler launches the same restricted executor in
`--cleanup-if-due` mode every six hours. A Trading-Agent-only maintenance
lease, transaction advisory lock, and timestamps prevent duplicate cleanup.
The executor deletes first and then uses a restricted lifecycle function to
mark manifest entries unavailable with `deleted_at`; it never deletes
unexpired artifacts.
Admission fails safely with `artifact_capacity_reached` when free space is
below 5 GiB or the Trading Agent root exceeds 20 GiB. Cleanup failure is a
visible readiness warning and blocks admission when either storage threshold
is crossed.

## Metrics

- Run admission success rate.
- Queue wait time and stage duration.
- Completion, cancellation, timeout, typed-auth-failure, and typed-capability-
  failure rates.
- Citation coverage for material claims.
- Active-run and Codex-process high-water marks.
- Orphan-process count after cancellation, timeout, and worker restart.
- Cross-feature write violations; target is zero.

## Acceptance Criteria

1. Primary navigation shows Trading Agent immediately after Command Workbench,
   and `/trading-agent` is a distinct workspace.
2. The public shell contains no run data; all run APIs require the canonical
   protected bearer-access contract.
3. Start Research accepts the V1 typed fields, returns a durable run ID, and
   shows immediate busy/queued/running feedback.
4. Five runs can be running with independent status; the sixth valid run is
   queued and later starts without user resubmission.
5. Each run exposes accurate stage, elapsed time, events, terminal state, and
   queue position without fabricated percentages.
6. A queued cancellation is immediate; a running cancellation stays
   `cancel_requested` until the Codex process group is terminated and the
   lease-guarded cancellation wins.
7. Whole-run timeout terminates the process group and renders a distinct safe
   timed-out state.
8. Retry creates a new linked run and preserves the original state/artifacts.
9. Results include evidence, bull and bear theses, risk decision, stance,
   confidence, invalidation triggers, unknowns, limitations, and citations.
10. Every material factual claim has a source URL and source date, or is
    explicitly labeled inference/unknown.
11. Codex uses ChatGPT subscription authentication only; missing/expired login
    fails as `auth_unavailable` without asking for or exposing token values.
12. The deployed CLI exposes native web search as the only model tool, passes
    structured output, and cannot read a local canary. Failure blocks
    execution and never enables local tools or danger-full-access.
13. The Trading Agent executor runs under a dedicated OS account and restricted
    PostgreSQL role; its Codex child receives no database/Git/deploy
    credentials or local/connector tools.
14. Permission-negative tests prove the executor cannot read forbidden tables
    or write holdings, transactions, Weekly Review, Daily Brief, existing
    research jobs, knowledge, code, Git, or deploy state.
15. Browser source links admit only validated public `http`/`https` URLs; DTOs
    omit paths, prompts, raw logs/errors, and credentials.
16. Durable submission keys replay the original create response under
    concurrent duplicate requests; rate/queue bounds return distinct typed
    `429` states without changing the five-running rule.
17. Artifact size, retention, symlink rejection, cleanup cadence, and storage
    admission thresholds are enforced within the Trading Agent root.
18. Desktop and 390-pixel layouts remain usable; focus, busy state, live
    announcements, selection, and polling follow accessibility contracts.
19. Local unit/integration/browser tests, deployed route health, worker health,
    five-run load, cancellation, timeout, restart recovery, artifact
    isolation, and independent cloud acceptance pass before Owner acceptance.

## Quality Route

Quality route: `L3`.

Rationale: V1 adds a protected cloud browser surface, a durable queue, a
subscription-authenticated Codex execution boundary, filesystem artifacts,
concurrency, cancellation, worker process control, and shared-service deploy
impact. Independent real-surface acceptance tied to the deployed ref is
required.

Acceptance row `AT-2026-07-23-001` is `not_required` during design because
there is no release candidate or deployed user surface. Update that same row
to `pending` or `needs_retest` when a reviewed release candidate is ready for
independent acceptance.

## Explicit Assumptions For Global PM Design Review

- V1 markets are CN, HK, US, and KR.
- Default horizon is 3-6 months.
- Source policy is user-selectable; `official_first` is the default.
- Material factual claims require source URL and source date.
- Artifact content retention is 90 days with the exact size/storage bounds
  above.
- A running cap of five is also a maximum of five Trading Agent Codex child
  process groups because stages are sequential within each run.
- The existing `investment-research-agent-worker` systemd host is reused, but
  its `research_jobs` schema, current handler, broad working directory, and
  danger-full-access invocation are not reused. Trading execution moves to
  short-lived processes under a dedicated OS account and restricted database
  role.
- Native Codex web search is the only admitted model tool. If the deployed CLI
  cannot exclude every local/MCP/app/connector tool while authenticating with
  ChatGPT, implementation is blocked pending a stronger execution surface.
- Results are research opinions and never become orders or cross-feature
  writes.

## Risks

- The deployed Codex CLI or ChatGPT session may be stale or lack the required
  built-in web-search capability.
- Managed Codex configuration may inject local or connector tools even when
  user configuration is ignored; the ECS tool inventory must fail closed.
- Five concurrent Codex runs may exceed host or subscription capacity.
- Refactoring the shared worker scheduler can regress existing stock research.
- Cancellation without process-group termination or lease fencing can produce
  orphan work or overwrite a cancelled state.
- Provisioning a dedicated OS account and restricted PostgreSQL role adds
  one-time host/schema setup even though no new long-lived service is added.
- Stored financial research can contain misleading claims; citation and
  inference labels are acceptance requirements, not optional copy.
- Artifact retention can exhaust disk if cleanup and size caps are omitted.

## Next Owner

Global Project Manager performs design review of this PRD and
`docs/techplans/trading-agent-workspace-v1.md`. Development must not be
dispatched until the review accepts the assumptions, worker-host reuse,
web-search-only tool boundary, concurrency semantics, and implementation
slice.
