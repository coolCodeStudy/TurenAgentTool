# Cloud Pull Deploy Technical Plan

## Instructions For Execution Sessions

Implement Cloud Pull Deploy with the first version focused on:

1. Add `POST /ops/deploy` to the ECS Ops API.
2. Add MCP tool `cloud_deploy(ref, mode, render=True)`.
3. Record deployment progress in `deploy_events`.
4. Run a health check after deployment and write the summary to the deploy event.
5. Keep GitHub Actions as backup/formal release path; do not refactor unrelated deployment logic.

Do not:

- Use `rsync` as the main deployment path.
- Add GitHub webhook automatic deployment.
- Introduce Kubernetes, Argo CD, Flux, or other heavyweight GitOps systems.
- Rework the DingTalk interaction path.
- Opportunistically split `command_router.py` or `repository.py`.
- Modify real `.env`, secrets, tokens, or webhooks.

First-version acceptance:

- Codex can call MCP tool `cloud_deploy(ref=<commit_sha>, mode="quick")`.
- ECS fetches the requested ref from GitHub through Ops API and deploys it.
- `deploy_events` records `started`, `succeeded`, and `failed`.
- System overview can show the latest deployment state.
- Deployment failure returns a clear error and writes it to `deploy_events`.

## Default Deployment Policy

Daily Codex deployments use MCP `cloud_deploy(ref=<commit_sha>, mode="quick"|"full")`, which calls ECS Ops API `/ops/deploy`.

GitHub Actions is not the default daily path. Keep it for formal releases, full rebuild backup, and disaster recovery unless the user explicitly requests Actions.

When the user asks for deploy validation after changes, including `改完部署验证`, the standing workflow is:

```text
local validation
  -> task-scoped commit
  -> git push
  -> cloud_deploy(ref=<commit_sha>, mode="quick"|"full")
  -> /ops/deploy pulls the ref on ECS
  -> remote health/status/log validation
```

For low-risk changes, the agent should not pause for another conversational approval before push/deploy. Ask again only for high-risk, destructive, secret-touching, production-data-changing, or service/database-scope-expanding changes.

## Goal

Change the daily deployment path to:

```text
Codex edits locally
  -> local validation
  -> git commit / push
  -> Codex calls cloud_deploy(ref, mode)
  -> ECS fetches the requested commit from GitHub
  -> quick/full deploy
  -> health check
  -> deploy_events / system overview visibility
```

This supports the highest-frequency workflow:

```text
User
  -> Codex App
    -> edit code, validate, push, trigger cloud deploy, inspect result
```

DingTalk remains the daily investment query and notification entrypoint. GitHub Actions remains the formal release, full rebuild, and disaster-recovery path, not the high-frequency small-change path.

## Why Not Rsync As The Main Path

`rsync` is fast, but it makes the cloud runtime less auditable:

- Running code may not map to a clear Git commit.
- The source of truth becomes local file state instead of GitHub.
- Rollback and audit become less natural.
- Local, GitHub, and cloud state can drift.

Keep `rsync` only as an emergency fallback.

## Why Not GitHub Actions As The High-Frequency Path

GitHub Actions is appropriate for:

- Dependency changes.
- Dockerfile or image-structure changes.
- Full rebuilds.
- Formal `main` releases.
- Disaster recovery.

It is too heavy for frequent Codex collaboration changes because checkout, build, packaging, SCP, and SSH add fixed cost and slow feedback. Therefore, Actions remains the formal release rail, while daily changes use cloud pull deploy.

## Principles

1. GitHub is the code source of truth.
2. ECS pulls a specific commit instead of receiving local files.
3. Codex explicitly triggers deployment; push does not deploy automatically.
4. Every deployment writes `deploy_events`.
5. Every deployment runs a health check.
6. The user does not inspect Docker or GitHub logs manually; Codex uses system overview and event tables.

## Architecture

```text
Codex App
  |
  | 1. git push branch / commit
  v
GitHub

Codex App
  |
  | 2. MCP tool: cloud_deploy(ref, mode)
  v
InvestmentKnowledge MCP
  |
  | 3. POST /ops/deploy
  v
ECS Ops API
  |
  +-- deployment lock
  +-- deploy_events started
  +-- git fetch origin
  +-- checkout ref
  +-- deploy_from_local_checkout.sh
  +-- health check
  +-- deploy_events succeeded/failed
```

## ECS Directory Layout

Keep two directories:

```text
/opt/investment-knowledge-repo
  GitHub checkout
  Only fetches code and selects refs

/opt/investment-knowledge
  Runtime directory
  Keeps .env, drafts, and mounted runtime paths
  docker compose starts here
```

Deployment copies source from the repo checkout to the runtime directory:

```bash
SOURCE_DIR=/opt/investment-knowledge-repo \
APP_DIR=/opt/investment-knowledge \
BUILD_IMAGE=false \
bash /opt/investment-knowledge-repo/scripts/deploy_from_local_checkout.sh
```

`deploy_from_local_checkout.sh` already syncs source directories, dependencies, compose files, and restarts the relevant services. Ops API should become the single place that records `deploy_events`.

## GitHub Permissions

The first version assumes `coolCodeStudy/TurenAgentTool` is publicly readable and uses anonymous HTTPS fetch:

```text
https://github.com/coolCodeStudy/TurenAgentTool.git
```

If the repository becomes private, use a read-only deploy key bound only to this repository. Do not use a personal GitHub token as the main deployment credential. If cross-repository access is needed later, consider a GitHub App installation token.

## Notification And Triggering

Do not use GitHub webhooks for the first version:

- Not every push should deploy.
- Codex may push intermediate branches.
- The user should choose when a ref is deployed.

The intended flow is:

```text
Codex push
-> Codex calls cloud_deploy(ref=<commit_sha>, mode="quick"|"full")
-> Ops API deploys the exact ref
```

## Deploy Modes

- `quick`: copy code and restart services without rebuilding the image. Use for Python, scripts, DB, docs, and shell-script changes.
- `full`: rebuild or refresh the image and restart services. Use for dependency, Dockerfile, or compose-structure changes.

Prefer commit SHA refs for auditability.

## Validation

Local validation before push:

```bash
.venv/bin/python scripts/smoke_test.py
```

Remote validation after deploy:

- `cloud_system_status`
- `system_overview`
- recent service logs
- health-check result attached to `deploy_events`

## Risks

- ECS cannot reach GitHub: report deploy failure clearly and preserve logs.
- Deploy lock is missing: concurrent deploys may corrupt runtime state.
- Ref does not exist remotely: return a clear error before touching runtime services.
- Health check is too shallow: service may start but be functionally broken.
- Public `/mcp` protection remains a separate security TODO.
