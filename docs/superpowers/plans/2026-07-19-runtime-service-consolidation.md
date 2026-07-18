# Runtime Service Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce idle Python runtime overhead while preserving DingTalk transport behavior, scheduled-job isolation, durable history processing, deployment safety, and control-plane independence.

**Architecture:** Measure before changing topology. Replace three always-on schedulers with one supervisor and run historical generation as an on-demand child. Retire unused DingTalk HTTP transport when evidence permits; otherwise supervise both adapters behind one gateway only if necessary.

**Tech Stack:** Python 3.11, subprocess, signal, PostgreSQL durable jobs, Docker Compose, systemd/host diagnostics, existing Ops deploy lock.

## Global Constraints

- Do not infer current production memory or callers from static source.
- Never log credential values, raw authorization headers, DingTalk messages, or sender IDs.
- Ops API remains an independent control-plane process.
- Every scheduled job retains independent health, timeout, overlap, and failure status.
- History processing remains outside the scheduler main execution thread.
- Production deploys are serialized and use pushed refs only.

---

### Task 1: Sanitized Runtime Baseline

**Files:**
- Modify only if necessary: `.github/workflows/ops-api.yml`
- Modify only if necessary: `tests/test_ops_api_workflow_contract.py`
- Record evidence in the approved architecture delivery state, not a daily log.

**Interfaces:**
- Consumes: existing `resource-diagnostics` workflow.
- Produces: timestamped service/PID RSS, restart counts, host `MemAvailable`, profiles, and exposed listener ownership without environment values.

- [ ] **Step 1: Verify the existing diagnostic contract emits `free -b`, `docker stats --no-stream`, and sanitized host `ps`**
- [ ] **Step 2: Run idle diagnostics through the authorized Ops workflow**
- [ ] **Step 3: Capture load snapshots around Weekly/Daily generation and a bounded history job**
- [ ] **Step 4: Inventory host Ops, Codex, and research Python services by unit/process name and RSS only**
- [ ] **Step 5: Establish the before table used by every later retirement gate**

Verification: `python3 -m unittest tests.test_ops_api_workflow_contract -v`

### Task 2: DingTalk HTTP Usage Instrumentation

**Files:**
- Modify: `investment_knowledge_mcp/dingtalk_api.py`
- Test: `tests/test_dingtalk_api.py`
- Modify: `scripts/deploy_contract.py`
- Test: `tests/test_deploy_change_classifier.py`

**Interfaces:**
- Produces: one INFO event `event=dingtalk_http_webhook_received` containing only normalized message type and boolean presence fields.

- [ ] **Step 1: Run the existing failing/passing red-green logging test from commit `b289b5e`**
- [ ] **Step 2: Add the narrow transport deploy PathRule so this file targets only `dingtalk-api`**
- [ ] **Step 3: Run logging, classifier, and deploy contract tests**
- [ ] **Step 4: Push and targeted-deploy only `dingtalk-api`**
- [ ] **Step 5: Observe one complete operational window and inspect only event counts/timestamps**

### Task 3: Scheduler Job Contract

**Files:**
- Create: `investment_knowledge_mcp/scheduler_host.py`
- Create: `investment_knowledge_mcp/scheduler_jobs.py`
- Test: `tests/test_scheduler_host.py`

**Interfaces:**
- Produces: `JobDefinition`, `JobState`, `SchedulerHost.tick(now)`, and non-overlapping execution supervision.
- Consumes: one-shot callbacks exposed by existing scheduler modules.

- [ ] **Step 1: Write failing deterministic scheduler tests**

```python
def test_due_jobs_run_independently(): ...
def test_failed_job_does_not_stop_other_jobs(): ...
def test_running_job_is_not_started_twice(): ...
def test_health_reports_each_job_last_success_and_failure(): ...
```

- [ ] **Step 2: Verify RED**

Run: `python3 -m unittest tests.test_scheduler_host -v`

- [ ] **Step 3: Implement a monotonic supervisor with injected clock/executor**

```python
@dataclass(frozen=True)
class JobDefinition:
    job_id: str
    interval_seconds: float
    run_once: Callable[[], object]
    timeout_seconds: float
    allow_overlap: bool = False

class SchedulerHost:
    def tick(self, now: float) -> tuple[JobState, ...]: ...
```

- [ ] **Step 4: Verify GREEN and signal-safe shutdown**
- [ ] **Step 5: Commit**

```bash
git add investment_knowledge_mcp/scheduler_host.py investment_knowledge_mcp/scheduler_jobs.py tests/test_scheduler_host.py
git commit -m "feat: add isolated scheduler host"
```

### Task 4: Adapt Three Schedulers To One-Shot Jobs

