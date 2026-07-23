# Trading Agent Workspace V1 Technical Design

Status: draft_pending_global_pm_review
Owner: Trading Agent Workspace Feature Coordinator
Source PRD: `docs/product/PRD-Trading-Agent-Workspace.md`
Implementation plan: `docs/superpowers/plans/2026-07-23-trading-agent-workspace-v1.md`
Feature Registry row: `Trading Agent Workspace`
Quality route: `L3`
Last updated: 2026-07-23

## Design Scope

This design defines the complete V1 implementation slice but does not authorize
runtime implementation, service changes, deployment, or production mutation.
Global Project Manager design review is the next gate.

V1 adds a protected browser workspace, an isolated Trading Agent run model, a
three-stage Codex CLI workflow, at-most-five running semantics, cooperative
cancellation, whole-run timeout, safe artifacts, and cloud readiness checks.
It does not modify any existing investment workflow or import the
TradingAgents runtime.

## Decision Summary

Conditionally reuse the existing `investment-research-agent-worker` systemd
host and ChatGPT-authenticated Codex installation. Do not reuse its broad
database connection for Trading execution, the existing `research_jobs`
schema, `process_job()` handler, shared application working directory, broad
artifact model, or danger-full-access Codex invocation.

Add a typed handler registry to the worker host:

- legacy stock research remains a compatibility handler;
- Trading Agent uses new run/event tables, lease lifecycle, artifact root, and
  browser controller;
- a work-conserving scheduler fills a shared global slot pool;
- each Trading slot spawns a short-lived executor process under a dedicated OS
  account with a PostgreSQL role restricted to Trading Agent tables;
- each Trading Agent run keeps one slot while its three Codex stages execute
  sequentially; and
- every nested Codex process uses a scrubbed environment, ephemeral session,
  ignored user config/rules, empty MCP configuration, native web search as its
  only model tool, explicit disabling of local/connector tools, read-only
  sandboxing as defense in depth, and structured output.

This choice adds no new long-lived daemon. It does add one dedicated OS account,
one restricted database role, and up to five short-lived executor processes.
Host reuse is conditional on the pre-development gate proving the installed
CLI can enforce the web-search-only tool profile.

## Alternatives Considered

### A. Extend The Existing Research Job Handler

Rejected.

The current schema requires stock-research-specific fields, deduplicates active
work by symbol/market, exposes import behavior, lacks lease/heartbeat/retry
fencing, and lets running cancellation be overwritten by late worker
finalization. The current Codex path uses the shared application directory and
defaults to danger-full-access. Passing Trading Agent fields into that handler
would mix product state and violate isolation.

### B. Reuse The Existing Worker Host With A Typed Handler

Selected.

Benefits:

- no new long-lived ECS process;
- reuses the installed ChatGPT subscription login and worker service;
- keeps queue, Web, and worker state in the existing operational system;
- allows a separate schema, artifacts, lifecycle, and Codex child boundary;
- permits explicit compatibility tests for the legacy research path.

Costs:

- the shared scheduler remains privileged, so Trading logic must stay in the
  restricted short-lived executor;
- scheduler refactoring can affect legacy work;
- worker restart affects both handler types;
- deploy classification and worker-specific health need improvement.

### C. Add A Dedicated Trading Agent Systemd Service

Deferred fallback.

This provides the strongest long-lived process separation but adds a new
daemon, installation/bootstrap path, service health contract, restart policy,
and deployment target. Use it only if the pre-development gate shows that the
existing host cannot launch a web-search-only, restricted-user executor or
cannot provide fair scheduling and safe rollback.

### D. One Codex Invocation Or Eleven Upstream-Style Agents

Rejected for V1.

A one-shot prompt hides stage progress and creates all-or-nothing failures.
Eleven independent invocations multiply scheduling, latency, and subscription
load. V1 uses three sequential structured stages that preserve evidence,
challenge, and risk-decision boundaries while keeping at most one Codex child
per running run.

## Evidence Baseline

### Repository Evidence

- `scripts/research_agent_worker.py` already runs a queued Codex research
  worker and can use thread concurrency, but fills slots in batches.
- `investment_knowledge_mcp/research/jobs.py` uses
  `FOR UPDATE SKIP LOCKED`, but its records have no lease token, attempt,
  heartbeat, or guarded finish.
- `investment_knowledge_mcp/daily_market_jobs.py` and
  `scripts/daily_market_brief_history_worker.py` provide the repository's
  stronger lease, heartbeat, stale-recovery, cancellation, and deadline
  patterns.
- `investment_knowledge_mcp/app_gateway.py` is the route/access registry.
- `investment_knowledge_mcp/web_experience.py` owns primary navigation and the
  canonical bearer-access contract.
- `docs/architecture/architecture-contract.md` requires one route owner,
  access class, and contract test.
- Architecture audit result: P0 `0`, P1 `8`. The existing large
  `command_workbench.py`, `weekly_review_web.py`, and `repository.py` modules
  support dedicated Trading Agent modules rather than further concentration.

### TradingAgents Evidence

Verified local ref:
`a33fd4c0f134485a43553a2c23a63cb14adbd88f`, Apache-2.0.

