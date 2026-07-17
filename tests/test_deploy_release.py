from __future__ import annotations

import tempfile
import json
import os
import re
import subprocess
import tarfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from scripts.deploy_contract import APPLICATION_SERVICES, DeployMode, DeploymentPlan
from scripts.deploy_release import (
    DeployRequest,
    DeploymentContext,
    DeploymentEngine,
    DeploymentError,
    DeploymentHealthError,
    DockerHealthChecker,
    SelectorSnapshot,
)
from scripts.deploy_retention import ImageRecord
from scripts.deploy_state import DeploymentState, load_state, write_state
from scripts.deploy_support import CommandResult


OLD_SHA = "a" * 40
TARGET_SHA = "b" * 40
OLDER_SHA = "0" * 40


def _without_compose_file(command: tuple[str, ...]) -> tuple[str, ...]:
    if command[:3] == ("docker", "compose", "-f") and len(command) >= 5:
        return (*command[:2], *command[4:])
    return command


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.results: dict[tuple[str, ...], CommandResult | BaseException] = {}
        self.sequences: dict[tuple[str, ...], list[CommandResult | BaseException]] = {}
        self.environments: list[dict[str, str | None]] = []
        self.on_run = None

    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        del timeout
        self.commands.append(command)
        if self.on_run is not None:
            self.on_run(command)
        self.environments.append(
            {
                name: os.environ.get(name)
                for name in ("COMPOSE_PROJECT_NAME", "POSTGRES_HOST", "POSTGRES_PORT")
            }
        )
        lookup_command = _without_compose_file(command)
        sequence = self.sequences.get(command) or self.sequences.get(lookup_command)
        configured = (
            sequence.pop(0)
            if sequence
            else self.results.get(command, self.results.get(lookup_command))
        )
        if isinstance(configured, BaseException):
            raise configured
        if configured is not None:
            return configured
        if command[-2:] == ("rev-parse", "origin/main"):
            return CommandResult(0, TARGET_SHA + "\n", "")
        if command == (
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=turenagenttool_prod",
            "--format",
            "{{json .}}",
        ):
            return CommandResult(
                0,
                json.dumps(
                    {
                        "ID": "container-1",
                        "Image": f"investment-knowledge-app:{OLD_SHA}",
                        "Names": "app-command-api-1",
                    }
                )
                + "\n",
                "",
            )
        if command[:3] == ("docker", "load", "--input"):
            return CommandResult(
                0, f"Loaded image: investment-knowledge-app:{TARGET_SHA}\n", ""
            )
        if command[:4] == ("docker", "image", "inspect", "--format"):
            image_id = (
                "sha256:old-image"
                if command[-1] == f"investment-knowledge-app:{OLD_SHA}"
                else "sha256:target-image"
            )
            return CommandResult(0, image_id + "\n", "")
        if command[:4] == ("docker", "inspect", "--format", "{{.Image}}"):
            return CommandResult(0, "sha256:old-image\n", "")
        if (
            command[:3] == ("docker", "compose", "-f")
            and command[-2:] == ("config", "--services")
        ):
            return CommandResult(
                0,
                "\n".join(
                    (
                        "postgres",
                        "mcp",
                        "dingtalk-api",
                        "account-snapshot-scheduler",
                        "command-api",
                        "weekly-review-web",
                        "dingtalk-stream-bot",
                        "ipo-reminder-scheduler",
                    )
                )
                + "\n",
                "",
            )
        return CommandResult(0, "", "")


