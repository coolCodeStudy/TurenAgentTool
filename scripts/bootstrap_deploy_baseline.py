from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager, Protocol

try:
    from scripts.deploy_preflight import deployment_lock, validate_runtime
    from scripts.deploy_release import (
        DeploymentEngine,
        DeploymentError,
        SelectorSnapshot,
        SystemClock,
        _compose_environment,
    )
    from scripts.deploy_state import DeploymentState, load_state, resolve_production_target, write_state
    from scripts.deploy_support import CommandRunner, SubprocessRunner
except ModuleNotFoundError:  # Direct execution through scripts/bootstrap_deploy_baseline.py.
    from deploy_preflight import deployment_lock, validate_runtime
    from deploy_release import (
        DeploymentEngine,
        DeploymentError,
        SelectorSnapshot,
        SystemClock,
        _compose_environment,
    )
    from deploy_state import DeploymentState, load_state, resolve_production_target, write_state
    from deploy_support import CommandRunner, SubprocessRunner


class BaselineClock(Protocol):
    def now(self) -> datetime: ...


ReleaseStager = Callable[[str], Path]
RuntimeValidator = Callable[[CommandRunner, Path], tuple[str, ...]]
LockFactory = Callable[[Path], ContextManager[None]]
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


class _UnusedHealth:
    def check_service(self, service: str, feature_routes: tuple[str, ...]) -> None:
        raise AssertionError("baseline initialization must not restart services")

    def check_aggregate(self, feature_routes: tuple[str, ...]) -> None:
        raise AssertionError("baseline initialization must not restart services")


def initialize_baseline(
    *,
    repo: Path,
    app_root: Path,
    runner: CommandRunner,
    clock: BaselineClock,
    compose_project_name: str,
    release_stager: ReleaseStager | None = None,
    runtime_validator: RuntimeValidator = validate_runtime,
    lock_factory: LockFactory = deployment_lock,
) -> DeploymentState:
    shared_dir = app_root / "shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    with lock_factory(shared_dir / "deploy.lock"):
        return _initialize_locked(
            repo=repo,
            app_root=app_root,
            runner=runner,
            clock=clock,
            compose_project_name=compose_project_name,
            release_stager=release_stager,
            runtime_validator=runtime_validator,
        )


def _initialize_locked(
    *,
    repo: Path,
    app_root: Path,
    runner: CommandRunner,
    clock: BaselineClock,
    compose_project_name: str,
    release_stager: ReleaseStager | None,
    runtime_validator: RuntimeValidator,
) -> DeploymentState:
    state_path = app_root / "shared" / "deploy-state.json"
    if (app_root / "shared" / "deploy.lockout").exists():
        raise DeploymentError("deployment is locked out pending manual recovery")
    engine = DeploymentEngine(
        repo=repo,
        app_root=app_root,
        runner=runner,
        health=_UnusedHealth(),
        clock=SystemClock(),
        compose_project_name=compose_project_name,
    )
    if state_path.exists():
        state = load_state(state_path)
        _validate_existing_baseline(app_root, state)
        selectors = SelectorSnapshot(
            current_release=engine._resolved_link(engine.current_link),
            previous_release=engine._resolved_link(engine.previous_link),
            env_contents=engine.env_file.read_bytes() if engine.env_file.exists() else None,
        )
        engine._verify_release_baseline(state, selectors)
        with _compose_environment(compose_project_name):
            runtime_validator(runner, engine.current_link / "docker-compose.prod.yml")
        engine._verify_baseline_image_identity(state, selectors)
        return state

    legacy_sha = _deployed_sha(app_root, runner)
    resolved_sha = resolve_production_target(repo, legacy_sha, runner)
    if resolved_sha != legacy_sha:
        raise DeploymentError("legacy deployment commit resolution changed unexpectedly")

    release = (release_stager or engine._stage_release)(legacy_sha)
    image_id = _running_application_image_id(runner, compose_project_name)
    immutable_image = f"investment-knowledge-app:{legacy_sha}"
    old_env = engine.env_file.read_bytes() if engine.env_file.exists() else None
    old_current = engine._resolved_link(engine.current_link)
    created_tag = _ensure_immutable_tag(runner, image_id, immutable_image)
    try:
        engine._write_image_tag(immutable_image)
        engine._replace_symlink(engine.current_link, release)
        with _compose_environment(compose_project_name):
            labels = runtime_validator(runner, engine.current_link / "docker-compose.prod.yml")
        timestamp = clock.now().astimezone(timezone.utc).isoformat()
        state = DeploymentState(
            schema_version=1,
            current_sha=legacy_sha,
            previous_sha=None,
            current_image=immutable_image,
            previous_image=None,
            active_release=str(release),
            previous_release=None,
            last_mode="baseline_bootstrap",
            requested_ref=legacy_sha,
            resolved_ref=legacy_sha,
            targets=(),
            last_event_id=None,
            started_at=timestamp,
            completed_at=timestamp,
            preflight={
                "source_valid": "valid",
                **engine._runtime_observations(labels),
            },
            final_health="baseline_verified",
        )
        selectors = SelectorSnapshot(
            current_release=engine._resolved_link(engine.current_link),
            previous_release=engine._resolved_link(engine.previous_link),
            env_contents=engine.env_file.read_bytes(),
        )
        engine._verify_release_baseline(state, selectors)
        engine._verify_baseline_image_identity(state, selectors)
        write_state(state_path, state)
        return state
    except Exception as error:
        rollback_errors = _rollback_baseline(
            engine=engine,
            runner=runner,
            old_env=old_env,
            old_current=old_current,
            immutable_image=immutable_image,
            created_tag=created_tag,
        )
        if rollback_errors:
            _write_lockout(engine, old_current, rollback_errors)
            raise DeploymentError(
                "baseline initialization failed and rollback was incomplete"
            ) from error
        raise


