# Trading Agent Workspace V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a protected browser workspace that queues up to five isolated
Trading Agent runs and executes a three-stage, ChatGPT-subscription-backed
Codex CLI research workflow without writing any existing investment or
delivery state.

**Architecture:** Reuse the existing `investment-research-agent-worker`
systemd host only after Gate A proves the ECS tool and host boundary. Store
Trading Agent state in separate lease-fenced run/event tables. Each Trading
slot launches a short-lived executor under a dedicated OS account and
restricted PostgreSQL role; its nested Codex process has native web search as
its only model tool. Expose only allowlisted protected DTOs through a
dedicated route owner.

**Tech Stack:** Python 3.11, PostgreSQL/psycopg, stdlib HTTP server and
JavaScript, Codex CLI, unittest, Node browser harness, Playwright, systemd, and
the repository deploy classifier.

## Global Constraints

- Development must not start until Global PM accepts
  `docs/product/PRD-Trading-Agent-Workspace.md` and
  `docs/techplans/trading-agent-workspace-v1.md`.
- TradingAgents is design evidence only at
  `a33fd4c0f134485a43553a2c23a63cb14adbd88f`, Apache-2.0; copy no upstream
  code, prompts, schemas, UI, images, or dataflows.
- V1 uses ChatGPT-authenticated Codex CLI only and has no `OPENAI_API_KEY`
  fallback.
- Every Codex child uses strict option parsing, an empty MCP config, native
  `--search`, explicit local/connector tool disables, `--ephemeral`,
  `--ignore-user-config`, `--ignore-rules`, `--sandbox read-only`,
  `--skip-git-repo-check`, `--output-schema`, `--output-last-message`, and
  `--json`.
- Native web search is the only admitted model tool. Tool inventory, local
  canary, or capability failure blocks claims and never enables a local tool
  or danger-full-access.
- At most five Trading Agent runs are `running`; the sixth valid run remains
  `queued`.
- A running run executes one Codex stage at a time.
- Codex children receive no database, GitHub, deploy, DingTalk, broker,
  browser-access, or API-key credentials.
- The restricted executor role has no direct table DML. It receives only
  `EXECUTE` on fixed-search-path, versioned `SECURITY DEFINER` lifecycle
  and maintenance functions that touch only the new Trading Agent tables,
  plus its executor-owned artifact root.
- V1 allows 100 queued rows and 10 creates/minute/protected identity; excess
  admission returns typed `429` without changing the five-running rule.
- Artifacts are capped at 20 MiB/run, retained for 90 days, cleaned every six
  hours, and admission-blocked below 5 GiB free or above 20 GiB root usage.
- No writes to holdings, transactions, Weekly Review, Daily Brief,
  `research_jobs`, knowledge, code, Git, or deploy state.
- All production code follows TDD with a witnessed failing test before the
  implementation change.
- Quality route is L3 and requires a deployed-ref manifest plus independent
  real-surface acceptance.

---

### Task 0: Read-Only ECS Gate A And Host Decision

**Files:**

- Modify only after the probe: `docs/techplans/trading-agent-workspace-v1.md`
- Modify only after the probe: `docs/project-management/Feature-Registry.md`
- Modify only after the probe: `docs/project-management/Delivery-Queue.md`

- [ ] **Step 1: Inspect the existing unit without restart or mutation**

Record the unit `ExecStart`, active/enabled state, loaded ref, effective
concurrency, legacy queue state, host CPU/memory/disk/process baseline, and
public app ref. Redact environment values and account/auth identity.

- [ ] **Step 2: Probe the installed Codex boundary**

Verify version, ChatGPT login mode, no API-key fallback, strict option support,
native `--search`, structured output, empty MCP/app/plugin inventory, and the
full tool-disable vector. Use version-admitted prompt/tool introspection
(`codex debug prompt-input` for the currently observed CLI, or an equivalently
reviewed contract) plus an adversarial execution probe. Run a non-secret
local-canary negative probe and reject any JSONL
local/shell/unified-exec/patch/MCP/app/browser/computer/connector event.

