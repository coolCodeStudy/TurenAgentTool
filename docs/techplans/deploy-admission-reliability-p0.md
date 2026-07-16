# Deploy Admission Reliability P0 Technical Plan

## Objective

Make the production release lane forward-only, single-owner, truthful, and
actionable from an isolated Feature Coordinator worktree using existing GitHub
permission, while keeping Ops and browser credentials private and distinct.

Source change package:
`docs/changes/deploy-admission-reliability-p0/`.

## Implementation Sequence

### Task 1: Admission And Serialization

Files:

- Modify: `scripts/deploy_state.py`
- Modify: `scripts/ecs_ops_api.py`
- Modify: `.github/workflows/ops-api.yml`
- Test: `tests/test_deploy_state.py`
- Test: `tests/test_ecs_ops_api.py`
- Test: `tests/test_ops_api_workflow_contract.py`

TDD sequence:

1. Add tests proving an old ancestor is rejected, current `origin/main` is
   accepted, the handler does not resolve outside the engine lock, mutating Ops
   workflow actions share `production-deploy` concurrency, and the host lock is
   acquired before control-plane mutation.
2. Run the focused tests and capture the expected failures.
3. Implement the narrow policy and rerun until green.

- Change `resolve_production_target()` so an explicit SHA must equal the freshly
  fetched `origin/main` tip.
- Make the locked deployment engine the single authoritative resolver.
- Preserve typed `source_policy_rejected` recovery guidance.
- Put `.github/workflows/ops-api.yml` in `production-deploy` concurrency and use
  the host deploy lock for mutating control-plane operations.
- Keep one event/channel owner and forward source/requester labels without
  accepting secret-shaped values.

Verification: `tests/test_deploy_state.py`, `tests/test_deploy_release.py`,
`tests/test_deploy_workflow_contract.py`, and Ops workflow contract tests.

### Task 2: Resource Policy, Packaging, And Evidence

Files:

- Modify: `scripts/deploy_preflight.py`
- Modify: `scripts/deploy_state.py`
- Modify: `scripts/deploy_release.py`
- Modify: `scripts/ecs_ops_api.py`
- Modify: `.github/workflows/deploy.yml`
- Test: `tests/test_deploy_preflight.py`
- Test: `tests/test_deploy_state.py`
- Test: `tests/test_deploy_release.py`
- Test: `tests/test_ecs_ops_api.py`
- Test: `tests/test_deploy_workflow_contract.py`

TDD sequence:

1. Add exact-boundary tests for quick/config/full start reserve, low-memory
   failure evidence, full-image post-load/before-activation rechecks, terminal
   HTTP status/evidence, and `--no-build` forward/rollback commands.
2. Add a workflow assertion that request-only deploy does not check out code and
   full-image build remains on GitHub.
3. Run focused tests and capture the expected failures.
4. Implement resource/evidence/packaging changes and rerun until green.

- Expose mode-specific required memory through `deploy_preflight.py`.
- Record observations before rejecting the request.
- Preserve 512 MiB for quick/config; require provisional 768 MiB for the
  full-image start and recheck 512 MiB after load/before activation.
- Track minimum/phase memory in the durable event-compatible preflight map.
- Add `--no-build` to forward and rollback Compose `up` commands.
- Remove the unnecessary Actions checkout from the request-only shared job;
  preserve the GitHub Buildx/GHA cache/full-image archive path.
- Return event/status/evidence on both success and post-allocation failure, and
  use HTTP 200 for the synchronous terminal success.

Verification: preflight, release engine, retention, ECS Ops API, and workflow
contract tests, including historical low-memory failure fixtures.

### Task 3: Client, MCP, And Credential Boundaries

Files:

- Modify: `investment_knowledge_mcp/ops_client.py`
- Modify: `investment_knowledge_mcp/server.py`
- Modify: `.env.example`
- Modify: `docker-compose.prod.yml` only if needed to separate host/container
  Ops URLs without changing public ports.
