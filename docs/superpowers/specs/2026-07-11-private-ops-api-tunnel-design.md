# Private Ops API Tunnel Design

## Problem

The production Ops API intentionally listens on the ECS Docker bridge at
`172.17.0.1:8767`. It is not reachable from a GitHub-hosted runner, and the
repository has no `OPS_API_URL` variable. The deploy workflow introduced by
Deploy Flow Optimization P0 therefore stops before classification. Publishing
port 8767 would also send a bearer token over plain HTTP and is not acceptable.

The existing Ops API maintenance workflow has a second compatibility gap: it
uploads only the historical single-file implementation, while the current Ops
API imports the shared deploy modules installed from a complete checkout.

## Decision

GitHub Actions will create a short-lived SSH local-forward tunnel for jobs that
must call the private Ops API. The runner calls `http://127.0.0.1:18767`; SSH
forwards that connection to `172.17.0.1:8767` on ECS. No new public port is
opened, the bearer token stays inside the encrypted SSH session, and the tunnel
terminates with the job.

The Ops API maintenance workflow will upload and run
`bootstrap_ops_api_v2_on_ecs.sh`. The bootstrap fetches the requested pushed
commit into `/opt/investment-knowledge-repo`, installs the complete import
closure under `/opt/investment-ops`, restarts only
`investment-ops-api.service`, and verifies its private health endpoint.

## Components

- `scripts/open_ops_api_ssh_tunnel.sh` validates ECS credentials, opens the
  tunnel with password supplied through `SSHPASS`, retries transient SSH
  failures, verifies `/health`, and exports `OPS_API_URL` through
  `GITHUB_ENV`.
- `.github/workflows/deploy.yml` opens the tunnel only for plans that require
  server state and for deployment jobs that delegate to Ops API. Explicit
  manual `no_deploy` remains credential-free.
- `.github/workflows/ops-api.yml` bootstraps the control plane from the exact
  workflow SHA instead of copying an incomplete module set into the mutable
  application directory.

## Security And Failure Handling

- Port 8767 remains private; ECS security-group changes are not required.
- The ECS password is read from `SSHPASS` and is never placed in command-line
  arguments or written to disk.
- SSH host identity is pinned through the `ECS_SSH_KNOWN_HOSTS` repository
  secret and strict host-key checking. A missing or changed key fails before
  the ECS password is sent.
- Tunnel setup retries three times and fails before any deployment mutation if
  SSH or `/health` is unavailable.
- PostgreSQL is not restarted or recreated by control-plane bootstrap.

## Verification

- Workflow contract tests prove all Ops API calls are preceded by the private
  tunnel and no repository `OPS_API_URL` variable is required.
- Shell syntax and focused deploy tests must pass locally.
- Cloud rollout must bootstrap `investment-ops-api.service`, rerun the failed
  deployment for the merged main SHA, and verify the production deploy state,
  stable containers, disk usage, and public product routes.
