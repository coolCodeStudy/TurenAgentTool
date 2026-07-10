from __future__ import annotations

import tempfile
import json
import os
import subprocess
import tarfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase

from scripts.deploy_contract import DeployMode, DeploymentPlan
from scripts.deploy_release import (
    DeployRequest,
    DeploymentEngine,
    DeploymentHealthError,
    DockerHealthChecker,
)
from scripts.deploy_retention import ImageRecord
from scripts.deploy_state import DeploymentState, load_state, write_state
from scripts.deploy_support import CommandResult


OLD_SHA = "a" * 40
TARGET_SHA = "b" * 40
OLDER_SHA = "0" * 40


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.results: dict[tuple[str, ...], CommandResult | BaseException] = {}
        self.environments: list[dict[str, str | None]] = []

    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        del timeout
        self.commands.append(command)
        self.environments.append(
            {
                name: os.environ.get(name)
                for name in ("COMPOSE_PROJECT_NAME", "POSTGRES_HOST", "POSTGRES_PORT")
            }
        )
        configured = self.results.get(command)
        if isinstance(configured, BaseException):
            raise configured
        if configured is not None:
            return configured
        if command[-2:] == ("rev-parse", "origin/main"):
            return CommandResult(0, TARGET_SHA + "\n", "")
        return CommandResult(0, "", "")


class FakeHealth:
    def __init__(self) -> None:
        self.failed_services: set[str] = set()
        self.service_checks: list[tuple[str, tuple[str, ...]]] = []
        self.aggregate_checks = 0
        self.fail_aggregate_after: int | None = None

    def fail_for(self, service: str) -> None:
        self.failed_services.add(service)

    def check_service(self, service: str, feature_routes: tuple[str, ...]) -> None:
        self.service_checks.append((service, feature_routes))
        if service in self.failed_services:
            self.failed_services.remove(service)
            raise DeploymentHealthError(f"{service} failed health verification")

    def check_aggregate(self, feature_routes: tuple[str, ...]) -> None:
        del feature_routes
        self.aggregate_checks += 1
        if (
            self.fail_aggregate_after is not None
            and self.aggregate_checks > self.fail_aggregate_after
        ):
            raise DeploymentHealthError("aggregate health verification failed")


