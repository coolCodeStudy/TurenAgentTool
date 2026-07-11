# Deploy Flow Optimization P0 Design

## Status

Approved direction. The user approved retaining AKShare, avoiding paid ECS
capacity changes, and fixing deployment classification, image lifecycle,
resource protection, deployment targeting, and rollback before any further
Daily Market Brief release.

## Incident Summary

The production ECS instance reached 100% usage on its 40 GB root filesystem.
The kernel entered out-of-memory handling on a host with about 1.6 GiB RAM and
no swap, killing system and application processes including FutuOpenD. Docker
and PostgreSQL entered restart loops, SSH and Workbench became unreliable, and
the Daily Market Brief deployment timed out after `docker load`.

Manual cleanup removed 13.13 GB of unused Docker images and reduced root disk
usage from 100% to 35%. All seven Compose containers returned to running state
and PostgreSQL became healthy.

An audit of the 19 full deployments between 2026-06-28 and 2026-07-10 found:

- 1 deployment that genuinely required an application image rebuild.
- 4 deployments with Compose-only changes that required container recreation,
  not an image rebuild.
- 12 deployments with no image-input change.
- 2 deployments whose apparent dependency changes were caused by switching
  production between incomplete feature branches.

The application source copied into the image is about 1.1 MB. The current
AKShare-enabled application image is about 576 MB, with about 285 MB in its
Python dependency layer. The pre-AKShare image was about 300 MB. Image size is
acceptable for this host if only the current and previous application images
are retained; unlimited release-image accumulation is not acceptable.

## Goals

1. Make routine releases use the independent ECS Ops API and avoid image
   rebuilds.
2. Permit production deployment only from `main` or an immutable commit that
   is reachable from `main`.
3. Classify changes against the currently deployed production commit, not only
   the target commit's first parent.
4. Separate documentation-only, code-only, runtime-configuration, and
   image-input changes.
5. Restart only affected application services for routine releases.
6. Build immutable application images for real dependency or Dockerfile
   changes while retaining AKShare.
7. Retain at most the current and previous application images on ECS.
8. Abort before staging or loading artifacts when disk, memory, Docker, or
   PostgreSQL preconditions are unsafe.
9. Roll back release code, image selection, and already-recreated services when
   activation fails.
10. Keep PostgreSQL running during application releases.
11. Use one deployment core from both Ops API and GitHub Actions.
12. Reduce routine deployment time from about 6-7.5 minutes to less than one
    minute without weakening health verification.

## Non-Goals

- Removing AKShare.
- Paid disk or RAM expansion.
- Adding swap in this P0.
- Migrating images to ACR, GHCR, or another registry.
- Blue-green deployment requiring duplicate application stacks.
- Redesigning application service boundaries.
- Solving external market-data provider availability or data-quality issues.
- Deploying Daily Market Brief before this P0 passes its release-safety gate.

## Deployment Model

### Production Source Policy

Production accepts either:

- named ref `main`; or
- a 40-character commit SHA for which `git merge-base --is-ancestor <sha>
  origin/main` succeeds.

Named feature branches are rejected. This prevents a later feature deployment
from replacing production with a snapshot that omits previously released
features.

### Modes and Targets

Deployment mode and deployment target are separate concepts.

| Mode | Trigger | Image build | Runtime action |
| --- | --- | --- | --- |
| `no_deploy` | Documentation, tests, local governance, evaluation assets | No | No ECS access |
| `targeted_quick` | Application code, scripts, DB initialization code, host worker code | No | Stage release and recreate mapped targets |
| `config_restart` | Compose runtime configuration or environment wiring without image-semantic changes | No | Validate Compose and recreate mapped targets |
| `full_image` | Dockerfile, requirements, base-image, or Compose image/build semantics | Yes, on GitHub runner | Load immutable image and recreate application targets sequentially |

`docker-compose.prod.yml` is not automatically `full_image`. A classifier must
inspect whether the diff changes `image`, `build`, build arguments, or image
platform semantics. Environment, mounts, commands, ports, health checks, and
restart policy changes use `config_restart` unless the classifier cannot prove
that they are runtime-only.

Unknown runtime paths conservatively map to all application targets under
`targeted_quick`. Unknown image/package paths map to `full_image`. Unknown
documentation or repository-control paths fail classification and require an
explicit rule; they do not silently trigger a full production deploy.

### Target Mapping

The classifier returns a sorted target set in addition to the mode. Initial
targets are:

- `weekly-review-web`
- `command-api`
- `dingtalk-api`
- `mcp`
- `account-snapshot-scheduler`
- `ipo-reminder-scheduler`
- `dingtalk-stream-bot`
- host control-plane units such as `investment-ops-api.service` and the
  research worker

