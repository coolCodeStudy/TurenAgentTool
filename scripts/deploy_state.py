from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

try:
    from scripts.deploy_support import CommandRunner
except ModuleNotFoundError:  # Direct execution through scripts/deploy_state.py.
    from deploy_support import CommandRunner


class SourcePolicyError(ValueError):
    """Raised when a production deployment target is not trusted."""


class SourceRefreshError(RuntimeError):
    """Raised when authoritative repository state cannot be refreshed or resolved."""


class StateFormatError(ValueError):
    """Raised when durable deployment state or events do not match the schema."""


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
    source: str = "direct"
    requested_by: str = "unspecified"
    failure_category: str | None = None


_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_STATE_FIELDS = tuple(field.name for field in fields(DeploymentState))
_PREFLIGHT_OBSERVATION_TYPES: dict[str, type | tuple[type, ...]] = {
    "disk_available_bytes": int,
    "disk_used_percent": (int, float),
    "available_memory_bytes": int,
    "docker_response_ms": (int, float),
    "docker_health": str,
    "postgresql_health": str,
    "compose_valid": str,
    "source_valid": str,
    "lock_valid": str,
    "archive_bytes": int,
    "required_free_bytes": int,
}
_SENSITIVE_TEXT = re.compile(
    r"(?i)\b(?:database[_-]?url|password|passwd|token|api[_-]?key|secret|credential|"
    r"authorization|bearer|private[_-]?key|access[_-]?key)\b"
)
_ASSIGNMENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\s*=\s*\S+")
_AUTHENTICATED_URI = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*:\/\/[^\s/:@]+:[^\s@]+@[^\s]+"
)
_BARE_CREDENTIAL = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])[^\s/:@]+:[^\s/@]+@[^\s]+"
)
_DEPLOY_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}")


def resolve_production_target(repo: Path, requested_ref: str, runner: CommandRunner) -> str:
    """Resolve an approved production ref to the freshly fetched origin/main tip."""
    if requested_ref != "main" and not _SHA_PATTERN.fullmatch(requested_ref):
        raise SourcePolicyError("production ref must be main or a 40-character SHA")

    refreshed = runner.run(("git", "-C", str(repo), "fetch", "origin", "main"))
    if refreshed.returncode != 0:
        raise SourceRefreshError("production source refresh failed")

    result = runner.run(("git", "-C", str(repo), "rev-parse", "origin/main"))
    if result.returncode != 0:
        raise SourceRefreshError("production source resolution failed")
    authoritative_sha = result.stdout.strip()
    if not _SHA_PATTERN.fullmatch(authoritative_sha):
        raise SourceRefreshError("production source resolution failed")

    if requested_ref != "main" and requested_ref != authoritative_sha:
        raise SourcePolicyError(
            "production ref must equal the current origin/main tip; integrate the commit "
            "into authoritative main, push main, and dispatch the new main tip"
        )
    return authoritative_sha


def resolve_historical_production_target(
    repo: Path,
    deployed_sha: str,
    runner: CommandRunner,
) -> str:
    """Trust an existing deployed baseline only when it remains on origin/main history."""
    if not _SHA_PATTERN.fullmatch(deployed_sha):
        raise SourcePolicyError("historical production baseline must be a 40-character SHA")

    refreshed = runner.run(("git", "-C", str(repo), "fetch", "origin", "main"))
    if refreshed.returncode != 0:
        raise SourceRefreshError("production source refresh failed")

    reachable = runner.run(
        (
            "git",
            "-C",
            str(repo),
            "merge-base",
            "--is-ancestor",
            deployed_sha,
            "origin/main",
        )
    )
    if reachable.returncode != 0:
        raise SourcePolicyError(
            "historical production baseline is not reachable from authoritative origin/main"
        )
    return deployed_sha


def load_state(path: Path) -> DeploymentState:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise StateFormatError(f"invalid deployment state JSON: {path}") from error
    except OSError:
        raise

    return _state_from_payload(payload, path)


def write_state(path: Path, state: DeploymentState) -> None:
    payload = _state_payload(state)
    _atomic_write(path, payload)


def write_event(events_dir: Path, event: DeploymentEvent) -> Path:
    payload = _event_payload(event)
    if not event.event_id or Path(event.event_id).name != event.event_id:
        raise ValueError("event_id must be a single path component")

    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / f"{event.event_id}.json"
    _atomic_write(path, payload)
    return path


def _state_payload(state: DeploymentState) -> dict[str, Any]:
    _validate_state(state)
    payload = asdict(state)
    payload["targets"] = list(state.targets)
    return payload


def _event_payload(event: DeploymentEvent) -> dict[str, Any]:
    _validate_event(event)
    payload = asdict(event)
    payload["changed_image_inputs"] = list(event.changed_image_inputs)
    payload["targets"] = list(event.targets)
    return payload


