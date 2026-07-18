from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import tarfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import ContextManager, Protocol

try:
    from scripts.deploy_contract import (
        APPLICATION_SERVICES,
        MODE_RANK,
        DeployMode,
        DeploymentPlan,
        classify_deployment,
    )
    from scripts.deploy_preflight import (
        ResourceSnapshot,
        collect_resources,
        deployment_lock,
        evaluate_preflight,
        required_available_memory_bytes,
        validate_runtime,
    )
    from scripts.deploy_retention import (
        ImageRecord,
        remove_managed_images,
        retain_release_directories,
        select_managed_images_for_removal,
    )
    from scripts.deploy_state import (
        DeploymentEvent,
        DeploymentState,
        SourcePolicyError,
        SourceRefreshError,
        is_allowed_deploy_source,
        is_safe_deploy_label,
        load_state,
        resolve_production_target,
        write_event,
        write_state,
    )
    from scripts.deploy_support import CommandRunner, SubprocessRunner
except ModuleNotFoundError:  # Direct execution through scripts/deploy_release.py.
    from deploy_contract import (
        APPLICATION_SERVICES,
        MODE_RANK,
        DeployMode,
        DeploymentPlan,
        classify_deployment,
    )
    from deploy_preflight import (
        ResourceSnapshot,
        collect_resources,
        deployment_lock,
        evaluate_preflight,
        required_available_memory_bytes,
        validate_runtime,
    )
    from deploy_retention import (
        ImageRecord,
        remove_managed_images,
        retain_release_directories,
        select_managed_images_for_removal,
    )
    from deploy_state import (
        DeploymentEvent,
        DeploymentState,
        SourcePolicyError,
        SourceRefreshError,
        is_allowed_deploy_source,
        is_safe_deploy_label,
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
_APPLICATION_TARGETS = set(APPLICATION_SERVICES)
_MANAGED_ARCHIVE_NAME = re.compile(
    r"investment-knowledge-app-(?P<sha>[0-9a-f]{40})-"
    r"(?P<suffix>[A-Za-z0-9][A-Za-z0-9._-]{0,127})\.tar\.gz"
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_SAFE_FEATURE_ROUTE = re.compile(
    r"/(?:[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*)?"
)
_BUILTIN_ROUTE_SMOKE_CHECKS = (
    "weekly-review-web:/health",
    "weekly-review-web:/weekly-review",
    "weekly-review-web:/command",
    "command-api:/health",
    "command-api:auth-boundary",
    "mcp:transport-boundary",
)


def deployment_route_smoke_checks(
    feature_routes: tuple[str, ...],
) -> tuple[str, ...]:
    extras = tuple(f"weekly-review-web:{route}" for route in feature_routes)
    return tuple(dict.fromkeys((*_BUILTIN_ROUTE_SMOKE_CHECKS, *extras)))


def is_safe_feature_route(route: object) -> bool:
    if not isinstance(route, str) or not 1 <= len(route) <= 256:
        return False
    if _SAFE_FEATURE_ROUTE.fullmatch(route) is None or _SENSITIVE_REASON.search(route):
        return False
    return all(segment not in {".", ".."} for segment in route.split("/")[1:])


def is_managed_image_archive(
    archive_path: Path,
    *,
    expected_sha: str | None = None,
    allowed_parent: Path = Path("/tmp"),
) -> bool:
    if not archive_path.is_absolute() or archive_path.parent != allowed_parent:
        return False
    if archive_path.is_symlink() or not archive_path.is_file():
        return False
    match = _MANAGED_ARCHIVE_NAME.fullmatch(archive_path.name)
    if match is None:
        return False
    return expected_sha is None or match.group("sha") == expected_sha


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_cleanup_from_rollback(rollback_status: str) -> str:
    match = re.search(r"(?:^|\|)archive_cleanup:([^|]+)", rollback_status)
    return match.group(1) if match is not None else "not_applicable"


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
        "daily-market-brief-history-worker",
        "daily-market-brief-scheduler",
        "ipo-reminder-scheduler",
        "dingtalk-stream-bot",
    }

    def __init__(
        self,
        runner: CommandRunner,
        current_release: Path,
        compose_project_name: str = "turenagenttool_prod",
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.runner = runner
        self.current_release = current_release
        self.compose_project_name = compose_project_name
        self.sleeper = sleeper

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
        elif service == "dingtalk-api":
            self._http_success("http://127.0.0.1:8002/health", "DingTalk API health route is unavailable")
            self._dingtalk_negative_check()
        elif service == "mcp":
            self._http_response("http://127.0.0.1:8000/mcp", {200, 400, 405, 406}, "MCP transport is unavailable")

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
        self._http_response("http://127.0.0.1:8000/mcp", {200, 400, 405, 406}, "aggregate MCP route is unavailable")

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
            self._raise_not_running(service)
        rows = _json_rows(result.stdout)
        matching = [row for row in rows if str(row.get("Service") or "") == service]
        if not matching or any(
            str(row.get("State") or "").lower() != "running"
            or "restarting" in str(row.get("Status") or "").lower()
            for row in matching
        ):
            self._raise_not_running(service)
        if service in self._PROCESS_SERVICES:
            for row in matching:
                container = str(row.get("ID") or row.get("Name") or "").strip()
                if not container:
                    continue
                restart_count = self._run(
                    ("docker", "inspect", "--format", "{{.RestartCount}}", container)
                )
                if restart_count.returncode != 0:
                    raise DeploymentHealthError(
                        f"{service} restart state could not be inspected"
                    )
                try:
                    restarted = int(restart_count.stdout.strip())
                except ValueError as exc:
                    raise DeploymentHealthError(
                        f"{service} restart state could not be inspected"
                    ) from exc
                if restarted:
                    raise DeploymentHealthError(f"{service} restarted during startup")

    def _raise_not_running(self, service: str) -> None:
        logs = self._run(("docker", "compose", "logs", "--no-color", "--tail", "200", service))
        detail = _safe_diagnostic_summary(logs.stdout if logs.returncode == 0 else "")
        suffix = f": {detail}" if detail else ""
        raise DeploymentHealthError(f"{service} is not running{suffix}")

    def _authenticated_negative_check(self) -> None:
        self._http_response(
            "http://127.0.0.1:8001/command",
            {401, 403},
            "command API authentication boundary is unavailable",
            method="POST",
        )

    def _dingtalk_negative_check(self) -> None:
        self._http_response(
            "http://127.0.0.1:8002/dingtalk/webhook",
            {400, 401, 403},
            "DingTalk webhook rejection boundary is unavailable",
            method="POST",
            body="{",
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
        body: str | None = None,
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
        if body is not None:
            command.extend(("--data-binary", body))
        command.append(url)
        for attempt in range(20):
            result = self._run(tuple(command))
            try:
                status = int(result.stdout.strip())
            except ValueError:
                status = 0
            if result.returncode == 0 and status in accepted:
                return
            if attempt < 19:
                self.sleeper(1.0)
        raise DeploymentHealthError(message)

    def _checked(self, command: tuple[str, ...], message: str) -> None:
        if self._run(command).returncode != 0:
            raise DeploymentHealthError(message)

    def _run(self, command: tuple[str, ...]):
        if command[:2] == ("docker", "compose"):
            command = (
                "docker",
                "compose",
                "-f",
                str(self.current_release / "docker-compose.prod.yml"),
                *command[2:],
            )
        with _compose_environment(self.compose_project_name):
            return self.runner.run(command)


@dataclass(frozen=True)
class DeployRequest:
    requested_ref: str
    requested_mode: DeployMode
    requested_targets: tuple[str, ...]
    archive_path: Path | None
    emergency_reason: str | None
    feature_routes: tuple[str, ...] = ()
    external_event_id: str | None = None
    source: str = "direct"
    requested_by: str = "unspecified"
    archive_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_targets", tuple(sorted(set(self.requested_targets))))
        object.__setattr__(self, "feature_routes", tuple(dict.fromkeys(self.feature_routes)))
        if any(not is_safe_feature_route(route) for route in self.feature_routes):
            raise ValueError("feature routes must be absolute local paths")
        if self.requested_mode is DeployMode.FULL_IMAGE:
            if self.archive_sha256 is None or not _SHA256_PATTERN.fullmatch(
                self.archive_sha256
            ):
                raise ValueError(
                    "full image deployment requires a 64-character lowercase archive SHA-256"
                )
        elif self.archive_sha256 is not None:
            raise ValueError("archive SHA-256 is supported only for full image deployment")
        for name in ("source", "requested_by"):
            value = getattr(self, name)
            valid = (
                is_allowed_deploy_source(value)
                if name == "source"
                else is_safe_deploy_label(value)
            )
            if not valid:
                raise ValueError(f"{name} must be a safe non-secret deployment label")


@dataclass(frozen=True)
class DeployOutcome:
    ok: bool
    target_sha: str
    mode: DeployMode
    activated_services: tuple[str, ...]
    rolled_back_services: tuple[str, ...]
    message: str
    manual_recovery: dict[str, str] | None = None
    rollback_failures: tuple[str, ...] = ()
    archive_cleanup: str = "not_applicable"
    audit_status: str = "not_recorded"
    image_count_after: int = -1
    disk_used_after: float = -1.0
    cleanup_reclaimed_bytes: int = -1
    cleanup_status: str = "not_applicable"
    failure_category: str | None = None


@dataclass
class SelectorSnapshot:
    current_release: Path | None
    previous_release: Path | None
    env_contents: bytes | None


@dataclass
class SelectorJournal:
    previous_attempted: bool = False
    current_attempted: bool = False
    image_attempted: bool = False

    @property
    def touched(self) -> bool:
        return self.previous_attempted or self.current_attempted or self.image_attempted


@dataclass(frozen=True)
class RollbackResult:
    successful_services: tuple[str, ...]
    service_failures: tuple[str, ...]
    selector_failures: tuple[str, ...]
    aggregate_failed: bool
    state_failed: bool

    @property
    def ok(self) -> bool:
        return not (
            self.service_failures
            or self.selector_failures
            or self.aggregate_failed
            or self.state_failed
        )


@dataclass
class DeploymentContext:
    request: DeployRequest
    started_at: str
    target_sha: str = ""
    computed_plan: DeploymentPlan | None = None
    plan: DeploymentPlan | None = None
    previous_state: DeploymentState | None = None
    selectors: SelectorSnapshot | None = None
    selector_journal: SelectorJournal = field(default_factory=SelectorJournal)
    touched_services: list[str] = field(default_factory=list)
    target_durations_ms: dict[str, int] = field(default_factory=dict)
    preflight: dict[str, int | float | str] = field(default_factory=dict)
    archive_bytes: int | None = None
    archive_cleanup: str = "not_applicable"
    candidate_loaded: bool = False
    image_count_before: int = -1
    image_count_after: int = -1
    disk_used_after: float = -1.0
    cleanup_reclaimed_bytes: int = -1
    cleanup_status: str = "not_applicable"



PlanBuilder = Callable[[Path, str, str, CommandRunner], DeploymentPlan]
ResourceCollector = Callable[[CommandRunner], ResourceSnapshot]
RuntimeValidator = Callable[[CommandRunner, Path], tuple[str, ...]]
ReleaseStager = Callable[[str], Path]
ImageInventory = Callable[[], tuple[ImageRecord, ...]]
ReferencedImageIds = Callable[[], set[str]]
LockFactory = Callable[[Path], ContextManager[None]]


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
        artifact_staging_dir: Path | None = None,
        lock_factory: LockFactory = deployment_lock,
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
        self.lock_factory = lock_factory
        self.releases_dir = app_root / "releases"
        self.shared_dir = app_root / "shared"
        self.current_link = app_root / "current"
        self.previous_link = app_root / "previous"
        self.env_file = env_file or app_root / ".env"
        self.state_path = self.shared_dir / "deploy-state.json"
        self.events_dir = self.shared_dir / "deploy-events"
        self.artifacts_dir = artifact_staging_dir or self.shared_dir / "deploy-artifacts"
        self.lock_path = self.shared_dir / "deploy.lock"
        self.lockout_path = self.shared_dir / "deploy.lockout"

    def deploy(self, request: DeployRequest) -> DeployOutcome:
        context = DeploymentContext(request=request, started_at=self._safe_timestamp())
        try:
            with self.lock_factory(self.lock_path):
                return self._deploy_locked(context)
        except Exception as error:
            return DeployOutcome(
                ok=False,
                target_sha="",
                mode=request.requested_mode,
                activated_services=(),
                rolled_back_services=(),
                message=(
                    "deployment lock could not be acquired"
                    if not isinstance(error, DeploymentError)
                    else self._safe_message(error)
                ),
                archive_cleanup="deferred_lock_unavailable",
            )

    def _deploy_locked(self, context: DeploymentContext) -> DeployOutcome:
        try:
            if self.lockout_path.exists():
                archive_cleanup = self._cleanup_archive_safe(
                    context.request.archive_path
                )
                return DeployOutcome(
                    ok=False,
                    target_sha="",
                    mode=context.request.requested_mode,
                    activated_services=(),
                    rolled_back_services=(),
                    message="deployment is locked out pending manual recovery",
                    manual_recovery=self._load_lockout_recovery(),
                    archive_cleanup=archive_cleanup,
                )
            return self._execute_locked(context)
        except Exception as error:
            return self._handle_failure_locked(context, error)

    def _execute_locked(self, context: DeploymentContext) -> DeployOutcome:
        request = context.request
        context.target_sha = resolve_production_target(
            self.repo, request.requested_ref, self.runner
        )
        context.previous_state = load_state(self.state_path)
        if context.previous_state.current_sha is None:
            raise DeploymentError("deployment state does not identify the active commit")
        context.computed_plan = self.plan_builder(
            self.repo,
            context.previous_state.current_sha,
            context.target_sha,
            self.runner,
        )
        context.plan = self._validate_request(request, context.computed_plan)
        if context.plan.mode is DeployMode.NO_DEPLOY:
            return DeployOutcome(
                ok=True,
                target_sha=context.target_sha,
                mode=DeployMode.NO_DEPLOY,
                activated_services=(),
                rolled_back_services=(),
                message="server classification requires no deployment",
                archive_cleanup="not_applicable",
            )

        context.selectors = SelectorSnapshot(
            current_release=self._resolved_link(self.current_link),
            previous_release=self._resolved_link(self.previous_link),
            env_contents=(
                self.env_file.read_bytes() if self.env_file.exists() else None
            ),
        )
        self._verify_release_baseline(context.previous_state, context.selectors)

        snapshot = self.resource_collector(self.runner)
        context.disk_used_after = snapshot.disk_used_percent
        if context.plan.mode is DeployMode.FULL_IMAGE and request.archive_path is None:
            raise DeploymentError(
                "full image deployment requires an immutable image archive"
            )
        if (
            context.plan.mode is DeployMode.FULL_IMAGE
            and request.archive_path is not None
            and not is_managed_image_archive(
                request.archive_path,
                expected_sha=context.target_sha,
                allowed_parent=self.artifacts_dir,
            )
        ):
            raise DeploymentError(
                "full image archive must be a SHA-bound managed regular file in private staging"
            )
        try:
            context.archive_bytes = (
                request.archive_path.stat().st_size if request.archive_path else None
            )
        except OSError as error:
            raise DeploymentError("full image archive is unavailable") from error
        context.preflight = self._preflight_observations(
            snapshot,
            context.archive_bytes,
            context.plan.mode,
        )
        result = evaluate_preflight(snapshot, context.plan.mode, context.archive_bytes)
        if not result.ok:
            raise DeploymentError(
                "deployment resource preflight failed: " + "; ".join(result.errors)
            )
        current_compose = self.current_link / "docker-compose.prod.yml"
        with _compose_environment(self.compose_project_name):
            labels = self.runtime_validator(self.runner, current_compose)
        context.preflight.update(self._runtime_observations(labels))
        self._verify_baseline_image_identity(
            context.previous_state, context.selectors
        )
        context.image_count_before = len(
            {image.image_id for image in self.image_inventory()}
        )
        context.image_count_after = context.image_count_before

        release = self.release_stager(context.target_sha)
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

        selected_image = context.previous_state.current_image
        if context.plan.mode is DeployMode.FULL_IMAGE:
            if request.archive_path is None:
                raise DeploymentError("full image deployment requires an archive")
            selected_image = f"investment-knowledge-app:{context.target_sha}"
            self._load_candidate_archive(
                context, request.archive_path, selected_image
            )
            self._record_full_image_memory_phase(context, "post_load")

        self._switch_selectors(context, release, selected_image)
        for target in context.plan.targets:
            if context.plan.mode is DeployMode.FULL_IMAGE:
                self._record_full_image_memory_phase(
                    context,
                    "before_activation",
                )
            started = self.clock.monotonic()
            context.touched_services.append(target)
            self._activate_target(target, release)
            self.health.check_service(target, request.feature_routes)
            context.target_durations_ms[target] = round(
                (self.clock.monotonic() - started) * 1000
            )
        self.health.check_aggregate(request.feature_routes)

        stability_seconds = 60 if context.plan.mode is DeployMode.FULL_IMAGE else 30
        self.clock.sleep(stability_seconds)
        for target in context.touched_services:
            self.health.check_service(target, request.feature_routes)
        self.health.check_aggregate(request.feature_routes)

        completed_at = self._safe_timestamp()
        event_id = self._event_id(
            context.target_sha,
            context.started_at,
            context.request.external_event_id,
        )
        state = self._successful_state(
            request=request,
            plan=context.plan,
            target_sha=context.target_sha,
            release=release,
            previous_state=context.previous_state,
            previous_current=(
                context.selectors.current_release if context.selectors else None
            ),
            preflight=context.preflight,
            event_id=event_id,
            started_at=context.started_at,
            completed_at=completed_at,
        )
        write_event(
            self.events_dir,
            self._event(
                event_id=event_id,
                request=request,
                plan=context.plan,
                computed_mode=context.computed_plan.mode,
                target_sha=context.target_sha,
                deployed_sha=context.target_sha,
                preflight=context.preflight,
                archive_bytes=context.archive_bytes,
                image_count_before=context.image_count_before,
                image_count_after=context.image_count_after,
                disk_used_after=context.disk_used_after,
                target_durations_ms=context.target_durations_ms,
                cleanup_reclaimed_bytes=context.cleanup_reclaimed_bytes,
                rollback_status="not_needed|cleanup:pending|archive_cleanup:pending",
                final_health="healthy",
                affected_services=tuple(context.touched_services),
                started_at=context.started_at,
                completed_at=completed_at,
            ),
        )
        write_state(self.state_path, state)

        cleanup_statuses: list[str] = []
        try:
            retain_release_directories(
                self.releases_dir,
                self._protected_release_shas(context),
            )
            cleanup_statuses.append("release_completed")
        except Exception:
            cleanup_statuses.append("release_failed")

        if context.plan.mode is DeployMode.FULL_IMAGE:
            try:
                context.cleanup_reclaimed_bytes = self._remove_images_with_metrics(
                    self.image_inventory(),
                    state,
                    self.referenced_image_ids(),
                    successful_full_deployment=True,
                )
                cleanup_statuses.append("image_completed")
            except Exception:
                context.cleanup_reclaimed_bytes = -1
                cleanup_statuses.append("image_failed")
        else:
            cleanup_statuses.append("image_not_applicable")

        context.archive_cleanup = self._cleanup_archive_safe(request.archive_path)
        cleanup_summary = "|".join(cleanup_statuses)
        context.cleanup_status = (
            f"{cleanup_summary}|archive_cleanup:{context.archive_cleanup}"
        )
        self._collect_post_metrics(context)
        cleanup_completed_at = self._safe_timestamp()
        audit_status = "recorded"
        try:
            write_event(
                self.events_dir,
                self._event(
                    event_id=event_id,
                    request=request,
                    plan=context.plan,
                    computed_mode=context.computed_plan.mode,
                    target_sha=context.target_sha,
                    deployed_sha=context.target_sha,
                    preflight=context.preflight,
                    archive_bytes=context.archive_bytes,
                    image_count_before=context.image_count_before,
                    image_count_after=context.image_count_after,
                    disk_used_after=context.disk_used_after,
                    target_durations_ms=context.target_durations_ms,
                    cleanup_reclaimed_bytes=context.cleanup_reclaimed_bytes,
                    rollback_status=(
                        f"not_needed|cleanup:{cleanup_summary}"
                        f"|archive_cleanup:{context.archive_cleanup}"
                    ),
                    final_health="healthy",
                    affected_services=tuple(context.touched_services),
                    started_at=context.started_at,
                    completed_at=cleanup_completed_at,
                ),
            )
        except Exception:
            audit_status = "cleanup_event_failed"
            context.cleanup_status += "|event_failed"

        cleanup_failed = "failed" in context.cleanup_status
        return DeployOutcome(
            ok=True,
            target_sha=context.target_sha,
            mode=context.plan.mode,
            activated_services=tuple(context.touched_services),
            rolled_back_services=(),
            message=(
                "deployment completed and remained healthy; post-success cleanup incomplete"
                if cleanup_failed
                else "deployment completed and remained healthy"
            ),
            archive_cleanup=context.archive_cleanup,
            audit_status=audit_status,
            image_count_after=context.image_count_after,
            disk_used_after=context.disk_used_after,
            cleanup_reclaimed_bytes=context.cleanup_reclaimed_bytes,
            cleanup_status=context.cleanup_status,
        )

    def _audit_plan(self, context: DeploymentContext) -> DeploymentPlan:
        if context.plan is not None:
            return context.plan
        if context.computed_plan is not None:
            return context.computed_plan
        return DeploymentPlan(
            mode=context.request.requested_mode,
            targets=context.request.requested_targets,
            changed_files=(),
            image_input_files=(),
            reasons=("deployment failed before classification",),
        )

    def _sanitized_audit_request(self, request: DeployRequest) -> DeployRequest:
        reason = request.emergency_reason
        if reason is not None and _SENSITIVE_REASON.search(reason):
            reason = None
        return replace(request, emergency_reason=reason)

    def _persist_audit_failure_locked(
        self, context: DeploymentContext, completed_at: str
    ) -> str:
        recovery = self._safe_manual_recovery(context.previous_state)
        audit_written = False
        lockout_written = False
        try:
            self._atomic_write(
                self.shared_dir / "deploy-audit-failure.json",
                (
                    json.dumps(
                        {
                            "completed_at": completed_at,
                            "status": "audit_failed",
                            "target_sha": context.target_sha or "unresolved",
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("ascii"),
            )
            audit_written = True
        except Exception:
            pass
        try:
            self._atomic_write(
                self.lockout_path,
                (
                    json.dumps(recovery, ensure_ascii=True, sort_keys=True) + "\n"
                ).encode("ascii"),
            )
            lockout_written = True
        except Exception:
            pass
        if context.previous_state is not None:
            try:
                write_state(
                    self.state_path,
                    replace(
                        context.previous_state,
                        completed_at=completed_at,
                        final_health="audit_failed",
                    ),
                )
            except Exception:
                pass
        return (
            "failed_durable"
            if audit_written and lockout_written
            else "failed_unpersisted"
        )

    def _verify_baseline_image_identity(
        self, state: DeploymentState, selectors: SelectorSnapshot | None
    ) -> None:
        if selectors is None or selectors.env_contents is None or not state.current_image:
            raise DeploymentError("active application image identity is unavailable")
        selected_tag = None
        try:
            for line in selectors.env_contents.decode("utf-8").splitlines():
                if line.startswith("APP_IMAGE_TAG="):
                    selected_tag = line.split("=", 1)[1].strip()
                    break
        except UnicodeDecodeError as error:
            raise DeploymentError("active application image identity is invalid") from error
        selected_image = (
            f"investment-knowledge-app:{selected_tag}" if selected_tag else None
        )
        if selected_image != state.current_image:
            raise DeploymentError(
                "durable and active application image identity do not match"
            )

        selected_result = self.runner.run(
            (
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Id}}",
                state.current_image,
            )
        )
        selected_image_id = selected_result.stdout.strip()
        if selected_result.returncode != 0 or not selected_image_id:
            raise DeploymentError(
                "durable application immutable image identity is unavailable"
            )

        result = self.runner.run(
            (
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.compose.project={self.compose_project_name}",
                "--format",
                "{{json .}}",
            )
        )
        if result.returncode != 0:
            raise DeploymentError("running application image identity could not be read")
        app_rows = tuple(
            row
            for row in _json_rows(result.stdout)
            if (
                str(row.get("Image") or "").startswith("investment-knowledge-app:")
                or _compose_service_from_row(row) in _APPLICATION_TARGETS
            )
        )
        if not app_rows:
            raise DeploymentError("running application image identity does not match state")
        for row in app_rows:
            container_id = str(row.get("ID") or "")
            if not container_id:
                raise DeploymentError(
                    "running application immutable image identity is unavailable"
                )
            container_result = self.runner.run(
                (
                    "docker",
                    "inspect",
                    "--format",
                    "{{.Image}}",
                    container_id,
                )
            )
            if (
                container_result.returncode != 0
                or container_result.stdout.strip() != selected_image_id
            ):
                raise DeploymentError(
                    "running application image identity does not match state: "
                    "immutable image identity mismatch"
                )

    def _verify_release_baseline(
        self, state: DeploymentState, selectors: SelectorSnapshot | None
    ) -> None:
        if (
            selectors is None
            or selectors.current_release is None
            or not state.current_sha
            or not state.active_release
        ):
            raise DeploymentError("active release baseline is unavailable")
        try:
            releases_root = self.releases_dir.resolve(strict=True)
            current_release = selectors.current_release.resolve(strict=True)
            durable_release = Path(state.active_release).resolve(strict=True)
        except OSError as error:
            raise DeploymentError("active release baseline is unavailable") from error
        if (
            not current_release.is_dir()
            or current_release.parent != releases_root
            or current_release.name != state.current_sha
            or durable_release != current_release
        ):
            raise DeploymentError(
                "durable and active release baseline do not match"
            )

    def _protected_release_shas(
        self, context: DeploymentContext
    ) -> tuple[str, ...]:
        protected = [context.target_sha]
        if context.previous_state is not None and context.previous_state.current_sha:
            protected.append(context.previous_state.current_sha)
        if context.selectors is not None and context.selectors.current_release is not None:
            snapshot = context.selectors.current_release
            try:
                releases_root = self.releases_dir.resolve(strict=True)
                snapshot = snapshot.resolve(strict=True)
            except OSError:
                snapshot = Path()
                releases_root = self.releases_dir
            if (
                snapshot.parent == releases_root
                and re.fullmatch(r"[0-9a-f]{40}", snapshot.name)
            ):
                protected.append(snapshot.name)
        return tuple(dict.fromkeys(value for value in protected if value))

    def _load_candidate_archive(
        self, context: DeploymentContext, archive_path: Path, expected_image: str
    ) -> None:
        inspect = (
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            expected_image,
        )
        before = self.runner.run(inspect)
        before_id = before.stdout.strip() if before.returncode == 0 else ""
        expected_digest = context.request.archive_sha256
        if expected_digest is None:
            raise DeploymentError("candidate image archive digest is required")
        try:
            observed_digest = _sha256_file(archive_path)
        except OSError as error:
            raise DeploymentError("candidate image archive digest could not be verified") from error
        if not hmac.compare_digest(observed_digest, expected_digest):
            raise DeploymentError("candidate image archive digest does not match admitted artifact")
        try:
            loaded = self.runner.run(("docker", "load", "--input", str(archive_path)))
        except Exception as error:
            raise DeploymentError("candidate image archive load could not run") from error
        context.candidate_loaded = True
        if loaded.returncode != 0:
            raise DeploymentError("candidate image archive load failed")
        loaded_images = {
            line.split(": ", 1)[1].strip()
            for line in loaded.stdout.splitlines()
            if line.startswith("Loaded image: ")
        }
        after = self.runner.run(inspect)
        after_id = after.stdout.strip() if after.returncode == 0 else ""
        if expected_image not in loaded_images or not after_id:
            raise DeploymentError("candidate archive image identity does not match target")
        if before_id and before_id == after_id and loaded_images != {expected_image}:
            raise DeploymentError("candidate archive image identity does not match target")

    def _cleanup_archive_safe(self, archive_path: Path | None) -> str:
        if archive_path is None:
            return "not_applicable"
        if not is_managed_image_archive(
            archive_path,
            allowed_parent=self.artifacts_dir,
        ):
            return "rejected_unmanaged"
        try:
            existed = archive_path.exists() or archive_path.is_symlink()
            self._remove_archive(archive_path)
            if archive_path.exists() or archive_path.is_symlink():
                return "failed"
            return "removed" if existed else "already_removed"
        except Exception:
            return "failed"

    def _cleanup_candidate_safe(self, context: DeploymentContext) -> str:
        if context.previous_state is None or not context.target_sha:
            return "not_applicable"
        try:
            candidate_tag = f"investment-knowledge-app:{context.target_sha}"
            candidate_images = tuple(
                image for image in self.image_inventory() if image.tag == candidate_tag
            )
            referenced_image_ids = self.referenced_image_ids()
            selected = select_managed_images_for_removal(
                candidate_images,
                current_image=context.previous_state.current_image,
                previous_image=context.previous_state.previous_image,
                referenced_image_ids=referenced_image_ids,
            )
            reclaimed = self._remove_images_with_metrics(
                candidate_images,
                context.previous_state,
                referenced_image_ids,
                successful_full_deployment=False,
            )
            if reclaimed >= 0:
                context.cleanup_reclaimed_bytes = reclaimed
            return "removed" if selected else "preserved_referenced"
        except Exception:
            return "failed"

    def _remove_images_with_metrics(
        self,
        images: tuple[ImageRecord, ...],
        state: DeploymentState,
        referenced_image_ids: set[str],
        *,
        successful_full_deployment: bool,
    ) -> int:
        removable = select_managed_images_for_removal(
            images,
            current_image=state.current_image,
            previous_image=state.previous_image,
            referenced_image_ids=referenced_image_ids,
        )
        reclaimed = 0
        metrics_available = True
        for image_id in removable:
            result = self.runner.run(
                ("docker", "image", "inspect", "--format", "{{.Size}}", image_id)
            )
            try:
                reclaimed += int(result.stdout.strip())
            except (ValueError, TypeError):
                metrics_available = False
        remove_managed_images(
            self.runner,
            images,
            state,
            referenced_image_ids,
            successful_full_deployment=successful_full_deployment,
            prune_builder_cache=successful_full_deployment,
        )
        return reclaimed if metrics_available else -1

    def _collect_post_metrics(self, context: DeploymentContext) -> None:
        try:
            context.image_count_after = len(
                {image.image_id for image in self.image_inventory()}
            )
        except Exception:
            context.image_count_after = -1
        try:
            context.disk_used_after = self.resource_collector(
                self.runner
            ).disk_used_percent
        except Exception:
            context.disk_used_after = -1.0

    def _handle_failure_locked(
        self, context: DeploymentContext, error: Exception
    ) -> DeployOutcome:
        rollback = RollbackResult((), (), (), False, False)
        rollback_attempted = bool(
            (context.selector_journal.touched or context.touched_services)
            and context.selectors is not None
            and context.previous_state is not None
        )
        if rollback_attempted:
            rollback = self._rollback(context)
        rollback_status = (
            "succeeded"
            if rollback_attempted and rollback.ok
            else "rollback_failed"
            if rollback_attempted
            else "not_started"
        )
        manual_recovery = None
        lockout_persisted = True
        completed_at = self._safe_timestamp()
        if rollback_attempted and not rollback.ok:
            manual_recovery = self._safe_manual_recovery(context.previous_state)
            lockout_persisted = self._persist_lockout_with_fallback(
                context.previous_state,
                context.target_sha,
                completed_at,
                manual_recovery,
            )
        if context.candidate_loaded and context.previous_state is not None:
            context.cleanup_status = self._cleanup_candidate_safe(context)
        context.archive_cleanup = self._cleanup_archive_safe(
            context.request.archive_path
        )
        self._collect_post_metrics(context)

        audit_plan = self._audit_plan(context)
        audit_request = self._sanitized_audit_request(context.request)
        audit_status = "recorded"
        try:
            write_event(
                self.events_dir,
                self._event(
                    event_id=self._event_id(
                        context.target_sha or "unresolved",
                        context.started_at,
                        context.request.external_event_id,
                    ),
                    request=audit_request,
                    plan=audit_plan,
                    computed_mode=(
                        context.computed_plan.mode
                        if context.computed_plan is not None
                        else audit_plan.mode
                    ),
                    target_sha=context.target_sha or "unresolved",
                    deployed_sha=None,
                    preflight=context.preflight,
                    archive_bytes=context.archive_bytes,
                    image_count_before=context.image_count_before,
                    image_count_after=context.image_count_after,
                    disk_used_after=context.disk_used_after,
                    target_durations_ms=context.target_durations_ms,
                    cleanup_reclaimed_bytes=context.cleanup_reclaimed_bytes,
                    rollback_status=(
                        f"{rollback_status}|archive_cleanup:{context.archive_cleanup}"
                        f"|candidate_cleanup:{context.cleanup_status}"
                    ),
                    final_health=(
                        "rollback_failed"
                        if rollback_attempted and not rollback.ok
                        else "unhealthy"
                    ),
                    affected_services=tuple(context.touched_services),
                    started_at=context.started_at,
                    completed_at=completed_at,
                    failure_category=(
                        "source_policy_rejected"
                        if isinstance(error, SourcePolicyError)
                        else None
                    ),
                ),
            )
        except Exception:
            audit_status = self._persist_audit_failure_locked(context, completed_at)

        message = self._safe_message(error)
        if audit_status == "failed_durable":
            message = f"{message}; audit persistence failed; deployment locked out"
            manual_recovery = self._load_lockout_recovery()
        elif audit_status == "failed_unpersisted":
            message = f"{message}; audit persistence failed"
        if not lockout_persisted:
            message = f"{message}; deployment lockout persistence failed"
        return DeployOutcome(
            ok=False,
            target_sha=context.target_sha,
            mode=(context.plan.mode if context.plan else context.request.requested_mode),
            activated_services=tuple(context.touched_services),
            rolled_back_services=rollback.successful_services,
            message=message,
            manual_recovery=manual_recovery,
            rollback_failures=rollback.service_failures,
            archive_cleanup=context.archive_cleanup,
            audit_status=audit_status,
            image_count_after=context.image_count_after,
            disk_used_after=context.disk_used_after,
            cleanup_reclaimed_bytes=context.cleanup_reclaimed_bytes,
            cleanup_status=context.cleanup_status,
            failure_category=(
                "source_policy_rejected"
                if isinstance(error, SourcePolicyError)
                else None
            ),
        )

    def _validate_request(
        self, request: DeployRequest, plan: DeploymentPlan
    ) -> DeploymentPlan:
        if request.emergency_reason is not None and len(request.emergency_reason.strip()) < 20:
            raise DeploymentError("emergency reason must be at least 20 characters")
        if request.emergency_reason is not None and _SENSITIVE_REASON.search(request.emergency_reason):
            raise DeploymentError("emergency reason contains protected material")
        legacy_omitted_targets = not request.requested_targets
        requested_targets = (
            plan.targets if legacy_omitted_targets else request.requested_targets
        )
        for target in requested_targets:
            if target == "postgres":
                raise DeploymentError("PostgreSQL cannot be an application deployment target")
            if target not in _APPLICATION_TARGETS and not target.endswith(".service"):
                raise DeploymentError("deployment request contains an unknown target")
        legacy_quick_matches = (
            legacy_omitted_targets
            and request.requested_mode is DeployMode.TARGETED_QUICK
            and plan.mode
            in {
                DeployMode.NO_DEPLOY,
                DeployMode.TARGETED_QUICK,
                DeployMode.CONFIG_RESTART,
            }
        )
        if (
            not legacy_quick_matches
            and (
                request.requested_mode is not plan.mode
                or requested_targets != plan.targets
            )
        ):
            if request.emergency_reason is not None:
                if requested_targets != plan.targets:
                    raise DeploymentError(
                        "emergency override cannot change server-computed deployment targets"
                    )
                if MODE_RANK[request.requested_mode] < MODE_RANK[plan.mode]:
                    raise DeploymentError(
                        "emergency override cannot reduce the server-computed deployment risk"
                    )
                if (
                    request.requested_mode is DeployMode.FULL_IMAGE
                    and plan.mode is not DeployMode.FULL_IMAGE
                    and requested_targets != tuple(sorted(APPLICATION_SERVICES))
                ):
                    raise DeploymentError(
                        "emergency full image deployment requires the complete application target set"
                    )
                return DeploymentPlan(
                    mode=request.requested_mode,
                    targets=requested_targets,
                    changed_files=plan.changed_files,
                    image_input_files=plan.image_input_files,
                    reasons=(*plan.reasons, "emergency operator override"),
                )
            raise DeploymentError("requested deployment plan does not match server classification")
        return plan

    def _switch_selectors(
        self, context: DeploymentContext, release: Path, selected_image: str | None
    ) -> None:
        if context.selectors is None:
            raise DeploymentError("deployment selectors were not snapshotted")
        if context.selectors.current_release is not None:
            context.selector_journal.previous_attempted = True
            self._replace_symlink(
                self.previous_link, context.selectors.current_release
            )
        context.selector_journal.current_attempted = True
        self._replace_symlink(self.current_link, release)
        if selected_image:
            context.selector_journal.image_attempted = True
            self._write_image_tag(selected_image)

    def _activate_target(self, target: str, release: Path) -> None:
        if target.endswith(".service"):
            self._run_checked(("systemctl", "restart", target), f"host unit {target} failed to restart")
            return
        with _compose_environment(self.compose_project_name):
            self._run_checked(
                (
                    "docker",
                    "compose",
                    "-f",
                    str(release / "docker-compose.prod.yml"),
                    "up",
                    "-d",
                    "--no-build",
                    "--no-deps",
                    "--force-recreate",
                    target,
                ),
                f"application service {target} failed to activate",
            )

    def _compose_services(self, release: Path) -> set[str]:
        with _compose_environment(self.compose_project_name):
            result = self.runner.run(
                (
                    "docker",
                    "compose",
                    "-f",
                    str(release / "docker-compose.prod.yml"),
                    "config",
                    "--services",
                )
            )
        if result.returncode != 0:
            raise DeploymentError("previous release services could not be read")
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def _remove_target(self, target: str, release: Path) -> None:
        with _compose_environment(self.compose_project_name):
            self._run_checked(
                (
                    "docker",
                    "compose",
                    "-f",
                    str(release / "docker-compose.prod.yml"),
                    "rm",
                    "--force",
                    "--stop",
                    target,
                ),
                f"new application service {target} failed to roll back",
            )

    def _rollback(self, context: DeploymentContext) -> RollbackResult:
        if context.selectors is None or context.previous_state is None:
            return RollbackResult((), (), ("snapshot",), True, True)

        selector_failures: list[str] = []
        if context.selector_journal.current_attempted:
            try:
                self._restore_link(
                    self.current_link, context.selectors.current_release
                )
            except Exception:
                selector_failures.append("current_release")
        if context.selector_journal.previous_attempted:
            try:
                self._restore_link(
                    self.previous_link, context.selectors.previous_release
                )
            except Exception:
                selector_failures.append("previous_release")
        if context.selector_journal.image_attempted:
            try:
                self._restore_env(context.selectors.env_contents)
            except Exception:
                selector_failures.append("current_image")

        successful_services: list[str] = []
        service_failures: list[str] = []
        previous_services: set[str] | None = None
        if context.selectors.current_release is None:
            selector_failures.append("previous_services")
        else:
            try:
                previous_services = self._compose_services(
                    context.selectors.current_release
                )
            except Exception:
                selector_failures.append("previous_services")
        for target in reversed(context.touched_services):
            if previous_services is None:
                service_failures.append(target)
                continue
            try:
                if context.selectors.current_release is None:
                    raise DeploymentError("previous release is unavailable")
                if target.endswith(".service") or target in previous_services:
                    self._activate_target(target, context.selectors.current_release)
                else:
                    self._remove_target(
                        target, self.releases_dir / context.target_sha
                    )
                successful_services.append(target)
            except Exception:
                service_failures.append(target)

        aggregate_failed = False
        try:
            self.health.check_aggregate(context.request.feature_routes)
        except Exception:
            aggregate_failed = True

        state_failed = False
        try:
            write_state(self.state_path, context.previous_state)
        except Exception:
            state_failed = True

        return RollbackResult(
            successful_services=tuple(successful_services),
            service_failures=tuple(service_failures),
            selector_failures=tuple(selector_failures),
            aggregate_failed=aggregate_failed,
            state_failed=state_failed,
        )

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
        cleanup_reclaimed_bytes: int,
        rollback_status: str,
        final_health: str,
        affected_services: tuple[str, ...],
        started_at: str,
        completed_at: str,
        failure_category: str | None = None,
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
            disk_used_before=float(preflight.get("disk_used_percent", -1.0)),
            disk_used_after=disk_used_after,
            target_durations_ms=target_durations_ms,
            rollback_status=rollback_status,
            cleanup_reclaimed_bytes=cleanup_reclaimed_bytes,
            emergency_override=request.emergency_reason is not None,
            emergency_reason=request.emergency_reason,
            final_health=final_health,
            started_at=started_at,
            completed_at=completed_at,
            source=request.source,
            requested_by=request.requested_by,
            failure_category=failure_category,
            feature_routes=request.feature_routes,
            stability_seconds=(60 if plan.mode is DeployMode.FULL_IMAGE else 30),
            affected_services=affected_services,
            route_smoke_checks=deployment_route_smoke_checks(request.feature_routes),
            archive_sha256=request.archive_sha256,
            artifact_cleanup_status=_artifact_cleanup_from_rollback(rollback_status),
        )

    def _preflight_observations(
        self,
        snapshot: ResourceSnapshot,
        archive_bytes: int | None,
        mode: DeployMode,
    ) -> dict[str, int | float | str]:
        start_required = required_available_memory_bytes(mode)
        observations: dict[str, int | float | str] = {
            "disk_available_bytes": snapshot.free_disk_bytes,
            "disk_used_percent": snapshot.disk_used_percent,
            "available_memory_bytes": snapshot.available_memory_bytes,
            "minimum_available_memory_bytes": snapshot.available_memory_bytes,
            "start_available_memory_bytes": snapshot.available_memory_bytes,
            "memory_policy_mode": mode.value,
            "required_available_memory_bytes": start_required,
            "start_required_available_memory_bytes": start_required,
            "source_valid": "valid",
            "lock_valid": "held",
            "required_free_bytes": 8 * 1024**3,
        }
        if archive_bytes is not None:
            observations["archive_bytes"] = archive_bytes
        if mode is DeployMode.FULL_IMAGE:
            observations["runtime_required_available_memory_bytes"] = (
                required_available_memory_bytes(
                    mode,
                    memory_phase="before_activation",
                )
            )
        return observations

    def _record_full_image_memory_phase(
        self,
        context: DeploymentContext,
        memory_phase: str,
    ) -> None:
        snapshot = self.resource_collector(self.runner)
        available = snapshot.available_memory_bytes
        required = required_available_memory_bytes(
            DeployMode.FULL_IMAGE,
            memory_phase=memory_phase,
        )
        context.disk_used_after = snapshot.disk_used_percent
        context.preflight[f"{memory_phase}_available_memory_bytes"] = available
        context.preflight[f"{memory_phase}_required_available_memory_bytes"] = required
        context.preflight["minimum_available_memory_bytes"] = min(
            int(context.preflight.get("minimum_available_memory_bytes", available)),
            available,
        )
        if memory_phase == "before_activation":
            context.preflight["activation_memory_check_count"] = (
                int(context.preflight.get("activation_memory_check_count", 0)) + 1
            )
        if available < required:
            label = "post-load" if memory_phase == "post_load" else "before activation"
            raise DeploymentError(
                "deployment resource preflight failed "
                f"{label}: available memory must be at least {required // (1024**2)} MiB"
            )

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

    def _persist_lockout_with_fallback(
        self,
        previous_state: DeploymentState,
        target_sha: str,
        completed_at: str,
        manual_recovery: dict[str, str],
    ) -> bool:
        try:
            self._persist_lockout(
                previous_state,
                target_sha,
                completed_at,
                manual_recovery,
            )
            return True
        except Exception:
            try:
                self._atomic_write(
                    self.lockout_path,
                    (
                        json.dumps(
                            manual_recovery, ensure_ascii=True, sort_keys=True
                        )
                        + "\n"
                    ).encode("ascii"),
                )
            except Exception:
                return False
            try:
                write_state(
                    self.state_path,
                    replace(
                        previous_state,
                        completed_at=completed_at,
                        final_health="rollback_failed",
                    ),
                )
            except Exception:
                pass
            return True

    def _manual_recovery(
        self, state: DeploymentState | None
    ) -> dict[str, str]:
        try:
            with _compose_environment(self.compose_project_name):
                result = self.runner.run(
                    (
                        "docker",
                        "compose",
                        "-f",
                        str(self.current_link / "docker-compose.prod.yml"),
                        "ps",
                        "--format",
                        "json",
                    )
                )
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

    def _safe_manual_recovery(
        self, state: DeploymentState | None
    ) -> dict[str, str]:
        try:
            return self._manual_recovery(state)
        except Exception:
            return {
                "current_release": "unknown",
                "current_image": (
                    state.current_image if state and state.current_image else "unknown"
                ),
                "container_status": "[]",
                "disk": json.dumps(
                    {"available_bytes": "unknown", "used_percent": "unknown"}
                ),
                "memory": json.dumps({"available_bytes": "unknown"}),
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
        return self._safe_manual_recovery(None)

    def _remove_archive(self, archive_path: Path | None) -> None:
        if archive_path is not None and (archive_path.is_file() or archive_path.is_symlink()):
            archive_path.unlink()

    def _run_checked(self, command: tuple[str, ...], message: str) -> None:
        result = self.runner.run(command)
        if result.returncode != 0:
            lines = [line.strip() for line in (result.stderr or result.stdout).splitlines() if line.strip()]
            detail = re.sub(r"[\x00-\x1f\x7f]", " ", lines[-1])[:300] if lines else ""
            if detail and not _SENSITIVE_REASON.search(detail):
                raise DeploymentError(f"{message}: {detail}")
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

    def _event_id(
        self,
        target_sha: str,
        started_at: str,
        external_event_id: str | None = None,
    ) -> str:
        if external_event_id and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", external_event_id):
            return external_event_id
        compact_time = started_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
        return f"{compact_time}-{target_sha[:12]}"

    def _timestamp(self) -> str:
        return self.clock.now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _safe_timestamp(self) -> str:
        try:
            return self._timestamp()
        except Exception:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _safe_message(self, error: Exception) -> str:
        if isinstance(error, (DeploymentError, SourcePolicyError, SourceRefreshError)):
            return str(error)
        return "deployment failed; inspect the product-safe deployment event"


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


def _safe_diagnostic_summary(output: str) -> str:
    signatures = (
        (("modulenotfounderror", "importerror"), "Python module import failed"),
        (("psycopg", "operationalerror"), "database connection failed during startup"),
        (("permission denied",), "startup permission check failed"),
        (("no such file or directory",), "startup file was not found"),
        (("traceback (most recent call last)",), "Python startup failed"),
    )
    for line in reversed(output.splitlines()):
        normalized = line.lower()
        for markers, summary in signatures:
            if any(marker in normalized for marker in markers):
                return summary
    return ""


def _compose_service_from_row(row: dict[str, object]) -> str | None:
    labels = str(row.get("Labels") or "")
    prefix = "com.docker.compose.service="
    for label in labels.split(","):
        if label.startswith(prefix):
            return label.removeprefix(prefix)
    return None


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
    parser.add_argument("--archive-sha256")
    parser.add_argument("--emergency-reason")
    parser.add_argument("--feature-routes")
    parser.add_argument("--external-event-id")
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
    if any(not is_safe_feature_route(route) for route in feature_routes):
        parser.error("feature routes must be absolute local paths")

    runner = SubprocessRunner()
    request = DeployRequest(
        requested_ref=arguments.ref,
        requested_mode=DeployMode(arguments.mode),
        requested_targets=_csv_values(arguments.targets),
        archive_path=arguments.archive,
        emergency_reason=arguments.emergency_reason,
        feature_routes=feature_routes,
        external_event_id=arguments.external_event_id,
        archive_sha256=arguments.archive_sha256,
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
