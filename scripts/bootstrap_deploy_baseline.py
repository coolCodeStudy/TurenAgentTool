from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager, Protocol

try:
    from scripts.deploy_contract import (
        APPLICATION_SERVICES,
        OBSOLETE_APPLICATION_SERVICES,
    )
    from scripts.deploy_preflight import deployment_lock, validate_runtime
    from scripts.deploy_release import (
        DeploymentEngine,
        DeploymentError,
        SelectorSnapshot,
        SystemClock,
        _compose_service_from_row,
        _compose_environment,
        _json_rows,
    )
    from scripts.deploy_state import (
        DeploymentState,
        load_state,
        resolve_historical_production_target,
        write_state,
    )
    from scripts.deploy_support import CommandRunner, SubprocessRunner
except ModuleNotFoundError:  # Direct execution through scripts/bootstrap_deploy_baseline.py.
    from deploy_contract import APPLICATION_SERVICES, OBSOLETE_APPLICATION_SERVICES
    from deploy_preflight import deployment_lock, validate_runtime
    from deploy_release import (
        DeploymentEngine,
        DeploymentError,
        SelectorSnapshot,
        SystemClock,
        _compose_service_from_row,
        _compose_environment,
        _json_rows,
    )
    from deploy_state import (
        DeploymentState,
        load_state,
        resolve_historical_production_target,
        write_state,
    )
    from deploy_support import CommandRunner, SubprocessRunner


class BaselineClock(Protocol):
    def now(self) -> datetime: ...


ReleaseStager = Callable[[str], Path]
RuntimeValidator = Callable[[CommandRunner, Path], tuple[str, ...]]
LockFactory = Callable[[Path], ContextManager[None]]
RunningServicesProvider = Callable[[], frozenset[str]]
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_APPLICATION_SERVICES = frozenset(
    (*APPLICATION_SERVICES, *OBSOLETE_APPLICATION_SERVICES)
)


class _UnusedHealth:
    def check_service(self, service: str, feature_routes: tuple[str, ...]) -> None:
        raise AssertionError("baseline initialization must not restart services")

    def check_aggregate(
        self,
        feature_routes: tuple[str, ...],
        *,
        services: frozenset[str] | None = None,
    ) -> None:
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
    resolved_sha = resolve_historical_production_target(repo, legacy_sha, runner)
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


def recover_lockout(
    *,
    repo: Path,
    app_root: Path,
    runner: CommandRunner,
    compose_project_name: str,
    runtime_validator: RuntimeValidator = validate_runtime,
    lock_factory: LockFactory = deployment_lock,
    running_services_provider: RunningServicesProvider | None = None,
) -> tuple[str, ...]:
    shared_dir = app_root / "shared"
    lockout_path = shared_dir / "deploy.lockout"
    shared_dir.mkdir(parents=True, exist_ok=True)
    with lock_factory(shared_dir / "deploy.lock"):
        expected_services = _lockout_services(lockout_path)
        state = load_state(shared_dir / "deploy-state.json")
        engine = DeploymentEngine(
            repo=repo,
            app_root=app_root,
            runner=runner,
            health=_UnusedHealth(),
            clock=SystemClock(),
            compose_project_name=compose_project_name,
        )
        _validate_existing_baseline(app_root, state)
        selectors = SelectorSnapshot(
            current_release=engine._resolved_link(engine.current_link),
            previous_release=engine._resolved_link(engine.previous_link),
            env_contents=engine.env_file.read_bytes() if engine.env_file.exists() else None,
        )
        engine._verify_release_baseline(state, selectors)
        with _compose_environment(compose_project_name):
            runtime_validator(runner, engine.current_link / "docker-compose.prod.yml")
            running_services = (
                running_services_provider()
                if running_services_provider is not None
                else _running_compose_services(runner, engine.current_link)
            )
            expected_baseline_services = expected_services
            if running_services_provider is None:
                baseline_services = frozenset(
                    engine._compose_services(selectors.current_release)
                )
                residual_services = frozenset(
                    (expected_services & running_services) - baseline_services
                )
                unsafe_residuals = residual_services - _APPLICATION_SERVICES
                if unsafe_residuals:
                    raise DeploymentError(
                        "deployment lockout recovery found non-application residual "
                        "services: " + ", ".join(sorted(unsafe_residuals))
                    )
                for service in sorted(residual_services):
                    _remove_residual_service(
                        runner,
                        compose_project_name=compose_project_name,
                        service=service,
                    )
                if residual_services:
                    running_services = _running_compose_services(
                        runner, engine.current_link
                    )
                expected_baseline_services = expected_services & baseline_services
        engine._verify_baseline_image_identity(state, selectors)
        missing = sorted(set(expected_baseline_services) - set(running_services))
        if missing:
            raise DeploymentError(
                "deployment lockout recovery is blocked by missing services: "
                + ", ".join(missing)
            )
        lockout_path.unlink()
        return tuple(sorted(expected_baseline_services))


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
        if (
            str(row.get("Image") or "").startswith("investment-knowledge-app:")
            or _compose_service_from_row(row) in _APPLICATION_SERVICES
        ):
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


def _lockout_services(lockout_path: Path) -> frozenset[str]:
    try:
        payload = json.loads(lockout_path.read_text(encoding="ascii"))
        rows = json.loads(payload["container_status"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise DeploymentError("deployment lockout recovery evidence is unavailable") from error
    if not isinstance(rows, list):
        raise DeploymentError("deployment lockout recovery evidence is invalid")
    services = {
        str(row.get("Service") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("State") or "") == "running"
    }
    services.discard("")
    if "postgres" not in services or not (services & _APPLICATION_SERVICES):
        raise DeploymentError("deployment lockout recovery evidence is incomplete")
    return frozenset(services)


def _running_compose_services(
    runner: CommandRunner, current_link: Path
) -> frozenset[str]:
    result = runner.run(
        (
            "docker",
            "compose",
            "-f",
            str(current_link / "docker-compose.prod.yml"),
            "ps",
            "--status",
            "running",
            "--format",
            "json",
        )
    )
    if result.returncode != 0:
        raise DeploymentError("running service recovery state could not be read")
    return frozenset(
        str(row.get("Service") or "")
        for row in _json_rows(result.stdout)
        if str(row.get("Service") or "")
    )


def _remove_residual_service(
    runner: CommandRunner, *, compose_project_name: str, service: str
) -> None:
    result = runner.run(
        (
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={compose_project_name}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        )
    )
    container_ids = tuple(result.stdout.split())
    if result.returncode != 0 or not container_ids:
        raise DeploymentError(
            f"residual application service {service} could not be identified"
        )
    _run_checked(
        runner,
        ("docker", "rm", "--force", *container_ids),
        f"residual application service {service} could not be removed",
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
    parser.add_argument("--recover-lockout", action="store_true")
    args = parser.parse_args()
    if args.recover_lockout:
        services = recover_lockout(
            repo=args.repo,
            app_root=args.app_root,
            runner=SubprocessRunner(),
            compose_project_name=args.compose_project_name,
        )
        print(json.dumps({"ok": True, "recovered_services": list(services)}))
        return 0
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
