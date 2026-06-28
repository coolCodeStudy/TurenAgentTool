# Agent Lessons

This file is the compact cross-task learning ledger for future agents. It is not a diary.
Use `docs/lesson-capture-protocol.md` to decide whether a lesson belongs here or in a narrower product, technical, project-management, state, or history document. Add only lessons that should change future behavior.

## Local Verification Scope

- Do not expand a local feature verification into a full prod-style compose startup.
- For command-router or display behavior, validate with `scripts/smoke_test.py` and `scripts/ikg.py` first.
- `command-api` is only an HTTP wrapper around `handle_command(...)`; it is not required for normal local feature verification.
- Start `command-api`, `dingtalk-api`, schedulers, or broad compose profiles only when the user explicitly asks to test those surfaces or approves the exact service list.
- When fixing a bug the user found on a cloud-served product page, local tests are only the pre-release gate. After they pass, continue to the release conversation: identify the exact push/deploy step, request approval for remote credentials or cloud service actions, then perform approved deployment and cloud verification.
- All new or agent-authored docs, code comments, PRDs, tech plans, and durable notes must be in English. If editing an existing non-English document, keep untouched existing content as-is but write any new agent-authored section in English unless the user explicitly asks for translation into another language.
- Do not hide missing product data or optional-source gaps as a substitute for completing the integration. If the product surface reasonably needs macro, news/theme, opportunity, or similar context, first investigate and connect an available source; keep transparent user-facing diagnostics until the source is genuinely implemented or a concrete product decision says it is out of scope.
- For value-generating product surfaces, acceptance testing must judge whether the output is useful enough for the product promise, not only whether missing data is explained safely. A Weekly Review can pass flow/persistence/error-copy tests and still fail user acceptance if missing index/event sources make the story shallow or non-actionable.

## Service Startup Preflight

- Before any service action, state the service names, database target, exposed ports, and external integrations.
- Verify `POSTGRES_HOST` and `POSTGRES_PORT` before starting containers. A compose stack may silently connect to a fresh empty database.
- If a service should use the existing local knowledge base, point it at the established local DB instead of a newly created prod-compose DB.
- Real trading records, account snapshots, and weekly-review source data are cloud-side product data. A missing local row is an environment limitation, not evidence that the product data is unavailable; use fixtures for local logic checks or an approved cloud read path when the task requires real data.
- Weekly review ranking must use interval P/L, not lifetime P/L labels. A closed losing position's realized loss can include losses accumulated before the review window; combine interval realized P/L with the change from the start snapshot so historical loss is not counted again.
- Explicit review dates must win over market-local "current session" inference. For cross-market daily-review or similar date-sensitive commands, include a regression check that forced modes such as `post_close` keep each market's `session_date` aligned to the requested user date, especially for U.S. markets before their local close.

## Worktree Session Isolation

- Use git worktrees for parallel Codex sessions. The main workspace should stay available for integration, release, urgent hotfixes, and cloud verification.
- Treat unexpected untracked files as another session's work unless proven otherwise. Do not stage, move, or delete them while working on an unrelated task.
- Create task worktrees with `scripts/create_task_worktree.sh <task-slug>` so paths and branch names stay predictable.
- Remember that ignored runtime directories such as `.venv` are per-worktree. A newly created task worktree usually needs its own venv before running preflight, smoke tests, or scripts.
- Push explicit commits from task branches; cloud deploy should target pushed refs, never uncommitted local state.

## Project Management Audits

