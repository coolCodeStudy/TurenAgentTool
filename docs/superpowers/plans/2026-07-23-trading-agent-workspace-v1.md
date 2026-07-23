# Trading Agent Workspace V1 Implementation Plan

Status: blocked_pending_owner_scope_decision

**Goal:** Deliver one protected Trading Agent browser workflow using a trusted
read-only evidence snapshot and ChatGPT-authenticated Codex CLI, with five-run
isolation and no cross-feature or real-trading action.

**Do not execute this plan** until:

1. Owner chooses PRD Choice A or B;
2. Global PM approves the corresponding stage contract; and
3. non-mutating ECS Gate A passes.

## Fixed Constraints

- TradingAgents ref
  `a33fd4c0f134485a43553a2c23a63cb14adbd88f` is design evidence only.
- No upstream runtime, prompt, schema, LLM client, dataflow, memory, UI, or
  asset is copied.
- No LLM API key.
- Native web search is the model's only tool.
- Trusted snapshot uses provider-neutral read-only contracts and no feature
  repository write interface.
- At most five Trading runs; later valid runs queue.
- One restricted executor and one sequential Codex child per active run.
- No holdings/review/research/knowledge/code/Git/deploy writes or broker call.
- Trading page reuses shared browser access; it creates no token UI/storage.
- TDD is required for every implementation task.

## Task 0: Owner Choice And Gate A

- [ ] Record Owner choice:
  - A: research stance only; or
  - B: simulated Trader proposal plus simulated Portfolio Manager decision.
- [ ] Update PRD/plan stage and acceptance traceability for that choice.
- [ ] Obtain Global PM design acceptance.
- [ ] Inspect ECS without mutation:
  unit/ref/health/concurrency, Codex version/login/options, web-search-only tool
  inventory, canary denial, executor boundary feasibility, provider-neutral
  snapshot feasibility, host baseline, and shared browser-access config.
- [ ] If any tool/credential/snapshot boundary fails, stop
  `blocked_with_owner`; do not weaken it or start Development.

## Task 1: One Vertical Evidence-To-Result Slice

Create:

- `investment_knowledge_mcp/trading_agent_models.py`
- `investment_knowledge_mcp/trading_agent_evidence.py`
- `investment_knowledge_mcp/trading_agent_runs.py`
- `investment_knowledge_mcp/trading_agent_runner.py`
- initial selected-choice schema
- focused model/evidence/run/runner tests

TDD:

- [ ] Fail request/default/idempotency tests.
- [ ] Fail fixture snapshot tests for CN/HK/US/KR covering source identity,
  as-of/freshness, coverage, deterministic indicators, partial, unavailable,
  and sanitized failures.
- [ ] Fail dependency/no-write tests for the snapshot builder.
- [ ] Fail one fake-Codex structured stage and artifact result test.
- [ ] Implement the minimum separate run/event schema and lifecycle.
- [ ] Implement provider-neutral snapshot assembly from market bars,
  valuation/official adapters where supported, and typed missing sections.
- [ ] Implement exact scrubbed Codex argument/environment construction.
- [ ] Prove one fixture run persists snapshot, validated output, citation
  references, and safe result without touching any other feature.
- [ ] Commit only after the focused suite passes.

This is the first end-to-end usable slice. Cleanup automation and production
deploy machinery are intentionally not prerequisites.

## Task 2: Lease Lifecycle And Five Shared Slots

Modify:

- `scripts/research_agent_worker.py`
- `scripts/trading_agent_executor.py`
- worker installers
- run/executor/worker tests

TDD:

- [ ] Fail five-running/queued-sixth and mixed legacy/Trading invariant tests.
- [ ] Fail lease fencing, heartbeat, stale recovery, cancel-wins, timeout,
  retry-lineage, and orphan-reap tests.
- [ ] Fail executor permission-negative database and environment tests.
- [ ] Add fair work-conserving handler scheduling.
- [ ] Launch Trading executor through fixed dedicated UID/GID arguments.
- [ ] Keep evidence snapshot in trusted code and Trading model logic in the
  restricted executor.
