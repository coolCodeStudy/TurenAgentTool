# Deploy Control-Plane Version Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect and explain independent Ops API version skew before application build or activation, then safely update the control plane and redeploy the blocked target.

**Architecture:** The target classifier identifies diffs that require an Ops control-plane install, while the installed Ops API reports its immutable bootstrap SHA. GitHub planning compares those facts and stops before image build when the target contract is newer. The executor converts classifier rejection into a typed deployment error as defense in depth.

**Tech Stack:** Python 3.11, `unittest`, Bash, GitHub Actions YAML, systemd-hosted Ops API, existing ECS Ops bootstrap workflow.

## Global Constraints

- Preserve unknown deployment-path rejection and the installed Ops API as deployment-policy authority.
- Never expose, print, persist, or test credential values.
- Keep Ops control-plane installation separate from application container activation.
- Use the existing `production-deploy` concurrency group and host deploy lock.
- Do not start a second deployment channel for the same SHA.

---

### Task 1: Classify control-plane update requirements

**Files:**
- Modify: `scripts/deploy_contract.py`
- Modify: `tests/test_deploy_change_classifier.py`

**Interfaces:**
- Produces: `requires_control_plane_update(paths: Iterable[str]) -> bool`
- Produces: serialized plan field `control_plane_update_required: bool`

- [ ] **Step 1: Write the failing classifier tests**

```python
def test_serialized_plan_marks_control_plane_update_requirement(self) -> None:
    plan = classify_paths(("scripts/deploy_contract.py",), compose_image_changed=False)
    self.assertTrue(serialize_plan(plan)["control_plane_update_required"])

def test_application_plan_does_not_require_control_plane_update(self) -> None:
    plan = classify_paths(("investment_knowledge_mcp/weekly_review_web.py",), compose_image_changed=False)
    self.assertFalse(serialize_plan(plan)["control_plane_update_required"])
```

- [ ] **Step 2: Run them and confirm RED**

```bash
.venv/bin/python -m unittest \
  tests.test_deploy_change_classifier.DeployContractTests.test_serialized_plan_marks_control_plane_update_requirement \
  tests.test_deploy_change_classifier.DeployContractTests.test_application_plan_does_not_require_control_plane_update -v
```

Expected: fail because the serialized field is absent.

- [ ] **Step 3: Implement the minimal classifier contract**

Define explicit installed/bootstrap file patterns next to the deployment rules, implement `requires_control_plane_update`, and add its result to `serialize_plan`. Do not alter mode or application targets.

- [ ] **Step 4: Run `tests.test_deploy_change_classifier` and confirm GREEN**

### Task 2: Record and expose immutable Ops control-plane identity

**Files:**
- Modify: `scripts/bootstrap_ops_api_v2_on_ecs.sh`
- Modify: `scripts/install_ops_api_on_ecs.sh`
- Modify: `scripts/ecs_ops_api.py`
- Modify: `tests/test_ops_api_workflow_contract.py`
- Modify: `tests/test_ecs_ops_api.py`

**Interfaces:**
- Consumes: bootstrap `resolved_commit`
- Produces: root-only `OPS_CONTROL_PLANE_REF=<40 lowercase hex SHA>`
- Produces: authenticated `/deploy/status` field `control_plane_ref: str`

- [ ] **Step 1: Write failing propagation and status tests**

Add contract assertions that bootstrap passes `OPS_CONTROL_PLANE_REF="$resolved_commit"`, installer validates a lowercase 40-character SHA and writes it to the Ops environment, and an API test that patched `OPS_CONTROL_PLANE_REF` is returned by `build_deploy_status()`.

- [ ] **Step 2: Run the exact new tests and confirm RED**

Expected: fail because propagation and status metadata do not exist.

- [ ] **Step 3: Implement exact identity propagation**

Pass `resolved_commit` from bootstrap, reject missing or malformed `OPS_CONTROL_PLANE_REF` in the installer, write it to `/etc/investment-knowledge/ops-api.env`, read it in `ecs_ops_api.py`, and return it from authenticated deployment status. Do not include it in public health output.

- [ ] **Step 4: Run `tests.test_ops_api_workflow_contract` and `tests.test_ecs_ops_api` and confirm GREEN**

### Task 3: Gate GitHub planning before image build

**Files:**
- Modify: `.github/workflows/deploy.yml`
- Modify: `tests/test_deploy_workflow_contract.py`

