# Agent Operating Notes

This file is the durable preflight guide for agents working in this repository.
Read it before changing code, running services, or touching deployment commands.

## Start Here

- Run `.venv/bin/python scripts/agent_preflight.py` at the start of a new task unless the user is asking only a tiny factual question.
- Check `git status --short` before edits. The worktree is often intentionally dirty.
- Read the specific tech plan or doc referenced by the user before implementing.
- Use English for all new or agent-authored docs, code comments, PRDs, tech plans, and durable notes. Preserve existing non-English content unless the task is to translate or rewrite it.
- Prefer local, narrow verification first: unit/smoke checks, CLI scripts, and the exact module entrypoint touched by the task.
- Use `docs/lesson-capture-protocol.md` to decide whether a completed task produced a durable lesson and where that lesson belongs.
- For substantial Delivery Coordinator flows, close the role learning loop before declaring done. Check Product, Engineering, Testing, and Coordinator learning, but record lessons only when they pass `docs/lesson-capture-protocol.md`; otherwise state `Role learning: none` with a reason.
- Do not create routine daily logs. Put durable lessons in the appropriate durable document, durable state in `docs/当前工程状态.md`, and milestones in `docs/project-history.md`.

## Planning And Scope

- Before choosing a workflow, classify the task weight and keep the process proportional.
- Lightweight documentation or project-management status edits may be done directly in the main workspace when it is clean and no concurrent editing session is active. Update the authoritative doc plus necessary direct references, run narrow verification such as `git diff --check` or the relevant audit script, then commit and push.
- Use the fuller worktree and verification path for code changes, deployment-impacting changes, high-blast-radius documentation rewrites, or any task running alongside other active editing sessions.
- For product-facing work, use the default sequence: product document, technical plan, then technical implementation.
- When proposing a technical plan, default to delivering the whole requested scope in one pass when it is safe and reasonably bounded.
- Prefer technical plans that can be completed in one implementation pass. If a plan cannot be completed in one pass, state the concrete reason before splitting it.
- If a plan is split into P0/P1/P2 or separate phases, explain the reason for the split directly: dependency uncertainty, external credentials, product decision needed, high blast radius, deployment risk, or verification limits.
- Do not use phased plans as a way to defer normal implementation work. The user expects bundled execution unless a concrete reason is stated.
- After finishing the technical implementation, review the technical plan for missed items. Complete straightforward misses immediately; for larger or blocked misses, clearly call them out or record them as follow-up work in the appropriate durable place.

## Project Management Discipline