Initial mapping rules include:

- `weekly_review_web.py` and Web-only template or shell modules target
  `weekly-review-web`.
- `command_workbench.py` targets both `weekly-review-web` and `command-api`
  because both services render that UI.
- `command_router.py`, `daily_market_brief.py`, and `weekly_review.py` target
  every active command consumer that imports them: `weekly-review-web`,
  `command-api`, `dingtalk-api`, `mcp`, and `dingtalk-stream-bot`.
- `scripts/init_db.py` targets every active application service that runs
  database initialization before startup: `weekly-review-web`, `command-api`,
  `dingtalk-api`, `mcp`, and `dingtalk-stream-bot`.
- Command API transport-only modules target `command-api`.
- DingTalk HTTP API transport-only modules target `dingtalk-api`.
- MCP server and MCP tool modules target `mcp`.
- Scheduler entrypoints target only their scheduler service.
- Shared runtime modules used by multiple entrypoints return the union of the
  affected services.
- Requirements or Dockerfile changes target every application service because
  the services share one application image.
- `dingtalk-api` is a Compose HTTP service that uses the shared application
  image and shared command router. It is distinct from `dingtalk-stream-bot`,
  the DingTalk Stream Mode long-connection service.
- For `config_restart`, `full_image`, and other all-application-service paths,
  the shared-image application service set is `weekly-review-web`,
  `command-api`, `dingtalk-api`, `mcp`, `account-snapshot-scheduler`,
  `ipo-reminder-scheduler`, and `dingtalk-stream-bot`.
- PostgreSQL is never an application deployment target. Schema initialization
  continues through application startup against the existing healthy database.
- Control-plane script changes target only the matching systemd unit and use
  the same global deployment lock.

The mapping lives in structured Python data with unit tests. It is not encoded
as shell `case` statements in multiple deployment entrypoints.

## Image Build and Transfer

### Immutable Identity

Full builds create:

```text
investment-knowledge-app:<40-character-commit-sha>
```

The Compose environment sets `APP_IMAGE_TAG` to that exact SHA. The mutable
`prod` tag is not used to identify the running release. Health and deploy state
report the commit SHA and image tag separately.

### Build Inputs

AKShare remains in `requirements.txt`. The P0 preserves the single shared
application image. Multiple containers share read-only Docker layers, so they
do not store seven copies of the image.

The GitHub full-build path:

1. Builds only the application image.
2. Uses GitHub Actions BuildKit cache keyed by Dockerfile and requirements
   content.
3. Saves and uploads only the SHA-tagged application image.
4. Does not save or upload `pgvector/pgvector:pg16` on every release.
5. Deletes the uploaded image archive and unused extraction directory after a
   successful load or failed attempt.

PostgreSQL's image is pinned independently and changed only through an explicit
database-image maintenance release.

## Durable Deployment State

Deployment state lives outside immutable releases at:

```text
/opt/investment-knowledge/shared/deploy-state.json
```

The state file records:

- schema version
- current commit SHA
- previous commit SHA
- current application image tag
- previous application image tag
- active release path
- previous release path
- last deployment mode
- requested and resolved refs
- affected targets
- deployment event ID
- timestamps
- preflight disk and memory observations
- final health result

State is written through a temporary file and atomic rename. Secrets are never
written to this file.

### Legacy Baseline Migration

The first V2 control-plane bootstrap initializes the durable state before the
Ops API starts. It resolves the commit from the existing production checkout,
proves that commit is reachable from `origin/main`, stages the matching
immutable release, tags the single running application image by that commit,
updates the image selector, and creates the `current` release symlink. The
migration is idempotent and does not recreate application containers or
PostgreSQL. Container verification uses Docker image IDs, so containers that
were originally created with the legacy mutable `prod` display tag remain a
valid baseline when the underlying image ID matches the immutable SHA tag.

Changes to the independent Ops control plane are classified as `no_deploy` for
the business stack. Release coordination must run the dedicated Ops API install
workflow and wait for it to finish before starting a business deployment; this
updates `/opt/investment-ops` without racing or restarting application services.

## Resource Preflight

Every mode that touches ECS runs preflight before release activation. The
preflight fails without changing production when any required condition is
false:

- root filesystem has at least 8 GiB available;
- root filesystem usage is at most 80%;
- available memory is at least 512 MiB;
- Docker responds within 10 seconds;
- PostgreSQL's existing container is running and healthy;
- no other deployment owns the global production lock;
- the target commit satisfies production source policy;
- Compose config validates with the target release and environment;
- for `full_image`, available disk is at least twice the compressed archive
  size plus 2 GiB.

The preflight output is machine-readable and included in the deployment event.
It never performs pruning automatically to make an unsafe deployment pass.

