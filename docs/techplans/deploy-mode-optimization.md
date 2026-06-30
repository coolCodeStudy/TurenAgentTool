# Deploy Mode Optimization

## Status

- Feature: Deploy mode optimization
- Product/Ops owner: Feature-level Delivery Coordinator
- Status: P0 implemented locally on branch `codex/deploy-mode-optimization`
- User acceptance: pending; independent product acceptance is not required because this is an operational workflow guardrail.

## Problem

Recent deploy history showed a valid user concern: agents sometimes select or trigger `full` deploys when the changed files do not require rebuilding production images. In the recent sample, `ac30bd0` changed `docker-compose.prod.yml`, so a full deploy was appropriate. `e9d6c85` changed `tests/test_weekly_review_holder_attribution.py`, but the GitHub Actions classifier did not treat `tests/*` as quick-compatible and therefore selected `full`. The same SHA also had a manual workflow dispatch with `full`, which means the process needs a reason gate, not only better auto-detection.

## P0 Decision

Use `quick` rather than a new `no_deploy` mode for docs-only and tests-only changes.

Rationale:

- `quick` avoids image rebuild and image upload, which is the wasteful part of accidental full deploys.
- `quick` still refreshes the checked-out release and restarts the known services, preserving the current "main push updates production state" expectation.
- `no_deploy` would be useful later, but it changes production freshness semantics and needs a separate acceptance path.

## Full Deploy Criteria

Automatic or manual full deploy is reserved for changes that affect the production image, dependency set, Compose service/image structure, or environment/service topology. Current explicit full-trigger files are:

- `Dockerfile`
- `requirements.txt`
- `docker-compose.prod.yml`

Unknown paths remain full by default until explicitly classified.

## Quick-Compatible Criteria

The classifier treats these paths as quick-compatible:

- `docs/**` and `*.md`
- `tests/**`
- `db/**`
- `investment_knowledge_mcp/**`
- `scripts/*.py`
- `scripts/*.sh`
- `deploy/systemd/**`
- `.github/workflows/*.yml`
- `.github/workflows/*.yaml`

## Implementation

- Add `scripts/classify_deploy_mode.py` as the shared deploy-mode classifier.
- Update `.github/workflows/deploy.yml` to call the classifier and print one classification line for every changed file.
- Add `tests/test_deploy_mode_classifier.py` to pin the important cases.
- Add a `deploy_reason` input to manual workflow dispatch and fail manual `full` dispatches that omit a reason.

## Verification

Required local verification:

- `python3 -m unittest tests.test_deploy_mode_classifier`
- classifier CLI simulation for test-only, dependency, mixed, and empty change sets
- `git diff --check`
- `python3 scripts/audit_delivery_state.py --feature "Deploy mode optimization"`

## P1 Follow-Up Options

- Add an explicit `no_deploy` mode for docs-only and tests-only changes after deciding how production freshness should behave for main pushes.
- Route local worker deploy requests through the same classifier before selecting an Ops API mode.
- Expand the classifier if future production-impacting files are identified.