- Use `docs/product/Delivery-Coordinator-Protocol.md` as the default single-front-door protocol when the user asks about product-feature status, next actions, role routing, handoffs, or acceptance readiness.
- Use `docs/product/Project-Management-Agent-Protocol.md` as the detailed operating protocol for project delivery tracking.
- Use `docs/product/Acceptance-Testing-Agent-Protocol.md` as the detailed operating protocol for user-facing acceptance testing.
- Maintain delivery state in `docs/project-management/Feature-Registry.md` when a PRD, technical plan, implementation status, verification status, user acceptance status, or next action changes.
- Maintain acceptance-test state in `docs/project-management/Acceptance-Queue.md` for deployed or user-facing features that still need independent acceptance testing.
- Maintain dispatch state in `docs/project-management/Delivery-Queue.md` when Delivery Coordinator dispatches work to another role/thread/session or receives a returned result that needs follow-up.
- For broad delivery-status, readiness, handoff, or acceptance questions, run `python3 scripts/audit_delivery_state.py` before doing a manual document audit.
- For feature-specific coordination, use `python3 scripts/audit_delivery_state.py --feature "<feature>"`; before routing substantial work to another role/session, generate the handoff with `python3 scripts/audit_delivery_state.py --handoff-packet "<feature>"`.
- When the user asks the Delivery Coordinator to follow through, route, assign, or reduce manual coordination, use Dispatch Mode: generate `python3 scripts/audit_delivery_state.py --dispatch-prompt "<feature>"`, send it to the next role/thread when tools are available, and report `dispatched`, `not_executed`, or `blocked`.
- A Delivery Coordinator that dispatches another role/session must establish an active watch path owned by that feature coordinator. Use a feature-scoped heartbeat/monitor, keep checking the child thread, or record `Monitoring not active` with the exact resume action; passive "I will wait" is not enough.
- Do not make the Global Project Manager the default watcher for feature-level child threads. The Global PM should audit portfolio health, stale coordinators, missing watch paths, cross-feature conflicts, and user decisions; it should only recover a feature flow when the feature coordinator is idle, blocked, or missing its watch path.
- After a dispatched role/session returns, apply the Coordinator Return Gate from `docs/product/Delivery-Coordinator-Protocol.md`: inspect the returned branch/result, integrate or reject it, update `Delivery-Queue.md`, and dispatch the next owner or record the blocker. A pushed child branch is not delivery closure by itself.
- For cloud-served or browser-tested features, a returned "code fixed and pushed" result must become an explicit deploy/retest next step. The coordinator must name or dispatch the deploy owner before routing to Acceptance Testing, and must not stop at "after deploy, retest" without an owner, branch or commit, deploy path, affected URL/service, and watch path.
- A substantial product feature should not enter implementation unless its PRD is ready, or the exception is explicitly recorded with the reason.
- A substantial product feature should not be considered ready for implementation unless there is a linked technical plan, or the exception is explicitly recorded with the reason.
- Do not equate code completion with product completion. Product completion requires acceptance criteria, implementation evidence, verification evidence, and any required deployment or user acceptance state.
- Do not ask the user for acceptance on a cloud-served or user-facing feature while its acceptance-test status is `failed`, `blocked`, or `needs_retest`, unless the user explicitly accepts the known gap.
- Do not route the same product-feature request across multiple role sessions without a Delivery Coordinator handoff packet that names the feature, source PRD, technical plan, registry row, acceptance queue row, scope, next owner, and expected handoff result.
- When reviewing or finishing work, check for broken delivery links: incomplete PRDs, PRDs without technical plans, technical plans without implementation evidence, implementations without verification, superseded documents without status notes, and blocked next actions without owners.
- For a quick PRD delivery-status answer, run `python3 scripts/audit_prd_status.py` before doing a manual document audit.
- The Project Management Agent tracks delivery integrity and documentation state. It may flag gaps, request missing product or technical decisions, and update registry status, but it should not silently make product decisions or mark user acceptance on behalf of the user.

## Worktree Session Mode

- The main workspace `/Users/lishaocheng/code/TurenAgentTool` is for integration, release, urgent hotfixes, and cloud deploy verification.
- When multiple sessions or longer-running tasks are active, every non-trivial editing task must use a dedicated task worktree before editing: `bash scripts/create_task_worktree.sh <task-slug>`.
- Use the main workspace for read-only checks only when other sessions are active, unless the task is an integration/release/hotfix/cloud-verification task that explicitly belongs in the main workspace.
- New task worktrees should start from `origin/main` by default. Start from another branch only when the task is explicitly continuing that branch.
- Use one worktree per session/task. Do not share a task worktree across concurrent sessions.
- Default task worktrees live under `/Users/lishaocheng/code/TurenAgentTool.worktrees/<task-slug>` and use branch `codex/<task-slug>`.
- Each task worktree has its own ignored `.venv`; create it before running Python checks if it is missing.
- Do not move, delete, or stage untracked/dirty files from another session while creating or using a worktree.
- Deploy only pushed commits/refs, not implicit local worktree state. Merge or cherry-pick task work into the release branch deliberately before `/ops/deploy`.
- Use `docs/codex-session-workflow.md` for the full multi-session branch/worktree flow.

## Development Handoff Discipline