The design consults the upstream analyst/debate/risk/decision progression,
typed handoffs, progress visibility, and report tree. It does not copy its
LangGraph orchestration, prompts, schemas, memory, LLM clients, dataflows, CLI,
or assets.

### Local Codex Execution Probes

Observed on `codex-cli 0.145.0-alpha.30`:

| Probe | Result |
|---|---|
| `codex login status` | `Logged in using ChatGPT`; no API key was supplied |
| `--ephemeral --ignore-user-config --ignore-rules --sandbox workspace-write` | Structured output and a synthetic workspace artifact succeeded |
| `--sandbox read-only --output-schema --output-last-message` | Structured output capture succeeded without model file writes |
| One `curl https://example.com` inside `workspace-write` | DNS blocked |
| top-level native `--search` with `shell_tool` disabled | Official IANA source found; local canary remained unread |
| `--ignore-user-config` plus partial tool disables | Managed non-web tools were still visible in the current app context |

The last result is a safety finding: neither `read-only` nor
`--ignore-user-config` proves a web-search-only tool boundary. The exact ECS
invocation must disable shell, unified execution, apps, plugins, MCP, browser,
computer, patch, and connector capabilities and must pass both tool-inventory
and local-canary negative probes. These local probes do not prove ECS CLI
version, managed policy, login, host capacity, or subscription concurrency.

Public cloud `/health` returned `200` during discovery with
`app_release_sha=77e15185584ba8e6867860420ab2b4ec810cfe03`. That endpoint does
not report worker health. The latest publicly visible Codex Worker workflow
run found during discovery was historical, from 2026-06-01, and cannot prove
current service or login health.

## Architecture

```text
Browser /trading-agent
  -> app_gateway route/access contract
  -> trading_agent_controller safe DTOs
  -> trading_agent_runs / trading_agent_events PostgreSQL queue
  -> existing investment-research-agent-worker process
       -> handler registry / fair slot scheduler
       -> short-lived TradingAgentExecutor process
            -> dedicated OS account
            -> restricted PostgreSQL role
            -> isolated artifact root
            -> scrubbed Codex child with web search as its only model tool
            -> three sequential structured stages
            -> validated structured outputs
            -> allowlisted artifact manifest
  -> protected polling/result APIs
```

The browser, worker scheduler, executor, and Codex child are distinct trust
zones:

- Browser is untrusted and sees only validated DTOs.
- Worker scheduler is trusted control-plane code with legacy privileges; it
  allocates slots and supervises processes but runs no Trading Agent logic.
- Executor is restricted by OS account, PostgreSQL grants, and artifact-root
  permissions.
- Codex child is untrusted research execution with ChatGPT auth, native web
  search only, no local/connector tools, and no application credentials.

## Planned Module Boundaries

### New Files

- `investment_knowledge_mcp/trading_agent_models.py`
  - request, stage, result, citation, and browser DTO dataclasses/enums;
  - validation and serialization only.
- `investment_knowledge_mcp/trading_agent_runs.py`
  - create/list/get/claim/heartbeat/cancel/finalize/retry/stale-recovery SQL;
  - no HTML, Codex execution, or existing research-job access.
- `investment_knowledge_mcp/trading_agent_runner.py`
  - stage prompt assembly, output-schema selection, child environment,
    cancellable Codex process group, deadlines, output validation, safe
    artifacts.
- `scripts/trading_agent_executor.py`
  - short-lived restricted-user entrypoint; claim one Trading run, heartbeat,
    invoke the runner, finalize under the active lease, clean retained
    artifacts, and exit.
- `investment_knowledge_mcp/trading_agent_controller.py`
  - HTTP request validation, protected API dispatch, status codes, and
    allowlisted browser projections.
- `investment_knowledge_mcp/trading_agent_workspace.py`
  - page renderer and page JavaScript; no database calls.
- `tests/test_trading_agent_models.py`
- `tests/test_trading_agent_runs.py`
- `tests/test_trading_agent_runner.py`
- `tests/test_trading_agent_executor.py`
- `tests/test_trading_agent_controller.py`
- `tests/test_trading_agent_workspace.py`

### Modified Files

- `db/schema.sql`
  - add isolated Trading Agent run/event/admission tables, lifecycle
    functions, indexes, grants, and checks.
- `scripts/research_agent_worker.py`
  - host handler registry and work-conserving scheduler;
  - preserve legacy handler through an adapter.
- `scripts/install_research_agent_worker_on_ecs.sh`
  - provision the dedicated executor OS account, executor-owned `CODEX_HOME`,
    restricted artifact root, and root-readable executor environment file.
- `scripts/install_codex_worker_on_ecs.sh`
  - keep combined installer consistent if still authoritative.
- `investment_knowledge_mcp/app_gateway.py`
  - add exact route contracts and controller dispatch.
- `investment_knowledge_mcp/web_experience.py`
  - add `trading_agent` page identity and destination after Command.
- `investment_knowledge_mcp/weekly_review_web.py`
  - only import/delegate the generic gateway; no Trading Agent logic.
- `docs/architecture/architecture-contract.md`
  - add `/trading-agent` route owner and access intent after implementation.
- `scripts/deploy_contract.py`
  - classify new route/controller/worker/schema paths and the systemd target.
