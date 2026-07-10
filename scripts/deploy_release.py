from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tarfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

try:
    from scripts.deploy_contract import APPLICATION_SERVICES, DeployMode, DeploymentPlan, classify_deployment
    from scripts.deploy_preflight import (
        ResourceSnapshot,
        collect_resources,
        deployment_lock,
        evaluate_preflight,
        validate_runtime,
    )
    from scripts.deploy_retention import (
        ImageRecord,
        load_image_archive,
        remove_managed_images,
        retain_release_directories,
    )
    from scripts.deploy_state import (
        DeploymentEvent,
        DeploymentState,
        load_state,
        resolve_production_target,
        write_event,
        write_state,
    )
    from scripts.deploy_support import CommandRunner, SubprocessRunner
except ModuleNotFoundError:  # Direct execution through scripts/deploy_release.py.
    from deploy_contract import APPLICATION_SERVICES, DeployMode, DeploymentPlan, classify_deployment
    from deploy_preflight import (
        ResourceSnapshot,
        collect_resources,
        deployment_lock,
        evaluate_preflight,
        validate_runtime,
    )
    from deploy_retention import ImageRecord, load_image_archive, remove_managed_images, retain_release_directories
    from deploy_state import (
        DeploymentEvent,
        DeploymentState,
        load_state,
        resolve_production_target,
        write_event,
        write_state,
    )
    from deploy_support import CommandRunner, SubprocessRunner


class DeploymentError(RuntimeError):
    """A product-safe deployment failure."""


class DeploymentHealthError(DeploymentError):
    """Raised when a target or aggregate health gate fails."""


_SENSITIVE_REASON = re.compile(
    r"(?i)(?:\b(?:token|password|passwd|secret|credential|authorization|api[_-]?key)\b|"
    r"\b[A-Za-z_][A-Za-z0-9_]*\s*=|[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s@]+@)"
)
_APPLICATION_TARGETS = set(APPLICATION_SERVICES) | {"dingtalk-api"}


class HealthChecker(Protocol):
    def check_service(self, service: str, feature_routes: tuple[str, ...]) -> None: ...

    def check_aggregate(self, feature_routes: tuple[str, ...]) -> None: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...

    def now(self) -> datetime: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class DockerHealthChecker:
    _PROCESS_SERVICES = {
        "account-snapshot-scheduler",
        "ipo-reminder-scheduler",
        "dingtalk-stream-bot",
    }

    def __init__(
        self,
        runner: CommandRunner,
        current_release: Path,
        compose_project_name: str = "turenagenttool_prod",
    ) -> None:
        self.runner = runner
        self.current_release = current_release
        self.compose_project_name = compose_project_name

    def check_service(self, service: str, feature_routes: tuple[str, ...]) -> None:
        if service.endswith(".service"):
            self._checked(("systemctl", "is-active", "--quiet", service), f"host unit {service} is not active")
            return
        self._check_running(service)
        if service == "weekly-review-web":
            for route in ("/health", "/weekly-review", "/command", *feature_routes):
                self._http_success(f"http://127.0.0.1:8010{route}", "weekly review route is unavailable")
        elif service == "command-api":
            self._http_success("http://127.0.0.1:8001/health", "command API health route is unavailable")
            self._authenticated_negative_check()
        elif service == "mcp":
            self._http_response("http://127.0.0.1:8000/mcp", {200, 400, 404, 405, 406}, "MCP transport is unavailable")
        elif service in self._PROCESS_SERVICES:
            result = self._run(
                ("docker", "compose", "logs", "--no-color", "--tail", "200", service)
            )
            if result.returncode != 0:
                raise DeploymentHealthError(f"{service} logs could not be inspected")
            logs = result.stdout.lower()
            if any(signal in logs for signal in ("traceback (most recent call last)", "crashloop", "restart loop")):
                raise DeploymentHealthError(f"{service} reported a startup failure")

    def check_aggregate(self, feature_routes: tuple[str, ...]) -> None:
        self._check_running("postgres")
        self._checked(
            ("docker", "compose", "exec", "-T", "postgres", "pg_isready"),
            "PostgreSQL aggregate health check failed",
        )
        for route in ("/health", "/weekly-review", "/command", *feature_routes):
            self._http_success(f"http://127.0.0.1:8010{route}", "aggregate weekly review route is unavailable")
        self._http_success("http://127.0.0.1:8001/health", "aggregate command API route is unavailable")
        self._authenticated_negative_check()
        self._http_response("http://127.0.0.1:8000/mcp", {200, 400, 404, 405, 406}, "aggregate MCP route is unavailable")

    def _check_running(self, service: str) -> None:
        result = self._run(
            (
                "docker",
                "compose",
                "ps",
                "--status",
                "running",
                "--format",
                "json",
                service,
            )
        )
        if result.returncode != 0:
            raise DeploymentHealthError(f"{service} is not running")
        rows = _json_rows(result.stdout)
        matching = [row for row in rows if str(row.get("Service") or "") == service]
        if not matching or any(
            str(row.get("State") or "").lower() != "running"
            or "restarting" in str(row.get("Status") or "").lower()
            for row in matching
        ):
            raise DeploymentHealthError(f"{service} is not running")

    def _authenticated_negative_check(self) -> None:
        self._http_response(
            "http://127.0.0.1:8001/command",
            {401, 403},
            "command API authentication boundary is unavailable",
            method="POST",
        )

    def _http_success(self, url: str, message: str) -> None:
        self._http_response(url, set(range(200, 400)), message)

    def _http_response(
        self,
        url: str,
        accepted: set[int],
        message: str,
        *,
        method: str | None = None,
    ) -> None:
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
        ]
        if method:
            command.extend(("--request", method))
        command.append(url)
        result = self._run(tuple(command))
        try:
            status = int(result.stdout.strip())
        except ValueError as error:
            raise DeploymentHealthError(message) from error
        if result.returncode != 0 or status not in accepted:
            raise DeploymentHealthError(message)

    def _checked(self, command: tuple[str, ...], message: str) -> None:
        if self._run(command).returncode != 0:
            raise DeploymentHealthError(message)

    def _run(self, command: tuple[str, ...]):
        with _working_directory(self.current_release), _compose_environment(
            self.compose_project_name
        ):
            return self.runner.run(command)