- [ ] Add sanitized readiness state; never store account/auth paths or values.
- [ ] Preserve legacy research behavior with compatibility tests.

## Task 3: Owner-Selected Full Workflow

Choice A:

- [ ] Evidence panel schema.
- [ ] Bull/bear debate schema.
- [ ] Neutral risk/research stance schema.

Choice B:

- [ ] All Choice A evidence/debate work.
- [ ] Simulated Trader proposal schema.
- [ ] Risk review schema.
- [ ] Simulated Portfolio Manager accept/modify/reject schema.
- [ ] Tests proving no real holding read, position sizing, order, or write.

Both:

- [ ] Prior validated JSON is the only stage handoff.
- [ ] Every material claim maps to snapshot evidence or dated native-search
  enrichment.
- [ ] Cancellation/timeout terminates and reaps the process group.
- [ ] Malformed output and managed-tool visibility fail closed.

## Task 4: Protected Browser Workspace

Create dedicated controller/workspace modules and route tests.

- [ ] Add `/trading-agent` after `/command`.
- [ ] Keep public shell empty of run data.
- [ ] Protect every run API with the existing shared access contract.
- [ ] Reuse `InvestmentKnowledgeAccess`; add no Trading token field, storage
  key, or setup path.
- [ ] Test navigation from an authorized Command page without credential
  re-entry.
- [ ] Test canonical recovery and exact request replay when access is absent.
- [ ] Implement Start busy state, durable idempotency, five-running/queued-
  sixth copy, polling, focus preservation, cancellation requested, timeout,
  retry, evidence freshness/missing state, and safe results.
- [ ] Test desktop and 390-pixel layouts and safe source URLs.

## Task 5: Operational Hardening

- [ ] Enforce configurable per-run and root capacity limits with safe admission
  failure.
- [ ] Add opportunistic executor-owned `flock` cleanup after the first
  end-to-end slice; reject symlinks and delete only expired UUID roots.
- [ ] Mark manifest artifacts unavailable only after deletion succeeds.
- [ ] Default, but do not hard-code Product acceptance to, 90 days, 20 MiB per
  run, 20 GiB root, 5 GiB free, and six-hour cleanup interval.
- [ ] Add durable admission bounds and safe rate-limit identity derived from
  domain-separated canonical access state without storing the bearer.
- [ ] Complete permission-negative, load, cancellation, timeout, restart, and
  artifact isolation tests.

## Task 6: Deploy And Acceptance

- [ ] Add exact classifier mapping for Web and worker targets.
- [ ] Independently review the full branch and resolve Critical/Important
  findings.
- [ ] Run full local tests, smoke, architecture audit, delivery audit, flow
  audit, and diff check.
- [ ] Record one Deploy Intent and watch owner.
- [ ] Bootstrap the Ops classifier from the reviewed ref and verify/rollback
  before product deployment.
- [ ] Provision the executor boundary without starting the worker.
- [ ] Use one serialized application deploy.
- [ ] Run Gate B: exact refs, one real run, five plus queued sixth, mixed load,
  cancel, timeout, restart, orphan scan, permissions, artifacts, shared-access
  browser journey, and zero cross-feature mutation.
- [ ] Activate `AT-2026-07-23-001` and dispatch independent L3 acceptance.
- [ ] Reconcile authoritative state before Owner acceptance.

## Verification Commands

Focused commands grow with each task. Final minimum:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/smoke_test.py
python3 scripts/audit_delivery_state.py --feature "Trading Agent Workspace"
python3 scripts/audit_agent_flow_health.py --feature "Trading Agent Workspace"
python3 scripts/audit_architecture_health.py --repo . --format markdown
git diff --check
```

## Current Return Gate

`blocked_with_owner`.

Required resume event: Global PM returns the Owner's explicit Choice A or B and
accepts the revised stage contract. Until then, do not run Gate A, dispatch
Development, change runtime code, deploy, or mutate production.