- A development task is not done until its code/doc changes are committed, verification has run or the verification limit is documented, and the related PRD/technical plan has been checked for missed items.
- For substantial delivery, role-protocol, or user-facing work, run `python3 scripts/audit_delivery_state.py` before handoff, or explain why the audit is not applicable.
- If implementation status, verification status, deployment status, user acceptance status, or next action changed, update `docs/project-management/Feature-Registry.md` in the same branch before handoff.
- If a user-facing feature is deployed or ready for user review, update `docs/project-management/Acceptance-Queue.md` or explain why independent acceptance testing is not required.
- When a task implements, partially implements, supersedes, or blocks a technical plan, mark that status in the registry instead of leaving `needs_review` for a future agent to rediscover.
- For PRDs with multiple phases, V1/V2 scope, or several material acceptance criteria, update the technical plan's implementation traceability matrix before handoff. Partial PRD completion must list what is implemented, verified, blocked, deferred, and still not started.
- Before handoff, check whether the task produced a durable lesson. Record it in the appropriate document, or state `Lessons: none` with a short reason.
- Before handoff, do not leave routine daily-log files under `docs/每日工作记录/`; move any durable content to the appropriate durable document or remove files you created.
- Before handoff, report the branch, commit SHA, verification performed, registry updates, remaining gaps, and whether the worktree is clean.
- A task worktree should be clean at handoff. If dirty files remain, list each file and explain whether it is intentional WIP, generated output, blocked work, or unrelated session state.
- Push the task branch or target branch immediately after committing unless the user explicitly asks to keep the work local. Do not wait for the user to ask whether a completed commit was pushed. If it remains local-only, record the reason in the final summary.
- Do not leave untracked experiments, generated files, or partial edits in a shared workspace as the normal result of development. Commit them, move them into the appropriate task worktree, document them as blocked/WIP, or remove only files you created and no longer need.

## Deployment And Service Boundaries

- For bugs observed on a cloud-served product surface, local verification is not the end of the task. After tests pass, proactively move to the release step: state the exact git push/deploy action needed, ask for approval when remote credentials or cloud services are involved, and continue through approved deployment/verification instead of stopping at a local summary.
- Deployment is a delivery state, not a vague future condition. When a feature branch fixes a browser/cloud blocker but is not yet on the relevant cloud service, record `needs_deploy` or dispatch the deploy owner; after deployment, route the same acceptance item back to testing instead of asking the user to manually remember the retest.
- When the user asks for a browser link to test or accept a product feature, assume they mean the cloud-served product URL. Do not offer `localhost`, `127.0.0.1`, or file URLs as the acceptance link unless the user explicitly asks for a local-only check. Local pages are for agent self-verification only; user-facing acceptance should use the deployed cloud surface or clearly state that the feature is not deployed yet.
- After a GitHub push is explicitly requested or approved, treat remote deployment through the standard Ops API path as pre-approved for that pushed ref unless the user says to pause. State the exact ref, deploy mode, and verification URL, then continue through deploy status checks and cloud verification.
- Do not treat "verify the change" as permission to start the whole prod-style stack.
- For local Task validation, prefer:
  - `.venv/bin/python scripts/smoke_test.py`
  - `.venv/bin/python scripts/ikg.py ...`
  - direct MCP/service checks only when the requested surface requires them.
- Only start `command-api`, `dingtalk-api`, schedulers, or a full `docker-compose.prod.yml` profile when the user explicitly asks to test those surfaces or approves the exact service list.
- Before any compose/service action, state:
  - which services will be started, stopped, or recreated;
  - which database they will connect to;
  - whether HTTP ports or external integrations are involved.