## Activation Flow

### No-Deploy

The workflow reports successful classification and exits without credentials,
SSH, Ops API, or ECS access.

### Targeted Quick and Config Restart

1. Resolve and verify target SHA against `origin/main`.
2. Diff the deployed SHA against the target SHA.
3. Recompute mode and targets server-side; reject a caller mismatch.
4. Run resource preflight.
5. Stage release files under `/opt/investment-knowledge/releases/<sha>`.
6. Validate Compose using the staged release and current immutable image tag.
7. Atomically switch `/opt/investment-knowledge/current`.
8. Recreate only mapped application services with `--no-deps` so PostgreSQL is
   not recreated.
9. Restart mapped host units independently when present.
10. Run target-specific health checks and a 30-second stability window.
11. Persist successful deployment state.
12. Retain the current, previous, and one in-progress release directory; remove
    older immutable release directories.

### Full Image

1. GitHub verifies that the target commit is on `main` and that image inputs
   differ from deployed state.
2. GitHub builds and tests the SHA-tagged application image.
3. ECS runs resource preflight before accepting the archive.
4. ECS loads the candidate image without changing `APP_IMAGE_TAG`.
5. Stage and validate the release with the candidate image tag.
6. Switch the release symlink and image tag as one activation transaction.
7. Recreate application services one at a time with `--no-deps`.
8. Check each service before moving to the next service.
9. Run aggregate health checks and a 60-second stability window.
10. Persist successful deployment state.
11. Remove the uploaded archive.
12. Remove managed application images except the current and previous tags.
13. Prune unused BuildKit cache older than seven days.

The full path never recreates PostgreSQL.

## Health Checks

Each recreated target must be running. HTTP targets additionally require their
existing product endpoint or health endpoint to return a successful response.

- `weekly-review-web`: `/health`, `/weekly-review`, `/command`, and any feature
  route explicitly named by the deployment request.
- `command-api`: HTTP health response and authenticated-route negative check.
- `dingtalk-api`: HTTP health response and DingTalk HTTP adapter readiness.
- `mcp`: transport endpoint responds without a process-level failure.
- schedulers and stream bot: container remains running through the stability
  window and logs contain no startup traceback or crash-loop signal.
- aggregate: PostgreSQL remains healthy throughout the deployment.

Product feature acceptance remains separate from deployment health. A 200
response proves availability, not product correctness.

## Rollback

Before activation, the deployer snapshots the previous state. If any recreate
or health step fails:

1. Stop progressing to untouched services.
2. Restore the previous release symlink and `APP_IMAGE_TAG`.
3. Recreate only services already switched during the failed attempt, in
   reverse order, using `--no-deps`.
4. Verify previous aggregate health.
5. Record the failed candidate and rollback result.
6. Remove the candidate image only when no container references it.
7. Preserve failure logs and the candidate release directory until the deploy
   event is recorded, then apply release retention.

If rollback health fails, the event is marked `rollback_failed`, all further
deployments remain locked out, and manual recovery instructions report the
exact current release, image, containers, disk, and memory state.

## Image and Release Retention

Automatic cleanup is scoped to managed resources. It must not call broad
`docker system prune` or `docker volume prune`.

After a stable successful full release:

- preserve application images named by current and previous deployment state;
- preserve images referenced by any container;
- remove older unreferenced `investment-knowledge-app:<sha>` images;
- preserve the pinned PostgreSQL image;
- remove uploaded deployment archives;
- preserve current, previous, and active candidate release directories;
- remove older release directories;
- report reclaimed bytes.

Quick and no-deploy paths do not create or delete application images.

## Manual and Emergency Controls

Manual requests cannot override computed mode by default.

- Requesting `full_image` without an image-input diff is rejected.
- An emergency override requires `emergency_override=true` and a non-empty
  reason of at least 20 characters.
- Emergency overrides are recorded in deployment events and still run source,
  resource, lock, Compose, health, rollback, and retention controls.
- Emergency override does not permit feature-branch production deployment.

## Entry-Point Responsibilities

### ECS Ops API

The Ops API is the primary daily control plane for `targeted_quick` and
`config_restart`. It resolves refs, recomputes classification, owns the global
lock, invokes the shared deployment core, and exposes asynchronous status.

### GitHub Actions

GitHub Actions performs CI and `no_deploy` classification for every main push.
It builds a full image only when server-confirmed classification requires
`full_image`. It transfers the immutable image and invokes the shared
activation core. It remains a rescue transport, not an alternate deployment
implementation.

### Shared Deployment Core

Classification, preflight, state transitions, activation, health checks,
rollback, and retention are implemented once in repository scripts and called
by both entrypoints. Shell wrappers remain thin process launchers.

