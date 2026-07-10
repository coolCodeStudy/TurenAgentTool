# Deploy Flow Optimization P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace routine full-image deployments with a safe, target-aware deployment control plane that preserves AKShare, deploys only production commits from `origin/main`, bounds Docker disk growth, and rolls back failed releases automatically.

**Architecture:** A shared Python deployment contract classifies a deployed-SHA-to-target-SHA diff into `no_deploy`, `targeted_quick`, `config_restart`, or `full_image`, then maps changed files to the smallest safe service set. Both the ECS Ops API and GitHub Actions call one deployment engine that performs source validation, resource preflight, immutable release activation, sequential service recreation, health verification, durable state updates, managed retention, and rollback; PostgreSQL is never recreated by application deployment.

**Tech Stack:** Python 3.11 standard library, `unittest`, Docker Compose v2, Bash, Git, GitHub Actions, JSON state files, existing ECS Ops API.

## Global Constraints

- Execute this plan in a fresh worktree created from `origin/main` on branch `codex/deploy-flow-optimization-impl`; do not implement it on `codex/deploy-flow-optimization-p0`, which contains Daily Market Brief branch history.
- Import design commit `9545432` and this plan document into the fresh implementation branch before Task 1, without importing unrelated Daily Market Brief commits.
- Keep AKShare in the application dependency set; do not remove or replace it to reduce image size.
- Do not add paid disk, RAM, or swap capacity in P0.
- Production targets must be either `main` or a 40-character commit SHA reachable from `origin/main`; feature branches are always rejected, including emergency overrides.
- Deployment modes are exactly `no_deploy`, `targeted_quick`, `config_restart`, and `full_image`.
- `weekly_review_web.py` targets `weekly-review-web`; `command_workbench.py` targets `weekly-review-web` and `command-api`; shared command/domain modules target `weekly-review-web`, `command-api`, `mcp`, and `dingtalk-stream-bot`; scheduler entrypoints target only their scheduler service.
- `requirements.txt` and `Dockerfile` changes target all application services and require `full_image`.
- PostgreSQL is never an application deployment target and is never recreated by this flow.
- Use immutable application image tags in the form `investment-knowledge-app:<40-char-sha>`.
- Retain only the current and previous managed application images, plus any image referenced by a running container; never run `docker system prune`, `docker volume prune`, or delete the pgvector image.
- Preflight requires at least 8 GiB free disk, disk use no higher than 80%, at least 512 MiB available memory, Docker response within 10 seconds, healthy PostgreSQL, a global deployment lock, valid source policy, and valid normalized Compose configuration.
- `full_image` additionally requires free disk of at least twice the compressed image archive size plus 2 GiB.
- Recreate application services sequentially with `docker compose up -d --no-deps --force-recreate <service>` and verify each service before proceeding.
- Store durable deployment state atomically at `/opt/investment-knowledge/shared/deploy-state.json`.
- A manual `full_image` request without an image-input diff requires an emergency reason of at least 20 characters; the reason does not bypass source policy or resource checks.
- Routine deployment target is under 60 seconds; cloud acceptance requires three quick deployments with no image-count growth and one controlled full deployment retaining at most two managed application images.
- Do not deploy Daily Market Brief until this P0 is merged to `main`, bootstrapped, and cloud-accepted; then integrate Daily Market Brief into unified `main` and perform the one expected full image deployment for AKShare.
- Do not mark user acceptance accepted; Acceptance Testing remains the authority for that state.

---

### Task 1: Deployment Contract, Classification, and Service Targeting

**Files:**
- Create: `scripts/deploy_support.py`
- Create: `scripts/deploy_contract.py`
- Modify: `scripts/classify_deploy_change.py`
- Modify: `tests/test_deploy_change_classifier.py`

**Interfaces:**
- Produces: `CommandResult(returncode: int, stdout: str, stderr: str)`, `CommandRunner.run(command: tuple[str, ...], timeout: int | None = None) -> CommandResult`, and `SubprocessRunner` in `scripts.deploy_support`.
- Produces: `DeployMode`, `DeploymentPlan`, `classify_deployment(repo: Path, base_sha: str, target_sha: str, runner: CommandRunner) -> DeploymentPlan`, and `serialize_plan(plan: DeploymentPlan) -> dict[str, object]` in `scripts.deploy_contract`.
- `DeploymentPlan` fields are `mode`, `targets`, `changed_files`, `image_input_files`, and `reasons`; every tuple is sorted for deterministic API and test output.

- [ ] **Step 1: Write failing contract tests**

Add table-driven tests covering documentation-only, web-only, shared command logic, scheduler-only, dependency, runtime-only Compose, image-affecting Compose, and unknown control-plane files:

