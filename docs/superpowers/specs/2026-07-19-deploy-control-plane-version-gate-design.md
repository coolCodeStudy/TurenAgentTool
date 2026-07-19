# Deploy Control-Plane Version Gate Design

## Status

Approved for implementation on 2026-07-19. The Owner authorized the Architecture & Code Health Coordinator to fix the incident end to end, deploy it, verify production, and notify the originating Frontend Experience session.

## Incident

GitHub Actions run `29672588130` planned target `20baa6903389fec0e97ccbd4cd443af6d840eeb1` with the target checkout's deployment contract. The independent Ops API was still installed from `86652e4409420e0dffb17e8bf8c940c34cf6b6c0`. The target contract admitted `.github/workflows/cloud-e2e.yml`, while the installed contract rejected that path. The executor therefore raised an untyped `ValueError` before resource preflight and returned only the generic product-safe failure message.

No application service was activated and the uploaded image archive was removed. Production remained on the prior healthy release.

## Goal

Make an independent Ops control-plane version mismatch explicit and mechanically detectable before an application image is built, while preserving the installed Ops API as the authoritative deployment policy executor.

## Non-Goals

- Do not load or execute deployment policy from an unactivated target release inside the running Ops API.
- Do not merge Ops API installation into normal application container activation.
- Do not redesign the deployment engine, deployment modes, or application topology.
- Do not weaken unknown-path rejection.

## Considered Approaches

### Selected: explicit version handshake and two-step release

The Ops bootstrap records its resolved commit as `OPS_CONTROL_PLANE_REF`. Authenticated deployment status returns that exact SHA. The target-side classifier marks whether the cumulative application diff changes any installed control-plane file. When it does, GitHub Actions classifies the narrower lineage from the installed control-plane ref to the target: it stops before build only when that lineage still contains control-plane changes. Documentation/test-only descendants of an installed control-plane ref remain compatible. The Coordinator runs the existing serialized Ops API install workflow for an incompatible target SHA, waits for health, and reruns the same application deployment.

This preserves the current trust boundary and the global deployment lock while making the required ordering mechanical and observable.

### Rejected: dynamically import the target deployment contract

This would let unactivated application source redefine the authority that decides whether that source may be deployed. It breaks the independent control-plane trust boundary.

### Rejected: silently bootstrap Ops API inside every business deployment

This would restart the control plane on unrelated releases, duplicate the dedicated installation workflow, and blur application and control-plane rollback ownership.

## Architecture

### Control-plane identity

`bootstrap_ops_api_v2_on_ecs.sh` already resolves `BOOTSTRAP_REF` to an immutable commit. It passes that commit to `install_ops_api_on_ecs.sh`, which validates the value as a lowercase 40-character SHA and persists it in the root-only Ops environment. `ecs_ops_api.py` exposes it only as non-secret authenticated deployment-status metadata.

The bootstrap credential and resolved identity are captured in readonly shell variables before the business environment is loaded. A business environment that attempts to rebind either preserved value fails the install rather than changing control-plane identity or authentication.

### Update requirement

`deploy_contract.py` owns the list of files copied into `/opt/investment-ops` or otherwise responsible for installing that directory. `serialize_plan()` adds `control_plane_update_required`, derived from the classified changed files. The flag does not change application deploy mode or targets.

Git diff collection disables rename collapsing so a rename includes the old installed control-plane path as a deletion and cannot evade the update requirement.

### Workflow gate

The GitHub planning job reads both `current_sha` and `control_plane_ref` from `/deploy/status`. It emits both the target plan and the installed control-plane identity. A missing legacy identity is treated as incompatible and requires one explicit install. When the cumulative plan includes control-plane changes and the identities differ, the job classifies `control_plane_ref..target_sha`; it fails before image build only when that delta still changes control-plane files, with an actionable message naming the target SHA and the dedicated `ops-api.yml` install workflow.

After the dedicated install succeeds, rerunning the same target sees matching identities and proceeds through the existing plan, build, Ops API delegation, health, stability, and route checks.

### Executor diagnostics

The deployment engine converts classifier `ValueError` failures into a typed `DeploymentError` that says the installed control-plane contract rejected the target and requires an Ops API install. This is defense in depth for callers that bypass or predate the workflow gate. Selector mutation and service activation remain untouched.

The engine applies the same lineage check for every computed non-`no_deploy` plan whose cumulative application diff changes a control-plane file. Authenticated direct clients therefore cannot bypass the GitHub planning gate, while documentation/test-only descendants do not force redundant control-plane restarts.

## Verification

- Unit-test control-plane path detection and serialized plan output.
- Unit-test bootstrap-to-installer propagation and status exposure of the exact SHA without exposing credentials.
- Contract-test that GitHub planning reads the installed SHA and blocks before `full_image` when an update is required.
- Unit-test that an unclassified path from the executor's plan builder returns an actionable typed outcome with zero activated services.
- Run the focused deployment, Ops API, bootstrap, and workflow contract suites.
- Run deployment classifier and architecture health audits.
- Install the Ops API from the pushed target ref, verify private health, rerun one deployment channel, and verify durable deploy evidence plus cloud routes.

## Deployment and Rollback

Deploy Intent uses the existing `production-deploy` concurrency group and host deploy lock:

1. Push the verified fix to its branch and integrate it into `main`.
2. Let the automatic business workflow stop at the version gate if the installed control plane is older.
3. Dispatch `ops-api.yml` with `mode=install` from the exact integrated SHA and wait for success.
4. Dispatch or rerun the business deploy once for that same SHA.
5. Verify stable services and product routes before notifying the originating session.

If Ops installation fails, the existing application release remains active. If the subsequent application deployment fails before activation, no rollback is needed; after activation, existing rollback and lockout behavior remains authoritative.