- For routine PRD status questions such as "which PRDs have not started?", run `python3 scripts/audit_prd_status.py` first and use manual document reading only to explain or verify unusual gaps.
- Scale the workflow to the task weight. Small project-management document or status-schema edits should stay lightweight: update the authoritative doc and direct references, run only narrow checks, then commit and push. Do not expand them into a full engineering workflow unless code, deployment, concurrency, or high blast radius requires it.
- For user-facing or cloud-served features, treat acceptance testing as a separate gate from developer verification and deployment verification. Test one PRD/user journey at a time from the real user surface, record the result in `docs/project-management/Acceptance-Queue.md`, and do not ask the user for acceptance while the row is `failed`, `blocked`, or `needs_retest` unless the known gap is explicitly presented.
- For multi-role product-feature delivery, use the Delivery Coordinator as the single front door. Answer or route by feature, create a handoff packet when another role/session must act, and keep the user focused on status, owner, blocker, and next decision instead of making them restate context to Product, Engineering, Testing, and Project Management separately.
- A Delivery Coordinator response that only names the next owner is not enough when the user's goal is reduced manual coordination. Default to Dispatch Mode: attempt to send the generated prompt to the next role/thread when tools are available, or explicitly say `Dispatch not executed` with the reason and the smallest user action needed.
- A Delivery Coordinator dispatch is not closed when a child role/session pushes a branch or posts a final message. The coordinator must apply the Return Gate: inspect the returned result, integrate or reject it, update `Delivery-Queue.md`, and dispatch the next owner or record the blocker.
- Passive waiting breaks multi-session delivery. After dispatching a child role/thread, the coordinator must establish an active watch path such as a heartbeat/monitor, explicit child-thread polling, or a recorded `Monitoring not active` blocker with the exact resume action.

## Secrets And HTTP Entrypoints

- `COMMAND_API_TOKEN` is required only when running the HTTP command API.
- Use strong tokens for command-api. Do not write temporary tokens, secrets, or credentials into docs, commits, logs, or summaries.
- If HTTP auth or gateway integration is not part of the task, prefer CLI/MCP verification over command-api verification.

## Git Trust Boundary

- Separate local Git metadata operations from remote operations in user-facing updates. Creating branches or commits writes local `.git` state; pushing can invoke remote credentials.
- Before a new class of `git push` or operation likely to touch the user's credential helper/keychain, state that explicitly and wait for clear user approval. Once the user has asked for implementation, recording, or delivery work that should be committed and pushed, do not ask for a second confirmation between commit and push.
- After a task reaches a completed commit and there is no local-only instruction, push the target branch immediately instead of waiting for the user to ask whether it was pushed. The handoff should explicitly state the commit SHA, remote branch, push result, and worktree cleanliness.
- If the user expresses concern about Git credentials, stop remote-oriented Git work immediately and continue only with local verification until they re-authorize.
- The preferred local GitHub token file is `/Users/lishaocheng/code/github_pat_only`; it should contain only the GitHub token. The legacy `/Users/lishaocheng/code/github_pat` file may contain other local secrets such as database passwords or command-api tokens, so use it only as a compatibility fallback and treat only its first line as the GitHub token. Do not rewrite, truncate, rename, split, clean up, or print either file unless the user explicitly asks for that exact file maintenance operation.
- For approved GitHub pushes, disable system Git config with `GIT_CONFIG_NOSYSTEM=1` so the macOS `osxkeychain` helper is not invoked. Use a temporary credential store under `/tmp`, delete it immediately after the operation, and never print or persist the token.
- If `git-credential-osxkeychain` opens a Keychain prompt, stop that push path. Do not ask the user to approve the prompt; retry with the isolated first-line PAT flow instead.

## Cloud Deploy Bootstrap