## Observability

Every deployment event includes:

- computed and requested mode
- deployed and target SHA
- changed image inputs
- targets
- preflight measurements
- image archive size
- image count before and after
- disk usage before and after
- per-target recreate and health durations
- rollback status
- cleanup result and reclaimed bytes

Health metadata exposes the active commit and application image tag. It does
not expose secrets, raw environment values, provider credentials, or database
credentials.

## Verification Strategy

### Unit Tests

- Diff classification for all four modes.
- Compose semantic classification distinguishes image/build changes from
  runtime-only changes.
- Target mapping for Web-only Daily Market Brief changes, shared Daily Market
  Brief logic, Weekly Review, Command Workbench, command routing, schedulers,
  and control-plane scripts.
- Feature-branch rejection and main-ancestor acceptance.
- Manual full rejection and emergency-override auditing.
- Preflight threshold boundaries.
- Current/previous state transitions.
- Retention preserves current, previous, container-referenced, and PostgreSQL
  images while selecting only older managed application images.

### Script Integration Tests

Tests use fake `docker`, `docker compose`, `git`, filesystem, and health
commands through an injected command runner or PATH fixture. They verify:

- quick deploy invokes no image build/load/remove command;
- targeted quick recreates only expected services;
- no application path recreates PostgreSQL;
- full deploy recreates application services sequentially;
- low disk and low memory fail before activation;
- candidate failure restores previous state and recreates switched services;
- successful full retains exactly current and previous managed images;
- failed full removes an unreferenced candidate image;
- archive cleanup occurs on success and failure.

### Workflow Tests

- Docs-only changes select `no_deploy` and do not expose deploy credentials.
- Python-only changes select `targeted_quick`.
- Compose environment-only changes select `config_restart`.
- Requirements changes select `full_image`.
- Manual full without an image diff fails before build.
- Full image bundle excludes pgvector.

### Cloud Acceptance

On a unified Deploy Flow P0 `main` release, before resuming Daily Market Brief:

1. Record baseline disk usage, memory, image list, containers, and active SHA.
2. Run three independently triggered code-only targeted quick releases; each
   must complete in under 60 seconds and image count must not increase.
3. Run one controlled full release; current and previous application images
   must be the only retained managed application images.
4. Confirm PostgreSQL container identity and start time did not change.
5. Confirm Daily Market Brief, Weekly Review, Command Workbench, MCP, and
   `dingtalk-api` routes remain available after each release.
6. Run a deliberately failing candidate in the test harness, not production,
   and verify rollback.
7. Confirm root disk remains below 70% after retention and pgvector remains
   present.
8. Record branch, commit, deployment mode, duration, managed image count, root
   disk percentage, PostgreSQL identity, route checks, and rollback state.

## Acceptance Criteria

- Three consecutive quick deployments add zero Docker images.
- Three consecutive full-image test deployments leave at most two managed
  application images after each stable success.
- Documentation-only changes make no ECS request.
- Python/Web changes do not build an image.
- Runtime-only Compose changes do not build an image.
- A named feature branch is rejected for production deployment.
- A non-main SHA is rejected for production deployment.
- Unsafe disk or memory state fails before image transfer/load or release
  activation.
- Application deployment never recreates PostgreSQL.
- Web-only Daily Market Brief changes recreate only `weekly-review-web`;
  shared Daily Market Brief logic recreates every active command consumer
  identified by the structured dependency map.
- Failed activation restores the previous release and image.
- Automatic cleanup never deletes volumes or non-managed images.
- Daily Market Brief, Weekly Review, Command Workbench, MCP, and `dingtalk-api`
  remain present after unrelated releases.
- Routine deployment completes in less than 60 seconds under normal ECS
  conditions.
- Root filesystem usage remains below 70% after stable-release cleanup.

## Rollout Order

1. Implement and test structured diff classification and target mapping.
2. Implement resource preflight and durable deployment state.
3. Refactor activation into a shared deployment core with targeted recreation
   and rollback.
4. Implement immutable image tagging and managed retention.
5. Route Ops API quick/config requests through the shared core.
6. Reduce GitHub full build to the app image and route activation through the
   shared core.
7. Validate locally with fake command integration tests.
8. Merge only Deploy Flow Optimization P0 to `main`; install or update the Ops
   API and validate the no-op plus narrow `targeted_quick` rollout gates.
9. Run the Deploy Flow P0 cloud acceptance matrix above.
10. After P0 cloud acceptance passes, integrate Daily Market Brief onto the
    accepted `main`, perform one controlled `full_image` release for AKShare,
    and dispatch independent Daily Market Brief product acceptance. The
    coordinator must not mark user acceptance accepted.
