# Deploy Classification

This document is the source-of-truth table for GitHub Actions deployment classification.
The executable rule lives in `scripts/classify_deploy_change.py`, and the regression tests live in `tests/test_deploy_change_classifier.py`.

## Goal

Keep production deployment proportional to the actual change:

- `no_deploy`: governance, documentation, local audit/eval, and tests-only changes should still pass CI but must not restart production.
- `quick`: application, script, database, or service-management changes that can update the existing production release without rebuilding images.
- `full`: image-layer, dependency, Compose, package metadata, or unknown high-blast-radius changes that require a full production deploy.

The workflow should succeed for `no_deploy` instead of skipping the workflow. This keeps future required checks green while avoiding production churn.

## File Classification

| Class | Paths | Result | Reason |
| --- | --- | --- | --- |
| Agent governance | `AGENTS.md`, `docs/**`, `*.md`, `**/*.md` | `no_deploy` | Durable rules and docs do not change the running service. |
| Local delivery audits and evals | `scripts/agent_preflight.py`, `scripts/audit_agent_flow_health.py`, `scripts/audit_delivery_state.py`, `scripts/audit_prd_status.py`, `scripts/classify_deploy_change.py`, `scripts/evaluate_agent_flow_cases.py` | `no_deploy` | These scripts are local coordination controls, not production runtime surfaces. |
| Tests | `tests/**` | `no_deploy` | Tests validate behavior but do not need production restart by themselves. |
| Workflow governance | `.github/workflows/*.yml`, `.github/workflows/*.yaml` | `no_deploy` | Workflow updates should be validated by the workflow, but they should not restart app services unless combined with runtime changes. |
| App runtime | `investment_knowledge_mcp/**` | `quick` | Python runtime code changes affect served behavior and need a release update. |
| Database and deploy scripts | `db/**`, `deploy/systemd/**`, most `scripts/*.py`, most `scripts/*.sh` | `quick` | These can usually update through the quick release path. |
| Image/dependency/Compose/package metadata | `Dockerfile`, `Dockerfile.*`, `docker-compose*.yml`, `docker-compose*.yaml`, `requirements*.txt`, `pyproject.toml`, `poetry.lock`, `package.json`, `package-lock.json` | `full` | These can affect build layers, dependencies, container shape, or package installation. |
| Unknown paths | Anything not matched above | `full` | Unknown change types default to the safer deploy mode. |

The highest-impact changed file wins: a docs change plus an app-runtime change is `quick`; a docs change plus a dependency change is `full`.

## Manual Dispatch

Manual `workflow_dispatch` may request `no_deploy`, `quick`, or `full`.
Manual mode overrides auto-classification and should still be used deliberately:

- Use `no_deploy` only for governance/docs/audit/test validation.
- Use `quick` for normal app releases that do not change image/dependency layers.
- Use `full` only for dependency, Compose, Docker image, or service-shape changes.

## Maintenance Rule

When a new path category is added, update all three places in the same change:

1. `scripts/classify_deploy_change.py`
2. `tests/test_deploy_change_classifier.py`
3. This document
