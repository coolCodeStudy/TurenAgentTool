from __future__ import annotations

import json
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from scripts.bootstrap_deploy_baseline import initialize_baseline
from scripts.deploy_release import DeploymentError
from scripts.deploy_state import load_state
from scripts.deploy_support import CommandResult


BASELINE_SHA = "a" * 40
IMAGE_ID = "sha256:" + "1" * 64


class BaselineRunner:
    def __init__(
        self,
        repo: Path,
        *,
        immutable_tag_exists: bool = False,
        immutable_image_id: str = IMAGE_ID,
        running_image: str = "investment-knowledge-app:prod",
    ) -> None:
        self.repo = repo
        self.immutable_tag_exists = immutable_tag_exists
        self.immutable_image_id = immutable_image_id
        self.running_image = running_image
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        del timeout
        self.commands.append(command)
        if command[-2:] == ("rev-parse", "HEAD"):
            return CommandResult(0, BASELINE_SHA + "\n", "")
        if "status" in command and "--porcelain" in command:
            return CommandResult(0, "", "")
        if command[:3] == ("git", "-C",) and "merge-base" in command:
            return CommandResult(0, "", "")
        if "archive" in command and "--output" in command:
            output = Path(command[command.index("--output") + 1])
            with tarfile.open(output, "w") as archive:
                for entry in sorted(self.repo.iterdir()):
                    archive.add(entry, arcname=entry.name)
            return CommandResult(0, "", "")
        if command[:2] == ("docker", "ps"):
            return CommandResult(
                0,
                json.dumps(
                    {
                        "ID": "container-1",
                        "Image": self.running_image,
                        "Labels": "com.docker.compose.service=weekly-review-web",
                    }
                )
                + "\n",
                "",
            )
        if command[:3] == ("docker", "inspect", "--format"):
            return CommandResult(0, IMAGE_ID + "\n", "")
        if command[:4] == ("docker", "image", "inspect", "--format"):
            if self.immutable_tag_exists:
                return CommandResult(0, self.immutable_image_id + "\n", "")
            return CommandResult(1, "", "not found")
        if command[:3] == ("docker", "image", "tag"):
            self.immutable_tag_exists = True
            return CommandResult(0, "", "")
        if command[:3] == ("docker", "image", "rm"):
            self.immutable_tag_exists = False
            return CommandResult(0, "", "")
        return CommandResult(0, "", "")


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 11, 3, 0, tzinfo=timezone.utc)