```python
from pathlib import Path
from unittest import TestCase

from scripts.deploy_contract import DeployMode, classify_paths


class DeployContractTests(TestCase):
    def test_classifies_known_paths_and_targets(self):
        cases = [
            (("docs/README.md",), DeployMode.NO_DEPLOY, ()),
            (("src/weekly_review_web.py",), DeployMode.TARGETED_QUICK, ("weekly-review-web",)),
            (("src/command_workbench.py",), DeployMode.TARGETED_QUICK, ("command-api", "weekly-review-web")),
            (("src/command_router.py",), DeployMode.TARGETED_QUICK, ("command-api", "dingtalk-stream-bot", "mcp", "weekly-review-web")),
            (("src/daily_market_brief.py",), DeployMode.TARGETED_QUICK, ("command-api", "dingtalk-stream-bot", "mcp", "weekly-review-web")),
            (("src/weekly_review.py",), DeployMode.TARGETED_QUICK, ("command-api", "dingtalk-stream-bot", "mcp", "weekly-review-web")),
            (("src/command_api_transport.py",), DeployMode.TARGETED_QUICK, ("command-api",)),
            (("src/mcp_server.py",), DeployMode.TARGETED_QUICK, ("mcp",)),
            (("src/account_snapshot_scheduler.py",), DeployMode.TARGETED_QUICK, ("account-snapshot-scheduler",)),
            (("src/new_runtime_module.py",), DeployMode.TARGETED_QUICK, ("account-snapshot-scheduler", "command-api", "dingtalk-stream-bot", "ipo-reminder-scheduler", "mcp", "weekly-review-web")),
            (("scripts/ecs_ops_api.py",), DeployMode.TARGETED_QUICK, ("investment-ops-api.service",)),
            (("requirements.txt",), DeployMode.FULL_IMAGE, ("account-snapshot-scheduler", "command-api", "dingtalk-stream-bot", "ipo-reminder-scheduler", "mcp", "weekly-review-web")),
            (("deploy/docker-compose.yml",), DeployMode.CONFIG_RESTART, ("account-snapshot-scheduler", "command-api", "dingtalk-stream-bot", "ipo-reminder-scheduler", "mcp", "weekly-review-web")),
        ]
        for paths, mode, targets in cases:
            with self.subTest(paths=paths):
                plan = classify_paths(paths, compose_image_changed=False)
                self.assertEqual(mode, plan.mode)
                self.assertEqual(targets, plan.targets)

    def test_unknown_deployment_control_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unclassified deployment-sensitive path"):
            classify_paths(("scripts/new_deploy_switch.py",), compose_image_changed=False)
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run: `.venv/bin/python -m unittest tests.test_deploy_change_classifier -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.deploy_contract'`.

- [ ] **Step 3: Implement focused support and contract modules**

Implement these exact public types and keep path rules in one ordered constant:

```python
class DeployMode(str, Enum):
    NO_DEPLOY = "no_deploy"
    TARGETED_QUICK = "targeted_quick"
    CONFIG_RESTART = "config_restart"
    FULL_IMAGE = "full_image"


@dataclass(frozen=True)
class DeploymentPlan:
    mode: DeployMode
    targets: tuple[str, ...]
    changed_files: tuple[str, ...]
    image_input_files: tuple[str, ...]
    reasons: tuple[str, ...]


def classify_paths(
    changed_files: Iterable[str], *, compose_image_changed: bool
) -> DeploymentPlan:
    """Return the smallest safe deterministic plan or raise on an unknown control path."""


def classify_deployment(
    repo: Path, base_sha: str, target_sha: str, runner: CommandRunner
) -> DeploymentPlan:
    """Read git diff and normalized Compose config at both SHAs, then classify."""
```

For Compose comparison, run `docker compose config --format json` against temporary files checked out with `git show <sha>:deploy/docker-compose.yml`, parse JSON, and compare each service's `image`, `build`, and `platform`. If those keys differ, return `full_image`; otherwise a Compose-only change returns `config_restart`. Unknown Python runtime paths conservatively target all application services under `targeted_quick`; unknown image/package paths return `full_image`; unknown documentation or deployment-control paths raise until an explicit rule is added. Control-plane scripts target their matching host systemd unit and share the global lock. Keep the CLI backward-compatible but emit JSON containing `mode`, `targets`, `changed_files`, `image_input_files`, and `reasons`.

- [ ] **Step 4: Add real-diff and normalized-Compose tests**

Use a fake `CommandRunner` that returns deterministic `git diff`, `git show`, and Compose JSON results. Assert that whitespace/environment-only Compose changes select `config_restart`, while an image/build/platform change selects `full_image`. Also assert mixed paths promote to the highest-risk mode and union all targets.

- [ ] **Step 5: Run the focused tests**

Run: `.venv/bin/python -m unittest tests.test_deploy_change_classifier -v`

Expected: all deployment classifier tests PASS.

- [ ] **Step 6: Commit the deployment contract**

```bash
git add scripts/deploy_support.py scripts/deploy_contract.py scripts/classify_deploy_change.py tests/test_deploy_change_classifier.py
git commit -m "feat: add deployment planning contract"
```

