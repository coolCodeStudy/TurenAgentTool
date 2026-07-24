# Deploy Classification

This document is the source-of-truth table for production deployment
classification. The executable rule lives in `scripts/classify_deploy_change.py`,
and the regression tests live in `tests/test_deploy_change_classifier.py`.

## Goal

Keep production deployment proportional to the actual change and safe for the
small ECS host:

- `no_deploy`: governance, documentation, local audit/eval, and tests-only
  changes should still pass CI but must not touch ECS.
- `targeted_quick`: application/source changes stage a release and recreate only
  the mapped application services without building or loading an image.
- `config_restart`: Compose or environment runtime wiring changes validate the
  rendered Compose config and recreate only mapped targets without changing the
  application image.
- `full_image`: Dockerfile, dependency, base-image, or Compose image/build
  semantic changes build and load one immutable application image.

The workflow should succeed for `no_deploy` instead of skipping the workflow. This keeps future required checks green while avoiding production churn.

Production source policy is strict: `main` resolves to the freshly fetched
`origin/main` tip, and an explicit 40-character commit SHA must equal that
same tip. Named feature branches, unintegrated SHAs, and older ancestors are
rejected; integrate, push `main`, and dispatch the new authoritative tip.

## Mode Matrix

| Mode | Paths / semantic trigger | ECS access | Image behavior | Runtime behavior |
| --- | --- | --- | --- | --- |
| `no_deploy` | Docs, governance, tests, local audit/eval assets | No | None | CI/classification only; no Ops API, SSH, SCP, or service restart. |
| `targeted_quick` | Python app code, scripts, DB initialization code, host worker code, source assets | Yes, 512 MiB `MemAvailable` reserve | Reuse current immutable application image | Stage release, switch `current`, recreate only mapped application targets with `--no-deps`, and keep PostgreSQL running. |
| `config_restart` | Compose/environment/runtime wiring with no `image`, `build`, platform, or image-input semantic change | Yes, 512 MiB `MemAvailable` reserve | Reuse current immutable application image | Validate Compose, switch release when needed, recreate only mapped targets with `--no-deps`, and keep PostgreSQL running. |
| `full_image` | `Dockerfile*`, `requirements*.txt`, package lockfiles, base-image changes, or Compose `image`/`build` semantics | Yes, 768 MiB start reserve plus 512 MiB after image load/before every activation | Build/load `investment-knowledge-app:<40-char-sha>` only | Activate the new release and image tag together; recreate application targets sequentially; never recreate PostgreSQL. |

Manual emergency `full_image` is allowed only when the operator records the
reason and the image archive path/size. A requested `full_image` without an
image-input diff is rejected unless the emergency override and archive evidence
are present.

## Target Mapping

The classifier returns both the mode and a sorted target set. PostgreSQL is not
an application deployment target.

| Path or module family | Mapped targets |
| --- | --- |
| Web-only Daily Market Brief files such as `daily_market_brief_web.py`, Web templates, and Web shell modules | `weekly-review-web` |
| `investment_knowledge_mcp/ai_industry_panorama/**`, including frozen release JSON | `weekly-review-web` |
| `command_workbench.py` and shared Web command-workbench assets | `weekly-review-web`, `command-api` |
| Shared command logic such as `command_router.py`, `daily_market_brief.py`, and `weekly_review.py` | `weekly-review-web`, `command-api`, `dingtalk-api`, `mcp`, `dingtalk-stream-bot` |
| Database initialization code such as `scripts/init_db.py` | `weekly-review-web`, `command-api`, `dingtalk-api`, `mcp`, `dingtalk-stream-bot` |
| Command API transport-only modules | `command-api` |
| DingTalk HTTP API transport-only modules | `dingtalk-api` |
| MCP server and MCP tool modules | `mcp` |
| Scheduler entrypoints | The matching scheduler service, such as `account-snapshot-scheduler` or `ipo-reminder-scheduler` |
| DingTalk stream bot entrypoint or adapter-only code | `dingtalk-stream-bot` |
| Shared runtime modules imported by several entrypoints | Union of affected application services |
| Host control-plane scripts | Matching host unit, such as `investment-ops-api.service`, under the global deployment lock |
| Requirements, Dockerfile, base-image, or app-image Compose semantics | All application services that share `investment-knowledge-app:<sha>` |
| Unknown runtime paths | All application services under `targeted_quick` |
| Unknown image/package paths | `full_image` |
| Unknown docs/governance paths | Fail classification until an explicit rule is added |

`dingtalk-api` is the DingTalk HTTP API Compose service. It uses the shared
application image and imports shared command logic, so it is targeted with the
other active command consumers. It is distinct from `dingtalk-stream-bot`, the
DingTalk Stream Mode long-connection service.

For `config_restart`, `full_image`, and other all-application-service paths,
the shared-image application service set is `weekly-review-web`, `command-api`,
`dingtalk-api`, `mcp`, `account-snapshot-scheduler`,
`ipo-reminder-scheduler`, and `dingtalk-stream-bot`.

## File Classification