@dataclass(frozen=True)
class DeployRequest:
    requested_ref: str
    requested_mode: DeployMode
    requested_targets: tuple[str, ...]
    archive_path: Path | None
    emergency_reason: str | None
    feature_routes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_targets", tuple(sorted(set(self.requested_targets))))
        object.__setattr__(self, "feature_routes", tuple(dict.fromkeys(self.feature_routes)))
        if any(not route.startswith("/") or route.startswith("//") for route in self.feature_routes):
            raise ValueError("feature routes must be absolute local paths")


@dataclass(frozen=True)
class DeployOutcome:
    ok: bool
    target_sha: str
    mode: DeployMode
    activated_services: tuple[str, ...]
    rolled_back_services: tuple[str, ...]
    message: str
    manual_recovery: dict[str, str] | None = None


PlanBuilder = Callable[[Path, str, str, CommandRunner], DeploymentPlan]
ResourceCollector = Callable[[CommandRunner], ResourceSnapshot]
RuntimeValidator = Callable[[CommandRunner, Path], tuple[str, ...]]
ReleaseStager = Callable[[str], Path]
ImageInventory = Callable[[], tuple[ImageRecord, ...]]
ReferencedImageIds = Callable[[], set[str]]


class DeploymentEngine:
    def __init__(
        self,
        *,
        repo: Path,
        app_root: Path,
        runner: CommandRunner,
        health: HealthChecker,
        clock: Clock,
        plan_builder: PlanBuilder = classify_deployment,
        resource_collector: ResourceCollector = collect_resources,
        runtime_validator: RuntimeValidator = validate_runtime,
        release_stager: ReleaseStager | None = None,
        image_inventory: ImageInventory | None = None,
        referenced_image_ids: ReferencedImageIds | None = None,
        compose_project_name: str = "turenagenttool_prod",
        env_file: Path | None = None,
    ) -> None:
        self.repo = repo
        self.app_root = app_root
        self.runner = runner
        self.health = health
        self.clock = clock
        self.plan_builder = plan_builder
        self.resource_collector = resource_collector
        self.runtime_validator = runtime_validator
        self.release_stager = release_stager or self._stage_release
        self.image_inventory = image_inventory or self._image_inventory
        self.referenced_image_ids = referenced_image_ids or self._referenced_image_ids
        self.compose_project_name = compose_project_name
        self.releases_dir = app_root / "releases"
        self.shared_dir = app_root / "shared"
        self.current_link = app_root / "current"
        self.previous_link = app_root / "previous"
        self.env_file = env_file or app_root / ".env"
        self.state_path = self.shared_dir / "deploy-state.json"
        self.events_dir = self.shared_dir / "deploy-events"
        self.lock_path = self.shared_dir / "deploy.lock"
        self.lockout_path = self.shared_dir / "deploy.lockout"

    def deploy(self, request: DeployRequest) -> DeployOutcome:
        if self.lockout_path.exists():
            if request.requested_mode is DeployMode.FULL_IMAGE:
                self._remove_archive(request.archive_path)
            return DeployOutcome(
                ok=False,
                target_sha="",
                mode=request.requested_mode,
                activated_services=(),
                rolled_back_services=(),
                message="deployment is locked out pending manual recovery",
                manual_recovery=self._load_lockout_recovery(),
            )

        preview = self._preview_plan(request)
        if isinstance(preview, DeployOutcome):
            if request.requested_mode is DeployMode.FULL_IMAGE:
                self._remove_archive(request.archive_path)
            return preview
        preview_sha, preview_plan = preview
        if preview_plan.mode is DeployMode.NO_DEPLOY:
            if request.requested_mode is not DeployMode.NO_DEPLOY or request.requested_targets:
                return DeployOutcome(
                    ok=False,
                    target_sha=preview_sha,
                    mode=preview_plan.mode,
                    activated_services=(),
                    rolled_back_services=(),
                    message="requested deployment plan does not match server classification",
                )
            return DeployOutcome(
                ok=True,
                target_sha=preview_sha,
                mode=DeployMode.NO_DEPLOY,
                activated_services=(),
                rolled_back_services=(),
                message="server classification requires no deployment",
            )

        target_sha = ""
        plan: DeploymentPlan | None = None
        computed_mode: DeployMode | None = None
        previous_state: DeploymentState | None = None
        previous_current = self._resolved_link(self.current_link)
        previous_previous = self._resolved_link(self.previous_link)
        previous_env = self.env_file.read_bytes() if self.env_file.exists() else None
        activated: list[str] = []
        target_durations_ms: dict[str, int] = {}
        started_at = self._timestamp()
        preflight: dict[str, int | float | str] = {}
        release_activated = False
        candidate_loaded = False
        manual_recovery: dict[str, str] | None = None
        archive_bytes: int | None = None
        image_count_before = 0
        image_count_after = 0
        disk_used_after = 0.0

        try:
            with deployment_lock(self.lock_path):
                self._run_checked(
                    ("git", "-C", str(self.repo), "fetch", "origin", "main"),
                    "production source refresh failed",
                )
                target_sha = resolve_production_target(self.repo, request.requested_ref, self.runner)
                previous_state = load_state(self.state_path)
                if previous_state.current_sha is None:
                    raise DeploymentError("deployment state does not identify the active commit")
                computed_plan = self.plan_builder(
                    self.repo,
                    previous_state.current_sha,
                    target_sha,
                    self.runner,
                )
                computed_mode = computed_plan.mode
                plan = self._validate_request(request, computed_plan)

                snapshot = self.resource_collector(self.runner)
                disk_used_after = snapshot.disk_used_percent
                archive_bytes = request.archive_path.stat().st_size if request.archive_path else None
                result = evaluate_preflight(snapshot, plan.mode, archive_bytes)
                if not result.ok:
                    raise DeploymentError("deployment resource preflight failed: " + "; ".join(result.errors))
                preflight = self._preflight_observations(snapshot, archive_bytes)

                current_compose = self.current_link / "docker-compose.prod.yml"
                with _compose_environment(self.compose_project_name):
                    labels = self.runtime_validator(self.runner, current_compose)
                preflight.update(self._runtime_observations(labels))
                image_count_before = len({image.image_id for image in self.image_inventory()})
                image_count_after = image_count_before

                release = self.release_stager(target_sha)
                with _compose_environment(self.compose_project_name):
                    self._run_checked(
                        (
                            "docker",
                            "compose",
                            "-f",
                            str(release / "docker-compose.prod.yml"),
                            "config",
                            "--quiet",
                        ),
                        "staged Compose configuration is invalid",
                    )

                selected_image = previous_state.current_image
                if plan.mode is DeployMode.FULL_IMAGE:
                    if request.archive_path is None:
                        raise DeploymentError("full image deployment requires an archive")
                    load_image_archive(self.runner, request.archive_path)
                    candidate_loaded = True
                    selected_image = f"investment-knowledge-app:{target_sha}"
                    self._run_checked(
                        ("docker", "image", "inspect", selected_image),
                        "immutable candidate image is unavailable",
                    )
                self._activate_release(release, previous_current)
                release_activated = True
                if selected_image:
                    self._write_image_tag(selected_image)

                for target in plan.targets:
                    started = self.clock.monotonic()
                    activated.append(target)
                    self._activate_target(target)
                    self.health.check_service(target, request.feature_routes)
                    self.health.check_aggregate(request.feature_routes)
                    target_durations_ms[target] = round(
                        (self.clock.monotonic() - started) * 1000
                    )

                stability_seconds = 60 if plan.mode is DeployMode.FULL_IMAGE else 30
                self.clock.sleep(stability_seconds)
                for target in activated:
                    self.health.check_service(target, request.feature_routes)
                self.health.check_aggregate(request.feature_routes)

                completed_at = self._timestamp()
                event_id = self._event_id(target_sha, started_at)
                state = self._successful_state(
                    request=request,
                    plan=plan,
                    target_sha=target_sha,
                    release=release,
                    previous_state=previous_state,
                    previous_current=previous_current,
                    preflight=preflight,
                    event_id=event_id,
                    started_at=started_at,
                    completed_at=completed_at,
                )
                write_state(self.state_path, state)
                retain_release_directories(
                    self.releases_dir,
                    tuple(
                        sha
                        for sha in (target_sha, previous_state.current_sha)
                        if sha is not None
                    ),
                )
                if plan.mode is DeployMode.FULL_IMAGE:
                    remove_managed_images(
                        self.runner,
                        self.image_inventory(),
                        state,
                        self.referenced_image_ids(),
                        successful_full_deployment=True,
                        prune_builder_cache=True,
                    )
                image_count_after = len({image.image_id for image in self.image_inventory()})
                final_snapshot = self.resource_collector(self.runner)
                disk_used_after = final_snapshot.disk_used_percent
                write_event(
                    self.events_dir,
                    self._event(
                        event_id=event_id,
                        request=request,
                        plan=plan,
                        computed_mode=computed_mode,
                        target_sha=target_sha,
                        deployed_sha=target_sha,
                        preflight=preflight,
                        archive_bytes=archive_bytes,
                        image_count_before=image_count_before,
                        image_count_after=image_count_after,
                        disk_used_after=disk_used_after,
                        target_durations_ms=target_durations_ms,
                        rollback_status="not_needed",
                        final_health="healthy",
                        started_at=started_at,
                        completed_at=completed_at,
                    ),
                )
                return DeployOutcome(
                    ok=True,
                    target_sha=target_sha,
                    mode=plan.mode,
                    activated_services=tuple(activated),
                    rolled_back_services=(),
                    message="deployment completed and remained healthy",
                )
        except Exception as error:
            rolled_back: tuple[str, ...] = ()
            rollback_status = "not_started"
            if release_activated and previous_state is not None:
                rolled_back = tuple(reversed(activated))
                rollback_status = self._rollback(
                    rolled_back,
                    previous_current,
                    previous_previous,
                    previous_env,
                    request.feature_routes,
                    previous_state,
                )
                if plan is not None and target_sha:
                    completed_at = self._timestamp()
                    final_health = "rollback_failed" if rollback_status == "rollback_failed" else "unhealthy"
                    if rollback_status == "rollback_failed":
                        manual_recovery = self._manual_recovery(previous_state)
                        self._persist_lockout(
                            previous_state,
                            target_sha,
                            completed_at,
                            manual_recovery,
                        )
                    try:
                        write_event(
                            self.events_dir,
                            self._event(
                                event_id=self._event_id(target_sha, started_at),
                                request=request,
                                plan=plan,
                                computed_mode=computed_mode or plan.mode,
                                target_sha=target_sha,
                                deployed_sha=None,
                                preflight=preflight,
                                archive_bytes=archive_bytes,
                                image_count_before=image_count_before,
                                image_count_after=image_count_after,
                                disk_used_after=disk_used_after,
                                target_durations_ms=target_durations_ms,
                                rollback_status=rollback_status,
                                final_health=final_health,
                                started_at=started_at,
                                completed_at=completed_at,
                            ),
                        )
                    except Exception:
                        pass
            if candidate_loaded and previous_state is not None and target_sha:
                try:
                    candidate_tag = f"investment-knowledge-app:{target_sha}"
                    candidate_images = tuple(
                        image for image in self.image_inventory() if image.tag == candidate_tag
                    )
                    remove_managed_images(
                        self.runner,
                        candidate_images,
                        previous_state,
                        self.referenced_image_ids(),
                    )
                except Exception:
                    pass
            if request.requested_mode is DeployMode.FULL_IMAGE:
                self._remove_archive(request.archive_path)
            return DeployOutcome(
                ok=False,
                target_sha=target_sha,
                mode=plan.mode if plan is not None else request.requested_mode,
                activated_services=tuple(activated),
                rolled_back_services=rolled_back,
                message=self._safe_message(error),
                manual_recovery=(
                    manual_recovery if rollback_status == "rollback_failed" else None
                ),
            )

    def _preview_plan(
        self, request: DeployRequest
    ) -> tuple[str, DeploymentPlan] | DeployOutcome:
        try:
            target_sha = resolve_production_target(self.repo, request.requested_ref, self.runner)
            state = load_state(self.state_path)
            if state.current_sha is None:
                raise DeploymentError("deployment state does not identify the active commit")
            return target_sha, self.plan_builder(
                self.repo, state.current_sha, target_sha, self.runner
            )
        except Exception as error:
            return DeployOutcome(
                ok=False,
                target_sha="",
                mode=request.requested_mode,
                activated_services=(),
                rolled_back_services=(),
                message=self._safe_message(error),
            )

    def _validate_request(
        self, request: DeployRequest, plan: DeploymentPlan
    ) -> DeploymentPlan:
        if request.emergency_reason is not None and len(request.emergency_reason.strip()) < 20:
            raise DeploymentError("emergency reason must be at least 20 characters")
        if request.emergency_reason is not None and _SENSITIVE_REASON.search(request.emergency_reason):
            raise DeploymentError("emergency reason contains protected material")
        requested_targets = request.requested_targets
        if plan.mode is not DeployMode.NO_DEPLOY and not requested_targets:
            raise DeploymentError("requested deployment plan does not match server classification")
        for target in requested_targets:
            if target == "postgres":
                raise DeploymentError("PostgreSQL cannot be an application deployment target")
            if target not in _APPLICATION_TARGETS and not target.endswith(".service"):
                raise DeploymentError("deployment request contains an unknown target")
        if request.requested_mode is not plan.mode or requested_targets != plan.targets:
            if request.emergency_reason is not None:
                return DeploymentPlan(
                    mode=request.requested_mode,
                    targets=requested_targets,
                    changed_files=plan.changed_files,
                    image_input_files=plan.image_input_files,
                    reasons=(*plan.reasons, "emergency operator override"),
                )
            raise DeploymentError("requested deployment plan does not match server classification")
        return plan

    def _activate_release(self, release: Path, previous_current: Path | None) -> None:
        if previous_current is not None:
            self._replace_symlink(self.previous_link, previous_current)
        self._replace_symlink(self.current_link, release)

    def _activate_target(self, target: str) -> None:
        if target.endswith(".service"):
            self._run_checked(("systemctl", "restart", target), f"host unit {target} failed to restart")
            return
        with _working_directory(self.current_link), _compose_environment(
            self.compose_project_name
        ):
            self._run_checked(
                (
                    "docker",
                    "compose",
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    target,
                ),
                f"application service {target} failed to activate",
            )

    def _rollback(
        self,
        targets: tuple[str, ...],
        previous_current: Path | None,
        previous_previous: Path | None,
        previous_env: bytes | None,
        feature_routes: tuple[str, ...],
        previous_state: DeploymentState,
    ) -> str:
        try:
            self._restore_link(self.current_link, previous_current)
            self._restore_link(self.previous_link, previous_previous)
            self._restore_env(previous_env)
            for target in targets:
                self._activate_target(target)
            self.health.check_aggregate(feature_routes)
            write_state(self.state_path, previous_state)
            return "succeeded"
        except Exception:
            return "rollback_failed"

    def _successful_state(
        self,
        *,
        request: DeployRequest,
        plan: DeploymentPlan,
        target_sha: str,
        release: Path,
        previous_state: DeploymentState,
        previous_current: Path | None,
        preflight: dict[str, int | float | str],
        event_id: str,
        started_at: str,
        completed_at: str,
    ) -> DeploymentState:
        current_image = previous_state.current_image
        previous_image = previous_state.previous_image
        if plan.mode is DeployMode.FULL_IMAGE:
            current_image = f"investment-knowledge-app:{target_sha}"
            previous_image = previous_state.current_image
        return DeploymentState(
            schema_version=1,
            current_sha=target_sha,
            previous_sha=previous_state.current_sha,
            current_image=current_image,
            previous_image=previous_image,
            active_release=str(release),
            previous_release=str(previous_current) if previous_current else None,
            last_mode=plan.mode.value,
            requested_ref=request.requested_ref,
            resolved_ref=target_sha,
            targets=plan.targets,
            last_event_id=event_id,
            started_at=started_at,
            completed_at=completed_at,
            preflight=preflight,
            final_health="healthy",
        )

    def _event(
        self,
        *,
        event_id: str,
        request: DeployRequest,
        plan: DeploymentPlan,
        computed_mode: DeployMode,
        target_sha: str,
        deployed_sha: str | None,
        preflight: dict[str, int | float | str],
        archive_bytes: int | None,
        image_count_before: int,
        image_count_after: int,
        disk_used_after: float,
        target_durations_ms: dict[str, int],
        rollback_status: str,
        final_health: str,
        started_at: str,
        completed_at: str,
    ) -> DeploymentEvent:
        return DeploymentEvent(
            event_id=event_id,
            requested_mode=request.requested_mode.value,
            computed_mode=computed_mode.value,
            deployed_sha=deployed_sha,
            target_sha=target_sha,
            changed_image_inputs=plan.image_input_files,
            targets=plan.targets,
            preflight=preflight,
            archive_bytes=archive_bytes,
            image_count_before=image_count_before,
            image_count_after=image_count_after,
            disk_used_before=float(preflight.get("disk_used_percent", 0.0)),
            disk_used_after=disk_used_after,
            target_durations_ms=target_durations_ms,
            rollback_status=rollback_status,
            cleanup_reclaimed_bytes=0,
            emergency_override=request.emergency_reason is not None,
            emergency_reason=request.emergency_reason,
            final_health=final_health,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _preflight_observations(
        self, snapshot: ResourceSnapshot, archive_bytes: int | None
    ) -> dict[str, int | float | str]:
        observations: dict[str, int | float | str] = {
            "disk_available_bytes": snapshot.free_disk_bytes,
            "disk_used_percent": snapshot.disk_used_percent,
            "available_memory_bytes": snapshot.available_memory_bytes,
            "source_valid": "valid",
            "lock_valid": "held",
            "required_free_bytes": 8 * 1024**3,
        }
        if archive_bytes is not None:
            observations["archive_bytes"] = archive_bytes
        return observations

    def _runtime_observations(self, labels: tuple[str, ...]) -> dict[str, str]:
        available = set(labels)
        return {
            "docker_health": "healthy" if "docker_health" in available else "unknown",
            "compose_valid": "valid" if "compose_valid" in available else "unknown",
            "postgresql_health": "healthy" if "postgresql_health" in available else "unknown",
        }

    def _stage_release(self, target_sha: str) -> Path:
        release = self.releases_dir / target_sha
        if release.exists():
            self._validate_release(release)
            return release

        self.releases_dir.mkdir(parents=True, exist_ok=True)
        self.shared_dir.mkdir(parents=True, exist_ok=True)
        shared_drafts = self.shared_dir / "drafts"
        legacy_drafts = self.app_root / "drafts"
        if not shared_drafts.exists():
            if legacy_drafts.exists() and legacy_drafts.is_dir():
                shutil.copytree(legacy_drafts.resolve(), shared_drafts)
            else:
                shared_drafts.mkdir()
        staging = self.releases_dir / f".staging-{target_sha}-{os.getpid()}"
        archive = self.releases_dir / f".archive-{target_sha}-{os.getpid()}.tar"
        if staging.exists() or staging.is_symlink():
            raise DeploymentError("release staging path already exists")
        staging.mkdir()
        try:
            self._run_checked(
                (
                    "git",
                    "-C",
                    str(self.repo),
                    "archive",
                    "--format=tar",
                    "--output",
                    str(archive),
                    target_sha,
                ),
                "target release archive could not be created",
            )
            with tarfile.open(archive, "r") as bundle:
                members = bundle.getmembers()
                self._validate_archive_members(staging, members)
                bundle.extractall(staging, members=members)
            self._replace_staged_path(
                staging / "drafts", shared_drafts, directory=True
            )
            if self.env_file.exists():
                self._replace_staged_path(staging / ".env", self.env_file, directory=False)
            self._validate_release(staging)
            os.replace(staging, release)
            return release
        except DeploymentError:
            raise
        except (OSError, tarfile.TarError) as error:
            raise DeploymentError("target release could not be staged safely") from error
        finally:
            archive.unlink(missing_ok=True)
            if staging.exists() and staging.is_dir() and not staging.is_symlink():
                shutil.rmtree(staging)

    def _validate_release(self, release: Path) -> None:
        required = (
            release / "db" / "schema.sql",
            release / "investment_knowledge_mcp",
            release / "scripts" / "init_db.py",
            release / "scripts" / "ecs_ops_api.py",
            release / "Dockerfile",
            release / "requirements.txt",
            release / "docker-compose.prod.yml",
        )
        if any(not path.exists() for path in required):
            raise DeploymentError("staged release is incomplete")

    def _validate_archive_members(
        self, staging: Path, members: list[tarfile.TarInfo]
    ) -> None:
        root = staging.resolve()
        for member in members:
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise DeploymentError("target release archive contains an unsafe path")
            destination = (staging / member_path).resolve()
            if not destination.is_relative_to(root):
                raise DeploymentError("target release archive escapes the release directory")
            if member.issym() or member.islnk():
                link = Path(member.linkname)
                link_target = (destination.parent / link).resolve() if member.issym() else (staging / link).resolve()
                if link.is_absolute() or not link_target.is_relative_to(root):
                    raise DeploymentError("target release archive contains an unsafe link")

    def _replace_staged_path(self, path: Path, target: Path, *, directory: bool) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        path.symlink_to(target, target_is_directory=directory)

    def _image_inventory(self) -> tuple[ImageRecord, ...]:
        result = self.runner.run(
            ("docker", "image", "ls", "--no-trunc", "--format", "{{json .}}")
        )
        if result.returncode != 0:
            raise DeploymentError("managed image inventory failed")
        records: list[ImageRecord] = []
        for index, row in enumerate(_json_rows(result.stdout)):
            repository = str(row.get("Repository") or "")
            tag = str(row.get("Tag") or "")
            image_id = str(row.get("ID") or "")
            if not image_id or not repository or tag in ("", "<none>"):
                continue
            records.append(
                ImageRecord(
                    image_id=image_id,
                    tag=f"{repository}:{tag}",
                    created_epoch=index,
                )
            )
        return tuple(records)

    def _referenced_image_ids(self) -> set[str]:
        containers = self.runner.run(("docker", "ps", "--all", "--quiet"))
        if containers.returncode != 0:
            raise DeploymentError("container image reference inventory failed")
        referenced: set[str] = set()
        for container_id in containers.stdout.split():
            result = self.runner.run(
                ("docker", "inspect", "--format", "{{.Image}}", container_id)
            )
            if result.returncode != 0:
                raise DeploymentError("container image reference inventory failed")
            if result.stdout.strip():
                referenced.add(result.stdout.strip())
        return referenced

    def _persist_lockout(
        self,
        previous_state: DeploymentState,
        target_sha: str,
        completed_at: str,
        manual_recovery: dict[str, str],
    ) -> None:
        self._atomic_write(
            self.lockout_path,
            (json.dumps(manual_recovery, ensure_ascii=True, sort_keys=True) + "\n").encode("ascii"),
        )
        write_state(
            self.state_path,
            replace(
                previous_state,
                completed_at=completed_at,
                final_health="rollback_failed",
            ),
        )

    def _manual_recovery(
        self, state: DeploymentState | None
    ) -> dict[str, str]:
        try:
            with _working_directory(self.current_link), _compose_environment(
                self.compose_project_name
            ):
                result = self.runner.run(("docker", "compose", "ps", "--format", "json"))
            rows = _json_rows(result.stdout) if result.returncode == 0 else ()
            containers = [
                {
                    key: str(row.get(key) or "")
                    for key in ("Service", "State", "Status", "Image")
                }
                for row in rows
            ]
        except Exception:
            containers = []
        try:
            snapshot = self.resource_collector(self.runner)
            disk = json.dumps(
                {
                    "available_bytes": snapshot.free_disk_bytes,
                    "used_percent": snapshot.disk_used_percent,
                },
                sort_keys=True,
            )
            memory = json.dumps(
                {"available_bytes": snapshot.available_memory_bytes}, sort_keys=True
            )
        except Exception:
            disk = json.dumps({"available_bytes": "unknown", "used_percent": "unknown"})
            memory = json.dumps({"available_bytes": "unknown"})
        return {
            "current_release": str(self._resolved_link(self.current_link) or "unknown"),
            "current_image": (state.current_image if state and state.current_image else "unknown"),
            "container_status": json.dumps(containers, sort_keys=True),
            "disk": disk,
            "memory": memory,
        }

    def _load_lockout_recovery(self) -> dict[str, str]:
        try:
            payload = json.loads(self.lockout_path.read_text(encoding="ascii"))
            if isinstance(payload, dict) and set(payload) == {
                "current_release",
                "current_image",
                "container_status",
                "disk",
                "memory",
            } and all(isinstance(value, str) for value in payload.values()):
                return payload
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        return self._manual_recovery(None)

    def _remove_archive(self, archive_path: Path | None) -> None:
        if archive_path is not None and (archive_path.is_file() or archive_path.is_symlink()):
            archive_path.unlink()

    def _run_checked(self, command: tuple[str, ...], message: str) -> None:
        result = self.runner.run(command)
        if result.returncode != 0:
            raise DeploymentError(message)

    def _write_image_tag(self, image: str) -> None:
        tag = image.rsplit(":", 1)[-1]
        lines = self.env_file.read_text(encoding="utf-8").splitlines() if self.env_file.exists() else []
        updated: list[str] = []
        replaced = False
        for line in lines:
            if line.startswith("APP_IMAGE_TAG="):
                updated.append(f"APP_IMAGE_TAG={tag}")
                replaced = True
            else:
                updated.append(line)
        if not replaced:
            updated.append(f"APP_IMAGE_TAG={tag}")
        self._atomic_write(self.env_file, ("\n".join(updated) + "\n").encode())

    def _restore_env(self, contents: bytes | None) -> None:
        if contents is None:
            self.env_file.unlink(missing_ok=True)
        else:
            self._atomic_write(self.env_file, contents)

    def _restore_link(self, link: Path, target: Path | None) -> None:
        if target is None:
            link.unlink(missing_ok=True)
        else:
            self._replace_symlink(link, target)

    def _replace_symlink(self, link: Path, target: Path) -> None:
        if link.exists() and not link.is_symlink():
            raise DeploymentError(f"refusing to replace non-symlink deployment path: {link.name}")
        temporary = link.with_name(f"{link.name}.next")
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, link)

    def _resolved_link(self, link: Path) -> Path | None:
        try:
            return link.resolve(strict=True)
        except FileNotFoundError:
            return None

    def _atomic_write(self, path: Path, contents: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.next")
        mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
        try:
            temporary.unlink(missing_ok=True)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _event_id(self, target_sha: str, started_at: str) -> str:
        compact_time = started_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
        return f"{compact_time}-{target_sha[:12]}"

    def _timestamp(self) -> str:
        return self.clock.now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _safe_message(self, error: Exception) -> str:
        if isinstance(error, DeploymentError):
            return str(error)
        return "deployment failed; inspect the product-safe deployment event"


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


@contextmanager
def _compose_environment(project_name: str):
    previous_project = os.environ.get("COMPOSE_PROJECT_NAME")
    removed = {
        name: os.environ.pop(name)
        for name in ("POSTGRES_HOST", "POSTGRES_PORT")
        if name in os.environ
    }
    os.environ["COMPOSE_PROJECT_NAME"] = project_name
    try:
        yield
    finally:
        if previous_project is None:
            os.environ.pop("COMPOSE_PROJECT_NAME", None)
        else:
            os.environ["COMPOSE_PROJECT_NAME"] = previous_project
        os.environ.update(removed)


def _json_rows(output: str) -> tuple[dict[str, object], ...]:
    text = output.strip()
    if not text:
        return ()
    try:
        value = json.loads(text)
        values = value if isinstance(value, list) else [value]
    except json.JSONDecodeError:
        try:
            values = [json.loads(line) for line in text.splitlines()]
        except json.JSONDecodeError:
            return ()
    return tuple(value for value in values if isinstance(value, dict))


def _csv_values(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the shared transactional deployment engine.")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--mode", required=True, choices=[mode.value for mode in DeployMode])
    parser.add_argument("--targets")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--emergency-reason")
    parser.add_argument("--feature-routes")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--app-root", type=Path, default=Path("/opt/investment-knowledge")
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--project-name", default="turenagenttool_prod")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _argument_parser()
    arguments = parser.parse_args(argv)
    feature_routes = _csv_values(arguments.feature_routes)
    if any(not route.startswith("/") or route.startswith("//") for route in feature_routes):
        parser.error("feature routes must be absolute local paths")

    runner = SubprocessRunner()
    request = DeployRequest(
        requested_ref=arguments.ref,
        requested_mode=DeployMode(arguments.mode),
        requested_targets=_csv_values(arguments.targets),
        archive_path=arguments.archive,
        emergency_reason=arguments.emergency_reason,
        feature_routes=feature_routes,
    )
    engine = DeploymentEngine(
        repo=arguments.repo.resolve(),
        app_root=arguments.app_root,
        runner=runner,
        health=DockerHealthChecker(
            runner,
            arguments.app_root / "current",
            compose_project_name=arguments.project_name,
        ),
        clock=SystemClock(),
        compose_project_name=arguments.project_name,
        env_file=arguments.env_file,
    )
    outcome = engine.deploy(request)
    payload = asdict(outcome)
    payload["mode"] = outcome.mode.value
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
