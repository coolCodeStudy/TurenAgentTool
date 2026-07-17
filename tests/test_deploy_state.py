from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from scripts.deploy_state import (
    DeploymentEvent,
    DeploymentState,
    SourcePolicyError,
    StateFormatError,
    load_state,
    resolve_production_target,
    write_event,
    write_state,
)
from scripts.deploy_support import CommandResult


def ok(stdout: str) -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr="")


def sample_state(*, current_sha: str | None, previous_sha: str | None) -> DeploymentState:
    return DeploymentState(
        schema_version=1,
        current_sha=current_sha,
        previous_sha=previous_sha,
        current_image="investment-knowledge:current",
        previous_image="investment-knowledge:previous",
        active_release="/opt/investment-knowledge/releases/current",
        previous_release="/opt/investment-knowledge/releases/previous",
        last_mode="targeted_quick",
        requested_ref="main",
        resolved_ref=current_sha,
        targets=("mcp", "weekly-review-web"),
        last_event_id="event-1",
        started_at="2026-07-10T01:02:03Z",
        completed_at="2026-07-10T01:03:04Z",
        preflight=_valid_preflight(),
        final_health="healthy",
    )


def sample_event() -> DeploymentEvent:
    return DeploymentEvent(
        event_id="event-1",
        requested_mode="quick",
        computed_mode="targeted_quick",
        deployed_sha="b" * 40,
        target_sha="b" * 40,
        changed_image_inputs=("Dockerfile",),
        targets=("mcp", "weekly-review-web"),
        preflight=_valid_preflight(),
        archive_bytes=1234,
        image_count_before=2,
        image_count_after=3,
        disk_used_before=20.5,
        disk_used_after=22.0,
        target_durations_ms={"mcp": 120, "weekly-review-web": 240},
        rollback_status="not_needed",
        cleanup_reclaimed_bytes=456,
        emergency_override=False,
        emergency_reason=None,
        final_health="healthy",
        started_at="2026-07-10T01:02:03Z",
        completed_at="2026-07-10T01:03:04Z",
    )