- Daily cloud releases should use the pull-based `/ops/deploy quick` path through the independent ECS Ops API. Use full deploy only for `Dockerfile`, `requirements.txt`, compose/image-layer, or dependency changes.
- Production deploy/restart is a shared global resource. Feature Coordinators and Development Agents may request deploy, but they must use the shared deploy workflow or Ops API path and must not bypass the deploy lock with ad hoc SSH, direct `docker compose up`, or service restarts unless the user explicitly asks for an urgent manual recovery.
- Before requesting or triggering production deploy, record or report Deploy Intent: feature, ref or commit, deploy mode (`quick`/`full`/restart-only), affected services, reason, verification URL or command, and watch owner/path.
- Before stopping on any cloud-served or browser-tested feature return, make a concrete deploy decision: `self_deploy`, `dispatch_deploy_owner`, `blocked`, or `not_required`. Vague next owners such as `Coordinator/Ops`, `someone`, `later`, or `after deploy` are not valid handoff closure.
- Before escalating from quick deploy to full deploy because a product URL or service is missing, first confirm the service is included in the deploy script's explicit `docker compose up` list, the required Compose profile is active, the container is running on ECS, host-local curl works, and the public port/security group is open. Do not use full deploy as a diagnostic substitute for service/ingress checks.
- Avoid overlapping deploy channels for the same ref. After pushing `main`, check whether the automatic GitHub Actions deploy is running before also starting Ops API deploy or manual workflow dispatch; let one deployment finish or explicitly cancel/skip the duplicate path.
- GitHub Actions production deploys are serialized by the `production-deploy` concurrency group. If a deploy is already running, wait for that run or record the blocker instead of launching a second deploy path.
- The ECS Ops API must live outside the business release directory, under `/opt/investment-ops`; business releases live under `/opt/investment-knowledge/releases/<sha>` with `/opt/investment-knowledge/current` as the active symlink.
- Updating the business release with `/ops/deploy quick` does not update the independent Ops API process. When `scripts/ecs_ops_api.py`, `scripts/install_ops_api_on_ecs.sh`, or `scripts/bootstrap_ops_api_v2_on_ecs.sh` changes, explicitly bootstrap/restart `/opt/investment-ops` as a separate control-plane step.
- Keep host and container database environments separate. Host/systemd/Ops API uses `POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432`; Docker app containers must use `POSTGRES_HOST=postgres POSTGRES_PORT=5432`. Compose launchers must strip host-only exported DB variables before invoking Docker Compose.
- Treat deploy health as stable only after services stay healthy for a short window. A container showing `Up 1 second` immediately after recreate is not sufficient evidence of a successful deploy.
- Diagnose cloud release failures from inside out: deploy event, `current` symlink/release files, container env, container logs, host-local curl, then public URL/security-group checks.
- Keep GitHub Actions as a secondary/rescue deployment path. Do not make GitHub hosted runner SSH to ECS the daily blocker; the known failure mode is runner-to-ECS `:22` handshake reset by peer.
- Full deploy is a multi-minute operation. The observed weekly-review release path takes about 6 minutes end to end; after triggering it, wait and poll calmly instead of treating the first few minutes of missing/unstable health checks as failure.
- `command-api` is only the HTTP wrapper around `handle_command(...)`. It is not required for ordinary local feature work unless the HTTP command endpoint itself is being tested.
- If `command-api` is started, it must use a strong `COMMAND_API_TOKEN`. Never write temporary tokens or secrets into docs, logs, commits, or chat summaries.

## Database Discipline

- Be explicit about database target. Local compose can accidentally create or connect to a fresh empty database.
- If a service should use the existing local knowledge base, verify `POSTGRES_HOST` and `POSTGRES_PORT` before starting it.
- Do not assume data exists in the current database just because drafts exist on disk.
- Real trading records, account snapshots, and weekly-review source data live in the cloud environment. If local database data is missing, treat it as an environment limitation and verify logic with fixtures or approved cloud read paths rather than assuming the product data does not exist.

## Verification Notes

- A passing CLI check against `scripts/ikg.py` validates the same `command_router.handle_command(...)` logic used by `command-api`.
- Only use `command-api` verification when HTTP auth, JSON request/response, or gateway integration is part of the requested task.
- If a planned snapshot stock is missing from the active database, record that as an environment limitation rather than expanding scope into imports unless the user asks.

## Learning Mechanism

- `AGENTS.md` contains operating rules.
- `docs/lesson-capture-protocol.md` defines when to capture a lesson, where it belongs, and what the handoff must say.
- `docs/agent-lessons.md` contains cross-task agent/process lessons learned from mistakes or repeated workflow corrections.
- Product, technical, project-management, current-state, and milestone lessons should be recorded in their relevant durable docs instead of being forced into one ledger.
- `scripts/agent_preflight.py` prints the rules, lessons, git status, and DB target for each new task.
- If a lesson should prevent future mistakes, update these files rather than adding a dated work log.
