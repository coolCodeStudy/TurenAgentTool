# Control Plane And Throughput Upgrade Plan

## Background

The highest-frequency InvestmentKnowledge workflow is no longer DingTalk query alone. It is:

```text
User
  -> Codex App
    -> Codex reads local code, edits code, runs validation
    -> Codex uses cloud MCP / Ops API to inspect ECS status and logs
    -> Codex summarizes issues, fixes them, triggers or checks deployment
```

DingTalk remains the daily investment query and notification entrypoint. Cloud workers remain async execution entrypoints. But development efficiency now depends on how smoothly Codex App can understand system state and act through the control plane.

Next-stage priority should therefore shift from "more entrypoints" to "Codex collaboration control plane":

- Let Codex quickly understand current system state.
- Let Codex quickly locate deployment, worker, and research-job bottlenecks.
- Persist tasks and deployments structurally instead of relying only on logs.
- Support batch, layered, and resumable data/research runs.

Security hardening remains important but should not block the minimum productive control plane.

## Revised Interaction Architecture

```text
User
  |
  | High frequency: ask Codex to judge, edit, deploy, diagnose
  v
Codex App
  |
  +-- Local repository: read code, edit code, run tests
  |
  +-- Cloud MCP /mcp
        |
        +-- InvestmentKnowledge MCP tools
              |
              +-- Ops API: ECS status, service logs, worker status
              +-- PostgreSQL: tasks, knowledge base, events, deployments
              +-- Futu OpenD: holdings, trades, IPOs
              +-- OpenAI: analysis, routing, research enrichment

DingTalk
  |
  +-- Daily queries: holdings analysis, monthly return, stock views
  +-- Notifications: worker completed, deploy completed, task failed, confirmation needed

Cloud worker
  |
  +-- research_jobs: research runs
  +-- coding_tasks: development tasks
```

## Persistence

Control-plane data should be stored in the current PostgreSQL database by default.

Suggested tables:

```text
work_sessions
  id
  source              -- codex_app / dingtalk / github_action / worker
  goal
  status             -- active / completed / blocked
  summary
  related_task_ids
  related_job_ids
  started_at
  finished_at
  created_at
  updated_at

task_events
  id
  task_type           -- research / coding / deploy / snapshot / ipo / command
  task_id
  event_type          -- claimed / started / step_finished / failed / completed
  status
  message
  metadata
  created_at

deploy_events
  id
  source              -- github_action / codex_worker / local_codex
  deploy_mode         -- quick / full / local
  commit_sha
  branch_name
  status              -- started / succeeded / failed
  started_at
  finished_at
  duration_seconds
  summary
  logs_tail
  created_at
```

Docs should preserve phase plans, project state, reusable lessons, and human-written reviews. Runtime facts belong in the database. Routine diary logs are retired.

## Current Pipeline Problems

### Codex Collaboration

Current state:

- Codex can read local code.
- Codex can inspect cloud status and logs through MCP/Ops API.
- Codex lacks a single system overview and must stitch together logs, tables, and commands.

Target:

- Add `system_overview`.
- Return service status, deployment state, task queues, recent failures, and account snapshot freshness in one response.
- Users should not read Docker logs; logs are Codex input.

### Deployment Pipeline

Current state:

- Quick and full deploy are separated.
- Quick deploy still packages more than it needs.
- Deployments mostly output logs instead of structured events.
- Health checks are not mandatory in every path.

Target:

- Exclude heavy artifacts such as `drafts/` from quick deploy.
- Make quick/full deploy write `deploy_events`.
- Run health checks after deploy and save summaries.
- Let Codex answer "what happened in the last deploy?" directly.

### Research Throughput

Current state:

- `research_jobs` exists.
- Worker concurrency is conservative and safe, but not ideal for batch completion.
- Status granularity is too coarse; it is hard to tell whether a job is stuck in source collection, draft, audit, or import.
- Some batch-creation scripts pass metadata that older creation functions may not accept; this path needs compatibility checks.

Target:

- Add `task_events` for each important step.
- Split research into fast seed and deep Codex stages.
- Allow fast seed concurrency while keeping deep Codex low-concurrency.
- Add `run_group_id` for batch jobs such as top holdings coverage.

## Priority Plan

### P0: Codex Collaboration Control Plane

Deliver:

- Add command/tool `system_overview`.
- Summarize services, latest deploy, research queue, coding queue, worker status, command failures, and account snapshot freshness.

Success:

- When the user asks "how is the system now?", Codex does not need to inspect five separate logs.
- Codex can identify within a minute whether the bottleneck is deployment, worker, Futu, OpenAI, DB, or task data.

### P1: Deployment Events

Deliver:

- Add `deploy_events`.
- Make GitHub Actions and `deploy_from_local_checkout.sh` write start/end events.
- Exclude `drafts/` from quick deploy.
- Run post-deploy health checks.

Success:

- The system can answer whether the last deploy succeeded.
- Codex can see commit, deploy mode, duration, and failure summary.

### P2: Task Events

Deliver:

- Add `task_events`.
- Make coding and research workers write events at key stages.
- Add commands such as task status, research-job status, and recent failed tasks.

Success:

- The system can identify where a task is stuck without raw logs.
- Failed tasks can be grouped by reason.

### P3: Research Concurrency And Layering

Deliver:

- Add `run_group_id`, `stage`, `max_attempts`, and `attempt_count` to `research_jobs`.
- Allow fast seed workers to run with concurrency 2-4.
- Keep deep Codex worker concurrency low.
- Add batch summary reports.

Success:

- Top holdings coverage can run in batches.
- Most stocks complete low-cost seed coverage first; only insufficient ones move to deep research.

### P4: Development Task Efficiency

Deliver:

- Improve `coding_tasks` visibility.
- Make worker status and recent failures visible in system overview.
- Preserve branch/commit/result metadata for completed coding tasks.

Success:

- Codex can claim, process, and report coding tasks with less manual inspection.

## Non-Goals

- Do not replace the whole runtime with a new orchestration platform.
- Do not add a broad public control plane without authentication.
- Do not move runtime facts into docs.
- Do not make users read raw logs as the primary interface.

## Verification

- Unit tests for new event-writing repository functions.
- Smoke test for `system_overview`.
- Manual cloud check through MCP tools after deployment.
- Regression check that existing DingTalk and command-router paths still work.