class FakeClock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.sleeps: list[float] = []
        self.epoch = datetime(2026, 7, 10, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.elapsed += seconds

    def now(self) -> datetime:
        return self.epoch + timedelta(seconds=self.elapsed)


class HealthRunner(RecordingRunner):
    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        del timeout
        self.commands.append(command)
        configured = self.results.get(command)
        if isinstance(configured, BaseException):
            raise configured
        if configured is not None:
            return configured
        if command[:3] == ("docker", "compose", "ps"):
            service = command[-1]
            return CommandResult(
                0,
                json.dumps(
                    {
                        "Service": service,
                        "State": "running",
                        "Status": "Up 2 minutes (healthy)" if service == "postgres" else "Up 2 minutes",
                    }
                )
                + "\n",
                "",
            )
        if command[:3] == ("docker", "compose", "logs"):
            return CommandResult(0, "service started normally\n", "")
        if command[:2] == ("curl", "--silent"):
            if "http://127.0.0.1:8001/command" in command:
                return CommandResult(0, "401", "")
            if "http://127.0.0.1:8000/mcp" in command:
                return CommandResult(0, "400", "")
            return CommandResult(0, "200", "")
        if command[-3:] == ("postgres", "pg_isready"):
            return CommandResult(0, "accepting connections\n", "")
        return CommandResult(0, "", "")


class ArchiveRunner(RecordingRunner):
    def __init__(self, repo: Path) -> None:
        super().__init__()
        self.repo = repo

    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        if "archive" in command and "--output" in command:
            self.commands.append(command)
            output = Path(command[command.index("--output") + 1])
            with tarfile.open(output, "w") as archive:
                for entry in sorted(self.repo.iterdir()):
                    archive.add(entry, arcname=entry.name)
            return CommandResult(0, "", "")
        return super().run(command, timeout)


class DeploymentEngineTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.directory = Path(self.tempdir.name)
        self.repo = self.directory / "repo"
        self.app_root = self.directory / "app"
        self.releases_dir = self.app_root / "releases"
        self.shared_dir = self.app_root / "shared"
        self.state_path = self.shared_dir / "deploy-state.json"
        self.repo.mkdir()
        self.releases_dir.mkdir(parents=True)
        self.shared_dir.mkdir()

        self.old_release = self.releases_dir / OLD_SHA
        self.older_release = self.releases_dir / OLDER_SHA
        self.old_release.mkdir()
        self.older_release.mkdir()
        (self.old_release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
        (self.older_release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
        (self.app_root / "current").symlink_to(self.old_release, target_is_directory=True)
        (self.app_root / "previous").symlink_to(self.older_release, target_is_directory=True)
        (self.app_root / ".env").write_text(f"APP_IMAGE_TAG={OLD_SHA}\n", encoding="utf-8")
        write_state(self.state_path, _state())

        self.runner = RecordingRunner()
        self.health = FakeHealth()
        self.clock = FakeClock()
        self.targeted_request = DeployRequest(
            requested_ref="main",
            requested_mode=DeployMode.TARGETED_QUICK,
            requested_targets=("command-api", "weekly-review-web"),
            archive_path=None,
            emergency_reason=None,
        )
        self.plan = DeploymentPlan(
            mode=DeployMode.TARGETED_QUICK,
            targets=("command-api", "weekly-review-web"),
            changed_files=("investment_knowledge_mcp/command_workbench.py",),
            image_input_files=(),
            reasons=("command workbench",),
        )
        self.stage_calls: list[str] = []
        self.engine = DeploymentEngine(
            repo=self.repo,
            app_root=self.app_root,
            runner=self.runner,
            health=self.health,
            clock=self.clock,
            plan_builder=lambda repo, base, target, runner: self.plan,
            resource_collector=lambda runner: _resources(),
            runtime_validator=lambda runner, compose_file: (
                "docker_health",
                "compose_valid",
                "postgresql_health",
            ),
            release_stager=self._stage_release,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _stage_release(self, target_sha: str) -> Path:
        self.stage_calls.append(target_sha)
        release = self.releases_dir / target_sha
        release.mkdir(exist_ok=True)
        (release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
        return release

    def assertSubsequence(
        self, expected: list[tuple[str, ...]], actual: list[tuple[str, ...]]
    ) -> None:
        iterator = iter(actual)
        for command in expected:
            self.assertTrue(any(candidate == command for candidate in iterator), command)

    def test_targeted_deploy_recreates_only_planned_services_sequentially(self) -> None:
        outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        self.assertSubsequence(
            [
                ("docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "command-api"),
                (
                    "docker",
                    "compose",
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "weekly-review-web",
                ),
            ],
            self.runner.commands,
        )
        self.assertNotIn("postgres", outcome.activated_services)

    def test_health_failure_rolls_back_activated_services_in_reverse_order(self) -> None:
        self.health.fail_for("weekly-review-web")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual(("weekly-review-web", "command-api"), outcome.rolled_back_services)
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)

    def test_no_deploy_recomputes_plan_without_mutating_runtime_or_filesystem(self) -> None:
        self.plan = DeploymentPlan(
            mode=DeployMode.NO_DEPLOY,
            targets=(),
            changed_files=("docs/README.md",),
            image_input_files=(),
            reasons=("documentation",),
        )
        request = replace(
            self.targeted_request,
            requested_mode=DeployMode.NO_DEPLOY,
            requested_targets=(),
        )
        state_before = self.state_path.read_bytes()
        current_before = os.readlink(self.app_root / "current")

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual([], self.stage_calls)
        self.assertEqual(state_before, self.state_path.read_bytes())
        self.assertEqual(current_before, os.readlink(self.app_root / "current"))
        self.assertFalse(self.engine.lock_path.exists())
        self.assertFalse(self.engine.events_dir.exists())
        self.assertFalse(any(command[:2] == ("docker", "compose") for command in self.runner.commands))
        self.assertFalse(any("fetch" in command for command in self.runner.commands))

    def test_config_restart_preserves_current_immutable_image(self) -> None:
        self.plan = replace(self.plan, mode=DeployMode.CONFIG_RESTART)
        request = replace(self.targeted_request, requested_mode=DeployMode.CONFIG_RESTART)

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual(f"investment-knowledge-app:{OLD_SHA}", load_state(self.state_path).current_image)
        self.assertEqual(f"APP_IMAGE_TAG={OLD_SHA}\n", (self.app_root / ".env").read_text())

    def test_full_image_loads_and_activates_target_sha_tag_for_sixty_seconds(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency image input",),
        )
        request = DeployRequest(
            requested_ref="main",
            requested_mode=DeployMode.FULL_IMAGE,
            requested_targets=("command-api",),
            archive_path=archive,
            emergency_reason=None,
        )

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertFalse(archive.exists())
        self.assertEqual(f"investment-knowledge-app:{TARGET_SHA}", load_state(self.state_path).current_image)
        self.assertEqual(f"APP_IMAGE_TAG={TARGET_SHA}\n", (self.app_root / ".env").read_text())
        self.assertEqual([60], self.clock.sleeps)
        self.assertIn(("docker", "load", "--input", str(archive)), self.runner.commands)
        self.assertIn(
            ("docker", "image", "inspect", f"investment-knowledge-app:{TARGET_SHA}"),
            self.runner.commands,
        )
        self.assertIn(
            ("docker", "builder", "prune", "--filter", "until=168h", "--force"),
            self.runner.commands,
        )

    def test_mismatched_client_plan_is_rejected_before_staging(self) -> None:
        request = replace(self.targeted_request, requested_targets=("command-api",))

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("does not match", outcome.message)
        self.assertEqual([], self.stage_calls)
        self.assertFalse(any(command[:3] == ("docker", "compose", "up") for command in self.runner.commands))

    def test_omitted_client_targets_are_rejected_for_a_runtime_deploy(self) -> None:
        request = replace(self.targeted_request, requested_targets=())

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("does not match", outcome.message)
        self.assertEqual([], self.stage_calls)

    def test_emergency_override_requires_twenty_character_reason(self) -> None:
        request = replace(
            self.targeted_request,
            requested_targets=("command-api",),
            emergency_reason="too short",
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("at least 20 characters", outcome.message)
        self.assertEqual([], self.stage_calls)

    def test_valid_emergency_override_can_narrow_targets_and_is_audited(self) -> None:
        reason = "Restore the command API while its peer is investigated."
        request = replace(
            self.targeted_request,
            requested_targets=("command-api",),
            emergency_reason=reason,
        )

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual(("command-api",), outcome.activated_services)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertTrue(event["emergency_override"])
        self.assertEqual(reason, event["emergency_reason"])
        self.assertEqual(["command-api"], event["targets"])

    def test_feature_ref_is_rejected_even_with_valid_emergency_reason(self) -> None:
        request = replace(
            self.targeted_request,
            requested_ref="feature/daily-market-brief",
            emergency_reason="Production source policy remains mandatory during recovery.",
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertEqual([], self.stage_calls)
        self.assertFalse(any(command[:3] == ("docker", "compose", "up") for command in self.runner.commands))

    def test_preflight_failure_happens_before_staging_or_runtime_mutation(self) -> None:
        from scripts.deploy_preflight import ResourceSnapshot

        self.engine.resource_collector = lambda runner: ResourceSnapshot(1, 99.0, 1)

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual([], self.stage_calls)
        self.assertFalse(any(command[:3] == ("docker", "compose", "up") for command in self.runner.commands))
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)

    def test_targeted_stability_and_event_timing_use_injected_clock(self) -> None:
        outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        self.assertEqual([30], self.clock.sleeps)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual("2026-07-10T00:00:00Z", event["started_at"])
        self.assertEqual("2026-07-10T00:00:30Z", event["completed_at"])
        self.assertEqual(
            {"command-api", "weekly-review-web"}, set(event["target_durations_ms"])
        )
        self.assertGreaterEqual(self.health.aggregate_checks, 3)

    def test_archive_is_removed_when_full_preflight_fails(self) -> None:
        from scripts.deploy_preflight import ResourceSnapshot

        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = replace(
            self.plan,
            mode=DeployMode.FULL_IMAGE,
            image_input_files=("requirements.txt",),
        )
        self.engine.resource_collector = lambda runner: ResourceSnapshot(1, 99.0, 1)
        request = replace(
            self.targeted_request,
            requested_mode=DeployMode.FULL_IMAGE,
            archive_path=archive,
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertFalse(archive.exists())

    def test_rollback_failure_persists_lockout_and_blocks_next_attempt(self) -> None:
        self.health.fail_for("weekly-review-web")
        self.health.fail_aggregate_after = 1

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertTrue(self.engine.lockout_path.exists())
        self.assertEqual("rollback_failed", load_state(self.state_path).final_health)
        command_count = len(self.runner.commands)

        second = self.engine.deploy(self.targeted_request)

        self.assertFalse(second.ok)
        self.assertIn("manual recovery", second.message)
        self.assertEqual(
            {"current_release", "current_image", "container_status", "disk", "memory"},
            set(outcome.manual_recovery or {}),
        )
        self.assertEqual(outcome.manual_recovery, second.manual_recovery)
        self.assertIsInstance(json.loads((outcome.manual_recovery or {})["container_status"]), list)
        self.assertIn("used_percent", (outcome.manual_recovery or {})["disk"])
        self.assertIn("available_bytes", (outcome.manual_recovery or {})["memory"])
        self.assertEqual(command_count, len(self.runner.commands))

    def test_no_deployment_command_can_recreate_or_remove_postgresql(self) -> None:
        outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        rendered = [" ".join(command) for command in self.runner.commands]
        self.assertFalse(any("force-recreate postgres" in command for command in rendered))
        self.assertFalse(any("rm postgres" in command for command in rendered))
        self.assertFalse(any(" down" in f" {command}" for command in rendered))

    def test_emergency_override_cannot_target_postgresql(self) -> None:
        request = replace(
            self.targeted_request,
            requested_targets=("postgres",),
            emergency_reason="Restart the database during this application recovery.",
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("PostgreSQL", outcome.message)
        self.assertEqual([], self.stage_calls)
        self.assertFalse(any(command[-1:] == ("postgres",) for command in self.runner.commands))

    def test_failed_activation_rolls_back_the_attempted_service(self) -> None:
        self.plan = replace(self.plan, targets=("command-api",))
        request = replace(self.targeted_request, requested_targets=("command-api",))
        activate = (
            "docker",
            "compose",
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "command-api",
        )
        self.runner.results[activate] = CommandResult(1, "", "partial activation")

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertEqual(("command-api",), outcome.rolled_back_services)
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)

    def test_image_switch_failure_restores_previous_release(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        self.engine._write_image_tag = lambda image: (_ for _ in ()).throw(
            DeploymentHealthError("image selector failed")
        )
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertEqual(self.old_release.resolve(), (self.app_root / "current").resolve())
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)

    def test_full_source_rejection_removes_uploaded_archive(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        request = DeployRequest(
            "feature/unsafe",
            DeployMode.FULL_IMAGE,
            ("command-api",),
            archive,
            "Source policy remains mandatory during emergency recovery.",
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertFalse(archive.exists())

    def test_sensitive_emergency_reason_is_rejected_before_staging(self) -> None:
        request = replace(
            self.targeted_request,
            requested_targets=("command-api",),
            emergency_reason="COMMAND_API_TOKEN=do-not-write-this-value",
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertEqual([], self.stage_calls)
        self.assertNotIn("do-not-write", outcome.message)

    def test_image_selector_update_preserves_restricted_env_permissions(self) -> None:
        self.engine.env_file.chmod(0o600)

        outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        self.assertEqual(0o600, self.engine.env_file.stat().st_mode & 0o777)

    def test_full_event_preserves_archive_size_and_image_counts(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        self.engine.image_inventory = lambda: (
            ImageRecord("current-id", f"investment-knowledge-app:{TARGET_SHA}", 2),
            ImageRecord("previous-id", f"investment-knowledge-app:{OLD_SHA}", 1),
        )
        self.engine.referenced_image_ids = lambda: {"current-id"}
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual(len(b"candidate"), event["archive_bytes"])
        self.assertEqual(2, event["image_count_before"])
        self.assertEqual(2, event["image_count_after"])

    def test_host_units_restart_independently_without_compose(self) -> None:
        self.plan = DeploymentPlan(
            mode=DeployMode.TARGETED_QUICK,
            targets=("investment-ops-api.service",),
            changed_files=("scripts/ecs_ops_api.py",),
            image_input_files=(),
            reasons=("control plane",),
        )
        request = replace(
            self.targeted_request,
            requested_targets=("investment-ops-api.service",),
        )

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertIn(
            ("systemctl", "restart", "investment-ops-api.service"), self.runner.commands
        )
        self.assertFalse(
            any(command[-1:] == ("investment-ops-api.service",) and command[:2] == ("docker", "compose") for command in self.runner.commands)
        )

    def test_failed_full_removes_unreferenced_candidate_and_preserves_previous_image(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        candidate = f"investment-knowledge-app:{TARGET_SHA}"
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        self.engine.image_inventory = lambda: (
            ImageRecord("candidate-id", candidate, 3),
            ImageRecord("current-id", f"investment-knowledge-app:{OLD_SHA}", 2),
            ImageRecord("previous-id", f"investment-knowledge-app:{OLDER_SHA}", 1),
        )
        self.engine.referenced_image_ids = lambda: set()
        self.health.fail_for("command-api")
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn(("docker", "image", "rm", "candidate-id"), self.runner.commands)
        self.assertEqual(f"investment-knowledge-app:{OLD_SHA}", load_state(self.state_path).current_image)
        self.assertEqual(f"APP_IMAGE_TAG={OLD_SHA}\n", self.engine.env_file.read_text())
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual("succeeded", event["rollback_status"])

    def test_failed_full_keeps_candidate_while_a_container_references_it(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        candidate = f"investment-knowledge-app:{TARGET_SHA}"
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        self.engine.image_inventory = lambda: (
            ImageRecord("candidate-id", candidate, 3),
        )
        self.engine.referenced_image_ids = lambda: {"candidate-id"}
        self.health.fail_for("command-api")
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertNotIn(("docker", "image", "rm", "candidate-id"), self.runner.commands)

    def test_candidate_cleanup_failure_still_returns_product_safe_outcome(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        calls = 0

        def inventory():
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("TOKEN=cleanup-secret")
            return ()

        self.engine.image_inventory = inventory
        self.health.fail_for("command-api")
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertNotIn("token", outcome.message.lower())
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)

    def test_failed_event_write_does_not_escape_product_safe_outcome(self) -> None:
        self.engine.events_dir.write_text("blocks event directory", encoding="utf-8")
        self.health.fail_for("weekly-review-web")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)
        self.assertNotIn("event directory", outcome.message)

    def test_full_archive_load_failure_is_safe_and_removes_archive(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        self.runner.results[("docker", "load", "--input", str(archive))] = CommandResult(
            1, "", "TOKEN=do-not-report"
        )
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertFalse(archive.exists())
        self.assertNotIn("token", outcome.message.lower())
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)

    def test_default_stager_archives_target_into_immutable_release(self) -> None:
        legacy_drafts = self.app_root / "drafts"
        legacy_drafts.mkdir()
        (legacy_drafts / "preserved.md").write_text("durable draft\n")
        (self.repo / "db").mkdir()
        (self.repo / "db" / "schema.sql").write_text("select 1;\n")
        (self.repo / "investment_knowledge_mcp").mkdir()
        (self.repo / "investment_knowledge_mcp" / "__init__.py").write_text("")
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "init_db.py").write_text("pass\n")
        (self.repo / "scripts" / "ecs_ops_api.py").write_text("pass\n")
        (self.repo / "Dockerfile").write_text("FROM scratch\n")
        (self.repo / "requirements.txt").write_text("example\n")
        (self.repo / "docker-compose.prod.yml").write_text("services: {}\n")
        runner = ArchiveRunner(self.repo)
        engine = DeploymentEngine(
            repo=self.repo,
            app_root=self.app_root,
            runner=runner,
            health=self.health,
            clock=self.clock,
            plan_builder=lambda repo, base, target, runner: self.plan,
            resource_collector=lambda runner: _resources(),
            runtime_validator=lambda runner, compose_file: (
                "docker_health",
                "compose_valid",
                "postgresql_health",
            ),
        )

        outcome = engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        release = self.releases_dir / TARGET_SHA
        self.assertTrue((release / "db" / "schema.sql").exists())
        self.assertTrue((release / "drafts").is_symlink())
        self.assertTrue((release / ".env").is_symlink())
        self.assertEqual(
            "durable draft\n",
            (self.shared_dir / "drafts" / "preserved.md").read_text(),
        )
        self.assertEqual([], list(self.releases_dir.glob(".staging-*")))
        self.assertEqual([], list(self.releases_dir.glob(".archive-*")))

    def test_compose_calls_use_stable_project_and_strip_host_database_values(self) -> None:
        previous_host = os.environ.get("POSTGRES_HOST")
        previous_port = os.environ.get("POSTGRES_PORT")
        os.environ["POSTGRES_HOST"] = "127.0.0.1"
        os.environ["POSTGRES_PORT"] = "55432"
        try:
            outcome = self.engine.deploy(self.targeted_request)
        finally:
            restored_host = os.environ.get("POSTGRES_HOST")
            restored_port = os.environ.get("POSTGRES_PORT")
            if previous_host is None:
                os.environ.pop("POSTGRES_HOST", None)
            else:
                os.environ["POSTGRES_HOST"] = previous_host
            if previous_port is None:
                os.environ.pop("POSTGRES_PORT", None)
            else:
                os.environ["POSTGRES_PORT"] = previous_port

        self.assertTrue(outcome.ok)
        activate_indexes = [
            index
            for index, command in enumerate(self.runner.commands)
            if command[:3] == ("docker", "compose", "up")
        ]
        self.assertTrue(activate_indexes)
        for index in activate_indexes:
            self.assertEqual("turenagenttool_prod", self.runner.environments[index]["COMPOSE_PROJECT_NAME"])
            self.assertIsNone(self.runner.environments[index]["POSTGRES_HOST"])
            self.assertIsNone(self.runner.environments[index]["POSTGRES_PORT"])
        self.assertEqual("127.0.0.1", restored_host)
        self.assertEqual("55432", restored_port)


class DockerHealthCheckerTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.current = Path(self.tempdir.name) / "current"
        self.current.mkdir()
        self.runner = HealthRunner()
        self.health = DockerHealthChecker(self.runner, self.current)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_exact_target_and_aggregate_health_routes_are_checked(self) -> None:
        self.health.check_service("weekly-review-web", ("/daily-market-brief",))
        self.health.check_service("command-api", ())
        self.health.check_service("mcp", ())
        self.health.check_aggregate(("/daily-market-brief",))

        rendered = [" ".join(command) for command in self.runner.commands]
        for url in (
            "http://127.0.0.1:8010/health",
            "http://127.0.0.1:8010/weekly-review",
            "http://127.0.0.1:8010/command",
            "http://127.0.0.1:8010/daily-market-brief",
            "http://127.0.0.1:8001/health",
            "http://127.0.0.1:8001/command",
            "http://127.0.0.1:8000/mcp",
        ):
            self.assertTrue(any(url in command for command in rendered), url)
        self.assertTrue(any("exec -T postgres pg_isready" in command for command in rendered))

    def test_scheduler_health_rejects_startup_traceback(self) -> None:
        logs = (
            "docker",
            "compose",
            "logs",
            "--no-color",
            "--tail",
            "200",
            "account-snapshot-scheduler",
        )
        self.runner.results[logs] = CommandResult(
            0, "Traceback (most recent call last):\nRuntimeError: boom\n", ""
        )

        with self.assertRaisesRegex(DeploymentHealthError, "startup failure"):
            self.health.check_service("account-snapshot-scheduler", ())


class ShellWrapperTests(TestCase):
    def test_wrapper_preserves_optional_values_as_single_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            output = directory / "args.txt"
            fake_python = directory / "fake python"
            fake_python.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$ARGS_OUTPUT\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = {
                **os.environ,
                "PYTHON_BIN": str(fake_python),
                "ARGS_OUTPUT": str(output),
                "DEPLOY_REF": "main",
                "DEPLOY_MODE": "targeted_quick",
                "DEPLOY_TARGETS": "command-api,weekly-review-web",
                "DEPLOY_ARCHIVE": str(directory / "archive with spaces.tar"),
                "DEPLOY_EMERGENCY_REASON": "A carefully scoped recovery reason with spaces.",
                "DEPLOY_FEATURE_ROUTES": "/daily-market-brief,/market-status",
                "SOURCE_DIR": str(directory / "repo with spaces"),
                "APP_ROOT": str(directory / "app with spaces"),
                "COMPOSE_ENV_FILE": str(directory / "compose env with spaces"),
                "COMPOSE_PROJECT_NAME": "stable_project",
            }

            subprocess.run(
                ["bash", str(Path(__file__).parents[1] / "scripts" / "deploy_from_local_checkout.sh")],
                check=True,
                env=env,
            )

            arguments = output.read_text(encoding="utf-8").splitlines()
            self.assertIn(str(directory / "archive with spaces.tar"), arguments)
            self.assertIn("A carefully scoped recovery reason with spaces.", arguments)
            self.assertIn(str(directory / "repo with spaces"), arguments)
            self.assertIn(str(directory / "compose env with spaces"), arguments)
            self.assertIn("stable_project", arguments)
            self.assertNotIn("", arguments)


def _state() -> DeploymentState:
    return DeploymentState(
        schema_version=1,
        current_sha=OLD_SHA,
        previous_sha=OLDER_SHA,
        current_image=f"investment-knowledge-app:{OLD_SHA}",
        previous_image=f"investment-knowledge-app:{OLDER_SHA}",
        active_release=str(Path("/releases") / OLD_SHA),
        previous_release=str(Path("/releases") / OLDER_SHA),
        last_mode=DeployMode.TARGETED_QUICK.value,
        requested_ref="main",
        resolved_ref=OLD_SHA,
        targets=("command-api",),
        last_event_id="previous-event",
        started_at="2026-07-09T00:00:00Z",
        completed_at="2026-07-09T00:00:30Z",
        preflight={},
        final_health="healthy",
    )


def _resources():
    from scripts.deploy_preflight import GIB, MIB, ResourceSnapshot

    return ResourceSnapshot(16 * GIB, 40.0, 1024 * MIB)
