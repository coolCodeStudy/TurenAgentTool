# Agent Operating Notes

This file is the durable preflight guide for agents working in this repository.
Read it before changing code, running services, or touching deployment commands.

## Start Here

- Run `.venv/bin/python scripts/agent_preflight.py` at the start of a new task unless the user is asking only a tiny factual question.
- Check `git status --short` before edits. The worktree is often intentionally dirty.
- Route the task through `docs/Agent协作工作流规范.md`: product design, technical architecture, engineering execution, ops diagnosis, or research/knowledge-base work.
- Read the specific tech plan or doc referenced by the user before implementing.
- Prefer local, narrow verification first: unit/smoke checks, CLI scripts, and the exact module entrypoint touched by the task.
- Do not create routine daily logs. Put durable lessons in `docs/agent-lessons.md`, durable state in `docs/当前工程状态.md`, and milestones in `docs/project-history.md`.

## Deployment And Service Boundaries

- Default deployment path: daily Codex deployment uses MCP `cloud_deploy(ref=<commit_sha>, mode="quick"|"full")`, which calls ECS Ops API `/ops/deploy`. GitHub Actions is reserved for formal releases, full rebuild backup, and disaster recovery unless the user explicitly asks for Actions.
- When the user asks to "deploy validate after changes", "deploy after fixing", "改完部署验证", or equivalent, treat that as standing authorization for the full low-risk engineering loop: local validation, task-scoped commit, `git push`, `cloud_deploy` through `/ops/deploy`, and remote validation. Do not pause for an extra conversational approval unless the change is high-risk, destructive, touches secrets, changes production data, or broadens service/database scope.
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
- `command-api` is only the HTTP wrapper around `handle_command(...)`. It is not required for ordinary local feature work unless the HTTP command endpoint itself is being tested.
- If `command-api` is started, it must use a strong `COMMAND_API_TOKEN`. Never write temporary tokens or secrets into docs, logs, commits, or chat summaries.

## Database Discipline

- Be explicit about database target. Local compose can accidentally create or connect to a fresh empty database.
- If a service should use the existing local knowledge base, verify `POSTGRES_HOST` and `POSTGRES_PORT` before starting it.
- Do not assume data exists in the current database just because drafts exist on disk.

## Verification Notes

- A passing CLI check against `scripts/ikg.py` validates the same `command_router.handle_command(...)` logic used by `command-api`.
- Only use `command-api` verification when HTTP auth, JSON request/response, or gateway integration is part of the requested task.
- If a planned snapshot stock is missing from the active database, record that as an environment limitation rather than expanding scope into imports unless the user asks.

## Documentation Language

- Use English for all repository documentation.
- New docs, substantive doc edits, plans, status updates, project history, and agent lessons must be written in English.
- Do not add new Chinese prose to docs. Chinese command examples, user-facing product phrases, source quotes, filenames, or domain terms may remain when they are part of the system behavior or source material.
- When substantially editing an older Chinese document, prefer translating the touched section to English or replacing it with an English equivalent.

## Git Remote And Secret Boundaries

- Local commits are allowed only when the user requested commit-level work or the workflow calls for it; do not mix unrelated dirty files into a commit.
- `git push` is a remote credential operation. It is allowed without extra conversational approval when the user requested push/deploy/deploy-validation for this task or when the low-risk deploy-validation standing rule applies. Otherwise, state the branch/ref and wait for explicit approval.
- The GitHub PAT file for this machine is `/Users/lishaocheng/code/github_pat`. Treat it as a secret.
- Do not search the user's home directory for token files. Use only the explicitly documented `/Users/lishaocheng/code/github_pat` path when PAT auth is needed.
- For an approved `git push` or deploy flow that requires GitHub authentication, read `/Users/lishaocheng/code/github_pat` only ephemerally for that single operation.
- Never print, copy, commit, summarize, or write the PAT value into Git remotes, docs, logs, commands, or chat.
- Prefer controlled deploy tools, GitHub Actions secrets, deploy keys, or existing credential helpers when they already satisfy the task; use `/Users/lishaocheng/code/github_pat` when the local push/deploy flow needs PAT auth.

## Learning Mechanism

- `AGENTS.md` contains operating rules.
- `docs/Agent协作工作流规范.md` contains role-specific workflows and closeout rules for product, architecture, engineering, ops, and knowledge-base work.
- `docs/Repo知识库索引.md` maps the durable knowledge locations in this repository and should be updated when the reading or maintenance path changes.
- `docs/agent-lessons.md` contains durable lessons learned from mistakes.
- `scripts/agent_preflight.py` prints the rules, lessons, git status, and DB target for each new task.
- If a lesson should prevent future mistakes, update these files rather than adding a dated work log.
- At the end of a non-trivial task, explicitly decide whether to update product docs, tech plans, current state, project history, agent lessons, or the InvestmentKnowledge database.
