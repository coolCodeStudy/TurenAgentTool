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


_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_STATE_FIELDS = tuple(field.name for field in fields(DeploymentState))
_EVENT_FIELDS = tuple(field.name for field in fields(DeploymentEvent))


def resolve_production_target(repo: Path, requested_ref: str, runner: CommandRunner) -> str:
    """Resolve an approved production ref and prove it is reachable from origin/main."""
    if requested_ref == "main":
        result = runner.run(("git", "-C", str(repo), "rev-parse", "origin/main"))
        if result.returncode != 0:
            raise SourcePolicyError(f"failed to resolve origin/main: {result.stderr.strip()}")
        sha = result.stdout.strip()
        if not _SHA_PATTERN.fullmatch(sha):
            raise SourcePolicyError("failed to resolve origin/main to a 40-character SHA")
    elif _SHA_PATTERN.fullmatch(requested_ref):
        sha = requested_ref
    else:
        raise SourcePolicyError("production ref must be main or a 40-character SHA")

    result = runner.run(
        ("git", "-C", str(repo), "merge-base", "--is-ancestor", sha, "origin/main")
    )
    if result.returncode != 0:
        raise SourcePolicyError(f"{sha} is not reachable from origin/main")
    return sha


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
    if not isinstance(event.event_id, str) or not event.event_id:
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
        not isinstance(key, str) or not _integer(value)
        for key, value in event.target_durations_ms.items()
    ):
        raise StateFormatError("target_durations_ms must map strings to integers")
    if not isinstance(event.emergency_override, bool):
        raise StateFormatError("emergency_override must be a boolean")


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise StateFormatError(f"{name} must be a string")
    return value


def _optional_string(value: object, name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise StateFormatError(f"{name} must be a string or null")
    return value


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
        raise StateFormatError(f"{name} must be a list of strings")
    return tuple(value)


def _metrics_dict(value: object, name: str) -> dict[str, int | float | str]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(item, (int, float, str)) or isinstance(item, bool)
        for key, item in value.items()
    ):
        raise StateFormatError(f"{name} must map strings to numbers or strings")
    return value


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
