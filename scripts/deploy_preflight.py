from __future__ import annotations

import errno
import fcntl
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

try:
    from scripts.deploy_contract import DeployMode
    from scripts.deploy_support import CommandRunner
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from deploy_contract import DeployMode
    from deploy_support import CommandRunner


GIB = 1024**3
MIB = 1024**2
_DOCKER_TIMEOUT_SECONDS = 10
_LOCK_RETRY_SECONDS = 0.05


class DeployPreflightError(RuntimeError):
    """Raised when deployment preflight cannot establish a safe runtime."""


@dataclass(frozen=True)
class ResourceSnapshot:
    free_disk_bytes: int
    disk_used_percent: float
    available_memory_bytes: int


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    errors: tuple[str, ...]


def collect_resources(runner: CommandRunner) -> ResourceSnapshot:
    disk_result = _run_resource_probe(runner, ("df", "-Pk", "/"), "disk")
    free_disk_bytes, disk_used_percent = _parse_disk_output(disk_result.stdout)

    memory_result = _run_resource_probe(runner, ("free", "-b"), "memory")
    available_memory_bytes = _parse_memory_output(memory_result.stdout)
    return ResourceSnapshot(
        free_disk_bytes=free_disk_bytes,
        disk_used_percent=disk_used_percent,
        available_memory_bytes=available_memory_bytes,
    )


def evaluate_preflight(
    snapshot: ResourceSnapshot,
    mode: DeployMode,
    archive_bytes: int | None,
) -> PreflightResult:
    errors: list[str] = []
    if snapshot.free_disk_bytes < 8 * GIB:
        errors.append("free disk must be at least 8 GiB")
    if snapshot.disk_used_percent > 80.0:
        errors.append("disk use must not exceed 80%")
    if snapshot.available_memory_bytes < 512 * MIB:
        errors.append("available memory must be at least 512 MiB")
    if mode is DeployMode.FULL_IMAGE:
        if archive_bytes is None:
            errors.append("full image requires a known archive size")
        elif archive_bytes < 0:
            errors.append("full image archive size must not be negative")
        elif snapshot.free_disk_bytes < archive_bytes * 2 + 2 * GIB:
            errors.append("full image requires twice the archive size plus 2 GiB free")
    return PreflightResult(ok=not errors, errors=tuple(errors))


def validate_runtime(runner: CommandRunner, compose_file: Path) -> tuple[str, ...]:
    compose = ("docker", "compose", "-f", str(compose_file))

    docker_result = _run_runtime_probe(
        runner,
        ("docker", "info"),
        timeout=_DOCKER_TIMEOUT_SECONDS,
        timeout_message="docker preflight timed out after 10 seconds",
        failure_message="docker is unavailable or unhealthy",
    )
    docker_label = _successful_label(docker_result, "docker_health")

    compose_result = _run_runtime_probe(
        runner,
        (*compose, "config", "--quiet"),
        timeout=None,
        timeout_message="compose validation timed out",
        failure_message="compose configuration is invalid",
    )
    compose_label = _successful_label(compose_result, "compose_valid")

    postgres_container = _run_runtime_probe(
        runner,
        (*compose, "ps", "--status", "running", "postgres"),
        timeout=None,
        timeout_message="postgresql container probe timed out",
        failure_message="postgresql container is not running",
    )
    _successful_label(postgres_container, "postgresql_health")

    health_result = _run_runtime_probe(
        runner,
        (*compose, "exec", "-T", "postgres", "pg_isready"),
        timeout=None,
        timeout_message="postgresql health check timed out",
        failure_message="postgresql health check failed",
    )
    health_label = _successful_label(health_result, "postgresql_health")
    return (docker_label, compose_label, health_label)


@contextmanager
def deployment_lock(path: Path, timeout_seconds: int = 0) -> Iterator[None]:
    if timeout_seconds < 0:
        raise ValueError("lock timeout must not be negative")

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN):
                    raise DeployPreflightError("deployment lock could not be acquired") from error
                if timeout_seconds == 0 or time.monotonic() >= deadline:
                    raise DeployPreflightError("another deployment is active")
                time.sleep(min(_LOCK_RETRY_SECONDS, max(0.0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _run_resource_probe(
    runner: CommandRunner, command: tuple[str, ...], resource: str
):
    try:
        result = runner.run(command)
    except (OSError, TimeoutError, subprocess.TimeoutExpired) as error:
        raise DeployPreflightError(f"resource {resource} probe could not run") from error
    if result.returncode != 0:
        raise DeployPreflightError(f"resource {resource} probe failed (exit code {result.returncode})")
    return result


def _run_runtime_probe(
    runner: CommandRunner,
    command: tuple[str, ...],
    *,
    timeout: int | None,
    timeout_message: str,
    failure_message: str,
):
    try:
        result = runner.run(command, timeout=timeout)
    except (TimeoutError, subprocess.TimeoutExpired):
        raise DeployPreflightError(timeout_message)
    except OSError as error:
        raise DeployPreflightError(failure_message) from error
    if result.returncode != 0:
        raise DeployPreflightError(f"{failure_message} (exit code {result.returncode})")
    return result


def _successful_label(result: object, label: str) -> str:
    del result
    return label


def _parse_disk_output(output: str) -> tuple[int, float]:
    lines = [line.split() for line in output.splitlines() if line.strip()]
    if len(lines) < 2:
        raise DeployPreflightError("resource disk probe returned invalid output")
    fields = lines[-1]
    if len(fields) < 5 or not fields[4].endswith("%"):
        raise DeployPreflightError("resource disk probe returned invalid output")
    try:
        available_kib = int(fields[3])
        used_percent = float(fields[4][:-1])
    except ValueError as error:
        raise DeployPreflightError("resource disk probe returned invalid output") from error
    if available_kib < 0 or not 0.0 <= used_percent <= 100.0:
        raise DeployPreflightError("resource disk probe returned invalid output")
    return available_kib * 1024, used_percent


def _parse_memory_output(output: str) -> int:
    memory_lines = [line.split() for line in output.splitlines() if line.strip().startswith("Mem:")]
    if len(memory_lines) != 1 or len(memory_lines[0]) < 7:
        raise DeployPreflightError("resource memory probe returned invalid output")
    try:
        available_bytes = int(memory_lines[0][6])
    except ValueError as error:
        raise DeployPreflightError("resource memory probe returned invalid output") from error
    if available_bytes < 0:
        raise DeployPreflightError("resource memory probe returned invalid output")
    return available_bytes
