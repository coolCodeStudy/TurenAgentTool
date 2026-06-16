# Agent Operating Notes

This file is the durable preflight guide for agents working in this repository.
Read it before changing code, running services, or touching deployment commands.

## Start Here

- Run `.venv/bin/python scripts/agent_preflight.py` at the start of a new task unless the user is asking only a tiny factual question.
- Check `git status --short` before edits. The worktree is often intentionally dirty.
- Read the specific tech plan or doc referenced by the user before implementing.
- Use English for all new or agent-authored docs, code comments, PRDs, tech plans, and durable notes. Preserve existing non-English content unless the task is to translate or rewrite it.
- Prefer local, narrow verification first: unit/smoke checks, CLI scripts, and the exact module entrypoint touched by the task.
- Do not create routine daily logs. Put durable lessons in `docs/agent-lessons.md`, durable state in `docs/当前工程状态.md`, and milestones in `docs/project-history.md`.

## Deployment And Service Boundaries

- For bugs observed on a cloud-served product surface, local verification is not the end of the task. After tests pass, proactively move to the release step: state the exact git push/deploy action needed, ask for approval when remote credentials or cloud services are involved, and continue through approved deployment/verification instead of stopping at a local summary.
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
- `docs/agent-lessons.md` contains durable lessons learned from mistakes.
- `scripts/agent_preflight.py` prints the rules, lessons, git status, and DB target for each new task.
- If a lesson should prevent future mistakes, update these files rather than adding a dated work log.
