# Trading Agent Workspace V1 Technical Design

Status: gate_a_in_progress
Owner: Trading Agent Workspace Feature Coordinator
Source PRD: `docs/product/PRD-Trading-Agent-Workspace.md`
Implementation plan: `docs/superpowers/plans/2026-07-23-trading-agent-workspace-v1.md`
Quality route: `L3`
Last updated: 2026-07-24

## Decision Summary

Fixed decisions:

- conditionally reuse the existing research-worker daemon as scheduler;
- use separate Trading Agent state and artifacts;
- build a trusted, read-only evidence snapshot inside the restricted executor
  before model execution;
- launch up to five dedicated-account short-lived executors;
- give each nested Codex process ChatGPT login and native web search only;
- expose one first-class protected browser workspace; and
- make no cross-feature read/write, broker, Git, or deploy action.

Selected Product contract:

- Choice B: evidence panel, bull/bear debate, simulated Trader proposal, risk
  review, and simulated Portfolio Manager accept/modify/reject decision.

The Owner selected Choice B and Global PM accepted the revised stage contract
on 2026-07-24. Development remains gated only on passing non-mutating ECS
Gate A.

## Evidence Baseline

### Repository

- `scripts/research_agent_worker.py` provides the existing systemd host but
  currently batches slots, uses a shared work directory, lacks lease fencing,
  and defaults its stock-research Codex path to danger-full-access.
- `daily_market_jobs.py` and its worker provide stronger lease, heartbeat,
  cancellation, deadline, and recovery patterns.
- `data_sources/contracts.py` defines immutable provider-neutral requests,
  results, source capabilities, freshness, coverage, and typed failures.
- `data_sources/market_bars.py` supports Futu/Yahoo market bars for the
  requested markets.
- `valuation_data_provider.py`, `data_sources/valuation.py`, and
  `research/official_sources.py` provide bounded read-only market,
  official-financial, filing, and company-source patterns.
- `app_gateway.py`, `web_experience.py`, and `web_access.py` own route,
  navigation, and shared protected-access contracts.

Architecture audit at local ref `50f1648`: P0 `0`, P1 `8`, all pre-existing
module-concentration findings. The new feature therefore uses dedicated
modules instead of adding Trading logic to existing large controllers.

### TradingAgents

Verified ref `a33fd4c0f134485a43553a2c23a63cb14adbd88f`, Apache-2.0.
Adopt role/workflow concepts only. Do not copy its LangGraph runtime, prompts,
schemas, LLM clients, dataflows, memory, CLI, UI, or assets.

### Codex

Local `codex-cli 0.145.0-alpha.30` probes established:

- ChatGPT login without an API key;
- structured output and wrapper-controlled result capture;
- native `--search` works with shell disabled; and
- `read-only` plus ignored user config does not by itself remove managed
  tools.

Therefore ECS Gate A must prove the exact model-visible tool inventory. Local
success is not production readiness.

## Architecture

```text
Browser /trading-agent
  -> protected Trading controller
  -> trading_agent_runs / trading_agent_events
  -> existing research-worker daemon
       -> fair shared slot scheduler
       -> restricted short-lived executor
            -> trusted read-only evidence snapshot builder
            -> one Codex child at a time
            -> snapshot + typed request + native web search only
            -> validated structured stages
            -> isolated artifacts
```

Trust zones:

- Browser is untrusted and receives allowlisted DTOs.
- Scheduler is trusted control code. It allocates slots and launches a fixed
  executor; it does not run Trading business logic.
- Executor has a dedicated OS identity, isolated root, function-only Trading
  Agent database role, and the trusted pre-model snapshot builder.
- Snapshot builder uses only admitted read-only provider configuration and
  provider-neutral contracts; it imports no repository write interface.
- Codex child has no database/application credential or local/connector tool.

## Bounded Modules

New:

- `trading_agent_models.py`: request, snapshot, stage, and DTO types.
- `trading_agent_evidence.py`: read-only snapshot builder and source adapters.
- `trading_agent_runs.py`: isolated run/event lifecycle.
- `trading_agent_runner.py`: workflow, schemas, Codex child, validation.
- `trading_agent_controller.py`: protected APIs and safe projections.
- `trading_agent_workspace.py`: page and browser state.
- `scripts/trading_agent_executor.py`: one restricted claimed run or bounded
  artifact cleanup.

Modified:

- `db/schema.sql`
- `scripts/research_agent_worker.py`
- worker installers
- `app_gateway.py`, `web_experience.py`
- route architecture contract
- deploy classifier only; no new Ops endpoint
- focused unit, integration, browser, deploy, and cloud tests

## Trusted Evidence Snapshot