def _state_from_payload(payload: object, path: Path) -> DeploymentState:
    if not isinstance(payload, dict) or set(payload) != set(_STATE_FIELDS):
        raise StateFormatError(f"deployment state has an invalid schema: {path}")
    if not isinstance(payload["schema_version"], int) or isinstance(payload["schema_version"], bool):
        raise StateFormatError("deployment state schema_version must be an integer")
    if payload["schema_version"] != 1:
        raise StateFormatError(f"unsupported deployment state schema_version: {payload['schema_version']}")

    try:
        state = DeploymentState(
            schema_version=payload["schema_version"],
            current_sha=_optional_string(payload["current_sha"], "current_sha"),
            previous_sha=_optional_string(payload["previous_sha"], "previous_sha"),
            current_image=_optional_string(payload["current_image"], "current_image"),
            previous_image=_optional_string(payload["previous_image"], "previous_image"),
            active_release=_optional_string(payload["active_release"], "active_release"),
            previous_release=_optional_string(payload["previous_release"], "previous_release"),
            last_mode=_optional_string(payload["last_mode"], "last_mode"),
            requested_ref=_optional_string(payload["requested_ref"], "requested_ref"),
            resolved_ref=_optional_string(payload["resolved_ref"], "resolved_ref"),
            targets=_string_tuple(payload["targets"], "targets"),
            last_event_id=_optional_string(payload["last_event_id"], "last_event_id"),
            started_at=_optional_string(payload["started_at"], "started_at"),
            completed_at=_optional_string(payload["completed_at"], "completed_at"),
            preflight=_metrics_dict(payload["preflight"], "preflight"),
            final_health=_optional_string(payload["final_health"], "final_health"),
        )
    except (TypeError, ValueError) as error:
        raise StateFormatError(f"deployment state has invalid field values: {path}") from error
    _validate_state(state)
    return state


def _validate_state(state: DeploymentState) -> None:
    if not isinstance(state.schema_version, int) or isinstance(state.schema_version, bool):
        raise StateFormatError("deployment state schema_version must be an integer")
    if state.schema_version != 1:
        raise StateFormatError(f"unsupported deployment state schema_version: {state.schema_version}")
    for name in (
        "current_sha",
        "previous_sha",
        "current_image",
        "previous_image",
        "active_release",
        "previous_release",
        "last_mode",
        "requested_ref",
        "resolved_ref",
        "last_event_id",
        "started_at",
        "completed_at",
        "final_health",
    ):
        _optional_string(getattr(state, name), name)
    _string_tuple(state.targets, "targets")
    _metrics_dict(state.preflight, "preflight")


def _validate_event(event: DeploymentEvent) -> None:
    _required_string(event.event_id, "event_id")
    if not event.event_id:
        raise StateFormatError("event_id must be a non-empty string")
    for name in (
        "requested_mode",
        "computed_mode",
        "target_sha",
        "rollback_status",
        "final_health",
        "started_at",
        "completed_at",
    ):
        _required_string(getattr(event, name), name)
    _optional_string(event.deployed_sha, "deployed_sha")
    _optional_string(event.emergency_reason, "emergency_reason")
    _deploy_label(event.source, "source")
    _deploy_label(event.requested_by, "requested_by")
    _optional_string(event.failure_category, "failure_category")
    _string_tuple(event.changed_image_inputs, "changed_image_inputs")
    _string_tuple(event.targets, "targets")
    _metrics_dict(event.preflight, "preflight")
    if event.archive_bytes is not None and not _integer(event.archive_bytes):
        raise StateFormatError("archive_bytes must be an integer or null")
    for name in ("image_count_before", "image_count_after", "cleanup_reclaimed_bytes"):
        if not _integer(getattr(event, name)):
            raise StateFormatError(f"{name} must be an integer")
    for name in ("disk_used_before", "disk_used_after"):
        if not _number(getattr(event, name)):
            raise StateFormatError(f"{name} must be a number")
    if not isinstance(event.target_durations_ms, dict) or any(
        not isinstance(key, str) or not _integer(value) or _has_sensitive_material(key)
        for key, value in event.target_durations_ms.items()
    ):
        raise StateFormatError("target_durations_ms must map strings to integers")
    if not isinstance(event.emergency_override, bool):
        raise StateFormatError("emergency_override must be a boolean")


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise StateFormatError(f"{name} must be a string")
    _reject_sensitive_material(value, name)
    return value


def _deploy_label(value: object, name: str) -> str:
    validated = _required_string(value, name)
    if not _DEPLOY_LABEL.fullmatch(validated):
        raise StateFormatError(f"{name} must be a safe deployment label")
    return validated


def _optional_string(value: object, name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise StateFormatError(f"{name} must be a string or null")
    if value is not None:
        _reject_sensitive_material(value, name)
    return value


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
        raise StateFormatError(f"{name} must be a list of strings")
    for item in value:
        _reject_sensitive_material(item, name)
    return tuple(value)


def _metrics_dict(value: object, name: str) -> dict[str, int | float | str]:
    if not isinstance(value, dict):
        raise StateFormatError(f"{name} must be a deployment observation object")
    unknown_keys = set(value) - set(_PREFLIGHT_OBSERVATION_TYPES)
    if unknown_keys:
        raise StateFormatError(f"{name} contains unknown observation keys")
    for key, item in value.items():
        expected_type = _PREFLIGHT_OBSERVATION_TYPES[key]
        if isinstance(item, bool) or not isinstance(item, expected_type):
            raise StateFormatError(f"{name}.{key} has an invalid observation type")
        if isinstance(item, str):
            _reject_sensitive_material(item, f"{name}.{key}")
        elif item < 0 or (key == "disk_used_percent" and item > 100):
            raise StateFormatError(f"{name}.{key} has an invalid observation value")
    return value


def _has_sensitive_material(value: str) -> bool:
    return bool(
        _SENSITIVE_TEXT.search(value)
        or _ASSIGNMENT.search(value)
        or _AUTHENTICATED_URI.search(value)
        or _BARE_CREDENTIAL.search(value)
    )


def _reject_sensitive_material(value: str, name: str) -> None:
    if _has_sensitive_material(value):
        raise StateFormatError(f"{name} contains credential or environment material")


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