class FakeHealth:
    def __init__(self) -> None:
        self.failed_services: set[str] = set()
        self.service_checks: list[tuple[str, tuple[str, ...]]] = []
        self.aggregate_checks = 0
        self.fail_aggregate_after: int | None = None
        self.on_check = None

    def fail_for(self, service: str) -> None:
        self.failed_services.add(service)

    def check_service(self, service: str, feature_routes: tuple[str, ...]) -> None:
        if self.on_check is not None:
            self.on_check(f"service:{service}")
        self.service_checks.append((service, feature_routes))
        if service in self.failed_services:
            self.failed_services.remove(service)
            raise DeploymentHealthError(f"{service} failed health verification")

    def check_aggregate(self, feature_routes: tuple[str, ...]) -> None:
        if self.on_check is not None:
            self.on_check("aggregate")
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
        lookup_command = _without_compose_file(command)
        configured = self.results.get(command, self.results.get(lookup_command))
        if isinstance(configured, BaseException):
            raise configured
        if configured is not None:
            return configured
        if lookup_command[:3] == ("docker", "compose", "ps"):
            service = command[-1]
            return CommandResult(
                0,
                json.dumps(
                    {
                        "ID": f"{service}-container",
                        "Name": f"turenagenttool_prod-{service}-1",
                        "Service": service,
                        "State": "running",
                        "Status": "Up 2 minutes (healthy)" if service == "postgres" else "Up 2 minutes",
                    }
                )
                + "\n",
                "",
            )
        if command[:3] == ("docker", "inspect", "--format"):
            return CommandResult(0, "0\n", "")
        if lookup_command[:3] == ("docker", "compose", "logs"):
            return CommandResult(0, "service started normally\n", "")
        if command[:2] == ("curl", "--silent"):
            if "http://127.0.0.1:8001/command" in command:
                return CommandResult(0, "401", "")
            if "http://127.0.0.1:8002/dingtalk/webhook" in command:
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
        write_state(
            self.state_path,
            replace(
                _state(),
                active_release=str(self.old_release),
                previous_release=str(self.older_release),
            ),
        )

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
        staged_compose = self.releases_dir / TARGET_SHA / "docker-compose.prod.yml"
        self.assertSubsequence(
            [
                (
                    "docker",
                    "compose",
                    "-f",
                    str(staged_compose),
                    "up",
                    "-d",
                    "--no-build",
                    "--no-deps",
                    "--force-recreate",
                    "command-api",
                ),
                (
                    "docker",
                    "compose",
                    "-f",
                    str(staged_compose),
                    "up",
                    "-d",
                    "--no-build",
                    "--no-deps",
                    "--force-recreate",
                    "weekly-review-web",
                ),
            ],
            self.runner.commands,
        )
        self.assertNotIn("postgres", outcome.activated_services)

    def test_activation_uses_the_staged_release_compose_file_explicitly(self) -> None:
        outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        staged_compose = self.releases_dir / TARGET_SHA / "docker-compose.prod.yml"
        self.assertIn(
            (
                "docker",
                "compose",
                "-f",
                str(staged_compose),
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--force-recreate",
                "command-api",
            ),
            self.runner.commands,
        )

    def test_rollback_uses_the_previous_release_compose_file_explicitly(self) -> None:
        self.health.fail_for("weekly-review-web")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        previous_compose = self.old_release.resolve() / "docker-compose.prod.yml"
        self.assertIn(
            (
                "docker",
                "compose",
                "-f",
                str(previous_compose),
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--force-recreate",
                "command-api",
            ),
            self.runner.commands,
        )

    def test_manual_recovery_uses_the_current_release_compose_file_explicitly(self) -> None:
        self.engine._manual_recovery(load_state(self.state_path))

        self.assertIn(
            (
                "docker",
                "compose",
                "-f",
                str(self.engine.current_link / "docker-compose.prod.yml"),
                "ps",
                "--format",
                "json",
            ),
            self.runner.commands,
        )

    def test_rollback_removes_a_service_missing_from_the_previous_release(self) -> None:
        self.plan = replace(self.plan, targets=("daily-market-brief-scheduler",))
        request = replace(
            self.targeted_request,
            requested_targets=("daily-market-brief-scheduler",),
        )
        self.health.fail_for("daily-market-brief-scheduler")

        outcome = self.engine.deploy(request)

        target_compose = self.releases_dir / TARGET_SHA / "docker-compose.prod.yml"
        self.assertFalse(outcome.ok)
        self.assertEqual(("daily-market-brief-scheduler",), outcome.rolled_back_services)
        self.assertEqual((), outcome.rollback_failures)
        self.assertIn(
            (
                "docker",
                "compose",
                "-f",
                str(target_compose),
                "rm",
                "--force",
                "--stop",
                "daily-market-brief-scheduler",
            ),
            self.runner.commands,
        )

    def test_command_failure_keeps_a_product_safe_diagnostic_line(self) -> None:
        command = ("docker", "compose", "up", "service")
        self.runner.results[command] = CommandResult(
            1,
            "",
            'service "worker" depends on undefined service "postgres": invalid compose project\n',
        )

        with self.assertRaisesRegex(DeploymentError, "invalid compose project"):
            self.engine._run_checked(command, "application service failed to activate")

    def test_baseline_image_identity_accepts_legacy_display_tag_with_matching_image_id(self) -> None:
        self.runner.results[
            (
                "docker",
                "ps",
                "--filter",
                "label=com.docker.compose.project=turenagenttool_prod",
                "--format",
                "{{json .}}",
            )
        ] = CommandResult(
            0,
            json.dumps(
                {
                    "ID": "legacy-container",
                    "Image": "investment-knowledge-app:prod",
                }
            )
            + "\n",
            "",
        )

        self.engine._verify_baseline_image_identity(
            load_state(self.state_path),
            SelectorSnapshot(
                current_release=self.old_release,
                previous_release=self.older_release,
                env_contents=f"APP_IMAGE_TAG={OLD_SHA}\n".encode(),
            ),
        )

    def test_baseline_image_identity_accepts_compose_service_label_with_custom_image_name(self) -> None:
        self.runner.results[
            (
                "docker",
                "ps",
                "--filter",
                "label=com.docker.compose.project=turenagenttool_prod",
                "--format",
                "{{json .}}",
            )
        ] = CommandResult(
            0,
            json.dumps(
                {
                    "ID": "legacy-container",
                    "Image": "turenagenttool_prod-weekly-review-web",
                    "Labels": "com.docker.compose.service=weekly-review-web",
                }
            )
            + "\n",
            "",
        )

        self.engine._verify_baseline_image_identity(
            load_state(self.state_path),
            SelectorSnapshot(
                current_release=self.old_release,
                previous_release=self.older_release,
                env_contents=f"APP_IMAGE_TAG={OLD_SHA}\n".encode(),
            ),
        )

    def test_health_failure_rolls_back_activated_services_in_reverse_order(self) -> None:
        self.health.fail_for("weekly-review-web")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual(("weekly-review-web", "command-api"), outcome.rolled_back_services)
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)

    def test_global_lock_remains_held_through_rollback_event_and_lockout(self) -> None:
        lock_state = {"held": False}
        observations: list[str] = []

        @contextmanager
        def tracking_lock(path: Path):
            del path
            self.assertFalse(lock_state["held"])
            lock_state["held"] = True
            try:
                yield
            finally:
                lock_state["held"] = False

        self.runner.on_run = lambda command: observations.append(
            f"command:{command[0]}:{lock_state['held']}"
        )
        self.health.on_check = lambda label: observations.append(
            f"health:{label}:{lock_state['held']}"
        )
        self.health.fail_for("weekly-review-web")
        self.health.fail_aggregate_after = 0
        engine = DeploymentEngine(
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
            lock_factory=tracking_lock,
        )

        outcome = engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertFalse(lock_state["held"])
        self.assertTrue(engine.lockout_path.exists())
        self.assertTrue(observations)
        self.assertTrue(all(observation.endswith(":True") for observation in observations))

    def test_previous_selector_partial_failure_restores_all_selectors(self) -> None:
        original = self.engine._replace_symlink

        def fail_after_previous(link: Path, target: Path) -> None:
            original(link, target)
            if link == self.engine.previous_link:
                raise OSError("selector write failed")

        self.engine._replace_symlink = fail_after_previous

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual(self.old_release.resolve(), self.engine.current_link.resolve())
        self.assertEqual(self.older_release.resolve(), self.engine.previous_link.resolve())
        self.assertEqual(f"APP_IMAGE_TAG={OLD_SHA}\n", self.engine.env_file.read_text())

    def test_current_selector_partial_failure_restores_all_selectors(self) -> None:
        original = self.engine._replace_symlink

        def fail_after_current(link: Path, target: Path) -> None:
            original(link, target)
            if link == self.engine.current_link:
                raise OSError("selector write failed")

        self.engine._replace_symlink = fail_after_current

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual(self.old_release.resolve(), self.engine.current_link.resolve())
        self.assertEqual(self.older_release.resolve(), self.engine.previous_link.resolve())
        self.assertEqual(f"APP_IMAGE_TAG={OLD_SHA}\n", self.engine.env_file.read_text())

    def test_rollback_attempts_every_service_and_reports_only_successful_restores(self) -> None:
        command_api = (
            "docker",
            "compose",
            "up",
            "-d",
            "--no-build",
            "--no-deps",
            "--force-recreate",
            "command-api",
        )
        self.runner.sequences[command_api] = [
            CommandResult(0, "", ""),
            CommandResult(1, "", "rollback command failed"),
        ]
        self.health.fail_for("weekly-review-web")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual(("weekly-review-web",), outcome.rolled_back_services)
        self.assertEqual(("command-api",), outcome.rollback_failures)
        self.assertEqual(1, self.health.aggregate_checks)

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
        lock_held = False
        plan_computed_while_locked = False

        @contextmanager
        def tracking_lock(path):
            nonlocal lock_held
            del path
            lock_held = True
            try:
                yield
            finally:
                lock_held = False

        def locked_plan_builder(repo, base_sha, target_sha, runner):
            nonlocal plan_computed_while_locked
            del repo, base_sha, target_sha, runner
            plan_computed_while_locked = lock_held
            return self.plan

        self.engine.lock_factory = tracking_lock
        self.engine.plan_builder = locked_plan_builder

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertTrue(plan_computed_while_locked)
        self.assertEqual([], self.stage_calls)
        self.assertEqual(state_before, self.state_path.read_bytes())
        self.assertEqual(current_before, os.readlink(self.app_root / "current"))
        self.assertFalse(self.engine.events_dir.exists())
        self.assertFalse(any(command[:2] == ("docker", "compose") for command in self.runner.commands))
        self.assertIn(
            ("git", "-C", str(self.repo), "fetch", "origin", "main"),
            self.runner.commands,
        )

    def test_no_deploy_refreshes_origin_before_resolving_and_classifying(self) -> None:
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
        source_fresh = False

        def observe(command):
            nonlocal source_fresh
            if command == (
                "git",
                "-C",
                str(self.repo),
                "fetch",
                "origin",
                "main",
            ):
                source_fresh = True

        def classify_after_refresh(repo, base_sha, target_sha, runner):
            del repo, base_sha, target_sha, runner
            self.assertTrue(source_fresh)
            return self.plan

        self.runner.on_run = observe
        self.engine.plan_builder = classify_after_refresh

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual(
            1,
            self.runner.commands.count(
                ("git", "-C", str(self.repo), "fetch", "origin", "main")
            ),
        )

    def test_no_deploy_does_not_read_or_rewrite_image_selector(self) -> None:
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
        self.engine.env_file.unlink()
        self.engine.env_file.mkdir()

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertTrue(self.engine.env_file.is_dir())

    def test_config_restart_preserves_current_immutable_image(self) -> None:
        self.plan = replace(self.plan, mode=DeployMode.CONFIG_RESTART)
        request = replace(self.targeted_request, requested_mode=DeployMode.CONFIG_RESTART)

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual(f"investment-knowledge-app:{OLD_SHA}", load_state(self.state_path).current_image)
        self.assertEqual(f"APP_IMAGE_TAG={OLD_SHA}\n", (self.app_root / ".env").read_text())

    def test_targeted_rejects_env_selector_mismatch_before_staging(self) -> None:
        self.engine.env_file.write_text(f"APP_IMAGE_TAG={OLDER_SHA}\n", encoding="utf-8")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertIn("image identity", outcome.message)
        self.assertEqual([], self.stage_calls)
        self.assertEqual("recorded", outcome.audit_status)

    def test_targeted_rejects_running_managed_container_image_mismatch(self) -> None:
        managed_command = (
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=turenagenttool_prod",
            "--format",
            "{{json .}}",
        )
        self.runner.results[managed_command] = CommandResult(
            0,
            json.dumps(
                {
                    "ID": "mismatched-container",
                    "Image": f"investment-knowledge-app:{TARGET_SHA}",
                    "Names": "app-command-api-1",
                }
            )
            + "\n",
            "",
        )
        self.runner.results[
            ("docker", "inspect", "--format", "{{.Image}}", "mismatched-container")
        ] = CommandResult(0, "sha256:target-image\n", "")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertIn("running application image identity", outcome.message)
        self.assertEqual([], self.stage_calls)

    def test_image_identity_ignores_containers_outside_managed_compose_project(self) -> None:
        self.runner.results[("docker", "ps", "--format", "{{json .}}")]= CommandResult(
            0,
            json.dumps({"Image": f"investment-knowledge-app:{TARGET_SHA}"}) + "\n",
            "",
        )
        managed_command = (
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=turenagenttool_prod",
            "--format",
            "{{json .}}",
        )
        self.runner.results[managed_command] = CommandResult(
            0,
            json.dumps(
                {
                    "ID": "container-1",
                    "Image": f"investment-knowledge-app:{OLD_SHA}",
                }
            )
            + "\n",
            "",
        )

        outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        self.assertIn(managed_command, self.runner.commands)

    def test_active_image_rejects_same_tag_with_wrong_container_image_id(self) -> None:
        selected_image = f"investment-knowledge-app:{OLD_SHA}"
        managed_command = (
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=turenagenttool_prod",
            "--format",
            "{{json .}}",
        )
        self.runner.results[managed_command] = CommandResult(
            0,
            json.dumps({"ID": "container-1", "Image": selected_image}) + "\n",
            "",
        )
        self.runner.results[
            ("docker", "image", "inspect", "--format", "{{.Id}}", selected_image)
        ] = CommandResult(0, "sha256:expected\n", "")
        self.runner.results[
            ("docker", "inspect", "--format", "{{.Image}}", "container-1")
        ] = CommandResult(0, "sha256:wrong\n", "")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertIn("immutable image identity", outcome.message)
        self.assertEqual([], self.stage_calls)

    def test_active_image_accepts_matching_tag_and_container_image_ids(self) -> None:
        selected_image = f"investment-knowledge-app:{OLD_SHA}"
        managed_command = (
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=turenagenttool_prod",
            "--format",
            "{{json .}}",
        )
        self.runner.results[managed_command] = CommandResult(
            0,
            json.dumps({"ID": "container-1", "Image": selected_image}) + "\n",
            "",
        )
        self.runner.results[
            ("docker", "image", "inspect", "--format", "{{.Id}}", selected_image)
        ] = CommandResult(0, "sha256:expected\n", "")
        container_inspect = (
            "docker",
            "inspect",
            "--format",
            "{{.Image}}",
            "container-1",
        )
        self.runner.results[container_inspect] = CommandResult(
            0, "sha256:expected\n", ""
        )

        outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        self.assertIn(container_inspect, self.runner.commands)

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
            (
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Id}}",
                f"investment-knowledge-app:{TARGET_SHA}",
            ),
            self.runner.commands,
        )
        self.assertIn(
            ("docker", "builder", "prune", "--filter", "until=168h", "--force"),
            self.runner.commands,
        )

    def test_full_rejects_stale_expected_tag_when_archive_loads_different_image(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        expected = f"investment-knowledge-app:{TARGET_SHA}"
        inspect = (
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            expected,
        )
        self.runner.sequences[inspect] = [
            CommandResult(0, "sha256:stale\n", ""),
            CommandResult(0, "sha256:stale\n", ""),
        ]
        self.runner.results[("docker", "load", "--input", str(archive))] = CommandResult(
            0, "Loaded image: investment-knowledge-app:" + "c" * 40 + "\n", ""
        )
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("archive image identity", outcome.message)
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)
        self.assertEqual("recorded", outcome.audit_status)

    def test_full_rejects_mutable_prod_only_archive_with_product_safe_event(self) -> None:
        archive = self.directory / "candidate.tar.gz"
        archive.write_bytes(b"legacy-prod-image")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        self.runner.results[("docker", "load", "--input", str(archive))] = (
            CommandResult(0, "Loaded image: investment-knowledge-app:prod\n", "")
        )
        request = DeployRequest("main", DeployMode.FULL_IMAGE, (), archive, None)

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("archive image identity", outcome.message)
        self.assertEqual("recorded", outcome.audit_status)
        self.assertFalse(
            any(command[:3] == ("docker", "compose", "up") for command in self.runner.commands)
        )

    def test_archive_less_legacy_full_returns_product_safe_audited_error(self) -> None:
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        request = DeployRequest("main", DeployMode.FULL_IMAGE, (), None, None)

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("archive", outcome.message)
        self.assertEqual("recorded", outcome.audit_status)
        self.assertNotIn("traceback", outcome.message.lower())

    def test_mismatched_client_plan_is_rejected_before_staging(self) -> None:
        request = replace(self.targeted_request, requested_targets=("command-api",))

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("does not match", outcome.message)
        self.assertEqual([], self.stage_calls)
        self.assertFalse(any(command[:3] == ("docker", "compose", "up") for command in self.runner.commands))
        self.assertEqual("recorded", outcome.audit_status)
        self.assertTrue(self.engine.events_dir.is_dir())

    def test_omitted_client_targets_use_server_computed_runtime_targets(self) -> None:
        request = replace(self.targeted_request, requested_targets=())

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual(self.plan.targets, outcome.activated_services)

    def test_legacy_quick_intent_accepts_server_computed_config_restart(self) -> None:
        self.plan = replace(self.plan, mode=DeployMode.CONFIG_RESTART)
        request = replace(self.targeted_request, requested_targets=())

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual(DeployMode.CONFIG_RESTART, outcome.mode)

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

    def test_emergency_override_cannot_change_server_computed_targets(self) -> None:
        reason = "Restore the command API while its peer is investigated."
        request = replace(
            self.targeted_request,
            requested_targets=("command-api",),
            emergency_reason=reason,
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("cannot change", outcome.message)
        self.assertEqual((), outcome.activated_services)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertTrue(event["emergency_override"])
        self.assertEqual(reason, event["emergency_reason"])
        self.assertEqual(["command-api", "weekly-review-web"], event["targets"])

    def test_emergency_override_cannot_downgrade_full_image_to_no_deploy(self) -> None:
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        request = DeployRequest(
            "main",
            DeployMode.NO_DEPLOY,
            (),
            None,
            "Keep production unchanged while dependency risk is reviewed.",
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("cannot reduce", outcome.message)
        self.assertEqual([], self.stage_calls)

    def test_emergency_override_cannot_escalate_narrow_targets_to_full_image(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        state_before = self.state_path.read_bytes()
        current_before = self.engine.current_link.resolve()
        env_before = self.engine.env_file.read_bytes()
        request = DeployRequest(
            "main",
            DeployMode.FULL_IMAGE,
            self.plan.targets,
            archive,
            "Force an immutable rebuild while investigating runtime drift.",
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("complete application target set", outcome.message)
        self.assertEqual((), outcome.activated_services)
        self.assertEqual(state_before, self.state_path.read_bytes())
        self.assertEqual(current_before, self.engine.current_link.resolve())
        self.assertEqual(env_before, self.engine.env_file.read_bytes())
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual("targeted_quick", event["computed_mode"])
        self.assertEqual("full_image", event["requested_mode"])

    def test_emergency_full_escalation_accepts_complete_application_targets(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.CONFIG_RESTART,
            targets=APPLICATION_SERVICES,
            changed_files=("docker-compose.prod.yml",),
            image_input_files=(),
            reasons=("runtime configuration",),
        )
        request = DeployRequest(
            "main",
            DeployMode.FULL_IMAGE,
            APPLICATION_SERVICES,
            archive,
            "Force a complete immutable rebuild for configuration recovery.",
        )

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual(DeployMode.FULL_IMAGE, outcome.mode)
        self.assertIn("dingtalk-api", APPLICATION_SERVICES)
        self.assertIn("dingtalk-api", outcome.activated_services)

    def test_feature_ref_is_rejected_even_with_valid_emergency_reason(self) -> None:
        request = replace(
            self.targeted_request,
            requested_ref="feature/daily-market-brief",
            emergency_reason="Production source policy remains mandatory during recovery.",
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertEqual("source_policy_rejected", outcome.failure_category)
        self.assertEqual([], self.stage_calls)
        self.assertFalse(any(command[:3] == ("docker", "compose", "up") for command in self.runner.commands))
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual("source_policy_rejected", event["failure_category"])

    def test_preflight_failure_happens_before_staging_or_runtime_mutation(self) -> None:
        from scripts.deploy_preflight import ResourceSnapshot

        self.engine.resource_collector = lambda runner: ResourceSnapshot(1, 99.0, 1)

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual([], self.stage_calls)
        self.assertFalse(any(command[:3] == ("docker", "compose", "up") for command in self.runner.commands))
        self.assertEqual(OLD_SHA, load_state(self.state_path).current_sha)
        self.assertEqual("recorded", outcome.audit_status)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual(1, event["preflight"]["available_memory_bytes"])
        self.assertEqual(512 * 1024**2, event["preflight"]["required_available_memory_bytes"])
        self.assertEqual(1, event["preflight"]["minimum_available_memory_bytes"])
        self.assertEqual("targeted_quick", event["preflight"]["memory_policy_mode"])

    def test_full_image_rechecks_memory_after_load_before_selector_mutation(self) -> None:
        from scripts.deploy_preflight import GIB, MIB, ResourceSnapshot

        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("Dockerfile",),
            image_input_files=("Dockerfile",),
            reasons=("image input",),
        )
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )
        snapshots = iter(
            (
                ResourceSnapshot(16 * GIB, 40.0, 768 * MIB),
                ResourceSnapshot(16 * GIB, 40.0, 512 * MIB - 1),
                ResourceSnapshot(16 * GIB, 40.0, 512 * MIB - 1),
            )
        )
        self.engine.resource_collector = lambda runner: next(snapshots)

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("post-load", outcome.message)
        self.assertFalse(
            any(_without_compose_file(command)[:3] == ("docker", "compose", "up") for command in self.runner.commands)
        )
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual(768 * MIB, event["preflight"]["start_available_memory_bytes"])
        self.assertEqual(512 * MIB - 1, event["preflight"]["post_load_available_memory_bytes"])
        self.assertEqual(512 * MIB - 1, event["preflight"]["minimum_available_memory_bytes"])
        self.assertEqual("not_started", event["rollback_status"].split("|")[0])

    def test_full_image_rechecks_memory_before_each_activation_and_rolls_back(self) -> None:
        from scripts.deploy_preflight import GIB, MIB, ResourceSnapshot

        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api", "weekly-review-web"),
            changed_files=("Dockerfile",),
            image_input_files=("Dockerfile",),
            reasons=("image input",),
        )
        request = DeployRequest(
            "main",
            DeployMode.FULL_IMAGE,
            ("command-api", "weekly-review-web"),
            archive,
            None,
        )
        snapshots = iter(
            (
                ResourceSnapshot(16 * GIB, 40.0, 768 * MIB),
                ResourceSnapshot(16 * GIB, 40.0, 700 * MIB),
                ResourceSnapshot(16 * GIB, 40.0, 600 * MIB),
                ResourceSnapshot(16 * GIB, 40.0, 512 * MIB - 1),
                ResourceSnapshot(16 * GIB, 40.0, 512 * MIB - 1),
            )
        )
        self.engine.resource_collector = lambda runner: next(snapshots)

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("before activation", outcome.message)
        self.assertEqual(("command-api",), outcome.activated_services)
        self.assertEqual(("command-api",), outcome.rolled_back_services)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual(2, event["preflight"]["activation_memory_check_count"])
        self.assertEqual(512 * MIB - 1, event["preflight"]["before_activation_available_memory_bytes"])
        self.assertEqual(512 * MIB - 1, event["preflight"]["minimum_available_memory_bytes"])

    def test_every_compose_activation_and_rollback_uses_no_build(self) -> None:
        self.health.fail_for("weekly-review-web")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        compose_up_commands = [
            _without_compose_file(command)
            for command in self.runner.commands
            if _without_compose_file(command)[:3] == ("docker", "compose", "up")
        ]
        self.assertGreaterEqual(len(compose_up_commands), 2)
        self.assertTrue(all("--no-build" in command for command in compose_up_commands))

    def test_source_failure_records_sanitized_failed_event(self) -> None:
        self.runner.results[("git", "-C", str(self.repo), "fetch", "origin", "main")] = CommandResult(
            1, "", "TOKEN=source-secret"
        )

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertIsNone(outcome.failure_category)
        self.assertNotIn("token", outcome.message.lower())
        self.assertEqual("recorded", outcome.audit_status)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual("unhealthy", event["final_health"])
        self.assertEqual("targeted_quick", event["requested_mode"])

    def test_deploy_event_persists_sanitized_source_and_requester_labels(self) -> None:
        request = replace(
            self.targeted_request,
            source="github_actions",
            requested_by="weekly_review_coordinator",
        )

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual("github_actions", event["source"])
        self.assertEqual("weekly_review_coordinator", event["requested_by"])

    def test_deploy_request_rejects_secret_shaped_source_labels(self) -> None:
        with self.assertRaisesRegex(ValueError, "source"):
            replace(self.targeted_request, source="TOKEN=hidden-value")

    def test_deploy_request_rejects_source_outside_explicit_allowlist(self) -> None:
        with self.assertRaisesRegex(ValueError, "source"):
            replace(self.targeted_request, source="rogue_dispatcher")

    def test_deploy_request_accepts_supported_source_allowlist(self) -> None:
        for source in (
            "direct",
            "github_actions",
            "ops_client",
            "mcp",
            "codex_app",
            "verification",
        ):
            with self.subTest(source=source):
                request = replace(self.targeted_request, source=source)
                self.assertEqual(source, request.source)

    def test_deploy_request_rejects_synthetic_credential_label_shapes(self) -> None:
        shapes = (
            "github_pat_" + "A" * 24,
            "sk-" + "B" * 32,
            "AKIA" + "C" * 16,
            "eyJ" + "D" * 12 + "." + "E" * 12 + "." + "F" * 12,
        )

        for index, label in enumerate(shapes):
            with self.subTest(shape=index):
                with self.assertRaisesRegex(ValueError, "requested_by"):
                    replace(self.targeted_request, requested_by=label)

    def test_runtime_failure_records_failed_event(self) -> None:
        self.engine.runtime_validator = lambda runner, compose: (_ for _ in ()).throw(
            RuntimeError("PASSWORD=runtime-secret")
        )

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual("recorded", outcome.audit_status)
        self.assertEqual([], self.stage_calls)

    def test_staging_failure_records_failed_event(self) -> None:
        self.engine.release_stager = lambda sha: (_ for _ in ()).throw(
            OSError("TOKEN=staging-secret")
        )

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual("recorded", outcome.audit_status)
        self.assertNotIn("token", outcome.message.lower())

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
        self.assertEqual(2, self.health.aggregate_checks)

    def test_aggregate_health_runs_only_after_all_targets_are_activated(self) -> None:
        observations: list[str] = []
        self.health.on_check = observations.append

        outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        self.assertEqual(
            [
                "service:command-api",
                "service:weekly-review-web",
                "aggregate",
                "service:command-api",
                "service:weekly-review-web",
                "aggregate",
            ],
            observations,
        )

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
        self.health.fail_aggregate_after = 0

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

    def test_history_worker_target_is_recreated_without_postgresql(self) -> None:
        self.plan = replace(
            self.plan,
            targets=("daily-market-brief-history-worker",),
        )
        request = replace(
            self.targeted_request,
            requested_targets=("daily-market-brief-history-worker",),
        )

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        rendered = [" ".join(_without_compose_file(command)) for command in self.runner.commands]
        self.assertTrue(
            any(
                "docker compose up -d --no-build --no-deps --force-recreate daily-market-brief-history-worker"
                in command
                for command in rendered
            )
        )
        self.assertFalse(any("force-recreate postgres" in command for command in rendered))

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
            "--no-build",
            "--no-deps",
            "--force-recreate",
            "command-api",
        )
        self.runner.sequences[activate] = [
            CommandResult(1, "", "partial activation"),
            CommandResult(0, "", ""),
        ]

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

    def test_full_records_real_post_metrics_and_reclaimed_image_bytes(self) -> None:
        from scripts.deploy_preflight import ResourceSnapshot

        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.plan = DeploymentPlan(
            mode=DeployMode.FULL_IMAGE,
            targets=("command-api",),
            changed_files=("requirements.txt",),
            image_input_files=("requirements.txt",),
            reasons=("dependency input",),
        )
        inventories = [
            (
                ImageRecord("current-id", f"investment-knowledge-app:{OLD_SHA}", 2),
                ImageRecord("old-id", f"investment-knowledge-app:{OLDER_SHA}", 1),
            ),
            (
                ImageRecord("target-id", f"investment-knowledge-app:{TARGET_SHA}", 3),
                ImageRecord("current-id", f"investment-knowledge-app:{OLD_SHA}", 2),
                ImageRecord("old-id", f"investment-knowledge-app:{OLDER_SHA}", 1),
            ),
            (
                ImageRecord("target-id", f"investment-knowledge-app:{TARGET_SHA}", 3),
                ImageRecord("current-id", f"investment-knowledge-app:{OLD_SHA}", 2),
            ),
        ]
        self.engine.image_inventory = lambda: inventories.pop(0)
        self.engine.referenced_image_ids = lambda: {"target-id"}
        resources = [
            ResourceSnapshot(16 * 1024**3, 40.0, 1024 * 1024**2),
            ResourceSnapshot(16 * 1024**3, 39.0, 1000 * 1024**2),
            ResourceSnapshot(16 * 1024**3, 38.0, 900 * 1024**2),
            ResourceSnapshot(17 * 1024**3, 35.0, 1100 * 1024**2),
        ]
        self.engine.resource_collector = lambda runner: resources.pop(0)
        self.runner.results[
            ("docker", "image", "inspect", "--format", "{{.Size}}", "old-id")
        ] = CommandResult(0, "123\n", "")
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, ("command-api",), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertTrue(outcome.ok)
        self.assertEqual(2, outcome.image_count_after)
        self.assertEqual(35.0, outcome.disk_used_after)
        self.assertEqual(123, outcome.cleanup_reclaimed_bytes)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual(2, event["image_count_after"])
        self.assertEqual(35.0, event["disk_used_after"])
        self.assertEqual(123, event["cleanup_reclaimed_bytes"])

    def test_late_release_cleanup_failure_keeps_healthy_activation_committed(self) -> None:
        activation_commands = (
            (
                "docker",
                "compose",
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--force-recreate",
                "command-api",
            ),
            (
                "docker",
                "compose",
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--force-recreate",
                "weekly-review-web",
            ),
        )

        def fail_after_durable_success(releases_dir, protected_shas):
            del releases_dir, protected_shas
            self.assertEqual(TARGET_SHA, load_state(self.state_path).current_sha)
            event = json.loads(
                next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8")
            )
            self.assertEqual("healthy", event["final_health"])
            raise OSError("PASSWORD=late-cleanup-secret")

        with patch(
            "scripts.deploy_release.retain_release_directories",
            side_effect=fail_after_durable_success,
        ):
            outcome = self.engine.deploy(self.targeted_request)

        self.assertTrue(outcome.ok)
        self.assertIn("release_failed", outcome.cleanup_status)
        self.assertEqual(TARGET_SHA, load_state(self.state_path).current_sha)
        self.assertEqual((self.releases_dir / TARGET_SHA).resolve(), self.engine.current_link.resolve())
        self.assertTrue(self.old_release.exists())
        for command in activation_commands:
            self.assertEqual(
                1,
                sum(
                    _without_compose_file(candidate) == command
                    for candidate in self.runner.commands
                ),
            )
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertIn("release_failed", event["rollback_status"])

    def test_release_selector_state_drift_fails_before_staging_or_mutation(self) -> None:
        stale_state = replace(
            load_state(self.state_path),
            current_sha=OLDER_SHA,
            active_release=str(self.older_release),
        )
        write_state(self.state_path, stale_state)
        current_before = self.engine.current_link.resolve()

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertIn("release baseline", outcome.message)
        self.assertEqual([], self.stage_calls)
        self.assertEqual(current_before, self.engine.current_link.resolve())
        self.assertFalse(
            any(command[:3] == ("docker", "compose", "up") for command in self.runner.commands)
        )

    def test_retention_protects_snapshotted_rollback_release_name(self) -> None:
        context = DeploymentContext(
            request=self.targeted_request,
            started_at="2026-07-10T00:00:00Z",
            target_sha=TARGET_SHA,
            previous_state=replace(
                load_state(self.state_path),
                current_sha=OLDER_SHA,
            ),
            selectors=SelectorSnapshot(
                current_release=self.old_release.resolve(),
                previous_release=self.older_release.resolve(),
                env_contents=self.engine.env_file.read_bytes(),
            ),
        )

        protected = self.engine._protected_release_shas(context)

        self.assertEqual({TARGET_SHA, OLDER_SHA, OLD_SHA}, set(protected))

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
        self.assertTrue(event["rollback_status"].startswith("succeeded|"))

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
        self.assertEqual("failed_durable", outcome.audit_status)
        self.assertTrue(self.engine.lockout_path.exists())
        self.assertIn("audit persistence failed", outcome.message)

    def test_lockout_primary_write_failure_uses_durable_fallback(self) -> None:
        self.health.fail_for("weekly-review-web")
        self.health.fail_aggregate_after = 0
        self.engine._persist_lockout = lambda *args: (_ for _ in ()).throw(
            OSError("PASSWORD=lockout-secret")
        )

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertNotIn("password", outcome.message.lower())
        self.assertTrue(self.engine.lockout_path.exists())
        self.assertIsNotNone(outcome.manual_recovery)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertTrue(event["rollback_status"].startswith("rollback_failed|"))

    def test_archive_cleanup_failure_does_not_mask_primary_source_failure(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.runner.results[("git", "-C", str(self.repo), "fetch", "origin", "main")] = CommandResult(
            1, "", "PASSWORD=source-secret"
        )
        self.engine._remove_archive = lambda path: (_ for _ in ()).throw(
            OSError("TOKEN=cleanup-secret")
        )
        request = DeployRequest(
            "main", DeployMode.FULL_IMAGE, (), archive, None
        )

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertIn("production source refresh failed", outcome.message)
        self.assertNotIn("token", outcome.message.lower())
        self.assertEqual("failed", outcome.archive_cleanup)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertIn("archive_cleanup:failed", event["rollback_status"])

    def test_malformed_state_returns_product_safe_audited_outcome(self) -> None:
        self.state_path.write_text('{"PASSWORD":"not-state"}', encoding="utf-8")

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertNotIn("password", outcome.message.lower())
        self.assertEqual("recorded", outcome.audit_status)
        event = json.loads(next(self.engine.events_dir.iterdir()).read_text(encoding="utf-8"))
        self.assertEqual("unhealthy", event["final_health"])

    def test_environment_read_failure_returns_product_safe_audited_outcome(self) -> None:
        self.engine.env_file.unlink()
        self.engine.env_file.mkdir()

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual(
            "deployment failed; inspect the product-safe deployment event",
            outcome.message,
        )
        self.assertEqual("recorded", outcome.audit_status)

    def test_lock_acquisition_failure_returns_product_safe_outcome(self) -> None:
        @contextmanager
        def failed_lock(path):
            del path
            raise OSError("PASSWORD=lock-secret")
            yield

        self.engine.lock_factory = failed_lock

        outcome = self.engine.deploy(self.targeted_request)

        self.assertFalse(outcome.ok)
        self.assertEqual("deployment lock could not be acquired", outcome.message)
        self.assertNotIn("password", outcome.message.lower())
        self.assertEqual("deferred_lock_unavailable", outcome.archive_cleanup)

    def test_existing_lockout_removes_full_archive_while_lock_is_held(self) -> None:
        archive = self.directory / "candidate.tar"
        archive.write_bytes(b"candidate")
        self.engine.lockout_path.write_text("{}\n", encoding="ascii")
        lock_held = False

        @contextmanager
        def tracking_lock(path):
            nonlocal lock_held
            del path
            lock_held = True
            try:
                yield
            finally:
                lock_held = False

        def checked_remove(path):
            self.assertTrue(lock_held)
            path.unlink()

        self.engine.lock_factory = tracking_lock
        self.engine._remove_archive = checked_remove
        request = DeployRequest("main", DeployMode.FULL_IMAGE, (), archive, None)

        outcome = self.engine.deploy(request)

        self.assertFalse(outcome.ok)
        self.assertFalse(archive.exists())
        self.assertEqual("removed", outcome.archive_cleanup)

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
            if _without_compose_file(command)[:3] == ("docker", "compose", "up")
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
        self.health = DockerHealthChecker(
            self.runner, self.current, sleeper=lambda seconds: None
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_history_worker_compose_contract_is_private_and_uses_container_database(self) -> None:
        source = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
        start = source.index("  daily-market-brief-history-worker:\n")
        worker = source[start:source.index("\nvolumes:\n", start)]

        self.assertIn("image: investment-knowledge-app:${APP_IMAGE_TAG:-prod}", worker)
        self.assertIn("restart: unless-stopped", worker)
        self.assertIn("POSTGRES_HOST: postgres", worker)
        self.assertIn("POSTGRES_PORT: 5432", worker)
        self.assertNotIn("ports:", worker)
        self.assertIn("scripts/daily_market_brief_history_worker.py", worker)

    def test_history_worker_compose_entrypoint_exists_in_integrated_checkout(self) -> None:
        source = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
        start = source.index("  daily-market-brief-history-worker:\n")
        worker = source[start:source.index("\nvolumes:\n", start)]
        script_paths = re.findall(r"python (scripts/[A-Za-z0-9_./-]+\.py)", worker)

        self.assertEqual(
            ["scripts/init_db.py", "scripts/daily_market_brief_history_worker.py"],
            script_paths,
        )
        for script_path in script_paths:
            with self.subTest(script_path=script_path):
                self.assertTrue(
                    Path(script_path).is_file(),
                    "integrate the Async Task 2 worker commit before deploying this wiring",
                )

    def test_exact_target_and_aggregate_health_routes_are_checked(self) -> None:
        self.health.check_service("weekly-review-web", ("/daily-market-brief",))
        self.health.check_service("command-api", ())
        self.health.check_service("dingtalk-api", ())
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
            "http://127.0.0.1:8002/health",
            "http://127.0.0.1:8002/dingtalk/webhook",
            "http://127.0.0.1:8000/mcp",
        ):
            self.assertTrue(any(url in command for command in rendered), url)
        self.assertTrue(
            any(
                "--request POST" in command
                and "http://127.0.0.1:8002/dingtalk/webhook" in command
                for command in rendered
            )
        )
        self.assertTrue(any("exec -T postgres pg_isready" in command for command in rendered))

    def test_compose_health_checks_use_the_release_file_explicitly(self) -> None:
        self.health.check_service("weekly-review-web", ())

        self.assertTrue(
            any(
                command[:4]
                == (
                    "docker",
                    "compose",
                    "-f",
                    str(self.current / "docker-compose.prod.yml"),
                )
                for command in self.runner.commands
            )
        )

    def test_aggregate_health_does_not_require_the_optional_dingtalk_api(self) -> None:
        self.health.check_aggregate(())

        rendered = [" ".join(command) for command in self.runner.commands]
        self.assertFalse(
            any("http://127.0.0.1:8002" in command for command in rendered)
        )

    def test_dingtalk_target_health_still_checks_its_http_boundaries(self) -> None:
        self.health.check_service("dingtalk-api", ())

        rendered = [" ".join(command) for command in self.runner.commands]
        self.assertTrue(
            any("http://127.0.0.1:8002/health" in command for command in rendered)
        )
        self.assertTrue(
            any(
                "http://127.0.0.1:8002/dingtalk/webhook" in command
                for command in rendered
            )
        )

    def test_dingtalk_webhook_accepts_bad_request_as_a_safe_rejection(self) -> None:
        command = (
            "curl",
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            "--request",
            "POST",
            "--data-binary",
            "{",
            "http://127.0.0.1:8002/dingtalk/webhook",
        )
        self.runner.results[command] = CommandResult(0, "400", "")

        self.health.check_service("dingtalk-api", ())

        self.assertIn(command, self.runner.commands)

    def test_http_health_retries_a_transient_startup_failure(self) -> None:
        class FlakyHttpRunner(HealthRunner):
            def __init__(self) -> None:
                super().__init__()
                self.health_attempts = 0

            def run(
                self, command: tuple[str, ...], timeout: int | None = None
            ) -> CommandResult:
                if "http://127.0.0.1:8001/health" in command:
                    self.commands.append(command)
                    self.health_attempts += 1
                    if self.health_attempts == 1:
                        return CommandResult(7, "000", "connection refused")
                    return CommandResult(0, "200", "")
                return super().run(command, timeout)

        runner = FlakyHttpRunner()
        sleeps: list[float] = []
        health = DockerHealthChecker(runner, self.current, sleeper=sleeps.append)

        health.check_service("command-api", ())

        self.assertEqual(2, runner.health_attempts)
        self.assertEqual([1.0], sleeps)

    def test_running_scheduler_ignores_handled_task_traceback(self) -> None:
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

        self.health.check_service("account-snapshot-scheduler", ())

        self.assertNotIn(logs, self.runner.commands)

    def test_history_worker_health_uses_running_state_without_log_scan(self) -> None:
        self.health.check_service("daily-market-brief-history-worker", ())

        rendered = [" ".join(command) for command in self.runner.commands]
        self.assertTrue(
            any(
                "ps --status running --format json daily-market-brief-history-worker" in command
                for command in rendered
            )
        )
        self.assertFalse(
            any("logs --no-color" in command for command in rendered)
        )

    def test_scheduler_health_rejects_restart_count(self) -> None:
        inspect = (
            "docker",
            "inspect",
            "--format",
            "{{.RestartCount}}",
            "account-snapshot-scheduler-container",
        )
        self.runner.results[inspect] = CommandResult(0, "1\n", "")

        with self.assertRaisesRegex(DeploymentHealthError, "restarted during startup"):
            self.health.check_service("account-snapshot-scheduler", ())

    def test_not_running_service_reports_safe_startup_log_detail(self) -> None:
        ps = (
            "docker",
            "compose",
            "ps",
            "--status",
            "running",
            "--format",
            "json",
            "daily-market-brief-history-worker",
        )
        logs = (
            "docker",
            "compose",
            "logs",
            "--no-color",
            "--tail",
            "200",
            "daily-market-brief-history-worker",
        )
        self.runner.results[ps] = CommandResult(0, "", "")
        self.runner.results[logs] = CommandResult(
            0,
            (
                "PASSWORD=must-not-leak\n"
                "psycopg.OperationalError: db.internal:5432 unavailable\n"
                "RuntimeError: sk-proj-example-value\n"
                "ModuleNotFoundError: No module named 'investment_knowledge_mcp'\n"
            ),
            "",
        )

        with self.assertRaises(DeploymentHealthError) as raised:
            self.health.check_service("daily-market-brief-history-worker", ())

        message = str(raised.exception)
        self.assertIn("Python module import failed", message)
        self.assertNotIn("must-not-leak", message)
        self.assertNotIn("db.internal", message)
        self.assertNotIn("sk-proj", message)
        self.assertNotIn("investment_knowledge_mcp", message)

    def test_startup_diagnostic_prefers_latest_recognized_failure(self) -> None:
        ps = (
            "docker",
            "compose",
            "ps",
            "--status",
            "running",
            "--format",
            "json",
            "daily-market-brief-history-worker",
        )
        logs = (
            "docker",
            "compose",
            "logs",
            "--no-color",
            "--tail",
            "200",
            "daily-market-brief-history-worker",
        )
        self.runner.results[ps] = CommandResult(0, "", "")
        self.runner.results[logs] = CommandResult(
            0,
            "ModuleNotFoundError: old failure\nPermission denied: current failure\n",
            "",
        )

        with self.assertRaisesRegex(
            DeploymentHealthError, "startup permission check failed"
        ):
            self.health.check_service("daily-market-brief-history-worker", ())

    def test_mcp_target_rejects_not_found_transport(self) -> None:
        command = (
            "curl",
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            "http://127.0.0.1:8000/mcp",
        )
        self.runner.results[command] = CommandResult(0, "404", "")

        with self.assertRaisesRegex(DeploymentHealthError, "MCP transport"):
            self.health.check_service("mcp", ())

    def test_aggregate_rejects_not_found_mcp_transport(self) -> None:
        command = (
            "curl",
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            "http://127.0.0.1:8000/mcp",
        )
        self.runner.results[command] = CommandResult(0, "404", "")

        with self.assertRaisesRegex(DeploymentHealthError, "aggregate MCP"):
            self.health.check_aggregate(())


class ShellWrapperTests(TestCase):
    def _run_wrapper(self, directory: Path, extra_env: dict[str, str]) -> list[str]:
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
            "SOURCE_DIR": str(directory / "repo"),
            "APP_ROOT": str(directory / "app"),
            **extra_env,
        }
        subprocess.run(
            [
                "bash",
                str(
                    Path(__file__).parents[1]
                    / "scripts"
                    / "deploy_from_local_checkout.sh"
                ),
            ],
            check=True,
            env=env,
        )
        return output.read_text(encoding="utf-8").splitlines()

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

    def test_wrapper_maps_legacy_quick_and_external_event_without_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            arguments = self._run_wrapper(
                Path(temporary_directory),
                {
                    "DEPLOY_REF": TARGET_SHA,
                    "DEPLOY_MODE": "quick",
                    "DEPLOY_EVENT_ID": "ops-event-123",
                },
            )

        self.assertEqual("targeted_quick", arguments[arguments.index("--mode") + 1])
        self.assertNotIn("--targets", arguments)
        self.assertEqual(
            "ops-event-123", arguments[arguments.index("--external-event-id") + 1]
        )

    def test_wrapper_maps_legacy_full_and_locates_conventional_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            archive = directory / "legacy images.tar.gz"
            archive.write_bytes(b"legacy archive")
            arguments = self._run_wrapper(
                directory,
                {
                    "DEPLOY_MODE": "full",
                    "IMAGE_TAR": str(archive),
                },
            )

        self.assertEqual("full_image", arguments[arguments.index("--mode") + 1])
        self.assertEqual(str(archive), arguments[arguments.index("--archive") + 1])
        self.assertNotIn("--targets", arguments)

    def test_github_preloaded_archive_environment_selects_explicit_full_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            archive = directory / "investment-knowledge-images.tar.gz"
            archive.write_bytes(b"mutable prod archive")
            arguments = self._run_wrapper(
                directory,
                {
                    "BUILD_IMAGE": "false",
                    "IMAGE_TAR": str(archive),
                },
            )

        self.assertEqual("full_image", arguments[arguments.index("--mode") + 1])
        self.assertEqual(str(archive), arguments[arguments.index("--archive") + 1])
        self.assertNotIn("--targets", arguments)

    def test_ecs_ops_full_environment_does_not_fabricate_missing_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            arguments = self._run_wrapper(
                directory,
                {
                    "BUILD_IMAGE": "true",
                    "DEPLOY_EVENT_ID": "ops-event-456",
                    "IMAGE_TAR": str(directory / "missing-images.tar.gz"),
                },
            )

        self.assertEqual("full_image", arguments[arguments.index("--mode") + 1])
        self.assertEqual("main", arguments[arguments.index("--ref") + 1])
        self.assertNotIn("--targets", arguments)
        self.assertNotIn("--archive", arguments)
        self.assertEqual(
            "ops-event-456", arguments[arguments.index("--external-event-id") + 1]
        )

    def test_wrapper_derives_detached_checkout_sha_when_ref_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            repo = directory / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
            (repo / "README.md").write_text("checkout\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "--quiet",
                    "-m",
                    "checkout",
                ],
                cwd=repo,
                check=True,
            )
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()

            arguments = self._run_wrapper(directory, {"BUILD_IMAGE": "false"})

        self.assertEqual(sha, arguments[arguments.index("--ref") + 1])

    def test_codex_worker_quick_environment_derives_ref_and_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            arguments = self._run_wrapper(
                Path(temporary_directory),
                {"BUILD_IMAGE": "false"},
            )

        self.assertEqual("targeted_quick", arguments[arguments.index("--mode") + 1])
        self.assertEqual("main", arguments[arguments.index("--ref") + 1])
        self.assertNotIn("--targets", arguments)
        self.assertNotIn("--archive", arguments)


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