`trading_evidence_snapshot.v1` contains:

```json
{
  "target": {"market": "US", "symbol": "NVDA", "as_of": "2026-07-23"},
  "sections": {
    "market_bars": {
      "status": "ok",
      "source_ids": ["yahoo_chart"],
      "fetched_at": "2026-07-23T...",
      "freshness": "as_of_close",
      "coverage": 1.0,
      "records": []
    },
    "indicators": {"status": "ok", "method_version": "trading-indicators.v1"},
    "official_financials": {"status": "partial", "records": []},
    "events_news": {"status": "partial", "records": []}
  },
  "failures": []
}
```

Rules:

- Requested market/symbol/as-of are immutable.
- Every section has status, source identity, fetch time, freshness/coverage,
  and typed failures.
- Indicators are deterministic functions of admitted bars.
- Existing provider-neutral contracts are reused; clean-room adapters may
  fill genuine gaps.
- CN/HK/US/KR fixtures prove complete, partial, and unavailable behavior.
- No holdings, transactions, reviews, existing research, knowledge, or other
  product records are inputs.
- Snapshot is persisted only in the Trading run artifact root and passed to
  Codex as bounded structured input.
- Native search enrichment cannot overwrite the trusted snapshot; it appends
  separately sourced claims.

## Workflow Contract

Common:

1. `evidence_panel`: technical/market, fundamental/valuation, and
   news/catalyst analysis from snapshot plus bounded enrichment.
2. `thesis_debate`: strongest bull and bear cases with evidence references.

Choice A:

3. `risk_decision`: neutral research stance, confidence, horizon,
   invalidation, unknowns, and limitations.

Choice B:

3. `trader_proposal`: simulated buy/hold/sell/avoid proposal, hypothetical
   risk-budget band, entry conditions, horizon, and exit/invalidation.
4. `risk_review`: challenges evidence, concentration, downside, and proposal.
5. `portfolio_decision`: simulated accept/modify/reject with rationale.

Choice B never reads real holdings and never creates an order.

Each stage has a versioned JSON schema. Prior validated output is included in
the next prompt. The trusted runner renders Markdown from validated fields.

## State And Lifecycle

`trading_agent_runs` stores:

- UUID, normalized request, idempotency hash, selected workflow choice/version;
- status, stage, timestamps, deadline, retry lineage;
- worker/slot, lease token, attempt, heartbeat, cancellation;
- safe failure code, summaries, and artifact manifest.

`trading_agent_events` stores bounded safe lifecycle events only.

Create uses a UUID `Idempotency-Key`; the server stores its SHA-256 hash.
Concurrent replay returns the original run. V1 rate limiting reuses the
canonical `APP_ACCESS_TOKEN` as a domain-separated HMAC key and stores no
bearer value.

Claim:

1. scheduler reserves a free shared slot;
2. restricted executor transaction counts Trading active rows;
3. if fewer than five, claim FIFO with `FOR UPDATE SKIP LOCKED`;
4. set lease, attempt, worker/slot, heartbeat, deadline, and `running`;
5. executor builds and persists the immutable snapshot before Codex stages.

Heartbeats and final writes require the active lease. Queued cancellation is
immediate. Running cancellation signals the executor/Codex process group and
remains requested until finalization. Stale work is requeued once; later stale
work fails as `worker_lost`.

Invariants:

- `trading_active <= 5`
- `trading_executors + legacy_active <= global_slot_limit`
- one Codex child per Trading run

## Codex Boundary

The exact command uses:

- `--ephemeral`
- `--ignore-user-config`
- `--ignore-rules`
- strict config and empty MCP
- native `--search`
- explicit disable list for shell, unified execution, patch, apps, plugins,
  browser/computer, skills, multi-agent, and connectors
- `--sandbox read-only`
- run-specific `--cd`
- versioned `--output-schema`
- wrapper-owned `--output-last-message`
- `--json`

Arguments are an array, never a shell string. Unknown options fail readiness.

Executor environment: restricted database URL, lease, artifact root,
allowlisted read-only provider configuration, and process essentials.

Codex child environment: `PATH`, executor `HOME`/`CODEX_HOME`, run `TMPDIR`,
locale, and admitted non-secret model settings only. It excludes database,
API-key, browser-access, GitHub, deploy/Ops, DingTalk, Futu/broker, and
application secrets, including the executor's provider configuration.

## Browser And Access

Public:

- `GET /trading-agent`
- `GET /assets/trading-agent.js`

Protected:

- list/create/detail/cancel/retry/events/admitted-artifact APIs under
  `/api/trading-agent/runs`.