**Interfaces:**
- Consumes: `/deploy/status.current_sha`, `/deploy/status.control_plane_ref`, serialized `control_plane_update_required`
- Produces: actionable planning failure when the update flag is true and `control_plane_ref != target_sha`

- [ ] **Step 1: Write a failing workflow contract test**

Require the planning block to parse `control_plane_ref`, inspect `control_plane_update_required`, emit an `Ops control plane update required` error containing the target SHA, and perform this check before the `full_image` job.

- [ ] **Step 2: Run the new workflow test and confirm RED**

Expected: fail because the workflow does not compare control-plane identity.

- [ ] **Step 3: Implement the planning gate**

Extend the status parser to require both 40-character SHAs. After creating `plan_json`, fail with a GitHub error when the plan requires a control-plane update and the installed SHA differs. Name `.github/workflows/ops-api.yml`, `mode=install`, and the exact target SHA in the message.

- [ ] **Step 4: Run `tests.test_deploy_workflow_contract` and confirm GREEN**

### Task 4: Return an actionable executor error for classifier rejection

**Files:**
- Modify: `scripts/deploy_release.py`
- Modify: `tests/test_deploy_release.py`

**Interfaces:**
- Consumes: `plan_builder(...)` raising `ValueError`
- Produces: failed `DeployOutcome` with typed control-plane update guidance and zero activated services

- [ ] **Step 1: Write a failing engine regression test**

Inject a plan builder that raises `ValueError("unclassified deployment-sensitive path: .github/workflows/future.yml")` and assert that `deploy()` returns `ok=False`, no activated services, and a message containing `Ops control plane update required` plus the rejected path.

- [ ] **Step 2: Run the exact new test and confirm RED**

Expected: the outcome contains the generic product-safe message.

- [ ] **Step 3: Add the minimal exception boundary**

Wrap only `plan_builder(...)` in `try/except ValueError` and raise `DeploymentError` with actionable control-plane installation guidance, preserving the original repository-path evidence.

- [ ] **Step 4: Run `tests.test_deploy_release` and confirm GREEN**

### Task 5: Verify, integrate, deploy, and close coordination

**Files:**
- Modify if delivery state changes: `docs/project-management/Delivery-Queue.md`
- Modify if acceptance state changes: `docs/project-management/Acceptance-Queue.md`
- Modify if durable state changes: `docs/当前工程状态.md`
- Modify if a durable lesson qualifies: `docs/agent-lessons.md`

**Interfaces:**
- Consumes: verified branch commit and exact integrated `main` SHA
- Produces: healthy Ops install, one successful application deployment, durable event evidence, and a return message to session `019f6b6b-76d0-7dd0-89cb-34a844098597`

- [ ] **Step 1: Run complete local verification**

```bash
.venv/bin/python -m unittest \
  tests.test_deploy_change_classifier \
  tests.test_ops_api_workflow_contract \
  tests.test_deploy_workflow_contract \
  tests.test_ecs_ops_api \
  tests.test_deploy_release -v
python3 scripts/audit_architecture_health.py --repo . --format markdown
git diff --check
```

- [ ] **Step 2: Review scope, delivery state, and durable lessons; then commit and push**

Inspect `git diff --stat`, `git diff`, and `git status --short`. Commit only the version gate and required durable state, then push `codex/deploy-control-plane-version-gate`.

- [ ] **Step 3: Integrate the verified commit into authoritative `main`**

Confirm no overlapping `production-deploy` run is active before integration.

- [ ] **Step 4: Install the control plane from the exact integrated SHA**

Record Deploy Intent for `ops-api.yml`, `mode=install`, affected service `investment-ops-api.service`, private `/health`, and this Coordinator as watch owner. Wait for completion.

- [ ] **Step 5: Run exactly one application deployment for the same SHA**

Wait through its full stability window and do not start another deploy channel.

- [ ] **Step 6: Verify cloud evidence and routes**

Confirm the exact SHA, five activated application services, healthy aggregate/stability state, and successful `/health`, `/weekly-review`, `/command`, and `/daily-market-brief` checks.

- [ ] **Step 7: Apply the Coordinator Return Gate**

Reconcile delivery and acceptance queues, record only qualifying durable lessons, and send session `019f6b6b-76d0-7dd0-89cb-34a844098597` the root cause, fix SHA, deployment evidence, production verification, and explicit instruction to resume frontend acceptance.