**Files:**
- Modify: `investment_knowledge_mcp/ipo_reminders.py`
- Modify: `investment_knowledge_mcp/account_snapshots.py`
- Modify: `investment_knowledge_mcp/daily_market_brief.py`
- Modify: `investment_knowledge_mcp/scheduler_jobs.py`
- Test: existing scheduler/Daily Brief suites plus `tests/test_scheduler_jobs.py`

**Interfaces:**
- Produces: `run_ipo_reminder_once()`, `run_account_snapshot_once()`, and `run_daily_market_brief_once()` adapters without embedded forever loops.

- [ ] **Step 1: Characterize each existing loop's due-time, disabled-state, and exception behavior**
- [ ] **Step 2: Extract one-shot callbacks while keeping old entrypoints as compatibility wrappers**
- [ ] **Step 3: Register the callbacks in `default_scheduler_host()`**
- [ ] **Step 4: Verify one job failure does not block later due jobs**
- [ ] **Step 5: Commit**

Run: `python3 -m unittest tests.test_scheduler_host tests.test_scheduler_jobs tests.test_daily_market_brief -v`

### Task 5: On-Demand History Child

**Files:**
- Modify: `scripts/daily_market_brief_history_worker.py`
- Modify: `investment_knowledge_mcp/scheduler_host.py`
- Test: `tests/test_daily_market_history_worker.py`
- Test: `tests/test_scheduler_host.py`

**Interfaces:**
- Produces: `--drain-until-idle`, deterministic exit codes, and `HistoryChildSupervisor` with at most one child.

- [ ] **Step 1: Write failing drain-mode tests**

```python
def test_drain_until_idle_processes_available_items_then_exits(): ...
def test_supervisor_starts_only_one_history_child(): ...
def test_child_crash_does_not_terminate_scheduler_host(): ...
def test_cancel_timeout_and_stale_requeue_semantics_are_preserved(): ...
```

- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Add bounded drain mode around existing `run_worker_once`**
- [ ] **Step 4: Launch the worker as a subprocess, never a scheduler thread**
- [ ] **Step 5: Verify all history job/worker suites and commit**

Run: `python3 -m unittest tests.test_daily_market_jobs tests.test_daily_market_history_worker tests.test_scheduler_host -v`

### Task 6: Compose And Deploy Topology Migration

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `scripts/deploy_contract.py`
- Modify: `scripts/deploy_release.py`
- Modify: `scripts/ecs_ops_api.py`
- Modify: deployment tests and operational docs

**Interfaces:**
- Produces: one `scheduler-host` service replacing three schedulers and the always-on history-worker service.

- [ ] **Step 1: Add failing topology tests expecting the new managed service set**
- [ ] **Step 2: Add `scheduler-host` with the union of required non-secret environment names and mounts**
- [ ] **Step 3: Remove the four old scheduler/history services from Compose and deploy aliases**
- [ ] **Step 4: Update health checks to inspect per-job health plus child state**
- [ ] **Step 5: Run classifier, Compose config, deploy release, and service health tests**
- [ ] **Step 6: Full/config deploy under lock and verify a stability window**
- [ ] **Step 7: Compare idle/load RSS against Task 1**

### Task 7: DingTalk Transport Retirement Or Gateway

**Files:**
- Conditional modify: `docker-compose.prod.yml`
- Conditional create: `investment_knowledge_mcp/dingtalk_gateway.py`
- Modify: deploy contract, health checks, and tests

**Interfaces:**
- Consumes: callback configuration inventory and sanitized observation evidence from Task 2.

- [ ] **Step 1: If HTTP has no caller and no accepted use, add failing topology tests for service removal**
- [ ] **Step 2A: Preferred path — remove `dingtalk-api` from Compose/deploy/health inventory**
- [ ] **Step 2B: Required dual-transport path — add one supervisor with separate HTTP and Stream health, then remove two old containers only after parity tests**
- [ ] **Step 3: Deploy the selected topology and verify the active DingTalk path from the real group-message surface**
- [ ] **Step 4: Compare RSS and restart behavior**

The task must choose exactly one of 2A or 2B from evidence; it must not keep an unused compatibility container.

### Task 8: Final Resource Budget And Governance

**Files:**
- Modify if evidence supports: `docs/architecture/architecture-contract.md`
- Modify: `docs/project-management/Deploy-Classification.md`
- Modify: durable project state/registry/queue documents required by the coordinator protocol
- Test: architecture, delivery, flow, and deploy contract suites

- [ ] **Step 1: Record before/after RSS, service topology, peak child state, and remaining host workers**
- [ ] **Step 2: Set memory budgets only from observed stable peaks; do not guess limits**
- [ ] **Step 3: Run architecture and delivery audits**
- [ ] **Step 4: Apply the Coordinator Return Gate and reconcile authoritative delivery state**
- [ ] **Step 5: Record Role learning only if it passes the lesson-capture protocol**

