# Private Ops API Tunnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore automatic main deployment without exposing the ECS Ops API publicly.

**Architecture:** GitHub-hosted jobs open a short-lived SSH local-forward tunnel to the private ECS Docker-bridge endpoint and call Ops API through localhost. The independent control plane is upgraded from an exact pushed commit using the existing V2 bootstrap script.

**Tech Stack:** GitHub Actions YAML, OpenSSH, sshpass, Bash, Python unittest, systemd.

## Global Constraints

- Do not expose ECS port 8767 publicly.
- Do not put passwords or bearer tokens in command-line arguments, files, or logs.
- Require the pinned `ECS_SSH_KNOWN_HOSTS` repository secret for every tunnel.
- Do not restart or recreate PostgreSQL during control-plane bootstrap.
- Deploy only pushed commits and preserve the existing production deploy lock.

---

### Task 1: Private tunnel contract

**Files:**
- Create: `scripts/open_ops_api_ssh_tunnel.sh`
- Modify: `.github/workflows/deploy.yml`
- Test: `tests/test_deploy_workflow_contract.py`

**Interfaces:**
- Consumes: `ECS_HOST`, `ECS_USERNAME`, `ECS_PASSWORD`, optional `ECS_PORT`, and optional `GITHUB_ENV`.
- Produces: a verified local endpoint and `OPS_API_URL=http://127.0.0.1:18767` in `GITHUB_ENV`.

- [x] **Step 1: Add failing workflow contract tests**

Assert that the workflow invokes `scripts/open_ops_api_ssh_tunnel.sh` before
server-authoritative planning and in both deployment jobs, and that it does not
read `vars.OPS_API_URL`.

- [x] **Step 2: Run the focused test and verify failure**

Run: `.venv/bin/python -m unittest tests.test_deploy_workflow_contract -v`

Expected: failure because the workflow still reads `vars.OPS_API_URL` and has
no private tunnel step.

- [x] **Step 3: Implement the tunnel and workflow steps**

Install `sshpass` on the runner, open
`127.0.0.1:18767 -> 172.17.0.1:8767`, retry SSH setup three times, poll
`/health`, and export the localhost URL.

- [x] **Step 4: Verify focused tests and shell syntax**

Run: `.venv/bin/python -m unittest tests.test_deploy_workflow_contract -v`

Run: `bash -n scripts/open_ops_api_ssh_tunnel.sh`

Expected: all tests pass and shell syntax exits 0.

### Task 2: Full control-plane bootstrap

**Files:**
- Modify: `.github/workflows/ops-api.yml`
- Test: `tests/test_ops_api_workflow_contract.py`

**Interfaces:**
- Consumes: the exact pushed `github.sha` and existing ECS SSH secrets.
- Produces: `/opt/investment-ops` installed from that SHA and a healthy `investment-ops-api.service`.

- [x] **Step 1: Add a failing bootstrap contract test**

Assert that the workflow uploads `bootstrap_ops_api_v2_on_ecs.sh`, passes the
exact SHA as `BOOTSTRAP_REF`, and no longer copies only `ecs_ops_api.py` into
the application directory.

- [x] **Step 2: Run the focused test and verify failure**

Run: `.venv/bin/python -m unittest tests.test_ops_api_workflow_contract -v`

Expected: failure against the historical single-file upload workflow.

- [x] **Step 3: Switch the workflow to V2 bootstrap**

Upload the bootstrap script, run it with `BOOTSTRAP_REF=${{ github.sha }}` and
the existing app/control-plane paths, then retain the status and health output.

- [x] **Step 4: Verify local deployment contracts**

Run: `.venv/bin/python -m unittest tests.test_deploy_workflow_contract tests.test_ops_api_workflow_contract tests.test_ecs_ops_api -v`

Expected: all tests pass.

### Task 3: Controlled cloud rollout

**Files:**
- Modify only durable deployment state or lessons if cloud evidence changes it.

**Interfaces:**
- Consumes: merged main SHA and GitHub Actions ECS secrets.
- Produces: updated private Ops API, successful production deployment, and cloud verification evidence.

- [ ] **Step 1: Commit, push, review, and merge the hotfix**

Push `codex/ops-api-private-tunnel-hotfix`, create a PR, verify checks, and merge
without bypassing branch protections.

- [ ] **Step 2: Bootstrap the independent Ops API**

Dispatch `ECS Ops API` with `mode=install` on merged `main`. This restarts only
`investment-ops-api.service`; app containers and PostgreSQL remain untouched.

- [ ] **Step 3: Rerun production deployment**

Dispatch `Deploy to Alibaba Cloud ECS` in `auto` mode for `main`, watch it to a
terminal state, and record the computed mode and target services.

- [ ] **Step 4: Verify cloud stability**

Verify Ops API status, stable container state, root disk usage, PostgreSQL
identity preservation, and required public routes after the deployment settles.