- `tests/test_app_gateway.py`
- `tests/test_web_experience.py`
- `tests/test_web_access.py`
- `tests/test_research_agent_worker.py`
- `tests/test_deploy_change_classifier.py`
- `tests/test_deploy_release.py`
- `e2e/cloud-pages.spec.ts`
- `e2e/public-api-contracts.spec.ts`

## Data Model

### `trading_agent_runs`

Required columns:

- `id BIGSERIAL PRIMARY KEY`
- `run_uuid UUID UNIQUE NOT NULL`
- `status TEXT NOT NULL`
- `stage TEXT NOT NULL`
- `market TEXT NOT NULL`
- `symbol TEXT NOT NULL`
- `instrument_name TEXT`
- `as_of_date DATE NOT NULL`
- `research_focus TEXT`
- `time_horizon TEXT NOT NULL`
- `source_policy TEXT NOT NULL`
- `request_fingerprint TEXT NOT NULL`
- `submission_key_hash CHAR(64) UNIQUE NOT NULL`
- `workflow_version TEXT NOT NULL`
- `policy_version TEXT NOT NULL`
- `retry_of_run_id BIGINT REFERENCES trading_agent_runs(id)`
- `attempt_count INTEGER NOT NULL DEFAULT 0`
- `worker_name TEXT`
- `slot_name TEXT`
- `lease_token TEXT`
- `claimed_at TIMESTAMPTZ`
- `heartbeat_at TIMESTAMPTZ`
- `cancel_requested_at TIMESTAMPTZ`
- `deadline_at TIMESTAMPTZ`
- `started_at TIMESTAMPTZ`
- `finished_at TIMESTAMPTZ`
- `failure_code TEXT`
- `result_summary TEXT`
- `artifact_manifest JSONB NOT NULL DEFAULT '{}'`
- `stage_summaries JSONB NOT NULL DEFAULT '{}'`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Allowed status:

- `queued`
- `running`
- `cancel_requested`
- `completed`
- `failed`
- `timed_out`
- `cancelled`

Allowed stage:

- `queued`
- `preparing`
- `evidence_panel`
- `thesis_debate`
- `risk_decision`
- `complete`

Indexes:

- FIFO claim index on `(status, created_at, id)`.
- partial running index for status in `running`, `cancel_requested`.
- heartbeat index for stale recovery.
- retry lineage index on `retry_of_run_id`.
- request fingerprint index for observability, not automatic deduplication.

V1 intentionally allows repeated research for the same instrument. It does not
silently return an existing run. The browser generates a random submission key
as a UUID for each user action, sends it in `Idempotency-Key`, and reuses it
after an HTTP timeout. The server validates the UUID and stores only its
SHA-256 hash. A concurrent create with the same key returns the
original run and canonical status URL. Submission keys never expire or become
reusable; the small hash remains with retained run metadata.

### Events

Use a separate `trading_agent_events` table keyed to
`trading_agent_runs.id`. Columns are `id`, `run_id`, `event_type`, `status`,
`stage`, `safe_message`, bounded `metadata JSONB`, and `created_at`. The
restricted executor role has no direct table DML. It receives only `EXECUTE`
on versioned `SECURITY DEFINER` functions for claim, heartbeat,
cancellation-aware finalize, and bounded event append; those functions enforce
the active lease and touch only the two Trading Agent tables. The role has no
grants on generic `task_events` or any existing investment table. Function
owners are non-login migration roles with a fixed `search_path`. Event metadata
may include elapsed time and attempt. It must not include prompts, credentials,
raw CLI events, local paths, or source document bodies. The only additional
executor grants are the maintenance functions defined below.

### `trading_agent_admission_windows`

The protected Web controller enforces the rolling create limit through a
Trading-Agent-only table with `identity_key_hash`, `window_started_at`,
`attempt_count`, and timestamps. V1 has one canonical protected access
identity, so the identity key is
`HMAC-SHA256(canonical APP_ACCESS_TOKEN, "trading-agent-rate-limit:v1")`.
This reuses the already required, redacted canonical access secret and adds no
new production secret. Neither the bearer nor a raw access identity is stored.
On token rotation, a new HMAC identity starts a new window; old buckets remain
unusable and are deleted after 24 hours. A future multi-identity access model
must version this derivation. The controller atomically increments the current
minute bucket before admission. The restricted executor role has no grant on
this table.

### `trading_agent_maintenance`

One Trading-Agent-only row per maintenance task stores `task_name`,
`lease_token`, `lease_expires_at`, `last_started_at`, `last_finished_at`,
`status`, and safe `last_error_code`. The executor has no direct DML. It
receives `EXECUTE` on fixed-search-path `SECURITY DEFINER` functions to:

- acquire an artifact-cleanup lease under a transaction advisory lock;
- list expired terminal runs and their current manifest hashes;
- record one successfully deleted run by marking manifest entries unavailable
  with `deleted_at`; and
- complete or fail the maintenance lease with a safe code.

Filesystem deletion happens before the manifest update. If the database update
fails, the next cleanup repeats the already-idempotent missing-directory
deletion. A manifest is never marked deleted before the bounded filesystem
operation succeeds.

### Artifact Manifest

The database stores logical artifact names and availability:

```json
{
  "workflow_version": "trading_agent.v1",
  "artifacts": [
    {
      "key": "evidence_panel",
      "kind": "json",
      "available": true,
      "size_bytes": 1234,
      "sha256": "..."
    }
  ]
}
```