- [ ] **Step 3: Validate executor-boundary feasibility**

Confirm the host can provision a dedicated executor account, executor-owned
`CODEX_HOME`, restricted PostgreSQL role, and isolated artifact root without a
new long-lived service. Do not create them in Gate A.

- [ ] **Step 4: Apply the decision gate**

If Gate A passes, update the technical design with redacted evidence and allow
Task 1. If the tool allowlist or restricted executor boundary cannot be
enforced, stop `blocked_with_owner` and return the dedicated-service or
CLI-upgrade alternatives to Global PM. Do not start shared-worker code.

### Task 1: Typed Run Model And Lease-Fenced Queue

**Files:**

- Create: `investment_knowledge_mcp/trading_agent_models.py`
- Create: `investment_knowledge_mcp/trading_agent_runs.py`
- Modify: `db/schema.sql`
- Create: `tests/test_trading_agent_models.py`
- Create: `tests/test_trading_agent_runs.py`

**Interfaces:**

- Produces:
  `TradingAgentRequest.from_payload(payload: dict[str, object])`,
  `create_run(request, idempotency_key)`,
  `claim_next_run(worker_name, slot_name, running_limit=5)`,
  `heartbeat_run(run_id, worker_name, slot_name, lease_token, attempt_count)`,
  `request_cancel(run_id)`, `finish_run(...)`, `retry_run(run_id)`,
  `recover_stale_runs(stale_after_seconds)`, and safe list/detail projections.
- Consumes: existing `investment_knowledge_mcp.db.transaction`,
  `serialization.to_jsonable`; uses isolated `trading_agent_events`, not
  generic task events.

- [ ] **Step 1: Write failing request-contract tests**

```python
def test_request_defaults_and_normalizes() -> None:
    request = TradingAgentRequest.from_payload(
        {"market": "us", "symbol": " nvda ", "time_horizon": "3-6 months"}
    )
    assert request.market == "US"
    assert request.symbol == "NVDA"
    assert request.source_policy == "official_first"


def test_request_rejects_future_date_and_unsafe_symbol() -> None:
    with unittest.TestCase().assertRaises(ValueError):
        TradingAgentRequest.from_payload(
            {"market": "US", "symbol": "../NVDA", "as_of_date": "2099-01-01"}
        )
```

Add tests that the create API requires a UUID `Idempotency-Key`, stores only
its SHA-256 hash, and reuses the same key after a transport timeout.