---

### Task 2: Production Source Policy and Durable Deployment State

**Files:**
- Create: `scripts/deploy_state.py`
- Create: `tests/test_deploy_state.py`

**Interfaces:**
- Consumes: `CommandRunner` from `scripts.deploy_support`.
- Produces: `DeploymentState`, `DeploymentEvent`, `load_state(path: Path) -> DeploymentState`, `write_state(path: Path, state: DeploymentState) -> None`, `write_event(events_dir: Path, event: DeploymentEvent) -> Path`, and `resolve_production_target(repo: Path, requested_ref: str, runner: CommandRunner) -> str`.

- [ ] **Step 1: Write source-policy and atomic-state tests**

```python
class DeployStateTests(TestCase):
    def test_resolves_main_to_origin_main_sha(self):
        runner = FakeRunner({("git", "-C", "/repo", "rev-parse", "origin/main"): ok("a" * 40), ("git", "-C", "/repo", "merge-base", "--is-ancestor", "a" * 40, "origin/main"): ok("")})
        self.assertEqual("a" * 40, resolve_production_target(Path("/repo"), "main", runner))

    def test_rejects_feature_branch_and_unreachable_sha(self):
        runner = FakeRunner({})
        with self.assertRaisesRegex(SourcePolicyError, "main or a 40-character SHA"):
            resolve_production_target(Path("/repo"), "feature/daily", runner)

    def test_state_round_trip_is_atomic_and_preserves_previous(self):
        path = self.directory / "deploy-state.json"
        state = sample_state(current_sha="b" * 40, previous_sha="a" * 40)
        write_state(path, state)
        self.assertEqual(state, load_state(path))
        self.assertFalse((self.directory / "deploy-state.json.tmp").exists())
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `.venv/bin/python -m unittest tests.test_deploy_state -v`

Expected: FAIL because `scripts.deploy_state` does not exist.

- [ ] **Step 3: Implement exact state schema and source checks**

```python
@dataclass(frozen=True)
class DeploymentState:
    schema_version: int
    current_sha: str | None
    previous_sha: str | None
    current_image: str | None
    previous_image: str | None
    active_release: str | None
    previous_release: str | None
    last_mode: str | None
    requested_ref: str | None
    resolved_ref: str | None
    targets: tuple[str, ...]
    last_event_id: str | None
    started_at: str | None
    completed_at: str | None
    preflight: dict[str, int | float | str]
    final_health: str | None

@dataclass(frozen=True)
class DeploymentEvent:
    event_id: str
    requested_mode: str
    computed_mode: str
    deployed_sha: str | None
    target_sha: str
    changed_image_inputs: tuple[str, ...]
    targets: tuple[str, ...]
    preflight: dict[str, int | float | str]
    archive_bytes: int | None
    image_count_before: int
    image_count_after: int
    disk_used_before: float
    disk_used_after: float
    target_durations_ms: dict[str, int]
    rollback_status: str
    cleanup_reclaimed_bytes: int
    emergency_override: bool
    emergency_reason: str | None
    final_health: str
    started_at: str
    completed_at: str


def resolve_production_target(repo: Path, requested_ref: str, runner: CommandRunner) -> str:
    if requested_ref == "main":
        sha = git(repo, runner, "rev-parse", "origin/main")
    elif re.fullmatch(r"[0-9a-f]{40}", requested_ref):
        sha = requested_ref
    else:
        raise SourcePolicyError("production ref must be main or a 40-character SHA")
    result = runner.run(("git", "-C", str(repo), "merge-base", "--is-ancestor", sha, "origin/main"))
    if result.returncode != 0:
        raise SourcePolicyError(f"{sha} is not reachable from origin/main")
    return sha
