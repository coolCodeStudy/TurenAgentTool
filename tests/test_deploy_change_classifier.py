from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

from scripts.deploy_contract import (
    APPLICATION_SERVICES,
    DeployMode,
    _read_changed_files,
    classify_deployment,
    classify_paths,
    serialize_plan,
)
from scripts.classify_deploy_change import classify_changed_files
from scripts.deploy_support import CommandResult


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
        if command[:6] == (
            "git",
            "-C",
            "/repo",
            "diff",
            "--no-renames",
            "--name-only",
        ):
            return ok("\0".join(self.changed_files) + ("\0" if self.changed_files else ""))
        if command[:4] == ("git", "-C", "/repo", "show"):
            return ok("services: {}\n")
        if command[:3] == ("docker", "compose", "-f"):
            return ok(json.dumps(self.compose_configs.pop(0)))
        raise AssertionError(f"unexpected command: {command}")


class DeployContractTests(TestCase):
    def test_known_documentation_roots_and_root_files_are_no_deploy(self) -> None:
        cases = (
            "docs/unreviewed-deployment-notes.md",
            "prompts/stock_research_draft_prompt.md",
            "DEPLOYMENT.md",
            "系统设计.md",
        )
        for path in cases:
            with self.subTest(path=path):
                plan = classify_paths((path,), compose_image_changed=False)
                self.assertEqual(DeployMode.NO_DEPLOY, plan.mode)

    def test_unknown_markdown_and_workflow_paths_are_rejected(self) -> None:
        for path in ("new_area/notes.md", "UNKNOWN.md", ".github/workflows/new-release.yml"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "unclassified deployment-sensitive path"):
                    classify_paths((path,), compose_image_changed=False)

    def test_legacy_classifier_keeps_docs_and_governance_no_deploy(self) -> None:
        result = classify_changed_files(
            (
                "AGENTS.md",
                "docs/project-management/Agent-Operating-Model-Roadmap.md",
                "skills/architecture-code-health/SKILL.md",
                "scripts/evaluate_agent_flow_cases.py",
                "scripts/audit_architecture_health.py",
                "scripts/install_architecture_code_health_skill.py",
                "scripts/smoke_test.py",
                "scripts/verify_change_package.py",
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

    def test_deploy_runner_alone_is_control_plane_only(self) -> None:
        plan = classify_paths(
            ("scripts/deploy_from_local_checkout.sh",),
            compose_image_changed=False,
        )

        self.assertEqual(DeployMode.NO_DEPLOY, plan.mode)
        self.assertEqual((), plan.targets)

    def test_production_env_generator_only_changes_provisioning_templates(self) -> None:
        plan = classify_paths(
            ("scripts/generate_prod_env.py",),
            compose_image_changed=False,
        )

        self.assertEqual(DeployMode.NO_DEPLOY, plan.mode)
        self.assertEqual((), plan.targets)
        self.assertIn("production environment provisioning", plan.reasons[0])

    def test_environment_example_only_changes_provisioning_template(self) -> None:
        plan = classify_paths((".env.example",), compose_image_changed=False)

        self.assertEqual(DeployMode.NO_DEPLOY, plan.mode)
        self.assertEqual((), plan.targets)
        self.assertIn("production environment template", plan.reasons[0])

    def test_real_diff_reads_non_ascii_paths_without_git_quote_escaping(self) -> None:
        class NulDiffRunner:
            def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
                del timeout
                self.command = command
                return ok("docs/中文部署说明.md\0scripts/generate_prod_env.py\0")

        runner = NulDiffRunner()

        paths = _read_changed_files(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(("docs/中文部署说明.md", "scripts/generate_prod_env.py"), paths)
        self.assertIn("-z", runner.command)

    def test_diff_disables_rename_collapsing_for_control_plane_paths(self) -> None:
        class RenameSafeRunner:
            def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
                del timeout
                self.command = command
                return ok("scripts/deploy_contract.py\0archive/deploy_contract.py\0")

        runner = RenameSafeRunner()

        paths = _read_changed_files(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertIn("--no-renames", runner.command)
        self.assertIn("scripts/deploy_contract.py", paths)

    def test_legacy_classifier_keeps_dependency_changes_full(self) -> None:
        self.assertEqual("full", classify_changed_files(("requirements.txt",)).deploy_mode)

    def test_legacy_classifier_keeps_tests_only_no_deploy(self) -> None:
        self.assertEqual(
            "no_deploy",
            classify_changed_files(("tests/test_weekly_review_holder_attribution.py",)).deploy_mode,
        )

    def test_browser_acceptance_specs_are_no_deploy(self) -> None:
        plan = classify_paths(("e2e/cloud-pages.spec.ts",), compose_image_changed=False)

        self.assertEqual(DeployMode.NO_DEPLOY, plan.mode)
        self.assertEqual((), plan.targets)
        self.assertFalse(plan.image_input_files)

    def test_legacy_classifier_keeps_empty_diff_full(self) -> None:
        self.assertEqual("full", classify_changed_files(()).deploy_mode)

    def test_classifies_known_paths_and_targets(self) -> None:
        cases = [
            ((".github/workflows/cloud-e2e.yml",), DeployMode.NO_DEPLOY, ()),
            ((".github/workflows/protected-e2e.yml",), DeployMode.NO_DEPLOY, ()),
            (("playwright.config.ts",), DeployMode.NO_DEPLOY, ()),
            (("docs/README.md",), DeployMode.NO_DEPLOY, ()),
            (
                ("investment_knowledge_mcp/weekly_review_web.py",),
                DeployMode.TARGETED_QUICK,
                ("weekly-review-web",),
            ),
            (
                ("investment_knowledge_mcp/command_workbench.py",),
                DeployMode.TARGETED_QUICK,
                ("weekly-review-web",),
            ),
            (
                ("investment_knowledge_mcp/command_router.py",),
                DeployMode.TARGETED_QUICK,
                ("dingtalk-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
            ),
            (
                ("investment_knowledge_mcp/daily_market_brief.py",),
                DeployMode.TARGETED_QUICK,
                (
                    "dingtalk-api",
                    "dingtalk-stream-bot",
                    "mcp",
                    "scheduler-host",
                    "weekly-review-web",
                ),
            ),
            (
                ("investment_knowledge_mcp/weekly_review.py",),
                DeployMode.TARGETED_QUICK,
                ("dingtalk-api", "dingtalk-stream-bot", "mcp", "weekly-review-web"),
            ),
            (("investment_knowledge_mcp/command_api.py",), DeployMode.TARGETED_QUICK, ("weekly-review-web",)),
            (("investment_knowledge_mcp/server.py",), DeployMode.TARGETED_QUICK, ("mcp",)),
            (
                ("investment_knowledge_mcp/account_snapshots.py",),
                DeployMode.TARGETED_QUICK,
                ("scheduler-host",),
            ),
            (
                ("investment_knowledge_mcp/ipo_reminders.py",),
                DeployMode.TARGETED_QUICK,
                ("scheduler-host",),
            ),
            (("investment_knowledge_mcp/new_runtime_module.py",), DeployMode.TARGETED_QUICK, APPLICATION_SERVICES),
            (("scripts/ecs_ops_api.py",), DeployMode.NO_DEPLOY, ()),
            (("requirements.txt",), DeployMode.FULL_IMAGE, APPLICATION_SERVICES),
            (("docker-compose.prod.yml",), DeployMode.CONFIG_RESTART, APPLICATION_SERVICES),
        ]

        for paths, mode, targets in cases:
            with self.subTest(paths=paths):
                plan = classify_paths(paths, compose_image_changed=False)
                self.assertEqual(mode, plan.mode)
                self.assertEqual(targets, plan.targets)

    def test_dingtalk_http_adapter_targets_only_dingtalk_api(self) -> None:
        plan = classify_paths(
            ("investment_knowledge_mcp/dingtalk_api.py",),
            compose_image_changed=False,
        )

        self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
        self.assertEqual(("dingtalk-api",), plan.targets)

    def test_app_gateway_and_route_controllers_target_only_weekly_review_web(self) -> None:
        for path in (
            "investment_knowledge_mcp/app_gateway.py",
            "investment_knowledge_mcp/weekly_review_controller.py",
            "investment_knowledge_mcp/daily_market_brief_controller.py",
        ):
            with self.subTest(path=path):
                plan = classify_paths((path,), compose_image_changed=False)
                self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
                self.assertEqual(("weekly-review-web",), plan.targets)

    def test_shared_web_experience_targets_only_weekly_review_web(self) -> None:
        plan = classify_paths(
            ("investment_knowledge_mcp/web_experience.py",),
            compose_image_changed=False,
        )

        self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
        self.assertEqual(("weekly-review-web",), plan.targets)

    def test_ai_panorama_package_targets_only_weekly_review_web(self) -> None:
        paths = (
            "investment_knowledge_mcp/ai_industry_panorama/release.py",
            "investment_knowledge_mcp/ai_industry_panorama/web.py",
            "investment_knowledge_mcp/ai_industry_panorama/controller.py",
            "investment_knowledge_mcp/ai_industry_panorama/releases/2026-07-24.v1.json",
        )

        for path in paths:
            with self.subTest(path=path):
                plan = classify_paths((path,), compose_image_changed=False)
                self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
                self.assertEqual(("weekly-review-web",), plan.targets)
                self.assertEqual(
                    (f"{path}: AI Industry Panorama public read surface",),
                    plan.reasons,
                )

    def test_earnings_brief_package_targets_only_weekly_review_web(self) -> None:
        paths = (
            "investment_knowledge_mcp/earnings_brief_studio/release.py",
            "investment_knowledge_mcp/earnings_brief_studio/web.py",
            "investment_knowledge_mcp/earnings_brief_studio/controller.py",
            "investment_knowledge_mcp/earnings_brief_studio/releases/2026-07-24.apple-fy2025-q1.v1.json",
        )

        for path in paths:
            with self.subTest(path=path):
                plan = classify_paths((path,), compose_image_changed=False)
                self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
                self.assertEqual(("weekly-review-web",), plan.targets)
                self.assertEqual(
                    (f"{path}: Earnings Brief Studio public read surface",),
                    plan.reasons,
                )

    def test_ai_panorama_mixed_paths_preserve_risk_and_control_plane_semantics(self) -> None:
        full = classify_paths(
            (
                "investment_knowledge_mcp/ai_industry_panorama/web.py",
                "requirements.txt",
            ),
            compose_image_changed=False,
        )
        control_plane = classify_paths(
            (
                "investment_knowledge_mcp/ai_industry_panorama/release.py",
                "scripts/deploy_contract.py",
            ),
            compose_image_changed=False,
        )

        self.assertEqual(DeployMode.FULL_IMAGE, full.mode)
        self.assertEqual(APPLICATION_SERVICES, full.targets)
        self.assertEqual(("requirements.txt",), full.image_input_files)
        self.assertEqual(DeployMode.TARGETED_QUICK, control_plane.mode)
        self.assertEqual(("weekly-review-web",), control_plane.targets)
        self.assertTrue(
            serialize_plan(control_plane)["control_plane_update_required"]
        )

    def test_ai_panorama_cumulative_candidate_is_contained_to_web(self) -> None:
        plan = classify_paths(
            (
                "docs/architecture/architecture-contract.md",
                "docs/product/PRD-AI-Industry-Panorama.md",
                "docs/project-management/Deploy-Classification.md",
                "docs/techplans/ai-industry-panorama-v1.md",
                "investment_knowledge_mcp/ai_industry_panorama/__init__.py",
                "investment_knowledge_mcp/ai_industry_panorama/controller.py",
                "investment_knowledge_mcp/ai_industry_panorama/release.py",
                "investment_knowledge_mcp/ai_industry_panorama/releases/2026-07-24.v1.json",
                "investment_knowledge_mcp/ai_industry_panorama/web.py",
                "investment_knowledge_mcp/app_gateway.py",
                "investment_knowledge_mcp/web_experience.py",
                "scripts/deploy_contract.py",
                "tests/test_ai_industry_panorama_release.py",
                "tests/test_ai_industry_panorama_web.py",
                "tests/test_app_gateway.py",
                "tests/test_deploy_change_classifier.py",
                "tests/test_web_experience.py",
            ),
            compose_image_changed=False,
        )

        self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
        self.assertEqual(("weekly-review-web",), plan.targets)
        self.assertEqual((), plan.image_input_files)
        self.assertTrue(serialize_plan(plan)["control_plane_update_required"])

    def test_shared_access_targets_only_the_gateway_after_command_retirement(self) -> None:
        for path in (
            "investment_knowledge_mcp/command_http.py",
            "investment_knowledge_mcp/http_access.py",
            "investment_knowledge_mcp/web_access.py",
            "investment_knowledge_mcp/command_workbench.py",
        ):
            with self.subTest(path=path):
                plan = classify_paths((path,), compose_image_changed=False)
                self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
                self.assertEqual(("weekly-review-web",), plan.targets)

    def test_full_and_config_targets_cover_every_managed_app_image_service(self) -> None:
        self.assertIn("dingtalk-api", APPLICATION_SERVICES)
        self.assertIn("scheduler-host", APPLICATION_SERVICES)
        self.assertNotIn("command-api", APPLICATION_SERVICES)
        self.assertEqual(5, len(APPLICATION_SERVICES))
        for path, expected_mode in (
            ("requirements.txt", DeployMode.FULL_IMAGE),
            ("docker-compose.prod.yml", DeployMode.CONFIG_RESTART),
        ):
            with self.subTest(path=path):
                plan = classify_paths((path,), compose_image_changed=False)
                self.assertEqual(expected_mode, plan.mode)
                self.assertEqual(APPLICATION_SERVICES, plan.targets)

    def test_known_production_runtime_scripts_target_current_consumers(self) -> None:
        cases = (
            (
                "scripts/daily_market_brief_history_worker.py",
                ("scheduler-host",),
            ),
            (
                "scripts/dingtalk_stream_bot.py",
                ("dingtalk-stream-bot",),
            ),
            (
                "scripts/init_db.py",
                (
                    "dingtalk-api",
                    "dingtalk-stream-bot",
                    "mcp",
                    "scheduler-host",
                    "weekly-review-web",
                ),
            ),
        )
        for path, targets in cases:
            with self.subTest(path=path):
                plan = classify_paths((path,), compose_image_changed=False)
                self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
                self.assertEqual(targets, plan.targets)
                self.assertNotIn("postgres", plan.targets)

    def test_unknown_deployment_control_file_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unclassified deployment-sensitive path"):
            classify_paths(("scripts/new_control.py",), compose_image_changed=False)

    def test_known_control_plane_modules_do_not_restart_business_services(self) -> None:
        paths = (
            "scripts/bootstrap_deploy_baseline.py",
            "scripts/bootstrap_ops_api_v2_on_ecs.sh",
            "scripts/deploy_contract.py",
            "scripts/deploy_preflight.py",
            "scripts/deploy_release.py",
            "scripts/deploy_retention.py",
            "scripts/deploy_state.py",
            "scripts/deploy_support.py",
            "scripts/ecs_ops_api.py",
            "scripts/smoke_test.py",
            "scripts/verify_change_package.py",
            "scripts/install_ops_api_on_ecs.sh",
        )

        plan = classify_paths(paths, compose_image_changed=False)

        self.assertEqual(DeployMode.NO_DEPLOY, plan.mode)
        self.assertEqual((), plan.targets)

    def test_serialized_plan_marks_control_plane_update_requirement(self) -> None:
        plan = classify_paths(
            ("scripts/deploy_contract.py",),
            compose_image_changed=False,
        )

        self.assertTrue(serialize_plan(plan)["control_plane_update_required"])

    def test_application_plan_does_not_require_control_plane_update(self) -> None:
        plan = classify_paths(
            ("investment_knowledge_mcp/weekly_review_web.py",),
            compose_image_changed=False,
        )

        self.assertFalse(serialize_plan(plan)["control_plane_update_required"])

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
        compose_commands = [command for command in runner.commands if command[:3] == ("docker", "compose", "-f")]
        self.assertTrue(compose_commands)
        self.assertTrue(all("--no-interpolate" in command for command in compose_commands))

    def test_real_diff_uses_config_restart_when_new_service_reuses_existing_image_inputs(self) -> None:
        shared = {"image": "app:stable", "build": {"context": "."}}
        runner = FakeRunner(
            ("docker-compose.prod.yml",),
            (
                {"services": {"weekly-review-web": shared}},
                {
                    "services": {
                        "weekly-review-web": shared,
                        "daily-market-brief-history-worker": shared,
                    }
                },
            ),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.CONFIG_RESTART, plan.mode)
        self.assertEqual(APPLICATION_SERVICES, plan.targets)

    def test_service_removal_is_config_restart_when_image_recipe_is_unchanged(self) -> None:
        shared = {"image": "app:stable", "build": {"context": "."}}
        runner = FakeRunner(
            ("docker-compose.prod.yml",),
            (
                {"services": {"web": shared, "worker": shared}},
                {"services": {"web": shared}},
            ),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.CONFIG_RESTART, plan.mode)

    def test_service_rename_is_config_restart_when_image_recipe_is_unchanged(self) -> None:
        shared = {"image": "app:stable", "build": {"context": "."}}
        runner = FakeRunner(
            ("docker-compose.prod.yml",),
            (
                {"services": {"old-worker": shared}},
                {"services": {"renamed-worker": shared}},
            ),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.CONFIG_RESTART, plan.mode)

    def test_cross_service_recipe_swap_requires_full_image(self) -> None:
        recipe_a = {"image": "app:a", "build": {"context": "./a"}}
        recipe_b = {"image": "app:b", "build": {"context": "./b"}}
        runner = FakeRunner(
            ("docker-compose.prod.yml",),
            (
                {"services": {"web": recipe_a, "worker": recipe_b}},
                {"services": {"web": recipe_b, "worker": recipe_a}},
            ),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.FULL_IMAGE, plan.mode)

    def test_changed_recipe_for_existing_service_requires_full_image(self) -> None:
        runner = FakeRunner(
            ("docker-compose.prod.yml",),
            (
                {"services": {"web": {"image": "app:old"}}},
                {"services": {"web": {"image": "app:new"}}},
            ),
        )

        plan = classify_deployment(Path("/repo"), "a" * 40, "b" * 40, runner)

        self.assertEqual(DeployMode.FULL_IMAGE, plan.mode)

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
                "control_plane_update_required": False,
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
                "targets": ["weekly-review-web"],
                "changed_files": ["investment_knowledge_mcp/command_workbench.py"],
                "image_input_files": [],
                "reasons": ["investment_knowledge_mcp/command_workbench.py: command workbench"],
                "control_plane_update_required": False,
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