class FakeRunner:
    def __init__(self, results: dict[tuple[str, ...], CommandResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        self.calls.append(command)
        return self.results.get(command, CommandResult(1, "", "missing fake result"))


class DeployStateTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.directory = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_resolves_main_to_origin_main_sha(self) -> None:
        runner = FakeRunner(
            {
                ("git", "-C", "/repo", "fetch", "origin", "main"): ok(""),
                ("git", "-C", "/repo", "rev-parse", "origin/main"): ok("a" * 40),
            }
        )

        self.assertEqual("a" * 40, resolve_production_target(Path("/repo"), "main", runner))

    def test_resolves_only_the_current_origin_main_full_sha(self) -> None:
        sha = "b" * 40
        runner = FakeRunner(
            {
                ("git", "-C", "/repo", "fetch", "origin", "main"): ok(""),
                ("git", "-C", "/repo", "rev-parse", "origin/main"): ok(sha),
            }
        )

        self.assertEqual(sha, resolve_production_target(Path("/repo"), sha, runner))
        self.assertEqual(
            [
                ("git", "-C", "/repo", "fetch", "origin", "main"),
                ("git", "-C", "/repo", "rev-parse", "origin/main"),
            ],
            runner.calls,
        )

    def test_rejects_feature_branch_and_stale_origin_main_ancestor(self) -> None:
        runner = FakeRunner({})
        with self.assertRaisesRegex(SourcePolicyError, "main or a 40-character SHA"):
            resolve_production_target(Path("/repo"), "feature/daily", runner)

        sha = "c" * 40
        runner = FakeRunner(
            {
                ("git", "-C", "/repo", "fetch", "origin", "main"): ok(""),
                ("git", "-C", "/repo", "rev-parse", "origin/main"): ok("d" * 40),
            }
        )
        with self.assertRaisesRegex(
            SourcePolicyError,
            "integrate.*authoritative main.*push.*new main tip",
        ):
            resolve_production_target(Path("/repo"), sha, runner)

    def test_rejects_failed_or_malformed_origin_main_resolution(self) -> None:
        runner = FakeRunner(
            {
                ("git", "-C", "/repo", "fetch", "origin", "main"): ok(""),
                ("git", "-C", "/repo", "rev-parse", "origin/main"): CommandResult(
                    1,
                    "",
                    "missing ref TOKEN=source-secret",
                )
            }
        )
        with self.assertRaisesRegex(SourcePolicyError, "resolve origin/main") as caught:
            resolve_production_target(Path("/repo"), "main", runner)
        self.assertNotIn("source-secret", str(caught.exception))

        runner = FakeRunner(
            {
                ("git", "-C", "/repo", "fetch", "origin", "main"): ok(""),
                ("git", "-C", "/repo", "rev-parse", "origin/main"): ok("not-a-sha"),
            }
        )
        with self.assertRaisesRegex(SourcePolicyError, "resolve origin/main"):
            resolve_production_target(Path("/repo"), "main", runner)

    def test_rejects_target_when_origin_main_cannot_be_refreshed(self) -> None:
        runner = FakeRunner(
            {
                ("git", "-C", "/repo", "fetch", "origin", "main"): CommandResult(
                    1, "", "network unavailable"
                )
            }
        )

        with self.assertRaisesRegex(SourcePolicyError, "refresh origin/main"):
            resolve_production_target(Path("/repo"), "main", runner)

    def test_state_round_trip_is_atomic_and_preserves_previous(self) -> None:
        path = self.directory / "deploy-state.json"
        state = sample_state(current_sha="b" * 40, previous_sha="a" * 40)

        write_state(path, state)

        self.assertEqual(state, load_state(path))
        self.assertFalse((self.directory / "deploy-state.json.tmp").exists())
        self.assertEqual(1, json.loads(path.read_text(encoding="utf-8"))["schema_version"])

    def test_load_state_rejects_malformed_json_and_schema(self) -> None:
        path = self.directory / "deploy-state.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(StateFormatError):
            load_state(path)

        path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        with self.assertRaises(StateFormatError):
            load_state(path)

    def test_load_state_rejects_unknown_fields_and_wrong_types(self) -> None:
        path = self.directory / "deploy-state.json"
        payload = _as_json(sample_state(current_sha="b" * 40, previous_sha="a" * 40))
        payload["unexpected"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(StateFormatError):
            load_state(path)

        payload = _as_json(sample_state(current_sha="b" * 40, previous_sha="a" * 40))
        payload["targets"] = "mcp"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(StateFormatError):
            load_state(path)

    def test_preflight_allowlist_rejects_unknown_key_and_preserves_state(self) -> None:
        path = self.directory / "deploy-state.json"
        previous = sample_state(current_sha="b" * 40, previous_sha="a" * 40)
        write_state(path, previous)

        invalid = replace(previous, preflight={"DATABASE_URL": "redacted"})
        with self.assertRaises(StateFormatError):
            write_state(path, invalid)

        self.assertEqual(previous, load_state(path))
        self.assertFalse((self.directory / "deploy-state.json.tmp").exists())

    def test_load_state_rejects_credential_bearing_preflight(self) -> None:
        path = self.directory / "deploy-state.json"
        payload = _as_json(sample_state(current_sha="b" * 40, previous_sha="a" * 40))
        payload["preflight"] = {"DATABASE_URL": "postgresql://user:password@db/app"}
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(StateFormatError):
            load_state(path)

    def test_write_event_is_atomic_and_returns_event_path(self) -> None:
        events_dir = self.directory / "events"
        event = sample_event()

        path = write_event(events_dir, event)

        self.assertEqual(events_dir / "event-1.json", path)
        self.assertEqual(event.event_id, json.loads(path.read_text(encoding="utf-8"))["event_id"])
        self.assertFalse((events_dir / "event-1.json.tmp").exists())

    def test_write_event_rejects_path_traversal_event_ids(self) -> None:
        event = sample_event()
        event = DeploymentEvent(**{**event.__dict__, "event_id": "../outside"})

        with self.assertRaises(ValueError):
            write_event(self.directory / "events", event)

    def test_write_event_rejects_credential_bearing_preflight(self) -> None:
        event = replace(sample_event(), preflight={"TOKEN": "abc123"})

        with self.assertRaises(StateFormatError):
            write_event(self.directory / "events", event)

        self.assertFalse((self.directory / "events" / "event-1.json").exists())

    def test_write_event_rejects_credential_material_in_free_text(self) -> None:
        event = replace(sample_event(), emergency_reason="DATABASE_URL=postgresql://user:password@db/app")

        with self.assertRaises(StateFormatError):
            write_event(self.directory / "events", event)

        self.assertFalse((self.directory / "events" / "event-1.json").exists())

    def test_write_event_rejects_authenticated_urls_bare_credentials_and_assignments(self) -> None:
        reasons = (
            "https://user:value@host/path",
            "user:secret@host/path",
            "database_url=postgresql://user:password@db/app",
            "Command_Api_Token=abc123",
            "name=value",
            "NaMe=value",
        )
        for reason in reasons:
            with self.subTest(reason=reason):
                with self.assertRaises(StateFormatError):
                    write_event(self.directory / "events", replace(sample_event(), emergency_reason=reason))

        self.assertFalse((self.directory / "events" / "event-1.json").exists())

    def test_state_preflight_rejects_authenticated_urls_bare_credentials_and_assignments(self) -> None:
        path = self.directory / "deploy-state.json"
        previous = sample_state(current_sha="b" * 40, previous_sha="a" * 40)
        write_state(path, previous)
        reasons = (
            "https://user:value@host/path",
            "user:secret@host/path",
            "database_url=postgresql://user:password@db/app",
            "command_api_token=abc123",
            "name=value",
        )

        for reason in reasons:
            with self.subTest(reason=reason):
                invalid = replace(previous, preflight={**_valid_preflight(), "docker_health": reason})
                with self.assertRaises(StateFormatError):
                    write_state(path, invalid)
                self.assertEqual(previous, load_state(path))

    def test_write_event_accepts_plain_language_emergency_reason(self) -> None:
        reason = "The previous release stayed healthy, but activation was not attempted."

        path = write_event(self.directory / "events", replace(sample_event(), emergency_reason=reason))

        self.assertEqual(reason, json.loads(path.read_text(encoding="utf-8"))["emergency_reason"])


def _as_json(value: DeploymentState) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "current_sha": value.current_sha,
        "previous_sha": value.previous_sha,
        "current_image": value.current_image,
        "previous_image": value.previous_image,
        "active_release": value.active_release,
        "previous_release": value.previous_release,
        "last_mode": value.last_mode,
        "requested_ref": value.requested_ref,
        "resolved_ref": value.resolved_ref,
        "targets": list(value.targets),
        "last_event_id": value.last_event_id,
        "started_at": value.started_at,
        "completed_at": value.completed_at,
        "preflight": value.preflight,
        "final_health": value.final_health,
    }


def _valid_preflight() -> dict[str, int | float | str]:
    return {
        "disk_available_bytes": 16 * 1024**3,
        "disk_used_percent": 42.5,
        "available_memory_bytes": 1024 * 1024**2,
        "docker_response_ms": 120,
        "docker_health": "healthy",
        "postgresql_health": "healthy",
        "compose_valid": "valid",
        "source_valid": "valid",
        "lock_valid": "free",
        "archive_bytes": 1234,
        "required_free_bytes": 2 * 1024**3,
    }
