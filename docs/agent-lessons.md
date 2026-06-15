# Agent Lessons

This file is the compact learning ledger for future agents. It is not a diary.
Add only lessons that should change future behavior.

## Local Verification Scope

- Do not expand a local feature verification into a full prod-style compose startup.
- For command-router or display behavior, validate with `scripts/smoke_test.py` and `scripts/ikg.py` first.
- `command-api` is only an HTTP wrapper around `handle_command(...)`; it is not required for normal local feature verification.
- Start `command-api`, `dingtalk-api`, schedulers, or broad compose profiles only when the user explicitly asks to test those surfaces or approves the exact service list.
- When fixing a bug the user found on a cloud-served product page, local tests are only the pre-release gate. After they pass, continue to the release conversation: identify the exact push/deploy step, request approval for remote credentials or cloud service actions, then perform approved deployment and cloud verification.

## Service Startup Preflight

- Before any service action, state the service names, database target, exposed ports, and external integrations.
- Verify `POSTGRES_HOST` and `POSTGRES_PORT` before starting containers. A compose stack may silently connect to a fresh empty database.
- If a service should use the existing local knowledge base, point it at the established local DB instead of a newly created prod-compose DB.
- Real trading records, account snapshots, and weekly-review source data are cloud-side product data. A missing local row is an environment limitation, not evidence that the product data is unavailable; use fixtures for local logic checks or an approved cloud read path when the task requires real data.

## Secrets And HTTP Entrypoints

- `COMMAND_API_TOKEN` is required only when running the HTTP command API.
- Use strong tokens for command-api. Do not write temporary tokens, secrets, or credentials into docs, commits, logs, or summaries.
- If HTTP auth or gateway integration is not part of the task, prefer CLI/MCP verification over command-api verification.

## Git Trust Boundary

- Separate local Git metadata operations from remote operations in user-facing updates. Creating branches or commits writes local `.git` state; pushing can invoke remote credentials.
- Before any `git push` or operation likely to touch the user's credential helper/keychain, state that explicitly and wait for clear user approval.
- If the user expresses concern about Git credentials, stop remote-oriented Git work immediately and continue only with local verification until they re-authorize.
- The preferred local GitHub token file is `/Users/lishaocheng/code/github_pat_only`; it should contain only the GitHub token. The legacy `/Users/lishaocheng/code/github_pat` file may contain other local secrets such as database passwords or command-api tokens, so use it only as a compatibility fallback and treat only its first line as the GitHub token. Do not rewrite, truncate, rename, split, clean up, or print either file unless the user explicitly asks for that exact file maintenance operation.
- For approved GitHub pushes, disable system Git config with `GIT_CONFIG_NOSYSTEM=1` so the macOS `osxkeychain` helper is not invoked. Use a temporary credential store under `/tmp`, delete it immediately after the operation, and never print or persist the token.
- If `git-credential-osxkeychain` opens a Keychain prompt, stop that push path. Do not ask the user to approve the prompt; retry with the isolated first-line PAT flow instead.

## Cloud Deploy Bootstrap

- Before asking the user to SSH into ECS for one-time setup, check whether the existing GitHub Actions deployment path can bootstrap the same state through its already-configured SSH credentials.
- For a public repository, ECS can maintain a read-only HTTPS checkout such as `/opt/investment-knowledge-repo` without any GitHub token or deploy key; only use a deploy key if the repository becomes private.
- When adding a cloud pull-deploy path, ensure the deployment workflow creates or refreshes the remote checkout and writes the checkout path into the Ops API systemd environment. Otherwise the new `/ops/deploy` endpoint may be deployed but unable to fetch refs.
- If `/ops/deploy` fails before fetch/checkout while recording `deploy_events`, treat that as deployment-control-plane debt, not a business deploy failure. Capture the failing stage, preserve the user-requested release path, and record a follow-up to make Ops API return actionable tracebacks or degrade deploy event recording.
- Keep host and container database profiles separate on ECS: host/systemd tools may use `127.0.0.1:55432`, while Docker compose services must use `postgres:5432`. Do not let a host `.env` leak into container runtime configuration.
- GitHub Actions quick deploy currently does not rebuild or restart every product surface. Before using it for a cloud-served Web page, confirm that the workflow actually refreshes that service; otherwise use full deploy or fix the quick deploy scope.
- GitHub Actions full deploy is multi-minute, not quick-deploy speed. In the 2026-06-16 weekly-review-web release it took about 6 minutes from dispatch to success; after triggering it, poll at a calm interval and verify only after completion.

## Daily Records Retired

- Do not create routine daily work logs by default.
- Durable project state belongs in `docs/当前工程状态.md`.
- Durable lessons belong in this file and `AGENTS.md`.
- Task plans belong in `docs/techplans/`.
- Historical milestones belong in `docs/project-history.md`.

## Documentation Governance

- Start documentation work from `docs/README.md`.
- Follow `docs/DOCUMENTATION-GOVERNANCE.md` before creating, moving, renaming, or retiring docs.
- Prefer indexes and status metadata before broad file moves; do not rename many docs without updating all references in the same branch.