- Before asking the user to SSH into ECS for one-time setup, check whether the existing GitHub Actions deployment path can bootstrap the same state through its already-configured SSH credentials.
- For a public repository, ECS can maintain a read-only HTTPS checkout such as `/opt/investment-knowledge-repo` without any GitHub token or deploy key; only use a deploy key if the repository becomes private.
- When adding a cloud pull-deploy path, ensure the deployment workflow creates or refreshes the remote checkout and writes the checkout path into the Ops API systemd environment. Otherwise the new `/ops/deploy` endpoint may be deployed but unable to fetch refs.
- If `/ops/deploy` fails before fetch/checkout while recording `deploy_events`, treat that as deployment-control-plane debt, not a business deploy failure. Capture the failing stage, preserve the user-requested release path, and record a follow-up to make Ops API return actionable tracebacks or degrade deploy event recording.
- Separate control-plane and app-plane releases. `/ops/deploy quick` updates `/opt/investment-knowledge/current`, but it does not update the running `/opt/investment-ops/ecs_ops_api.py` process. Any Ops API or bootstrap script change needs an explicit bootstrap/restart step before expecting new control-plane behavior.
- Keep host and container database profiles separate on ECS: host/systemd tools may use `127.0.0.1:55432`, while Docker compose services must use `postgres:5432`. Do not let a host `.env` leak into container runtime configuration.
- Docker Compose interpolation prefers exported shell/systemd environment variables over `--env-file`. When Ops API launches compose, explicitly remove host-only `POSTGRES_HOST` and `POSTGRES_PORT` so app containers keep using `postgres:5432` instead of `127.0.0.1:55432`.
- Verify the actual container environment after any env-related deploy fix with `docker inspect ... .Config.Env`; do not infer that `--env-file` won just because the file contains the desired values.
- Do not call a deploy successful from transient container startup output. Require stable health after recreate, and if services later show `Restarting`, prioritize container logs and env inspection over public ingress debugging.
- A public URL failure is only an ingress/network problem after host-local checks pass. First prove `docker ps` is stable and `curl 127.0.0.1:<port>` works on ECS.
- Bootstrap scripts should retry `/health` after restarting systemd services. A single immediate curl can race with service bind and produce a false failure even when the service becomes active seconds later.
- The daily production deploy path is pull-based and atomic: Codex/MCP calls the independent ECS Ops API, ECS fetches the requested commit locally, stages it under `/opt/investment-knowledge/releases/<sha>`, and flips `/opt/investment-knowledge/current` only after validation. The Ops API itself must stay under `/opt/investment-ops`, not inside the mutable business release.
- GitHub Actions SSH deploy is a secondary/rescue path, not the mainline. The observed hosted-runner failure was `ssh: handshake failed ... connection reset by peer` on ECS `:22`; do not spend daily release time on that channel unless the user explicitly asks to repair the rescue path.
- GitHub Actions quick deploy currently does not rebuild or restart every product surface. Before using it for a cloud-served Web page, confirm that the workflow actually refreshes that service; otherwise use full deploy or fix the quick deploy scope.
- When adding a Docker Compose product surface, update both `docker-compose.prod.yml` and `scripts/deploy_from_local_checkout.sh`; a service that exists only in Compose but is omitted from the explicit `docker compose up` service list will not run after quick or full deploy.
- If a newly added HTTP surface is unavailable after deploy, diagnose in this order before reaching for full deploy: service present in deploy script, Compose profile active, container running, container logs, host-local curl, then public port/security group. In the Command Workbench incident, the delay came from treating an unstarted service and unopened `8001` ingress as deploy-mode problems.
- Do not stack deployment mechanisms for the same SHA. A push to `main` can already trigger GitHub Actions while Ops API or a manual workflow dispatch is running; overlapping quick/full deploys create confusing transient outages and make root-cause analysis slower.
- GitHub Actions full deploy is multi-minute, not quick-deploy speed. In the 2026-06-16 weekly-review-web release it took about 6 minutes from dispatch to success; after triggering it, poll at a calm interval and verify only after completion.
- If cloud-side business verification succeeds and compose/logs show the target Web container is running, but the public URL still returns connection refused or is unreachable, classify the remaining work as public ingress/network-layer debugging. Do not reopen the already-verified business logic unless new evidence points back to it.
- When using a cloud command path as fallback verification for a Web bug, note any write side effects. For example, `复盘 2026-06-07 2026-06-13` can persist a `review_reports` row even when the goal is only verification.
- `/ops/deploy` must be atomic with respect to the running app directory. Never delete `APP_DIR/db`, `APP_DIR/scripts`, or other mounted runtime paths before the new release has been copied to staging and validated; failed deploys must leave the previous `db/schema.sql` and runnable scripts in place.
- Ops status and deploy-event endpoints must not depend solely on the current `APP_DIR`, because a failed deploy can corrupt that directory. Use the deploy repo checkout as a fallback for control-plane scripts so failures remain diagnosable.

## Daily Records Retired

- Do not create routine daily work logs by default.
- Durable project state belongs in `docs/当前工程状态.md`.
- Durable lessons belong in this file and `AGENTS.md`.
- Task plans belong in `docs/techplans/`.
- Historical milestones belong in `docs/project-history.md`.
