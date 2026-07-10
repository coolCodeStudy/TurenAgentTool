from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

from scripts.deploy_contract import (
    DeployMode,
    classify_deployment,
    classify_paths,
    serialize_plan,
)
from scripts.classify_deploy_change import classify_changed_files
from scripts.deploy_support import CommandResult


APPLICATION_SERVICES = (
    "account-snapshot-scheduler",
    "command-api",
    "dingtalk-stream-bot",
    "ipo-reminder-scheduler",
    "mcp",
    "weekly-review-web",
)


def ok(stdout: str) -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr="")


class FakeRunner:
    def __init__(self, changed_files: tuple[str, ...], compose_configs: tuple[dict[str, object], ...]):
        self.changed_files = changed_files
        self.compose_configs = list(compose_configs)
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        del timeout
        self.commands.append(command)
        if command[:5] == ("git", "-C", "/repo", "diff", "--name-only"):
            return ok("\n".join(self.changed_files))
        if command[:4] == ("git", "-C", "/repo", "show"):
            return ok("services: {}\n")
        if command[:3] == ("docker", "compose", "-f"):
            return ok(json.dumps(self.compose_configs.pop(0)))
        raise AssertionError(f"unexpected command: {command}")


class DeployContractTests(TestCase):
    def test_known_documentation_path_is_no_deploy(self) -> None:
        plan = classify_paths(("docs/README.md",), compose_image_changed=False)

        self.assertEqual(DeployMode.NO_DEPLOY, plan.mode)

    def test_unknown_documentation_and_workflow_paths_are_rejected(self) -> None:
        for path in ("docs/unreviewed-deployment-notes.md", ".github/workflows/new-release.yml"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "unclassified deployment-sensitive path"):
                    classify_paths((path,), compose_image_changed=False)

    def test_legacy_classifier_keeps_docs_and_governance_no_deploy(self) -> None:
        result = classify_changed_files(
            (
                "AGENTS.md",
                "docs/project-management/Agent-Operating-Model-Roadmap.md",
                "scripts/evaluate_agent_flow_cases.py",
                ".github/workflows/deploy.yml",
            )
        )

        self.assertEqual("no_deploy", result.deploy_mode)

    def test_legacy_classifier_keeps_runtime_and_deploy_script_quick(self) -> None:
        result = classify_changed_files(
            (
                "investment_knowledge_mcp/command_workbench.py",
                "scripts/deploy_from_local_checkout.sh",
            )
        )

        self.assertEqual("quick", result.deploy_mode)

    def test_legacy_classifier_keeps_dependency_changes_full(self) -> None:
        self.assertEqual("full", classify_changed_files(("requirements.txt",)).deploy_mode)

    def test_legacy_classifier_keeps_tests_only_no_deploy(self) -> None:
        self.assertEqual(
            "no_deploy",
            classify_changed_files(("tests/test_weekly_review_holder_attribution.py",)).deploy_mode,
        )

    def test_legacy_classifier_keeps_empty_diff_full(self) -> None:
        self.assertEqual("full", classify_changed_files(()).deploy_mode)

    def test_classifies_known_paths_and_targets(self) -> None:
        cases = [
            (("docs/README.md",), DeployMode.NO_DEPLOY, ()),
            (
                ("investment_knowledge_mcp/weekly_review_web.py",),
                DeployMode.TARGETED_QUICK,
                ("weekly-review-web",),
            ),
            (
                ("investment_knowledge_mcp/command_workbench.py",),
                DeployMode.TARGETED_QUICK,
                ("command-api", "weekly-review-web"),
            ),
            (
                ("investment_knowledge_mcp/command_router.py",),
                DeployMode.TARGETED_QUICK,
                ("command-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
            ),
            (
                ("investment_knowledge_mcp/daily_market_brief.py",),
                DeployMode.TARGETED_QUICK,
                ("command-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
            ),
            (
                ("investment_knowledge_mcp/weekly_review.py",),
                DeployMode.TARGETED_QUICK,
                ("command-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
            ),
            (("investment_knowledge_mcp/command_api.py",), DeployMode.TARGETED_QUICK, ("command-api",)),
            (("investment_knowledge_mcp/server.py",), DeployMode.TARGETED_QUICK, ("mcp",)),
            (
                ("investment_knowledge_mcp/account_snapshots.py",),
                DeployMode.TARGETED_QUICK,
                ("account-snapshot-scheduler",),
            ),
            (
                ("investment_knowledge_mcp/ipo_reminders.py",),
                DeployMode.TARGETED_QUICK,
                ("ipo-reminder-scheduler",),
            ),
            (("investment_knowledge_mcp/new_runtime_module.py",), DeployMode.TARGETED_QUICK, APPLICATION_SERVICES),
            (("scripts/ecs_ops_api.py",), DeployMode.TARGETED_QUICK, ("investment-ops-api.service",)),
            (("requirements.txt",), DeployMode.FULL_IMAGE, APPLICATION_SERVICES),
            (("docker-compose.prod.yml",), DeployMode.CONFIG_RESTART, APPLICATION_SERVICES),
        ]

        for paths, mode, targets in cases:
            with self.subTest(paths=paths):
                plan = classify_paths(paths, compose_image_changed=False)
                self.assertEqual(mode, plan.mode)
                self.assertEqual(targets, plan.targets)

    def test_unknown_deployment_control_file_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unclassified deployment-sensitive path"):
            classify_paths(("scripts/new_deploy_switch.py",), compose_image_changed=False)

    def test_compose_image_inputs_require_a_full_image_deploy(self) -> None:
        plan = classify_paths(("docker-compose.prod.yml",), compose_image_changed=True)

        self.assertEqual(DeployMode.FULL_IMAGE, plan.mode)
        self.assertEqual(("docker-compose.prod.yml",), plan.image_input_files)

    def test_real_diff_uses_config_restart_for_environment_only_compose_change(self) -> None:
        runner = FakeRunner(
            ("docker-compose.prod.yml",),
            (
                {"services": {"mcp": {"image": "app:base", "environment": {"LOG_LEVEL": "info"}}}},
                {"services": {"mcp": {"image": "app:base", "environment": {"LOG_LEVEL": "debug"}}}},
            ),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.CONFIG_RESTART, plan.mode)
        self.assertEqual(APPLICATION_SERVICES, plan.targets)
        self.assertEqual(("docker-compose.prod.yml",), plan.changed_files)
        self.assertEqual((), plan.image_input_files)

    def test_real_diff_uses_full_image_for_compose_build_change(self) -> None:
        runner = FakeRunner(
            ("docker-compose.prod.yml",),
            (
                {"services": {"mcp": {"image": "app:stable", "build": {"context": "./base"}}}},
                {"services": {"mcp": {"image": "app:stable", "build": {"context": "./next"}}}},
            ),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.FULL_IMAGE, plan.mode)
        self.assertEqual(("docker-compose.prod.yml",), plan.image_input_files)

    def test_real_diff_uses_full_image_for_compose_platform_change(self) -> None:
        runner = FakeRunner(
            ("docker-compose.prod.yml",),
            (
                {"services": {"mcp": {"image": "app:stable", "platform": "linux/amd64"}}},
                {"services": {"mcp": {"image": "app:stable", "platform": "linux/arm64"}}},
            ),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.FULL_IMAGE, plan.mode)
        self.assertEqual(("docker-compose.prod.yml",), plan.image_input_files)

    def test_mixed_paths_promote_risk_and_union_targets(self) -> None:
        runner = FakeRunner(
            ("investment_knowledge_mcp/command_api.py", "requirements.txt", "docs/README.md"),
            (),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.FULL_IMAGE, plan.mode)
        self.assertEqual(APPLICATION_SERVICES, plan.targets)
        self.assertEqual(("requirements.txt",), plan.image_input_files)
        self.assertEqual(
            {
                "mode": "full_image",
                "targets": list(APPLICATION_SERVICES),
                "changed_files": [
                    "docs/README.md",
                    "investment_knowledge_mcp/command_api.py",
                    "requirements.txt",
                ],
                "image_input_files": ["requirements.txt"],
                "reasons": list(plan.reasons),
            },
            serialize_plan(plan),
        )

    def test_cli_json_preserves_legacy_mode_and_emits_deployment_plan(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/classify_deploy_change.py",
                "--format",
                "json",
                "investment_knowledge_mcp/command_workbench.py",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            {
                "mode": "targeted_quick",
                "targets": ["command-api", "weekly-review-web"],
                "changed_files": ["investment_knowledge_mcp/command_workbench.py"],
                "image_input_files": [],
                "reasons": ["investment_knowledge_mcp/command_workbench.py: command workbench"],
                "deploy_mode": "quick",
            },
            json.loads(completed.stdout),
        )

    def test_cli_reference_mode_uses_normalized_compose_image_inputs(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "classify_deploy_change.py"
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            self._run(("git", "init"), cwd=repo)
            self._run(("git", "config", "user.email", "tests@example.com"), cwd=repo)
            self._run(("git", "config", "user.name", "Deployment Tests"), cwd=repo)
            compose = repo / "docker-compose.prod.yml"
            compose.write_text("services:\n  mcp:\n    build: ./base\n", encoding="utf-8")
            self._run(("git", "add", "docker-compose.prod.yml"), cwd=repo)
            self._run(("git", "commit", "-m", "base compose"), cwd=repo)
            base_sha = self._output(("git", "rev-parse", "HEAD"), cwd=repo).strip()

            compose.write_text("services:\n  mcp:\n    build: ./next\n", encoding="utf-8")
            self._run(("git", "commit", "-am", "change build input"), cwd=repo)
            target_sha = self._output(("git", "rev-parse", "HEAD"), cwd=repo).strip()

            bin_dir = Path(directory) / "bin"
            bin_dir.mkdir()
            docker = bin_dir / "docker"
            docker.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "import sys\n"
                "from pathlib import Path\n"
                "compose = Path(sys.argv[3]).read_text(encoding='utf-8')\n"
                "context = './next' if './next' in compose else './base'\n"
                "print(json.dumps({'services': {'mcp': {'build': {'context': context}}}}))\n",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            environment = os.environ | {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--format",
                    "json",
                    "--repo",
                    str(repo),
                    "--base-sha",
                    base_sha,
                    "--target-sha",
                    target_sha,
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("full_image", json.loads(completed.stdout)["mode"])
        self.assertEqual("full", json.loads(completed.stdout)["deploy_mode"])

    def _run(self, command: tuple[str, ...], *, cwd: Path) -> None:
        subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)

    def _output(self, command: tuple[str, ...], *, cwd: Path) -> str:
        return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True).stdout


if __name__ == "__main__":
    import unittest

    unittest.main()