def _deployed_sha(app_root: Path, runner: CommandRunner) -> str:
    current_link = app_root / "current"
    releases_root = app_root / "releases"
    if current_link.is_symlink():
        try:
            current_release = current_link.resolve(strict=True)
            resolved_releases = releases_root.resolve(strict=True)
        except OSError as error:
            raise DeploymentError("active legacy release link is unavailable") from error
        if (
            current_release.is_dir()
            and current_release.parent == resolved_releases
            and _SHA_PATTERN.fullmatch(current_release.name)
        ):
            return current_release.name
        raise DeploymentError("active legacy release link is outside the managed release root")

    return _legacy_checkout_sha(app_root, runner)


def _validate_existing_baseline(app_root: Path, state: DeploymentState) -> None:
    if not state.current_sha or not state.active_release or not state.current_image:
        raise DeploymentError("existing deployment state does not identify an active baseline")
    try:
        current_release = (app_root / "current").resolve(strict=True)
        durable_release = Path(state.active_release).resolve(strict=True)
        releases_root = (app_root / "releases").resolve(strict=True)
    except OSError as error:
        raise DeploymentError("existing deployment baseline is unavailable") from error
    if (
        current_release != durable_release
        or current_release.parent != releases_root
        or current_release.name != state.current_sha
    ):
        raise DeploymentError("existing deployment state and active release do not match")


def _legacy_checkout_sha(app_root: Path, runner: CommandRunner) -> str:
    result = runner.run(("git", "-C", str(app_root), "rev-parse", "HEAD"))
    sha = result.stdout.strip()
    if result.returncode != 0 or not _SHA_PATTERN.fullmatch(sha):
        raise DeploymentError("legacy deployment commit could not be identified")
    dirty = runner.run(
        ("git", "-C", str(app_root), "status", "--porcelain", "--untracked-files=no")
    )
    if dirty.returncode != 0 or dirty.stdout.strip():
        raise DeploymentError("legacy deployment has tracked source changes")
    return sha


def _running_application_image_id(
    runner: CommandRunner, compose_project_name: str
) -> str:
    result = runner.run(
        (
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={compose_project_name}",
            "--format",
            "{{json .}}",
        )
    )
    if result.returncode != 0:
        raise DeploymentError("running application containers could not be inspected")
    rows = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise DeploymentError("running application container metadata is invalid") from error
        if str(row.get("Image") or "").startswith("investment-knowledge-app:"):
            rows.append(row)
    if not rows:
        raise DeploymentError("running application image baseline is unavailable")

    image_ids: set[str] = set()
    for row in rows:
        container_id = str(row.get("ID") or "")
        if not container_id:
            raise DeploymentError("running application container identity is unavailable")
        inspected = runner.run(("docker", "inspect", "--format", "{{.Image}}", container_id))
        image_id = inspected.stdout.strip()
        if inspected.returncode != 0 or not image_id:
            raise DeploymentError("running application image identity is unavailable")
        image_ids.add(image_id)
    if len(image_ids) != 1:
        raise DeploymentError("running application containers do not share one image baseline")
    return next(iter(image_ids))


def _ensure_immutable_tag(
    runner: CommandRunner, image_id: str, immutable_image: str
) -> bool:
    inspected = runner.run(
        ("docker", "image", "inspect", "--format", "{{.Id}}", immutable_image)
    )
    existing_id = inspected.stdout.strip()
    if inspected.returncode == 0 and existing_id:
        if existing_id != image_id:
            raise DeploymentError("immutable baseline image tag already points elsewhere")
        return False
    _run_checked(
        runner,
        ("docker", "image", "tag", image_id, immutable_image),
        "legacy application image could not be tagged immutably",
    )
    return True


def _rollback_baseline(
    *,
    engine: DeploymentEngine,
    runner: CommandRunner,
    old_env: bytes | None,
    old_current: Path | None,
    immutable_image: str,
    created_tag: bool,
) -> tuple[str, ...]:
    errors: list[str] = []
    for label, restore in (
        ("environment", lambda: engine._restore_env(old_env)),
        ("current_release", lambda: engine._restore_link(engine.current_link, old_current)),
    ):
        try:
            restore()
        except Exception:
            errors.append(label)
    if created_tag:
        result = runner.run(("docker", "image", "rm", immutable_image))
        if result.returncode != 0:
            errors.append("image_tag")
    return tuple(errors)


def _write_lockout(
    engine: DeploymentEngine, old_current: Path | None, errors: tuple[str, ...]
) -> None:
    payload = {
        "current_release": str(old_current or "unknown"),
        "current_image": "unknown",
        "container_status": json.dumps({"rollback_errors": list(errors)}, sort_keys=True),
        "disk": json.dumps({"available_bytes": "unknown", "used_percent": "unknown"}),
        "memory": json.dumps({"available_bytes": "unknown"}),
    }
    engine.lockout_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="ascii",
    )


def _run_checked(
    runner: CommandRunner, command: tuple[str, ...], message: str
) -> None:
    result = runner.run(command)
    if result.returncode != 0:
        raise DeploymentError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize immutable deploy state from a legacy ECS checkout.")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--compose-project-name", default="turenagenttool_prod")
    args = parser.parse_args()
    state = initialize_baseline(
        repo=args.repo,
        app_root=args.app_root,
        runner=SubprocessRunner(),
        clock=SystemClock(),
        compose_project_name=args.compose_project_name,
    )
    print(json.dumps({"ok": True, "current_sha": state.current_sha, "mode": state.last_mode}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