```

Write state JSON to a sibling temporary file, call `flush()` and `os.fsync()`, then `os.replace()` it into place. Write each event atomically to `/opt/investment-knowledge/shared/deploy-events/<event-id>.json`. Reject malformed state instead of silently erasing rollback information; never write secrets, raw environment values, or credentials.

- [ ] **Step 4: Run state tests**

Run: `.venv/bin/python -m unittest tests.test_deploy_state -v`

Expected: all state and source-policy tests PASS.

- [ ] **Step 5: Commit state handling**

```bash
git add scripts/deploy_state.py tests/test_deploy_state.py
git commit -m "feat: enforce production deploy source policy"
```

---

### Task 3: Deterministic Resource Preflight and Global Lock

**Files:**
- Create: `scripts/deploy_preflight.py`
- Create: `tests/test_deploy_preflight.py`

**Interfaces:**
- Consumes: `DeployMode` and `CommandRunner`.
- Produces: `ResourceSnapshot`, `PreflightResult`, `collect_resources(runner: CommandRunner) -> ResourceSnapshot`, `evaluate_preflight(snapshot: ResourceSnapshot, mode: DeployMode, archive_bytes: int | None) -> PreflightResult`, `validate_runtime(runner: CommandRunner, compose_file: Path) -> tuple[str, ...]`, and `deployment_lock(path: Path, timeout_seconds: int = 0)`.

- [ ] **Step 1: Write threshold tests at exact boundaries**

```python
class PreflightTests(TestCase):
    def test_quick_accepts_exact_minimums(self):
        snapshot = ResourceSnapshot(free_disk_bytes=8 * GIB, disk_used_percent=80.0, available_memory_bytes=512 * MIB)
        self.assertTrue(evaluate_preflight(snapshot, DeployMode.TARGETED_QUICK, None).ok)

    def test_full_requires_archive_headroom(self):
        snapshot = ResourceSnapshot(free_disk_bytes=5 * GIB, disk_used_percent=50.0, available_memory_bytes=2 * GIB)
        result = evaluate_preflight(snapshot, DeployMode.FULL_IMAGE, int(1.6 * GIB))
        self.assertFalse(result.ok)
        self.assertIn("full image requires", " ".join(result.errors))

    def test_lock_is_non_reentrant(self):
        with deployment_lock(self.lock_path):
            with self.assertRaisesRegex(DeployPreflightError, "another deployment is active"):
                with deployment_lock(self.lock_path):
                    pass
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `.venv/bin/python -m unittest tests.test_deploy_preflight -v`

Expected: FAIL because `scripts.deploy_preflight` does not exist.

- [ ] **Step 3: Implement preflight evaluation and runtime probes**

```python
GIB = 1024**3
MIB = 1024**2

@dataclass(frozen=True)
class ResourceSnapshot:
    free_disk_bytes: int
    disk_used_percent: float
    available_memory_bytes: int

@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    errors: tuple[str, ...]

def evaluate_preflight(snapshot, mode, archive_bytes):
    errors = []
    if snapshot.free_disk_bytes < 8 * GIB:
        errors.append("free disk must be at least 8 GiB")
    if snapshot.disk_used_percent > 80.0:
        errors.append("disk use must not exceed 80%")
    if snapshot.available_memory_bytes < 512 * MIB:
        errors.append("available memory must be at least 512 MiB")
    if mode is DeployMode.FULL_IMAGE:
        if archive_bytes is None:
            errors.append("full image requires a known archive size")
        elif snapshot.free_disk_bytes < archive_bytes * 2 + 2 * GIB:
            errors.append("full image requires twice the archive size plus 2 GiB free")
    return PreflightResult(not errors, tuple(errors))
```

`validate_runtime` must run Docker `info` with a 10-second timeout, `docker compose config --quiet`, `docker compose ps --status running postgres`, and a PostgreSQL health probe. Return successful probe labels; raise `DeployPreflightError` containing only product-safe messages and command exit codes, not credentials or environment dumps.

- [ ] **Step 4: Add fake-runner tests for Docker timeout, invalid Compose, and unhealthy PostgreSQL**

Assert each failure prevents deployment and produces one stable public error message. Assert no test error contains `password`, `token`, or the raw command environment.

- [ ] **Step 5: Run focused tests**

Run: `.venv/bin/python -m unittest tests.test_deploy_preflight -v`

Expected: all preflight tests PASS.

- [ ] **Step 6: Commit preflight support**

```bash
git add scripts/deploy_preflight.py tests/test_deploy_preflight.py
git commit -m "feat: add deployment resource preflight"
```

---

### Task 4: Managed Image and Release Retention

**Files:**
- Create: `scripts/deploy_retention.py`
- Create: `tests/test_deploy_retention.py`

**Interfaces:**
- Consumes: `DeploymentState` and `CommandRunner`.
- Produces: `ImageRecord`, `select_managed_images_for_removal(...) -> tuple[str, ...]`, `remove_managed_images(...) -> tuple[str, ...]`, and `retain_release_directories(releases_dir: Path, keep_shas: tuple[str, ...]) -> tuple[Path, ...]`.

- [ ] **Step 1: Write retention safety tests**

```python
class RetentionTests(TestCase):
    def test_keeps_current_previous_running_and_pgvector(self):
        images = (
            ImageRecord("id-current", "investment-knowledge-app:" + "c" * 40, 4),
            ImageRecord("id-previous", "investment-knowledge-app:" + "b" * 40, 3),
            ImageRecord("id-old", "investment-knowledge-app:" + "a" * 40, 2),
            ImageRecord("id-pg", "pgvector/pgvector:pg16", 1),
        )
        removable = select_managed_images_for_removal(images, current_image=images[0].tag, previous_image=images[1].tag, referenced_image_ids={"id-old"})
        self.assertEqual((), removable)

    def test_removes_only_unreferenced_old_managed_app_images(self):
        removable = select_managed_images_for_removal(self.images, current_image=self.current, previous_image=self.previous, referenced_image_ids=set())
        self.assertEqual(("id-old",), removable)
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `.venv/bin/python -m unittest tests.test_deploy_retention -v`

Expected: FAIL because `scripts.deploy_retention` does not exist.

- [ ] **Step 3: Implement explicit allow-list cleanup**

```python
MANAGED_IMAGE_RE = re.compile(r"^investment-knowledge-app:[0-9a-f]{40}$")