Filesystem paths stay server-side and are derived from `run_uuid` plus admitted
artifact keys. Browser callers never provide or receive a path.

### Artifact Lifecycle

The restricted executor owns artifact writes and deletion within the Trading
Agent root. Limits are 2 MiB per structured stage result, 5 MiB per stage
event stream, 2 MiB for the final report, 2 MiB for citations, and 20 MiB per
run. Terminal artifacts are retained for 90 days.

The long-lived scheduler invokes the same restricted executable in
`--cleanup-if-due` mode every six hours; it does not delete files itself. The
maintenance lease, transaction advisory lock, and recorded timestamps prevent
duplicate cleanup. Cleanup derives UUID paths from admitted records, rejects
symlinks, updates manifests only after successful deletion, and never deletes
unexpired artifacts. Admission returns
`artifact_capacity_reached` when free space is below 5 GiB or Trading Agent
root usage exceeds 20 GiB. Cleanup failure is a readiness warning and blocks
admission only when either storage threshold is crossed.

## Queue And Lease Lifecycle

### Admission

- Validate and normalize request.
- Hash the browser submission key and atomically return the existing run on a
  unique-key conflict. A replay is resolved before rate-limit increment.
- Atomically increment the current HMAC-keyed admission window and insert
  `queued` while queued count is below 100 and the protected access identity
  is below 10 create attempts per rolling minute.
- Return `201` or `202` with safe DTO, queue position, and status URL.
- Never reject merely because five runs are running.
- Return typed `429 queue_capacity_reached` or `429 rate_limited` when those
  independent admission bounds are reached.

### Claim

The trusted scheduler allocates an in-memory free slot, chooses the next fair
handler type, and launches the Trading executor through a fixed `setpriv`
argument vector. It does not import or invoke Trading Agent business logic.

The restricted executor then claims within one database transaction:

1. take the Trading Agent advisory admission lock;
2. count `running` plus `cancel_requested` Trading rows and stop if already
   five;
3. select one queued row with `FOR UPDATE SKIP LOCKED`;
4. assign a random lease token, worker/slot identity, attempt count, heartbeat,
   deadline, status `running`, and stage `preparing`;
5. commit before starting Codex.

The scheduler refills one slot as soon as it completes. It does not claim a
five-item batch and wait for the slowest item. The invariant is
`trading_running <= 5` and
`trading_executors + legacy_active <= global_slot_limit`.

### Heartbeat And Cancellation

- Heartbeat updates require run ID, worker, slot, lease token, and attempt.
- It returns whether cancellation was requested and whether the lease remains
  active.
- Queued cancellation atomically sets `cancelled`.
- Running cancellation sets `cancel_requested_at` and status
  `cancel_requested`.
- The runner sees cancellation from the heartbeat loop, sends `SIGTERM` to the
  Codex process group, waits a bounded grace interval, then sends `SIGKILL`.
- Final cancellation requires the same active lease. A late result cannot
  overwrite it.

### Timeout And Restart

- Default stage deadline: 20 minutes.
- Default whole-run deadline: 60 minutes.
- Stage timeout or whole-run timeout terminates the process group and records
  `timed_out`.
- Stale leases are requeued once when heartbeat exceeds the stale threshold and
  `attempt_count < 2`.
- A second stale attempt terminalizes as `failed` with
  `failure_code='worker_lost'`.
- Model/business/schema/capability failures are not automatically retried.
- Retry from the browser creates a new run with `retry_of_run_id`.

## Workflow And Structured Outputs

### Stage 1: Evidence Panel

One Codex invocation returns:

- market/technical evidence;
- fundamentals/valuation evidence;
- news/catalyst/sentiment evidence;
- material claims with URL, publisher, source date, retrieval date, and
  official/non-official classification;
- conflicts, stale evidence, missing evidence, and explicit inference labels.

### Stage 2: Thesis Debate

One Codex invocation receives the normalized request and validated Stage 1
JSON. It returns:

- strongest bull thesis;
- strongest bear/failure-mode thesis;
- evidence references into Stage 1;
- conditions that would invalidate each side;
- unresolved disagreements.

It may use web search only to close an explicitly identified evidence gap and
must add any new sources to the same citation contract.

### Stage 3: Risk Decision

One Codex invocation receives validated Stage 1 and Stage 2 JSON. It returns:

- stance: `bullish`, `neutral`, `bearish`, or `insufficient_evidence`;
- confidence: `low`, `medium`, or `high`;
- time horizon;
- evidence-weighted rationale;
- counter-case;
- key risks;
- invalidation triggers;
- unknowns and limitations;
- complete citation references; and
- a research-only disclaimer.

The trusted parent renders final Markdown from validated structured fields.
Codex does not write final Markdown directly.

## Codex Child Contract

Illustrative command shape:

```bash
codex \
  --disable shell_tool \
  --disable unified_exec \
  --disable apply_patch_freeform \
  --disable apps \
  --disable plugins \
  --disable browser_use \
  --disable browser_use_external \
  --disable computer_use \
  --disable image_generation \
  --disable code_mode_host \
  --disable workspace_dependencies \
  --disable skill_search \
  --disable skill_mcp_dependency_install \
  --disable tool_suggest \
  --disable multi_agent \
  --disable goals \
  --search \
  --config 'mcp_servers={}' \
  exec \
  --strict-config \
  --ephemeral \
  --ignore-user-config \
  --ignore-rules \
  --sandbox read-only \
  --skip-git-repo-check \
  --cd <run-stage-directory> \
  --output-schema <versioned-stage-schema.json> \
  --output-last-message <wrapper-selected-result.json> \
  --json \
  <prompt>
```

The exact disable vector is versioned with the admitted ECS CLI. The
implementation passes arguments without a shell, treats any unknown option as
a readiness failure, and starts a new process session so cancellation can
terminate the group. `read-only` remains defense in depth; the primary secret
boundary is removal of every model-local tool except native web search.

The short-lived executor environment contains only its restricted PostgreSQL
connection, lease identity, executor-owned artifact root, and process
essentials. The nested Codex environment allowlist is narrower:

- `PATH`
- `HOME` set to the dedicated executor home
- `CODEX_HOME` set to the executor-owned ChatGPT auth location
- `TMPDIR` set to a run-specific temporary directory
- `LANG`
- `LC_ALL`
- explicit non-secret model/profile values admitted by the design

Explicitly absent:

- `OPENAI_API_KEY`
- `DATABASE_URL`
- all `POSTGRES_*`
- all GitHub tokens/credentials
- all deploy/Ops credentials
- browser/Command access credentials
- DingTalk credentials
- broker/Futu credentials
- application secret keys
- inherited proxy credentials

The runner validates at startup:

- Codex binary/version;
- `codex login status`;
- no API-key mode;
- strict option/config parsing;
- structured-output probe;
- version-admitted prompt/tool introspection (currently
  `codex debug prompt-input`, or an equivalently reviewed CLI contract) shows
  that the model-visible inventory equals native web search only;
- local canary and executor-environment values cannot be read by the model;
- native web-search probe reaches an admitted public source;
- JSONL contains only admitted event kinds and no local/MCP/app/tool call;
- the executor database role receives permission denial for representative
  forbidden reads and writes;
- artifact-root ownership and free space.

Any failure returns a typed readiness state and prevents claims.

## Browser API

Public shell:

- `GET /trading-agent`
- `GET /assets/trading-agent.js`

Protected:

- `GET /api/trading-agent/runs?limit=<1..50>`
- `POST /api/trading-agent/runs`
- `GET /api/trading-agent/runs/<id>`
- `POST /api/trading-agent/runs/<id>/cancel`
- `POST /api/trading-agent/runs/<id>/retry`
- `GET /api/trading-agent/runs/<id>/events`
- `GET /api/trading-agent/runs/<id>/artifacts/<admitted-key>`

Dynamic routes use anchored full-match patterns. Authorization runs before
body parsing or database lookup. Data/mutation routes reject tokenless access
with the existing structured access-recovery contract.

Create requires a valid UUID `Idempotency-Key`. The browser keeps the same key
until it receives a definitive response; only a later deliberate Start
Research action creates a new key.

Create response includes:

- run ID and UUID;
- status and stage;
- queue position;
- `running_count`;
- `running_limit=5`;
- canonical list/detail URLs.

Safe artifact endpoints return parsed/validated JSON or escaped text with
bounded size. They never accept a filename. Source links accept only public
`http`/`https` URLs with no credentials, localhost/private literal address, or
unsafe scheme; rendered links use `rel="noopener noreferrer"`. Invalid source
values remain non-clickable evidence warnings.

## Browser State Machine

- Keep immutable pending-create/cancel/retry requests for access retry.
- Distinguish browser timeout from worker timeout.
- Disable only the currently mutating control.
- Announce create/cancel/terminal transitions, not every poll.
- Preserve selection and focus during list refresh.
- Poll selected active detail every two seconds and list every five seconds.
- Back off after failure, pause when hidden, refresh on visibility.
- Never poll terminal runs.
- Render queued, running, cancel-requested, timed-out, failed, cancelled, and
  completed states separately.

Result views:

- Overview
- Evidence
- Bull/Bear
- Risk Decision
- Sources
- Structured Output

Markdown is escaped/read-only unless a separate sanitizer is admitted.

## Process And Deployment Impact

V1 process topology after implementation:

- no new long-lived service;
- one existing `investment-research-agent-worker` Python process;
- up to five shared scheduler slots;
- one dedicated `investment-trading-agent` OS account and executor-owned
  `CODEX_HOME`;
- one PostgreSQL executor role granted only the Trading Agent run/event
  lifecycle;
- at most five short-lived Trading Agent executor process groups and five
  nested Codex CLI processes;
- the existing `weekly-review-web` application process serves the new route;
- PostgreSQL stores the isolated run and event tables;
- the worker publishes a sanitized Trading Agent readiness heartbeat through
  the existing `worker_status` table; and
- the existing durable drafts mount stores the isolated artifact root.

The installed unit path, environment, active state, Codex version/login, and
effective concurrency are not statically known.

Future Deploy Intent:

- Feature: Trading Agent Workspace
- Ref: reviewed authoritative release commit
- Mode: one separately reviewed Ops control-plane bootstrap for the classifier
  update, one non-starting host bootstrap, then one serialized
  `targeted_quick` application deploy