All protected routes reuse the existing shared `InvestmentKnowledgeAccess`
browser state. The Trading page introduces no access storage key, token field,
or setup instructions. An authorized Command page to Trading page navigation
must issue protected requests without re-entry. Missing access invokes the
same canonical recovery panel and exact request replay.

UI shows queued/running/cancel-requested/terminal states, known stages, elapsed
time, queue position, source freshness/missing evidence, and safe results.
Links allow only public `http`/`https` URLs without credentials/private
literals and use safe link attributes.

## Artifact Defaults

Artifacts use UUID-derived paths under `drafts/trading_agent_runs/`.

Implementation defaults:

- 20 MiB per run;
- 90-day terminal retention;
- 20 GiB root cap;
- 5 GiB free-space admission floor; and
- opportunistic cleanup at most every six hours.

These are configuration defaults, not Product acceptance constants. The first
end-to-end slice requires per-run bounded writes and safe capacity failure.
Cleanup may follow that slice, uses an executor-owned `flock`/marker under the
Trading root, rejects symlinks, deletes only expired UUID directories, and
then calls one restricted manifest-tombstone function. It cannot delay proof
of snapshot → Codex → browser flow.

## Gate A: After Owner Decision, Before Development

Non-mutating ECS inspection verifies:

1. unit path/state/ref and current legacy concurrency/queue;
2. installed Codex version, ChatGPT login mode, no API-key fallback;
3. strict options, structured output, native search, and full disable vector;
4. model-visible tool inventory equals native web search only;
5. local canary remains unread and JSONL has no non-web tool event;
6. dedicated executor account/auth-home/function-only DB-role/root feasibility;
7. provider-neutral snapshot feasibility for CN/HK/US/KR without feature-state
   reads/writes;
8. host CPU/memory/disk/process baseline; and
9. current public app and shared access configuration.

Gate A does not deploy, restart, change schema/config, create accounts, or run
five production children. Failure returns `blocked_with_owner` with the
dedicated-service or CLI-upgrade alternative; isolation is never weakened.

## Verification

Unit/contract:

- request, idempotency, state, lease, cancellation, timeout, retry;
- snapshot source/as-of/freshness/coverage/failure contracts;
- fixture snapshots for CN/HK/US/KR and deterministic indicators;
- dependency test proving snapshot code imports no forbidden repository write;
- workflow schemas for the Owner-selected choice;
- exact Codex args/environment/tool inventory/canary;
- process-group termination/reaping;
- safe DTOs, shared access reuse, source links, and responsive state;
- deploy classification.

Integration:

- five concurrent claims plus queued sixth;
- mixed legacy/Trading slots;
- permission-negative forbidden database/write tests;
- fake-Codex complete/cancel/timeout/malformed/capability paths;
- browser navigation from authorized Command without access re-entry;
- bounded artifact/capacity behavior.

Cloud L3 after implementation:

- exact deployed and worker refs;
- one real cited run;
- five synthetic runs plus sixth queued;
- cancellation, timeout, restart recovery, and orphan scan;
- executor permissions and zero cross-feature mutation;
- shared authorized browser journey; and
- independent acceptance.

## Deployment And Rollback

No deploy is authorized now.

Future release order:

1. bootstrap the reviewed `deploy_contract.py` into independent
   `/opt/investment-ops`, verify status/classifier, and roll back that control
   plane on failure;
2. run the reviewed worker installer without `--start` to provision the
   executor boundary while snapshotting the prior unit;
3. run one serialized application deploy for `weekly-review-web` and
   `investment-research-agent-worker.service`;
4. require fresh worker readiness and route health before acceptance.

Rollback disables new admission, restores the prior application ref and unit,
restarts the legacy worker, and leaves additive Trading tables/artifacts
inert. No ad hoc SSH restart or second deployment channel.

## Bounded Implementation Slices

1. Choice B is selected; complete Gate A.
2. Vertical slice: request → snapshot → one fixture-backed workflow →
   protected result for one run.
3. Durable lifecycle and five-slot/mixed-load scheduler.
4. Selected full stage contract, cancellation/timeout/retry, and safe browser
   UX.
5. Operational defaults, deploy readiness, cloud Gate B, and L3 acceptance.

The first usable slice precedes cleanup and release automation hardening.

## Current Closure

Global PM return `TA-DESIGN-001..003` is accepted. The evidence snapshot and
access UX corrections are incorporated; retention values are defaults.
Independent bounded re-review found no remaining Critical or Important
contradiction.
Choice B and subsequent Global PM approval are recorded. Non-mutating ECS Gate
A is active under this Feature Coordinator's watch path. Closure:
`accept_and_route`. Deploy decision: `not_required` until Gate A passes and a
verified implementation candidate exists.