- Test: the existing Ops client/server/config test modules discovered by `rg`.

TDD sequence:

1. Add tests for structured HTTP/API errors, local ref/mode/target/route
   validation, typed full-image workflow rejection before network dispatch,
   supported provenance fields, truthful terminal rendering, and MCP
   `ok: false` behavior.
2. Add configuration contract tests for host versus container Ops URL and deploy
   timeout propagation when the existing configuration surface requires it.
3. Run focused tests and capture the expected failures.
4. Implement the smallest compatible client/server/config change and rerun.

- Add structured `OpsClientError` and parse sanitized server errors.
- Validate and canonicalize request fields locally.
- Support targets, feature routes, source, and requester for quick/config.
- Reject `full`/`full_image` locally with
  `full_image_requires_workflow`; do not imply an emergency reason alone is
  sufficient.
- Make rendered/MCP results accurately report terminal success/failure.
- Separate host/container Ops URL documentation and preserve user-facing
  browser access policy.

Verification: Ops client/server unit tests and configuration/Compose contract
tests.

### Task 4: Operating State And Return Gate

Files:

- Modify: `scripts/audit_agent_flow_health.py`
- Modify: `scripts/evaluate_agent_flow_cases.py` and/or its case fixtures
- Modify: `DEPLOYMENT.md`
- Modify: `docs/project-management/Deploy-Classification.md`
- Modify: `docs/project-management/Agent-Operating-Model-Roadmap.md`
- Modify: `docs/project-management/Delivery-Queue.md`
- Modify: relevant deploy/coordinator prompt templates only where the tested
  source/channel contract needs them.
- Test: flow audit/evaluation and deploy classifier/workflow contract tests.

TDD sequence:

1. Add regression cases proving `not_required` is not an active deploy,
   `blocked` recovery remains a visible follow-up, and public browser access is
   not grouped with Ops/tool credentials.
2. Run the focused audit/evaluation tests and capture the expected failures.
3. Implement the narrow audit logic and durable documentation/state updates.
4. Run the flow audit/evaluation, delivery audit, classifier, and diff checks.

- Update the roadmap with this P0 lane and P1 telemetry/registry-image follow-up.
- Correct the Delivery Queue: prior Weekly Review implementation/integration
  rows are closed; the remaining recovery row names the confirmed low-memory
  rejection, authoritative ref, one deploy owner/channel, and exact retest
  return.
- Update flow audits/evals so `not_required` is not an active deploy conflict,
  a blocked recovery row remains visible as follow-up, and product-browser
  access is not conflated with Ops/tool credentials.
- Run the Return Gate and produce coordinator-specific recovery instructions.

## Rollout Plan

Code under `scripts/ecs_ops_api.py`, `deploy_*`, or the Ops bootstrap path is
control-plane code. A normal business deployment cannot activate it.

1. Push and integrate the verified commit into authoritative `main`.
2. Confirm no active/queued `production-deploy` run or host deployment.
3. Record Deploy Intent for the Ops API update: exact main SHA, `ops-api.yml`
   `install`, affected service `investment-ops-api.service`, verification
   `/health` plus read-only deploy status, and this reliability lane as watcher.
4. Run only the serialized Ops API install workflow and wait for stable private
   health.
5. Confirm event/status contract with a non-mutating/read-only check.
6. Re-record the Weekly Review Deploy Intent at the then-current authoritative
   main tip and run only the GitHub `targeted_quick` path if the memory gate is
   satisfied.
7. Verify stable `weekly-review-web`, public Weekly Review read behavior,
   privileged write guards, and Daily Market Brief public/tokenless behavior;
   return to its Feature Coordinator for independent acceptance retest.

Do not lower the memory threshold, start a second channel, or use SSH/direct
Compose to unblock rollout. If memory is still below the required reserve, the
named infrastructure unblock is host capacity/memory-pressure remediation,
followed by the same serialized workflow.