- Affected targets: `weekly-review-web`, database schema consumers, and
  `investment-research-agent-worker.service`; one reviewed host bootstrap is
  required to create the executor account/auth home, restricted DB credential,
  and artifact permissions
- Reason: add route/controller/queue/handler and restart the worker on reviewed
  code
- Verification URL: `/trading-agent`
- Watch owner: Trading Agent Workspace Feature Coordinator through worker
  readiness, five-run load, cancellation, timeout, restart recovery, and L3
  acceptance

No deploy is authorized by this design-only change.

V1 changes `scripts/deploy_contract.py` so the server-authoritative classifier
can select `investment-research-agent-worker.service`; it does not change
`scripts/deploy_release.py` or `scripts/ecs_ops_api.py`. Because the independent
Ops API imports the classifier from `/opt/investment-ops`, the release owner
must first bootstrap/restart that control plane from the exact reviewed ref
through the existing Ops bootstrap workflow, verify `/health`, `/ops/status`,
and classifier output, and stop before product deployment if any check fails.
Control-plane rollback reinstalls the prior known-good Ops ref and verifies the
same checks.

After that succeeds, a non-starting host bootstrap from the reviewed candidate
creates the executor account/auth home, restricted database role/credential,
artifact permissions, and revised worker unit while snapshotting the prior
unit and ownership. It must not restart the worker or switch `current`.
Failure restores the unit snapshot and permissions. The normal serialized
application deployment then applies schema, switches the immutable release,
and restarts the classifier-selected Web and worker targets. Application
rollback restores the prior release and unit snapshot, restarts the legacy
worker, and leaves additive Trading Agent tables/artifacts inert.

Codex capability readiness is owned by the worker and stored as sanitized
`worker_status` metadata; no new Ops status endpoint is added.

If the executor-owned ChatGPT login is absent, the exact Owner/operator action
is to run the installer-provided device-login command as
`investment-trading-agent`, follow the displayed OpenAI device-login flow, and
then rerun the redacted readiness check. No token value is entered into the
product, repository, or chat.

## Cloud Readiness Gates

### Gate A: Before Development

A read-only ECS inspection must establish:

1. installed unit `ExecStart`, active/enabled state, and loaded immutable ref;
2. current worker concurrency, legacy queue state, and whether a restart would
   strand work;
3. installed Codex version supports strict option parsing, native `--search`,
   structured output, and every required tool-disable option;
4. ChatGPT login mode without exposing account/auth material and no API-key
   fallback;
5. version-admitted prompt/tool introspection plus an adversarial execution
   probe shows a web-search-only model inventory with empty MCP/app/plugin
   surfaces;
6. a negative local-canary probe and JSONL scan showing no local, shell,
   unified-exec, patch, MCP, app, browser, computer, or connector call;
7. feasibility of a dedicated executor account, executor-owned `CODEX_HOME`,
   restricted PostgreSQL role, and isolated artifact root on the current host;
8. current host CPU/memory/disk baseline and process limits; and
9. current public application ref and protected bearer-access configuration.

Gate A does not launch five production children, mutate the database, restart
the unit, or deploy. Host reuse remains conditional until Gate A passes. If
items 3-7 fail, the coordinator returns `blocked_with_owner` to Global PM with
the dedicated-service/CLI-upgrade alternatives; it never relaxes the tool or
credential boundary.

### Gate B: After Implementation, Before Release

Against the reviewed candidate and isolated test records, Gate B proves:

1. schema grants deny representative forbidden reads and writes;
2. exact artifact ownership, symlink rejection, free-space and size caps;
3. five synthetic concurrent executors fit CPU/memory/process and subscription
   limits while a sixth Trading run remains queued;
4. mixed legacy/Trading load satisfies both concurrency invariants;
5. cancellation and timeout terminate/reap the full executor/Codex process
   group;
6. worker restart recovers or terminalizes leases exactly once; and
7. the protected acceptance session/fixture contract is available.

Gate B authorizes neither deployment nor Owner acceptance by itself. It is the
precondition for the normal serialized deploy and L3 acceptance route.
The Feature Coordinator owns obtaining the acceptance path and dispatches the
Quality & Acceptance Lead. Preferred evidence uses an already authorized
in-app browser session. If none exists, the row becomes `blocked_with_owner`
for an approved secure fixture location/session calling contract; the Owner is
never asked to disclose the bearer value.

## Security And Failure Analysis