- [ ] **Step 2: Run the request tests and confirm the missing-module failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_trading_agent_models -v
```

Expected: import failure for `investment_knowledge_mcp.trading_agent_models`.

- [ ] **Step 3: Implement the exact request and status types**

```python
class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class RunStage(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    EVIDENCE_PANEL = "evidence_panel"
    THESIS_DEBATE = "thesis_debate"
    RISK_DECISION = "risk_decision"
    COMPLETE = "complete"
```

Implement `TradingAgentRequest` with the exact PRD enums and bounds. Generate
the request fingerprint from canonical JSON, but do not deduplicate separate
user submissions by fingerprint.

- [ ] **Step 4: Run the request tests and confirm they pass**

Run:

```bash
.venv/bin/python -m unittest tests.test_trading_agent_models -v
```

Expected: all model tests pass.

- [ ] **Step 5: Write failing queue/lease tests**

```python
def test_sixth_run_is_queued_when_five_are_running() -> None:
    runs = [create_fixture_run() for _ in range(6)]
    claims = [
        claim_next_run("worker", f"slot-{index}", running_limit=5)
        for index in range(1, 7)
    ]
    assert len([row for row in claims if row is not None]) == 5
    assert get_run(runs[5]["id"])["status"] == "queued"


def test_cancelled_lease_cannot_be_overwritten_by_late_finish() -> None:
    run = create_fixture_run()
    claimed = claim_next_run("worker", "slot-1")
    request_cancel(run["id"])
    finish_cancelled_run(**lease_args(claimed))
    with unittest.TestCase().assertRaisesRegex(ValueError, "lease"):
        finish_run(
            **lease_args(claimed),
            status="completed",
            result_summary="late",
            artifact_manifest={},
            stage_summaries={},
        )
```

Add tests for concurrent submission-key replay, raw-key non-persistence, the
100-queued and 10-create/minute bounds, and restricted-role permission denial
for representative holdings, transaction, Weekly, Daily, research, knowledge,
generic task-event, code, and deploy writes.

- [ ] **Step 6: Run queue tests and confirm lifecycle functions are missing**

Run:

```bash
.venv/bin/python -m unittest tests.test_trading_agent_runs -v
```

Expected: failures naming the unimplemented queue functions.

- [ ] **Step 7: Add the isolated schema and transactional queue functions**

Use separate `trading_agent_runs` and `trading_agent_events` tables with the
exact columns/checks in the technical design. Add a
`trading_agent_admission_windows` table keyed only by
`HMAC-SHA256(APP_ACCESS_TOKEN, "trading-agent-rate-limit:v1")` plus minute
bucket; add no secret, never persist the bearer, verify rotation starts a new
identity, and delete buckets older than 24 hours. Add
`trading_agent_maintenance` with a durable cleanup lease and timestamps. Store
a unique submission-key hash and
replay the original run on conflict. Enforce the 100-queued and
10-create/minute bounds atomically. Provision a restricted executor login role
with no direct table DML and `EXECUTE` only on fixed-search-path
`SECURITY DEFINER` functions for claim, heartbeat, bounded event append,
finalize, cleanup-lease acquisition/completion, expired-run listing, and
post-delete manifest tombstones. Claim with `FOR UPDATE SKIP LOCKED`;
heartbeat and finish require run ID, worker, slot, lease token, attempt, and
active status. Queued cancellation terminalizes immediately. Running
cancellation sets `cancel_requested`.

- [ ] **Step 8: Run queue, schema, and existing research tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_trading_agent_models \
  tests.test_trading_agent_runs \
  tests.test_command_router \
  -v
```

Expected: Trading Agent tests pass and existing research command behavior has
no regression.

- [ ] **Step 9: Commit the durable lifecycle**

```bash
git add \
  db/schema.sql \
  investment_knowledge_mcp/trading_agent_models.py \
  investment_knowledge_mcp/trading_agent_runs.py \
  tests/test_trading_agent_models.py \
  tests/test_trading_agent_runs.py
git commit -m "feat: add isolated trading agent run lifecycle"
```

### Task 2: Restricted Executor And Web-Search-Only Codex Runner

**Files:**

- Create: `investment_knowledge_mcp/trading_agent_runner.py`
- Create: `scripts/trading_agent_executor.py`
- Create: `investment_knowledge_mcp/trading_agent_schemas/evidence_panel.v1.json`
- Create: `investment_knowledge_mcp/trading_agent_schemas/thesis_debate.v1.json`
- Create: `investment_knowledge_mcp/trading_agent_schemas/risk_decision.v1.json`
- Create: `tests/test_trading_agent_runner.py`
- Create: `tests/test_trading_agent_executor.py`

**Interfaces:**

- Consumes: `TradingAgentRequest`, claimed run lease, heartbeat callback, and
  run-specific artifact root.
- Produces:
  `TradingAgentRunner.readiness() -> RunnerReadiness`,
  `TradingAgentRunner.run(claimed_run) -> RunOutcome`,
  `build_codex_args(stage, paths) -> list[str]`, and
  `build_child_env(base: Mapping[str, str], run_tmp: Path) -> dict[str, str]`.

- [ ] **Step 1: Write failing child-boundary tests**

```python
def test_codex_args_are_ephemeral_read_only_and_structured() -> None:
    args = build_codex_args(Stage.EVIDENCE_PANEL, fixture_paths())
    assert "--ephemeral" in args
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--search" in args
    assert "mcp_servers={}" in args
    assert "shell_tool" in disabled_features(args)
    assert "unified_exec" in disabled_features(args)
    assert "--dangerously-bypass-approvals-and-sandbox" not in args


def test_child_environment_drops_application_credentials() -> None:
    env = build_child_env(
        {
            "PATH": "/bin",
            "CODEX_HOME": "/auth",
            "DATABASE_URL": "secret",
            "POSTGRES_PASSWORD": "secret",
            "OPENAI_API_KEY": "secret",
            "OPS_API_TOKEN": "secret",
        },
        Path("/tmp/run"),
    )
    assert env["CODEX_HOME"] == "/auth"
    for name in (
        "DATABASE_URL",
        "POSTGRES_PASSWORD",
        "OPENAI_API_KEY",
        "OPS_API_TOKEN",
    ):
        assert name not in env
```

Add a subprocess-boundary test proving the executor is launched through a
fixed `setpriv` vector under the dedicated UID/GID with only the restricted
database connection and executor root, while the nested Codex environment
drops that database connection.

- [ ] **Step 2: Run runner tests and confirm the module is missing**

Run:

```bash
.venv/bin/python -m unittest tests.test_trading_agent_runner -v
```

Expected: import failure.

- [ ] **Step 3: Implement exact argument and environment construction**

Use an argument list with no shell and strict option parsing. Disable every
local/connector tool named in the technical design, configure empty MCP, and
enable native `--search` only. Set `start_new_session=True`. Use a fresh
run-specific `TMPDIR`. Validate output against the versioned JSON schema before
persisting a stage summary. Executor-render final Markdown from validated
structured values.

- [ ] **Step 4: Write failing cancellation, timeout, and readiness tests**

```python
def test_cancel_terminates_and_reaps_process_group() -> None:
    fake = FakeCodexProcess(waiting=True)
    outcome = runner(fake_process=fake).run(claimed_run(cancel_after_heartbeat=True))
    assert outcome.status == "cancelled"
    assert fake.group_signals == ["TERM", "KILL"]
    assert fake.waited


def test_readiness_fails_closed_when_managed_tool_is_visible() -> None:
    readiness = runner(
        probe_result={"web_search": True, "tool_names": ["web_search", "exec"]}
    ).readiness()
    assert not readiness.ready
    assert readiness.failure_code == "local_tool_visible"
```

Add tests proving the non-secret local canary cannot be read, JSONL rejects any
non-web tool call, source URLs reject unsafe schemes/private literals, and the
Codex child cannot see executor database values.

- [ ] **Step 5: Implement heartbeat-driven process control**

Start a heartbeat thread while each Codex child runs. On cancellation, timeout,
or lease loss, signal the process group, wait for the configured grace period,
kill if needed, and reap. Do not write terminal database state from the runner;
return a typed `RunOutcome` to the lease owner.

- [ ] **Step 6: Implement three sequential stages**

Evidence, debate, and risk-decision each invoke Codex once. Pass prior validated
JSON in the next prompt. The process cap remains one child per claimed run.
Record only bounded sanitized stage events.

- [ ] **Step 7: Implement bounded artifacts and retention cleanup**

Enforce 2 MiB per stage result, 5 MiB per stage event stream, 2 MiB final
report, 2 MiB citations, and 20 MiB/run. Run a symlink-rejecting cleanup every
six hours under an advisory lock and recorded last-cleanup timestamp, retain
terminal artifacts for 90 days, never delete unexpired artifacts, and block
admission below 5 GiB free or above 20 GiB root usage. The long-lived
scheduler invokes the same restricted executable with `--cleanup-if-due`; it
does not delete files itself. Acquire the durable maintenance lease, delete a
UUID-derived directory first, then call the restricted manifest-tombstone
function with the expected manifest hash. Missing directories are idempotent;
never mark an artifact deleted before filesystem success.

- [ ] **Step 8: Run runner, executor, and lifecycle suites**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_trading_agent_runner \
  tests.test_trading_agent_executor \
  tests.test_trading_agent_models \
  tests.test_trading_agent_runs \
  -v
```

Expected: all tests pass, including malformed output, cancellation, timeout,
lease loss, and capability failures.

- [ ] **Step 9: Commit the executor and runner**

```bash
git add \
  investment_knowledge_mcp/trading_agent_runner.py \
  investment_knowledge_mcp/trading_agent_schemas \
  scripts/trading_agent_executor.py \
  tests/test_trading_agent_runner.py \
  tests/test_trading_agent_executor.py
git commit -m "feat: run trading research in isolated Codex stages"
```

### Task 3: Fair Shared Worker Host

**Files:**

- Modify: `scripts/research_agent_worker.py`
- Create: `tests/test_research_agent_worker.py`
- Modify: `scripts/install_research_agent_worker_on_ecs.sh`
- Modify: `scripts/install_codex_worker_on_ecs.sh`

**Interfaces:**

- Consumes: legacy research claim/process functions and the fixed
  restricted-executor launch contract.
- Produces:
  `HandlerSpec`, `WorkItem`, `WorkerScheduler`, fair handler selection,
  immediate slot refill, restricted-user launch, and typed readiness.

- [ ] **Step 1: Write failing scheduler tests**

```python
def test_slot_refills_before_slowest_peer_finishes() -> None:
    scheduler = fixture_scheduler(slot_count=2, durations=[1, 10, 1])
    timeline = scheduler.run_until_idle()
    assert timeline["item-3.started"] < timeline["item-2.finished"]


def test_trading_queue_does_not_starve_legacy_research() -> None:
    scheduler = fixture_scheduler(
        slot_count=2,
        trading_items=range(10),
        research_items=range(2),
    )
    claimed_types = scheduler.claimed_types(limit=6)
    assert "research" in claimed_types
    assert "trading_agent" in claimed_types
```

- [ ] **Step 2: Run worker tests and confirm current batch behavior fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_research_agent_worker -v
```

Expected: the slot-refill and fair-selection tests fail against current batch
logic.

- [ ] **Step 3: Add handler registry and work-conserving scheduler**

Represent handlers explicitly:

```python
@dataclass(frozen=True)
class HandlerSpec:
    task_type: str
    start_one: Callable[[str, str], subprocess.Popen[bytes] | None]
```

Use a fixed executor, claim only for free slots, assign unique
`<worker>:<pid>:slot-<n>` identities, and rotate eligible queues. Preserve
legacy `process_job()` behind the research handler adapter. Trading
`start_one` launches `scripts/trading_agent_executor.py --once` through a
fixed `setpriv` vector; no Trading module is imported into the privileged
scheduler process.

- [ ] **Step 4: Add readiness-before-claim behavior**

Trading Agent claims are disabled while Codex login, structured output,
web-search-only tool inventory, local-canary denial, restricted-role grants,
artifact storage, or global capacity readiness fails.
Publish only a sanitized Trading Agent readiness heartbeat through the
existing `worker_status` table: readiness boolean, safe failure code, Codex
version, `chatgpt` auth mode, capability booleans, active slot count, and
artifact-storage readiness. Do not record account identity, auth paths,
prompts, inherited environment values, or credentials. Legacy behavior
remains explicit and covered by compatibility tests.

- [ ] **Step 5: Keep installer contracts consistent**

Add only reviewed non-secret settings:

- `TRADING_AGENT_ENABLED`
- `TRADING_AGENT_ARTIFACT_ROOT`
- `TRADING_AGENT_RUNNING_LIMIT=5`
- `CODEX_WORKER_GLOBAL_CONCURRENCY=5`
- stage/run timeout and stale thresholds

Provision the `investment-trading-agent` account, executor-owned
`CODEX_HOME`, artifact root, restricted PostgreSQL role, and a root-readable
executor environment file. Generate/store the restricted database credential
without printing it. Do not add API keys or initiate device login from the
daemon. If the executor login is absent, print the exact operator
device-login command for that account and stop readiness without requesting a
token value.

- [ ] **Step 6: Run worker, runner, and shell syntax checks**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_research_agent_worker \
  tests.test_trading_agent_runner \
  tests.test_trading_agent_runs \
  -v
bash -n \
  scripts/install_research_agent_worker_on_ecs.sh \
  scripts/install_codex_worker_on_ecs.sh
```

Expected: all tests and shell syntax checks pass.

- [ ] **Step 7: Commit the shared host**

```bash
git add \
  scripts/research_agent_worker.py \
  scripts/install_research_agent_worker_on_ecs.sh \
  scripts/install_codex_worker_on_ecs.sh \
  tests/test_research_agent_worker.py
git commit -m "feat: host typed trading runs in research worker"
```

### Task 4: Protected Browser Workspace

**Files:**

- Create: `investment_knowledge_mcp/trading_agent_controller.py`
- Create: `investment_knowledge_mcp/trading_agent_workspace.py`
- Modify: `investment_knowledge_mcp/app_gateway.py`
- Modify: `investment_knowledge_mcp/web_experience.py`
- Modify: `docs/architecture/architecture-contract.md`
- Create: `tests/test_trading_agent_controller.py`
- Create: `tests/test_trading_agent_workspace.py`
- Modify: `tests/test_app_gateway.py`
- Modify: `tests/test_web_experience.py`
- Modify: `tests/test_web_access.py`

**Interfaces:**

- Consumes: safe list/detail/event/artifact projections and canonical browser
  access.
- Produces: `/trading-agent`, its asset, and exact protected run APIs.

- [ ] **Step 1: Write failing route/access tests**

```python
def test_trading_agent_shell_is_public_but_run_apis_are_protected() -> None:
    expected = {
        ("GET", "/trading-agent"): AccessClass.PUBLIC_READ,
        ("GET", "/assets/trading-agent.js"): AccessClass.PUBLIC_READ,
        ("GET", "/api/trading-agent/runs"): AccessClass.PROTECTED,
        ("POST", "/api/trading-agent/runs"): AccessClass.PROTECTED,
    }
    for key, access in expected.items():
        assert resolve_route(*key).access == access


def test_dynamic_run_route_is_anchored() -> None:
    assert resolve_route("GET", "/api/trading-agent/runs/12") is not None
    assert resolve_route("GET", "/api/trading-agent/runs/12/../../health") is None
```

- [ ] **Step 2: Run gateway tests and confirm the routes are absent**

Run:

```bash
.venv/bin/python -m unittest tests.test_app_gateway tests.test_web_access -v
```

Expected: Trading Agent route assertions fail.

- [ ] **Step 3: Add dedicated gateway/controller dispatch**

Authorize before reading bodies or run IDs. Return only admitted DTO fields.
Create returns the durable run, queue position, running count, running limit,
and canonical URLs. Concurrent replay with one submission key returns the same
run. Queue/rate/storage admission failures return distinct typed `429`
responses. Cancel and retry use exact action routes.

- [ ] **Step 4: Write failing browser markup/state tests**

```python
def test_navigation_places_trading_agent_after_command() -> None:
    html = render_primary_navigation("trading_agent")
    assert html.index("/command") < html.index("/trading-agent")
    assert 'href="/trading-agent" aria-current="page"' in html


def test_public_shell_contains_no_run_or_artifact_payload() -> None:
    html = render_trading_agent_workspace_html()
    assert "Start Research" in html
    assert "artifact_manifest" not in html
    assert "worker_log" not in html
```

- [ ] **Step 5: Implement the page and browser state machine**

Use the shared shell/access script. Keep immutable pending mutations for access
retry. Show form busy state immediately. Poll only non-terminal runs. Preserve
selection/focus, pause while hidden, distinguish browser timeout from worker
timeout, and escape all rendered report content.
Validate source links as public `http`/`https` URLs without credentials,
localhost/private literals, or unsafe schemes; invalid values render as
non-clickable evidence warnings.

- [ ] **Step 6: Add Node behavior tests**

Cover:

- immediate `Starting…` state while create is pending;
- duplicate-submit prevention;
- access recovery and exact request replay;
- five running plus queued sixth copy;
- durable replay after a browser timeout;
- distinct rate, queue, and artifact-capacity copy;
- cancellation requested before terminal cancellation;
- browser timeout retaining prior state;
- retry as a new linked run;
- no poll for terminal rows;
- safe artifact rendering; and
- unsafe source-link rejection;
- 390-pixel structure without page overflow.

- [ ] **Step 7: Run focused Web suites**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_trading_agent_controller \
  tests.test_trading_agent_workspace \
  tests.test_app_gateway \
  tests.test_web_experience \
  tests.test_web_access \
  -v
```

Expected: all focused controller, route, access, browser, and shared-shell
tests pass.

- [ ] **Step 8: Commit the workspace**

```bash
git add \
  docs/architecture/architecture-contract.md \
  investment_knowledge_mcp/app_gateway.py \
  investment_knowledge_mcp/web_experience.py \
  investment_knowledge_mcp/trading_agent_controller.py \
  investment_knowledge_mcp/trading_agent_workspace.py \
  tests/test_app_gateway.py \
  tests/test_web_access.py \
  tests/test_web_experience.py \
  tests/test_trading_agent_controller.py \
  tests/test_trading_agent_workspace.py
git commit -m "feat: add protected trading agent workspace"
```

### Task 5: Deploy Classification And Worker Restart Safety

**Files:**

- Modify: `scripts/deploy_contract.py`
- Modify: `tests/test_deploy_change_classifier.py`
- Modify: `tests/test_deploy_release.py`

**Interfaces:**

- Consumes: changed-path classifier, serialized deploy path, systemd service
  inventory, and the worker's existing status heartbeat.
- Produces: explicit `weekly-review-web` plus
  `investment-research-agent-worker.service` targets, verification of the
  existing generic host-unit restart/rollback contract, and an explicit
  one-time Ops classifier bootstrap.

- [ ] **Step 1: Write failing classifier tests**

```python
def test_trading_route_and_runner_select_exact_targets() -> None:
    plan = classify_paths(
        [
            "investment_knowledge_mcp/trading_agent_controller.py",
            "investment_knowledge_mcp/trading_agent_runner.py",
        ]
    )
    assert set(plan.targets) == {
        "weekly-review-web",
        "investment-research-agent-worker",
    }
```

- [ ] **Step 2: Run deploy classifier tests and confirm unclassified paths**

Run:

```bash
.venv/bin/python -m unittest tests.test_deploy_change_classifier -v
```

Expected: new Trading Agent and worker paths fail explicit classification.

- [ ] **Step 3: Add exact path-to-target contracts**

UI/controller paths select `weekly-review-web`; runner/worker paths select the
systemd worker; schema/shared queue changes select all consumers. Installer
changes require a separate bootstrap classification and cannot masquerade as a
normal quick release.

- [ ] **Step 4: Write failing worker restart and rollback tests**

Add tests proving the existing generic `.service` target path restarts the
research worker, active leases recover, the new worker produces a fresh
sanitized `worker_status` heartbeat before health passes, and the prior worker
is restored if stable health fails. Product deployment must not modify or
restart the independent ECS Ops API.

- [ ] **Step 5: Verify the existing worker-target health and rollback path**

Do not modify `scripts/deploy_release.py` or `scripts/ecs_ops_api.py`. Verify
that their existing generic `.service` activation and rollback behavior covers
the classifier-selected research worker and that feature health adds no raw
auth data. Record that `scripts/deploy_contract.py` is an Ops control-plane
file and therefore must be bootstrapped separately before product deployment.

- [ ] **Step 6: Run deploy/Ops suites**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_deploy_change_classifier \
  tests.test_deploy_release \
  -v
```

Expected: exact classification, serialized worker restart, stable health,
heartbeat validation, rollback, and no control-plane update pass.

- [ ] **Step 7: Commit deploy readiness**

```bash
git add \
  scripts/deploy_contract.py \
  tests/test_deploy_change_classifier.py \
  tests/test_deploy_release.py
git commit -m "feat: add trading agent deployment readiness"
```

### Task 6: Integrated Verification, L3 Release, And Coordinator State

**Files:**

- Modify: `e2e/cloud-pages.spec.ts`
- Modify: `e2e/public-api-contracts.spec.ts`
- Modify: `docs/techplans/trading-agent-workspace-v1.md`
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

**Interfaces:**

- Consumes: reviewed implementation, exact release ref, shared deploy path,
  Owner-approved protected bearer-access browser session or secure fixture
  location, and L3 acceptance route. No token value enters chat or docs.
- Produces: traceability evidence, one release-verification manifest,
  activation of `AT-2026-07-23-001`, and a Coordinator Return Gate result.

- [ ] **Step 1: Add browser acceptance journeys before release**

Write Playwright coverage for public shell/protected APIs, Start Research busy
state, five running plus queued sixth, stage polling, running cancellation,
worker timeout, retry lineage, durable create replay, typed admission limits,
escaped artifacts, safe source links, focus, and 390-pixel overflow.

- [ ] **Step 2: Run the complete local gate**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/smoke_test.py
python3 scripts/audit_delivery_state.py --feature "Trading Agent Workspace"
python3 scripts/audit_architecture_health.py --repo . --format markdown
git diff --check
```

Expected: all tests pass, smoke passes, the feature audit has no missing PRD or
plan, the architecture audit has no new P0, and diff check is clean.

- [ ] **Step 3: Run independent whole-branch review**

Generate a review package from the merge base to the candidate head. Dispatch
one independent reviewer with the PRD, technical design, plan, review package,
test evidence, and Global Constraints. Resolve every Critical/Important
finding and rerun covering tests before release.

- [ ] **Step 4: Record one Deploy Intent**

Record the exact commit, one-time executor account/database/artifact bootstrap,
deploy mode, `weekly-review-web`, systemd worker, schema consumers,
`/trading-agent` URL, Gate B/load/cancel/timeout/restart checks, and this
Feature Coordinator as watch owner.

- [ ] **Step 5: Bootstrap the classifier and executor boundary**

Under the production deploy lock, bootstrap `/opt/investment-ops` from the
exact reviewed ref because the independent Ops API imports
`scripts/deploy_contract.py`. Verify control-plane health, status, and
classifier output; on failure, reinstall the prior known-good Ops ref and
stop. Then run the reviewed worker installer from the staged candidate without
`--start`, after snapshotting the prior unit/permissions. It provisions the
executor account/auth home, restricted role/credential, artifact root, and
unit but does not restart the worker or switch `current`. Restore the snapshot
on failure.

- [ ] **Step 6: Deploy through one serialized application channel**

Use the standard Ops application deploy for the exact ref. It applies schema,
switches the release, and activates only classifier-selected
`weekly-review-web` and `investment-research-agent-worker.service` targets.
Do not run ad hoc SSH or a competing GitHub deploy.

- [ ] **Step 7: Execute the cloud readiness and L3 matrix**

Verify:

- installed ref and unit ref;
- executor-account ChatGPT login and web-search-only tool inventory;
- local-canary denial and no non-web tool events;
- restricted-role permission-denied forbidden SQL;
- one complete real cited run;
- five concurrent synthetic runs and queued sixth;
- running cancellation with no orphan;
- forced timeout;
- worker restart and lease recovery;
- artifact permissions/isolation;
- retention/size/storage admission behavior;
- protected browser journey using the approved session/fixture; and
- zero forbidden-table, Git, or deploy writes.

- [ ] **Step 8: Apply the Coordinator Return Gate**

If independent acceptance passes, update the single Acceptance Queue row,
traceability matrix, Feature Registry, and Delivery Queue, reconcile the
feature branch with authoritative state, and end
`ready_for_user_acceptance`. If it fails, end `reject_and_return` or
`blocked_with_owner` with the exact owner and resume event.

- [ ] **Step 9: Commit and push state evidence**

```bash
git add \
  e2e/cloud-pages.spec.ts \
  e2e/public-api-contracts.spec.ts \
  docs/techplans/trading-agent-workspace-v1.md \
  docs/project-management/Feature-Registry.md \
  docs/project-management/Acceptance-Queue.md \
  docs/project-management/Delivery-Queue.md
git commit -m "docs: record trading agent release evidence"
git push
```

## Execution Gate

Do not select Subagent-Driven or Inline Execution yet. Global PM must first
review and accept the PRD, technical design, and this implementation plan.