| Class | Paths | Result | Reason |
| --- | --- | --- | --- |
| Agent governance | `AGENTS.md`, `docs/**`, `*.md`, `**/*.md` | `no_deploy` | Durable rules and docs do not change the running service. |
| Local delivery audits and evals | `scripts/agent_preflight.py`, `scripts/audit_agent_flow_health.py`, `scripts/audit_delivery_state.py`, `scripts/audit_prd_status.py`, `scripts/classify_deploy_change.py`, `scripts/evaluate_agent_flow_cases.py` | `no_deploy` | These scripts are local coordination controls, not production runtime surfaces. |
| Tests | `tests/**`, `e2e/**`, `playwright.config.ts` | `no_deploy` | Test code and browser-acceptance configuration validate behavior but do not need production restart by themselves. |
| Workflow governance | `.github/workflows/*.yml`, `.github/workflows/*.yaml` | `no_deploy` | Workflow updates should be validated by the workflow, but they should not restart app services unless combined with runtime changes. |
| App runtime | `investment_knowledge_mcp/**`, application Web modules, command router modules, scheduler entrypoints | `targeted_quick` | Python runtime code changes affect served behavior and need a targeted release update. |
| Database initialization and runtime scripts | `db/**`, most runtime `scripts/*.py`, most runtime `scripts/*.sh` | `targeted_quick` | These can update through the release path without rebuilding the image unless they change image inputs. |
| Compose runtime-only configuration | `docker-compose*.yml`, `docker-compose*.yaml` when only environment, ports, commands, health checks, mounts, profiles, or restart policy change | `config_restart` | Runtime wiring must be validated and restarted, but the app image does not change. |
| Image/dependency/package metadata | `Dockerfile`, `Dockerfile.*`, `requirements*.txt`, `pyproject.toml`, `poetry.lock`, `package.json`, `package-lock.json`, or Compose `image`/`build` semantics | `full_image` | These affect build layers, dependencies, base images, or image selection. |
| Unknown paths | Anything not matched above | Fail or `full_image`, depending on whether the path is docs/governance or possible runtime/image input | Unknown production-impacting changes must not silently become routine quick deploys. |

The highest-impact changed file wins: a docs change plus app-runtime code is
`targeted_quick`; a docs change plus a dependency change is `full_image`.

## AI Industry Panorama Release Sequence

A business change under
`investment_knowledge_mcp/ai_industry_panorama/**` is `targeted_quick` and
targets only `weekly-review-web`. This applies to its release validator,
renderer, controller, and canonical release JSON. It does not broaden shared
command, scheduler, DingTalk, or MCP targets.

A candidate that changes `scripts/deploy_contract.py` has an independent Ops
control-plane update even when its business target is only
`weekly-review-web`. Release that exact candidate SHA in two serialized
operations under the shared deployment lock:

1. Install the Ops API control plane from the exact target SHA. Wait for its
   private health check and verify that its reported control-plane identity is
   that same SHA.
2. Only after the identity check passes, run the same-SHA application quick
   deploy for `weekly-review-web`.

Do not bypass a failed or mismatched control-plane identity with a parallel
deploy channel. The existing `feature_routes` request should check HTTP success
for `/ai-industry-panorama` and `/api/ai-industry-panorama`; no change to
`scripts/deploy_release.py` is needed. Those checks establish route
availability, not JSON correctness. The L3 public API contract must separately
verify `ok`, schema version, release ID, and nonempty entity and relationship
collections.

## Preflight and Product-Safe Failure

Every ECS-touching mode must pass preflight before release activation or image
archive load. `MemAvailable` is a Linux availability signal, not raw free RAM;
it includes reclaimable cache. The 512 MiB quick/config reserve is deliberately
fail-closed for the small no-swap host and is not to be lowered merely to retry
a rejected release. Full-image work has higher transient pressure and starts at
768 MiB before its post-load/pre-activation 512 MiB rechecks:

- root filesystem has at least 8 GiB free;
- root filesystem usage is at most 80%;
- quick/config available memory is at least 512 MiB;
- full-image available memory is at least 768 MiB before load and at least 512 MiB after load/before each activation;
- Docker responds within 10 seconds;
- the existing PostgreSQL container is running and healthy;
- the global production deployment lock is available;
- the target satisfies the source policy above;
- Compose config is valid for the staged release and environment;
- `full_image` additionally requires available disk of at least two times the
  compressed image archive size plus 2 GiB.

Preflight failures, source-policy rejections, classifier ambiguity, and health
failures must be product-safe: return a clear operator error, write deployment
event evidence when possible, leave the previous release active, and do not
recreate PostgreSQL or apply broad pruning to force progress.

## Image and Retention Rules

Full image deployment creates exactly one managed application image named:

```text
investment-knowledge-app:<40-char-sha>
```

The mutable `prod` tag is not the deployment identity. Health and deploy state
report the active commit SHA and active app image tag separately.

Retention is scoped to managed app resources only:

- preserve current and previous managed app images from deployment state;
- preserve images referenced by any container;
- preserve the pinned PostgreSQL/pgvector image and PostgreSQL volume;
- remove only older unreferenced `investment-knowledge-app:<sha>` images;
- remove uploaded image archives after success or failed load;
- never use broad `docker system prune`, `docker image prune -a`, or
  `docker volume prune` as part of normal deployment.

## Manual Dispatch

Manual `workflow_dispatch` may request `no_deploy`, `targeted_quick`,
`config_restart`, or `full_image`.
Manual mode overrides auto-classification and should still be used deliberately:

- Use `no_deploy` only for governance/docs/audit/test validation.
- Use `targeted_quick` for normal app releases that do not change
  image/dependency layers.
- Use `config_restart` for runtime-only Compose/environment wiring changes.
- Use `full_image` only for dependency, Docker image, base-image, or Compose
  image/build semantic changes, or for a documented emergency with archive
  evidence.

Read-only audit commands for operators:

```bash
df -h /
free -m
docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
curl -fsS -H "Authorization: Bearer $OPS_API_TOKEN" \
  "http://127.0.0.1:8767/ops/deploy-status?id=$DEPLOY_EVENT_ID" | python3 -m json.tool
```

## Maintenance Rule

When a new path category is added, update all three places in the same change:

1. `scripts/classify_deploy_change.py`
2. `tests/test_deploy_change_classifier.py`
3. This document