| Risk | Required control |
|---|---|
| Prompt attempts to read auth/local data | Disable shell/unified-exec/patch/filesystem/MCP/app/browser/computer/connector tools; empty MCP config; negative canary and tool-inventory gate |
| Prompt attempts to write code/data | No model-local write tool; read-only sandbox as defense in depth; dedicated executor account |
| Executor reaches forbidden database state | Restricted PostgreSQL role plus permission-negative tests; Codex child receives no database environment |
| Child inherits database/deploy secrets | Construct environment from allowlist, never mutate inherited `os.environ` in place |
| Shell network bypass | No shell or unified-exec tool; native web search only; no danger-full-access |
| Cancellation overwritten by late completion | Lease-guarded finalization and cancellation-wins state transition |
| Orphan subprocess | New process session, TERM/KILL group cleanup, wait/reap assertion |
| User-controlled path traversal | UUID-only directories and admitted artifact keys |
| Raw output leaks | Schema validation, safe DTO allowlist, bounded sanitized events/errors |
| Sixth run rejected | Queued rows excluded from running cap |
| Browser timeout creates duplicate run | Idempotency key and distinct browser/worker timeout copy |
| Unsafe source link | Public `http`/`https` validation, no credentials/private literals, safe link attributes |
| Queue or disk exhaustion | 100 queued, 10 creates/minute/identity, 20 MiB/run, 20 GiB root, 5 GiB free-space admission floor |
| Shared-worker regression | Legacy compatibility adapter and focused worker scheduling tests |
| Worker restart strands work | Heartbeat, stale recovery, attempt fencing, drain/recovery deploy plan |
| Managed tool injection | Strict disable vector, empty MCP config, model-visible inventory and negative canary; fail closed |

## Test Strategy

### Unit And Contract

- request and structured-stage schema validation;
- citation/inference coverage;
- queue admission, FIFO order, and five-running cap;
- 100-queued and 10-create/minute admission bounds with typed `429` responses;
- durable submission-key replay under concurrent duplicate requests;
- concurrent claims with `FOR UPDATE SKIP LOCKED`;
- lease fencing, heartbeat, stale recovery, cancellation-wins, timeout, and
  retry lineage;
- restricted PostgreSQL grants and permission-negative forbidden-table tests;
- UUID-only workspace, artifact allowlist, size/storage thresholds, cleanup
  cadence, and symlink rejection;
- exact child argument vector, empty MCP config, tool-disable vector, and
  scrubbed environment;
- ChatGPT-only auth and no API-key fallback;
- structured-output, native-search-only inventory, local-canary denial, and
  managed-tool-injection readiness results;
- process-group TERM/KILL/reap behavior;
- legacy research handler compatibility;
- route owner/access inventory and authorization-before-body-read;
- public shell contains no run data;
- safe DTO projection and no path/log/prompt/credential fields;
- public `http`/`https` source-link validation and unsafe-scheme rejection;
- navigation order after Command Workbench;
- browser busy, access recovery, polling, focus, compact layout, cancel,
  timeout, retry, and result tabs;
- deploy classification and worker restart/rollback contract.

### Integration

- PostgreSQL concurrency tests for five claims plus queued sixth;
- restricted executor-role tests that representative forbidden SQL fails;
- short-lived executor launch under the dedicated OS account;
- worker restart with active leases;
- fake Codex executable for stage progression, cancellation, timeout,
  malformed output, and capability failure;
- artifact hash/size/retention cleanup bounded to Trading Agent root;
- app gateway HTTP tests for every public/protected route.

### Browser

- desktop and 390-pixel viewports;
- immediate Start Research progress and duplicate-submit prevention;
- five running plus queued sixth;
- selected-run polling and visibility pause/resume;
- cancel-requested transition;
- browser timeout preserving unknown/running state;
- worker timeout and retry-as-new-run;
- safe escaped artifacts and source links;
- keyboard/focus and live-region behavior;
- no horizontal overflow or secret/internal text.

### Cloud L3

- immutable deployed ref and worker-loaded ref;
- public shell and protected API boundary;
- one complete real Codex run with citations;
- five concurrent synthetic runs plus queued sixth;
- running cancellation and orphan-process scan;
- forced timeout and safe error;
- worker restart and lease recovery;
- artifact root/isolation/permission inspection;
- permission-denied reads/writes against forbidden tables and zero Git/deploy
  state mutation;
- protected independent-acceptance session/fixture provenance without
  disclosing its bearer value;
- independent real-browser acceptance.

## Rollback

- Stop new Trading Agent admission through a feature readiness flag.
- Allow active runs to drain or mark them cancelled through the lease contract.
- Roll back `weekly-review-web` and the shared worker to the prior immutable
  ref through the serialized deploy path.
- Leave the new tables and artifact root in place; schema rollback is not
  required to restore prior application behavior.
- Do not delete run artifacts during emergency rollback.
- Verify legacy research worker health and existing public routes after
  rollback.
- If the shared scheduler caused the incident, disable only the Trading Agent
  handler registration and preserve the legacy adapter.

## Bounded Implementation Slice

### Prerequisite: Gate A Host Decision

Before Development, the Feature Coordinator performs the read-only Gate A
inspection. Global PM accepts shared-host reuse only if the ECS CLI has the
required web-search-only tool boundary and the host can provision the
restricted executor account/role/root. Otherwise the feature returns to Global
PM with the dedicated-service or CLI-upgrade alternative; no shared-worker code
is started.

### Slice 1: Durable Run Lifecycle

Create typed models, isolated run/event schema, durable submission keys,
restricted executor role/grants, run repository, and deterministic lifecycle
tests. Completion gate: five-slot admission, queue/rate bounds, concurrent
idempotency replay, permission-negative SQL, lease fencing,
cancellation-wins, timeout, retry lineage, and stale recovery pass against
fixtures and PostgreSQL.

### Slice 2: Restricted Executor And Web-Search-Only Codex Runner