class BootstrapDeployBaselineTests(TestCase):
    def test_initializes_legacy_checkout_without_recreating_containers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            app_root = root / "app"
            repo.mkdir()
            app_root.mkdir()
            (repo / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
            (repo / "drafts").mkdir()
            (app_root / ".git").mkdir()
            (app_root / ".env").write_text("APP_IMAGE_TAG=prod\n", encoding="utf-8")
            runner = BaselineRunner(repo)

            def stage_release(sha: str) -> Path:
                release = app_root / "releases" / sha
                release.mkdir(parents=True)
                (release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
                return release

            state = initialize_baseline(
                repo=repo,
                app_root=app_root,
                runner=runner,
                clock=FixedClock(),
                compose_project_name="turenagenttool_prod",
                release_stager=stage_release,
                runtime_validator=lambda runner, compose: (
                    "docker_health",
                    "compose_valid",
                    "postgresql_health",
                ),
            )

            release = app_root / "releases" / BASELINE_SHA
            self.assertEqual(BASELINE_SHA, state.current_sha)
            self.assertEqual(f"investment-knowledge-app:{BASELINE_SHA}", state.current_image)
            self.assertEqual(release.resolve(), (app_root / "current").resolve())
            self.assertEqual(BASELINE_SHA, load_state(app_root / "shared" / "deploy-state.json").current_sha)
            self.assertIn(f"APP_IMAGE_TAG={BASELINE_SHA}", (app_root / ".env").read_text(encoding="utf-8"))
            self.assertIn(
                ("docker", "image", "tag", IMAGE_ID, f"investment-knowledge-app:{BASELINE_SHA}"),
                runner.commands,
            )
            self.assertFalse(any(command[:3] == ("docker", "compose", "up") for command in runner.commands))

    def test_prefers_existing_managed_release_link_over_root_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            app_root = root / "app"
            release = app_root / "releases" / BASELINE_SHA
            repo.mkdir()
            release.mkdir(parents=True)
            (release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
            (app_root / "current").symlink_to(release, target_is_directory=True)
            (app_root / ".env").write_text("APP_IMAGE_TAG=prod\n", encoding="utf-8")
            runner = BaselineRunner(repo)

            state = initialize_baseline(
                repo=repo,
                app_root=app_root,
                runner=runner,
                clock=FixedClock(),
                compose_project_name="turenagenttool_prod",
                release_stager=lambda sha: release,
                runtime_validator=lambda runner, compose: (
                    "docker_health",
                    "compose_valid",
                    "postgresql_health",
                ),
            )

            self.assertEqual(BASELINE_SHA, state.current_sha)
            self.assertFalse(any("rev-parse" in command for command in runner.commands))

    def test_identifies_application_container_by_compose_service_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            app_root = root / "app"
            release = app_root / "releases" / BASELINE_SHA
            repo.mkdir()
            release.mkdir(parents=True)
            (release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
            (app_root / "current").symlink_to(release, target_is_directory=True)
            (app_root / ".env").write_text("APP_IMAGE_TAG=prod\n", encoding="utf-8")
            runner = BaselineRunner(repo, running_image="turenagenttool_prod-weekly-review-web")

            state = initialize_baseline(
                repo=repo,
                app_root=app_root,
                runner=runner,
                clock=FixedClock(),
                compose_project_name="turenagenttool_prod",
                release_stager=lambda sha: release,
                runtime_validator=lambda runner, compose: (
                    "docker_health",
                    "compose_valid",
                    "postgresql_health",
                ),
            )

            self.assertEqual(BASELINE_SHA, state.current_sha)

    def test_existing_state_is_idempotent_and_does_not_touch_docker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            app_root = root / "app"
            repo.mkdir()
            app_root.mkdir()
            (repo / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
            (repo / "drafts").mkdir()
            (app_root / ".git").mkdir()
            (app_root / ".env").write_text("APP_IMAGE_TAG=prod\n", encoding="utf-8")
            first_runner = BaselineRunner(repo)

            def stage_release(sha: str) -> Path:
                release = app_root / "releases" / sha
                release.mkdir(parents=True)
                (release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
                return release

            expected = initialize_baseline(
                repo=repo,
                app_root=app_root,
                runner=first_runner,
                clock=FixedClock(),
                compose_project_name="turenagenttool_prod",
                release_stager=stage_release,
                runtime_validator=lambda runner, compose: (
                    "docker_health",
                    "compose_valid",
                    "postgresql_health",
                ),
            )
            second_runner = BaselineRunner(repo, immutable_tag_exists=True)

            actual = initialize_baseline(
                repo=repo,
                app_root=app_root,
                runner=second_runner,
                clock=FixedClock(),
                compose_project_name="turenagenttool_prod",
                runtime_validator=lambda runner, compose: (
                    "docker_health",
                    "compose_valid",
                    "postgresql_health",
                ),
            )

            self.assertEqual(expected, actual)
            self.assertFalse(
                any(command[:3] in (("docker", "image", "tag"), ("docker", "image", "rm")) for command in second_runner.commands)
            )

    def test_refuses_to_overwrite_conflicting_immutable_image_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            app_root = root / "app"
            release = app_root / "releases" / BASELINE_SHA
            repo.mkdir()
            release.mkdir(parents=True)
            (release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
            (app_root / "current").symlink_to(release, target_is_directory=True)
            (app_root / ".env").write_text("APP_IMAGE_TAG=prod\n", encoding="utf-8")
            runner = BaselineRunner(
                repo,
                immutable_tag_exists=True,
                immutable_image_id="sha256:" + "2" * 64,
            )

            with self.assertRaisesRegex(DeploymentError, "already points elsewhere"):
                initialize_baseline(
                    repo=repo,
                    app_root=app_root,
                    runner=runner,
                    clock=FixedClock(),
                    compose_project_name="turenagenttool_prod",
                    release_stager=lambda sha: release,
                    runtime_validator=lambda runner, compose: (),
                )

            self.assertEqual("APP_IMAGE_TAG=prod\n", (app_root / ".env").read_text())
            self.assertFalse(any(command[:3] == ("docker", "image", "tag") for command in runner.commands))

    def test_runtime_failure_restores_selectors_and_removes_created_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            app_root = root / "app"
            release = app_root / "releases" / BASELINE_SHA
            repo.mkdir()
            release.mkdir(parents=True)
            (release / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
            (app_root / "current").symlink_to(release, target_is_directory=True)
            (app_root / ".env").write_text("APP_IMAGE_TAG=prod\n", encoding="utf-8")
            runner = BaselineRunner(repo)

            with self.assertRaisesRegex(DeploymentError, "runtime unavailable"):
                initialize_baseline(
                    repo=repo,
                    app_root=app_root,
                    runner=runner,
                    clock=FixedClock(),
                    compose_project_name="turenagenttool_prod",
                    release_stager=lambda sha: release,
                    runtime_validator=lambda runner, compose: (_ for _ in ()).throw(
                        DeploymentError("runtime unavailable")
                    ),
                )

            self.assertEqual("APP_IMAGE_TAG=prod\n", (app_root / ".env").read_text())
            self.assertEqual(release.resolve(), (app_root / "current").resolve())
            self.assertFalse((app_root / "shared" / "deploy-state.json").exists())
            self.assertIn(
                ("docker", "image", "rm", f"investment-knowledge-app:{BASELINE_SHA}"),
                runner.commands,
            )