@dataclass(frozen=True)
class ImageRecord:
    image_id: str
    tag: str
    created_epoch: int

def select_managed_images_for_removal(images, *, current_image, previous_image, referenced_image_ids):
    protected_tags = {tag for tag in (current_image, previous_image) if tag}
    return tuple(
        image.image_id
        for image in sorted(images, key=lambda item: item.created_epoch)
        if MANAGED_IMAGE_RE.fullmatch(image.tag)
        and image.tag not in protected_tags
        and image.image_id not in referenced_image_ids
    )
```

Use `docker image rm <id>` only for selected IDs. Release retention may delete only SHA-named directories under the configured releases root and must preserve `current`, `previous`, candidate SHA, and any non-SHA directory. Remove uploaded image archives in a `finally` block on success and failure. The only permitted cache cleanup is `docker builder prune --filter until=168h --force` after a stable successful full deployment; do not invoke `docker image prune`, `docker system prune`, or `docker volume prune`.

- [ ] **Step 4: Add command-recording and filesystem boundary tests**

Assert the runner sees only `docker image rm` commands for allow-listed IDs and, when explicitly requested after a successful full deployment, the seven-day BuildKit cache command. Assert a symlink or path outside the releases root is not followed or deleted, and assert archive cleanup happens for both successful and failed loads.

- [ ] **Step 5: Run retention tests**

Run: `.venv/bin/python -m unittest tests.test_deploy_retention -v`

Expected: all retention tests PASS.

- [ ] **Step 6: Commit retention logic**

```bash
git add scripts/deploy_retention.py tests/test_deploy_retention.py
git commit -m "feat: bound deployment image retention"
```

---

### Task 5: Shared Deployment Engine, Sequential Activation, and Rollback

**Files:**
- Create: `scripts/deploy_release.py`
- Create: `tests/test_deploy_release.py`
- Modify: `scripts/deploy_from_local_checkout.sh`

**Interfaces:**
- Consumes: `DeploymentPlan`, `resolve_production_target`, preflight APIs, state APIs, retention APIs, and `CommandRunner`.
- Produces: `DeployRequest`, `DeployOutcome`, `DeploymentEngine.deploy(request: DeployRequest) -> DeployOutcome`, and CLI command `python3 scripts/deploy_release.py`.

- [ ] **Step 1: Write a successful targeted deployment orchestration test**

```python
class DeploymentEngineTests(TestCase):
    def test_targeted_deploy_recreates_only_planned_services_sequentially(self):
        request = DeployRequest(requested_ref="main", requested_mode=DeployMode.TARGETED_QUICK, requested_targets=("command-api", "weekly-review-web"), archive_path=None, emergency_reason=None)
        outcome = self.engine.deploy(request)
        self.assertTrue(outcome.ok)
        self.assertSubsequence([
            ("docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "command-api"),
            ("docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "weekly-review-web"),
        ], self.runner.commands)
        self.assertNotIn("postgres", outcome.activated_services)
```

- [ ] **Step 2: Write a rollback test before implementation**

```python
def test_health_failure_rolls_back_activated_services_in_reverse_order(self):
    self.health.fail_for("weekly-review-web")
    outcome = self.engine.deploy(self.targeted_request)
    self.assertFalse(outcome.ok)
    self.assertEqual(("weekly-review-web", "command-api"), outcome.rolled_back_services)
    self.assertEqual("a" * 40, load_state(self.state_path).current_sha)
```

- [ ] **Step 3: Run tests and confirm failure**

Run: `.venv/bin/python -m unittest tests.test_deploy_release -v`

Expected: FAIL because `scripts.deploy_release` does not exist.

- [ ] **Step 4: Implement request/outcome types and deployment sequence**

```python
@dataclass(frozen=True)
class DeployRequest:
    requested_ref: str
    requested_mode: DeployMode
    requested_targets: tuple[str, ...]
    archive_path: Path | None
    emergency_reason: str | None

@dataclass(frozen=True)
class DeployOutcome:
    ok: bool
    target_sha: str
    mode: DeployMode
    activated_services: tuple[str, ...]
    rolled_back_services: tuple[str, ...]
    message: str
```

Inside the global lock, execute in this order: fetch `origin/main`; resolve target; load deployed state; recompute the plan from `current_sha` to target; reject requested mode/targets that do not match; enforce emergency-reason rules; collect and evaluate resources; validate Docker, Compose, and PostgreSQL; stage `/opt/investment-knowledge/releases/<sha>`; validate release Compose config; snapshot the previous state; atomically repoint `current` while preserving `previous`; activate services sequentially with `--no-deps`; restart mapped host units independently when configured; run per-service health checks and a 30-second stability window for targeted/config deployments or 60 seconds for full; run aggregate PostgreSQL and route health; write successful state and event; remove only managed old images and releases. For `full_image`, verify the loaded immutable image tag exists before activation. On any activation or health failure, restore the previous release symlink and image tag, recreate already-touched services in reverse order, verify aggregate health, preserve previous durable state, and write a failed event including rollback status.

Target health rules are exact: `weekly-review-web` checks `/health`, `/weekly-review`, `/command`, plus feature routes supplied by the request; `command-api` checks health and an authenticated-route negative response; `mcp` checks its transport endpoint; schedulers and `dingtalk-stream-bot` must remain running through the stability window with no startup traceback or crash-loop signal; PostgreSQL must remain healthy throughout. If rollback health fails, persist `rollback_failed`, leave the global deployment lockout marker in place, and return manual recovery data limited to current release, image, container status, disk, and memory.

- [ ] **Step 5: Convert the shell script to a compatibility wrapper**

Keep accepted environment variables for existing callers, but make the shell script execute only the shared Python CLI:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$(dirname "$0")/deploy_release.py" \
  --ref "${DEPLOY_REF:-main}" \
  --mode "${DEPLOY_MODE:-targeted_quick}" \
  ${DEPLOY_TARGETS:+--targets "$DEPLOY_TARGETS"} \
  ${DEPLOY_ARCHIVE:+--archive "$DEPLOY_ARCHIVE"} \
  ${DEPLOY_EMERGENCY_REASON:+--emergency-reason "$DEPLOY_EMERGENCY_REASON"}
```

Build CLI arguments as a Bash array in the final implementation so empty optional values are omitted safely.

- [ ] **Step 6: Add tests for no-deploy, config restart, full image, mismatched plan, emergency override, and PostgreSQL immutability**

Assert `no_deploy` issues no Compose mutation; `config_restart` uses the current immutable image; a valid full uses `<target-sha>`; a mismatched client plan is rejected; a reason shorter than 20 characters is rejected; feature refs are rejected even with a valid reason; and no command contains `force-recreate postgres`, `rm postgres`, or `down`. Assert target and aggregate health checks, 30/60-second stability windows through an injected clock, event timing fields, archive cleanup on success and failure, candidate-image removal only when unreferenced, and persistent lockout after `rollback_failed`.

- [ ] **Step 7: Run engine and existing deployment tests**

Run: `.venv/bin/python -m unittest tests.test_deploy_release tests.test_deploy_change_classifier tests.test_deploy_preflight tests.test_deploy_retention tests.test_deploy_state -v`

Expected: all tests PASS.

- [ ] **Step 8: Commit the shared deployment engine**

```bash
git add scripts/deploy_release.py scripts/deploy_from_local_checkout.sh tests/test_deploy_release.py
git commit -m "feat: add transactional deployment engine"
```

---

### Task 6: ECS Ops API as the Daily Deployment Control Plane

**Files:**
- Modify: `scripts/ecs_ops_api.py`
- Modify: `tests/test_ecs_ops_api.py`
- Modify: `scripts/install_ecs_ops_api.sh`
- Modify: `scripts/bootstrap_ecs_ops_api.sh`

**Interfaces:**
- Consumes: `DeploymentEngine`, `DeployRequest`, `DeploymentPlan`, `serialize_plan`, and `ResourceSnapshot`.
- Produces: `POST /deploy` accepting `ref`, `mode`, `targets`, `emergency_reason`, and optional full-image archive metadata; `GET /deploy/status` exposing sanitized current/previous SHA, active mode, targets, resource thresholds, and last outcome.

- [ ] **Step 1: Replace legacy quick/full API tests with four-mode contract tests**

```python
def test_deploy_recomputes_plan_and_dispatches_shared_engine(self):
    response = self.client.post("/deploy", json={"ref": "main", "mode": "targeted_quick", "targets": ["weekly-review-web"]})
    self.assertEqual(202, response.status_code)
    self.assertEqual(DeployMode.TARGETED_QUICK, self.engine.requests[0].requested_mode)

def test_feature_ref_is_rejected_before_worker_dispatch(self):
    response = self.client.post("/deploy", json={"ref": "feature/daily", "mode": "full_image", "emergency_reason": "urgent production repair with evidence"})
    self.assertEqual(400, response.status_code)
    self.assertEqual([], self.engine.requests)
```

- [ ] **Step 2: Run API tests and confirm contract failures**

Run: `.venv/bin/python -m unittest tests.test_ecs_ops_api -v`

Expected: FAIL because the API still accepts only legacy `quick`/`full` and calls the shell deploy path directly.

- [ ] **Step 3: Inject the deployment engine and sanitize responses**

Remove the duplicate local `CommandResult` in favor of `scripts.deploy_support.CommandResult`. Parse mode with `DeployMode(payload["mode"])`, normalize targets to a sorted tuple, resolve source policy before starting a worker, and pass one `DeployRequest` to the shared engine. Return `409` when a deployment lock is active, `422` for plan mismatch or preflight rejection, and `500` only for unexpected internal errors. User-visible responses may include stable error codes and thresholds but must not include raw subprocess stderr, SSL internals, tokens, passwords, or environment values.

- [ ] **Step 4: Update service installation defaults**

Set `OPS_DEPLOY_ALLOWED_REFS=main`, state path `/opt/investment-knowledge/shared/deploy-state.json`, lock path `/opt/investment-knowledge/shared/deploy.lock`, release root `/opt/investment-knowledge/releases`, and a request timeout that permits a controlled full deployment without letting concurrent requests start.

- [ ] **Step 5: Add status and rejection tests**

Assert status includes current and previous SHA, resource snapshot, deployment mode, target list, and sanitized last failure. Assert API-requested full without image diff is rejected unless the emergency reason is at least 20 characters, and still rejects an unreachable SHA.

- [ ] **Step 6: Run API and engine tests**

Run: `.venv/bin/python -m unittest tests.test_ecs_ops_api tests.test_deploy_release -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit Ops API integration**

```bash
git add scripts/ecs_ops_api.py tests/test_ecs_ops_api.py scripts/install_ecs_ops_api.sh scripts/bootstrap_ecs_ops_api.sh
git commit -m "feat: route ops deploys through shared engine"
```

---

### Task 7: Immutable GitHub Full Deploy and Workflow Contract

**Files:**
- Modify: `.github/workflows/deploy.yml`
- Create: `tests/test_deploy_workflow_contract.py`

**Interfaces:**
- Consumes: classifier JSON and `scripts/deploy_release.py` CLI.
- Produces: GitHub jobs that skip `no_deploy`, delegate routine targeted/config deployments to the shared contract, and build/upload only the immutable application image for `full_image`.

- [ ] **Step 1: Write text-level workflow safety tests**

```python
class DeployWorkflowContractTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = Path(".github/workflows/deploy.yml").read_text()

    def test_uses_immutable_sha_image_and_build_cache(self):
        self.assertIn("investment-knowledge-app:${{ github.sha }}", self.workflow)
        self.assertIn("cache-from: type=gha", self.workflow)
        self.assertIn("cache-to: type=gha,mode=max", self.workflow)

    def test_does_not_bundle_pgvector_or_use_broad_prune(self):
        self.assertNotIn("docker save pgvector", self.workflow)
        self.assertNotIn("docker system prune", self.workflow)
        self.assertNotIn("docker volume prune", self.workflow)

    def test_runs_remote_preflight_before_archive_upload(self):
        self.assertLess(self.workflow.index("deploy_preflight.py"), self.workflow.index("scp-action"))
```

- [ ] **Step 2: Run workflow tests and confirm failure**

Run: `.venv/bin/python -m unittest tests.test_deploy_workflow_contract -v`

Expected: FAIL because the workflow uses mutable `prod`, bundles pgvector, and uploads before the new preflight.

- [ ] **Step 3: Rewrite workflow around the shared plan**

Use one classification job that fetches the deployed SHA from the Ops status endpoint and emits serialized plan outputs. A `no_deploy` result exits after validation. `targeted_quick` and `config_restart` call the Ops API with the exact target SHA, mode, and targets. `full_image` must run a remote resource preflight first, build `investment-knowledge-app:${{ github.sha }}` with `docker/build-push-action@v6`, `load: true`, `cache-from: type=gha`, and `cache-to: type=gha,mode=max`, save and gzip only that application image, upload it, then invoke the shared engine for the same SHA. Pin third-party action major versions already approved by the repository; do not introduce a registry or paid cache service.

- [ ] **Step 4: Add workflow dispatch safety**

Keep manual dispatch but allow only `main` or a 40-character SHA. Add optional `emergency_reason`; pass it only for a manually requested full deployment. The server remains authoritative and rejects unreachable SHAs, plan mismatches, inadequate reasons, or insufficient resources.

- [ ] **Step 5: Run workflow and classifier contract tests**

Run: `.venv/bin/python -m unittest tests.test_deploy_workflow_contract tests.test_deploy_change_classifier -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit workflow optimization**

```bash
git add .github/workflows/deploy.yml tests/test_deploy_workflow_contract.py
git commit -m "ci: optimize production deployment workflow"
```

---

### Task 8: Documentation, Local Verification, Controlled Rollout, and Cloud Acceptance

**Files:**
- Modify: `docs/project-management/Deploy-Classification.md`
- Modify: `docs/techplans/cloud-pull-deploy-plan.md`
- Modify: `DEPLOYMENT.md`
- Modify: `docs/superpowers/specs/2026-07-10-deploy-flow-optimization-design.md` only if implementation revealed a necessary design correction.

**Interfaces:**
- Consumes: all deployment commands and status fields implemented above.
- Produces: an operator runbook with exact commands, rollback interpretation, disk/image audit commands, and the gate for resuming Daily Market Brief delivery.

- [ ] **Step 1: Update operator documentation with the exact mode matrix**

Document all four modes, path-to-service mapping, source policy, preflight thresholds, immutable image naming, current/previous retention, full-deploy emergency rule, PostgreSQL immutability, and product-safe error behavior. Include these read-only audit commands:

```bash
df -h /
free -m
docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
curl -fsS http://127.0.0.1:8765/deploy/status | python3 -m json.tool
```

- [ ] **Step 2: Document the two-stage rollout**

Stage 1 merges only deploy-flow P0 to `main`, installs/updates the Ops API, records baseline disk/image/container/PostgreSQL identity, and validates one no-op plus one narrow quick deployment. Stage 2 runs the cloud acceptance matrix below. Daily Market Brief remains blocked until both stages pass; only then is its branch rebased or cherry-picked onto unified `main` and deployed once with `full_image` for AKShare.

- [ ] **Step 3: Run repository preflight and focused test suite**

Run:

```bash
.venv/bin/python scripts/agent_preflight.py
.venv/bin/python -m unittest \
  tests.test_deploy_change_classifier \
  tests.test_deploy_state \
  tests.test_deploy_preflight \
  tests.test_deploy_retention \
  tests.test_deploy_release \
  tests.test_ecs_ops_api \
  tests.test_deploy_workflow_contract -v
python3 scripts/audit_delivery_state.py
git diff --check
```

Expected: preflight succeeds, all focused tests PASS, delivery-state audit reports no newly introduced inconsistency, and `git diff --check` is silent.

- [ ] **Step 4: Run the complete automated test suite**

Run: `.venv/bin/python -m unittest discover -s tests -v`

Expected: all tests PASS. If an unrelated pre-existing failure exists, capture its exact test name and reproduce it on `origin/main` before treating it as non-blocking.

- [ ] **Step 5: Commit documentation and verification updates**

```bash
git add DEPLOYMENT.md docs/project-management/Deploy-Classification.md docs/techplans/cloud-pull-deploy-plan.md docs/superpowers/specs/2026-07-10-deploy-flow-optimization-design.md
git commit -m "docs: publish optimized deploy runbook"
```

- [ ] **Step 6: Request code review before production rollout**

Use `superpowers:requesting-code-review` against the implementation branch. Resolve correctness findings, rerun focused and complete suites, and merge the reviewed implementation to `main` before touching production.

- [ ] **Step 7: Bootstrap P0 on ECS without deploying Daily Market Brief**

Record the current PostgreSQL container ID and image ID, managed app image count, root disk percentage, and current route health. Deploy the P0 control-plane commit from `main`; confirm the Ops status endpoint reports the same SHA and valid resource snapshot. Stop and roll back if disk exceeds 80%, memory falls below 512 MiB available, PostgreSQL identity changes, or any required route fails.

- [ ] **Step 8: Execute cloud acceptance matrix**

Perform three independently triggered `targeted_quick` deployments whose diffs affect narrow service sets. After each, verify completion under 60 seconds, unchanged managed app image count, unchanged PostgreSQL container/image identity, and healthy required routes. Perform one controlled `full_image`; verify the final managed application image set contains at most current and previous SHA tags, pgvector remains present, root disk use is below 70%, all application services are healthy, and rollback state names the immediately previous SHA.

- [ ] **Step 9: Resume Daily Market Brief only after P0 acceptance**

Integrate Daily Market Brief onto the accepted `main`, let the classifier prove `full_image` is required by the AKShare dependency diff, perform that single controlled full deployment, and dispatch Acceptance Testing for the Daily page and live/degraded data behavior. Do not mark acceptance accepted from the coordinator role.

- [ ] **Step 10: Record final delivery evidence**

Update the existing delivery queue, feature registry, acceptance queue, and Daily Market Brief tech plan with branch, commit, deployment mode, duration, image count, disk percentage, PostgreSQL identity check, route checks, and Acceptance Testing owner. Do not create a routine daily log.

---

## Implementation Completion Criteria

- Every production deployment is planned from the durable deployed SHA to a target reachable from `origin/main`.
- Routine source changes recreate only mapped application services and complete in under 60 seconds in cloud acceptance.
- Compose runtime changes use `config_restart`; only image-input changes or a documented emergency use `full_image`.
- Full deployment transfers only the immutable application image, retains at most current and previous managed app images, and never bundles or removes pgvector.
- Resource checks and the global lock reject unsafe or concurrent deployments before large transfer or service mutation.
- Failed activation restores the previous release and service set without recreating PostgreSQL.
- Three quick cloud deployments produce no image-count growth; one controlled full leaves root disk below 70% and all required routes healthy.
- Daily Market Brief remains blocked until deploy-flow P0 passes review and cloud acceptance, then follows the shared deployment and Acceptance Testing flow.