Create the short-lived executor, three stage schemas, prompts, safe child
environment, process-group runner, tool-inventory/canary readiness probes,
artifact manifest, six-hour cleanup, exact storage bounds, and fake-Codex
tests. Completion gate: no API-key fallback, no local/connector model tool, no
inherited application credential, cancellation and timeout reap children,
malformed output fails safely, and managed tool injection blocks claims.

### Slice 3: Shared Worker Scheduler

Add handler registry, legacy adapter, restricted-user process launcher, fair
work-conserving slots, and sanitized readiness state in the existing
`worker_status` table. Completion
gate: legacy research tests pass, slot refill is immediate, queue starvation
is bounded, one handler failure does not kill the loop, and readiness metadata
contains no account identity, auth path, prompt, environment value, or token.

### Slice 4: Protected Browser Workspace

Add the route owner, controller, renderer, navigation, browser state machine,
safe artifacts, public-link validation, and typed admission errors. Completion
gate: public shell/protected API contract, immediate progress,
five-running/queued-sixth, duplicate replay, queue/rate/capacity states,
cancel/timeout/retry, safe results, accessibility, and compact layout tests
pass.

### Slice 5: Deploy And Cloud Readiness

Add host bootstrap classification, worker target/restart/rollback, safe
readiness reporting, and exact Gate B verification manifest. Completion gate:
the reviewed bootstrap provisions the executor boundary, one serialized
release path covers the route and worker, the capability/load/cleanup gates
pass, and no manual ad hoc service restart is needed.

### Slice 6: Independent Acceptance And State Reconciliation

Activate `AT-2026-07-23-001` for the reviewed release candidate, run L3
independent acceptance, update traceability and delivery state, reconcile the
coordinator ref with authoritative state, and ask the Owner only after
acceptance passes.

## Implementation Traceability

| PRD criterion | Planned slice | Design evidence |
|---|---|---|
| First-class route after Command | Slice 4 | shared navigation/gateway contract |
| Public shell, protected data | Slice 4 | Command recoverable-shell precedent |
| Immediate durable Start Research | Slices 1 and 4 | durable async Daily precedent |
| Five running, sixth queued | Slices 1 and 3 | explicit run/slot contract |
| Accurate stage/status/events | Slices 1-4 | three structured stages |
| Cooperative cancellation | Slices 1-3 | lease and process-group contract |
| Whole-run timeout | Slices 1-3 | deadline and typed terminal state |
| Retry lineage | Slices 1 and 4 | immutable original plus new run |
| Evidence/debate/risk result | Slice 2 | clean-room TradingAgents mapping |
| Citation coverage | Slice 2 | structured source contract |
| ChatGPT-only Codex | Slices 2, 3, and 5 | installer and local login probe |
| Web-search-only tool boundary | Prerequisite, Slices 2 and 5 | disable vector, inventory, canary, native-search probes |
| Executor credential isolation | Slices 1, 2, and 5 | OS user, restricted DB role, nested child allowlist |
| No cross-feature writes | Slices 1-5 | permission-negative SQL, separate queue/events/artifacts |
| Safe browser links and DTOs | Slice 4 | URL and controller allowlists |
| Durable duplicate replay and admission bounds | Slices 1 and 4 | submission-key hash, 100 queued, 10/minute, typed 429 |
| Artifact size, retention, and cleanup | Slices 1, 2, and 5 | maintenance lease/functions, manifest tombstones, 20 MiB/run, 90 days, six-hour cleaner, storage floors |
| Desktop/compact accessibility | Slice 4 | shared shell and browser contracts |
| Local/cloud/independent verification | Slices 5 and 6 | L3 route |

## Review Questions

Global PM should explicitly accept or change:

1. conditional shared worker host with a dedicated short-lived executor versus
   the long-lived dedicated-service fallback;
2. Gate A requiring native web search as the only model tool and rejecting
   managed tool injection;
3. dedicated executor OS account, executor-owned ChatGPT login, restricted
   PostgreSQL role, and isolated artifact root;
4. five running runs, at most five executor/Codex process pairs, and shared
   global slots with legacy research;
5. 100 queued and 10 create attempts/minute/access identity;
6. CN/HK/US/KR market set and typed input fields;
7. three sequential stage design;
8. 20-minute stage and 60-minute run deadlines;
9. one stale-worker retry, but no automatic model/business retry;
10. 90-day retention, exact file/run/root caps, six-hour cleanup, and storage
    admission floor;
11. public recovery shell with protected bearer-access run APIs;
12. owner-approved protected acceptance session/fixture before L3 closure; and
13. no cross-feature exports.

## Current State

- Product decisions and source provenance are documented.
- Local focused regression passed 94 tests covering the gateway, browser
  experience/access, and deploy classifier. Architecture audit remains P0 `0`,
  P1 `8`, with all P1 findings pre-existing and owned outside this design-only
  change.
- Local Codex execution probes completed as recorded above.
- Static worker and browser discovery returns passed the Coordinator Return
  Gate for design evidence.
- Independent design review initially found two Critical and six Important
  boundary/lifecycle gaps. The revised package was re-reviewed and approved
  with no remaining Critical or Important finding.
- Runtime implementation: not started.
- Deployment: not started and not authorized.
- Acceptance Queue: `AT-2026-07-23-001` is `not_required` because no release
  candidate exists; activate that row only after implementation integration.
- Next action: Global PM design review.
