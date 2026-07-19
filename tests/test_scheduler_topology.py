from __future__ import annotations

from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import unittest

from scripts import ecs_ops_api as ops
from scripts.deploy_contract import APPLICATION_SERVICES, DeployMode, classify_paths


OLD_SCHEDULER_SERVICES = {
    "ipo-reminder-scheduler",
    "account-snapshot-scheduler",
    "daily-market-brief-scheduler",
    "daily-market-brief-history-worker",
}
EXPECTED_APPLICATION_SERVICES = (
    "dingtalk-api",
    "dingtalk-stream-bot",
    "mcp",
    "scheduler-host",
    "weekly-review-web",
)


def _compose_service_names() -> set[str]:
    source = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    service_block = source.split("services:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    return set(re.findall(r"^  ([a-z0-9][a-z0-9-]*):$", service_block, re.MULTILINE))


class SchedulerTopologyTests(unittest.TestCase):
    def test_application_inventory_is_exact_five_service_compatibility_topology(self) -> None:
        self.assertEqual(EXPECTED_APPLICATION_SERVICES, APPLICATION_SERVICES)

    def test_default_production_profiles_start_every_health_required_application_service(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker Compose is unavailable")
        entries = dict(
            line.split("=", 1)
            for line in Path(".env.prod.example").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        )
        environment = {
            **os.environ,
            **entries,
            "DINGTALK_STREAM_CLIENT_ID": "test-only-placeholder",
            "DINGTALK_STREAM_CLIENT_SECRET": "test-only-placeholder",
        }

        def compose_services(*profile_args: str) -> set[str]:
            result = subprocess.run(
                (
                    docker,
                    "compose",
                    "-f",
                    "docker-compose.prod.yml",
                    *profile_args,
                    "config",
                    "--services",
                ),
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            return set(result.stdout.splitlines())

        default_services = compose_services()
        all_profile_services = compose_services("--profile", "*")
        source = Path("scripts/ecs_ops_api.py").read_text(encoding="utf-8")
        health_loop = re.search(
            r"for service in \((?P<services>.*?)\):\n\s+checks\.append\(_check_compose_service_running",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(health_loop)
        health_services = set(re.findall(r'"([a-z0-9-]+)"', health_loop.group("services")))

        self.assertEqual(set(APPLICATION_SERVICES), all_profile_services - {"postgres"})
        self.assertEqual(health_services, default_services - {"postgres"})
        self.assertEqual(set(APPLICATION_SERVICES), health_services)

    def test_command_api_is_a_gateway_alias_not_a_compose_target(self) -> None:
        services = _compose_service_names()

        self.assertNotIn("command-api", services)
        self.assertNotIn("command-api", ops.COMPOSE_SERVICES)
        self.assertEqual("weekly-review-web", ops.SERVICE_ALIASES["command-api"])
        self.assertEqual("weekly-review-web", ops.SERVICE_ALIASES["command"])

    def test_compose_replaces_four_old_services_with_scheduler_host(self) -> None:
        services = _compose_service_names()

        self.assertIn("scheduler-host", services)
        self.assertTrue(OLD_SCHEDULER_SERVICES.isdisjoint(services))

    def test_ops_targets_only_scheduler_host_but_preserves_old_aliases(self) -> None:
        self.assertEqual("scheduler-host", ops.COMPOSE_SERVICES["scheduler-host"])
        self.assertTrue(OLD_SCHEDULER_SERVICES.isdisjoint(ops.COMPOSE_SERVICES))
        for alias in (
            *OLD_SCHEDULER_SERVICES,
            "history-worker",
            "daily-market-history",
            "account-snapshot",
            "snapshot",
            "snapshot-scheduler",
            "ipo-reminder",
            "ipo-reminders",
            "ipo-scheduler",
            "daily-market-brief",
        ):
            with self.subTest(alias=alias):
                self.assertEqual("scheduler-host", ops.SERVICE_ALIASES[alias])

    def test_scheduler_runtime_paths_target_only_scheduler_host(self) -> None:
        for path in (
            "investment_knowledge_mcp/account_snapshots.py",
            "investment_knowledge_mcp/ipo_reminders.py",
            "investment_knowledge_mcp/scheduler_host.py",
            "investment_knowledge_mcp/scheduler_jobs.py",
            "investment_knowledge_mcp/scheduler_service.py",
            "scripts/daily_market_brief_history_worker.py",
        ):
            with self.subTest(path=path):
                plan = classify_paths((path,), compose_image_changed=False)
                self.assertEqual(DeployMode.TARGETED_QUICK, plan.mode)
                self.assertEqual(("scheduler-host",), plan.targets)

        shared_queue = classify_paths(
            ("investment_knowledge_mcp/daily_market_jobs.py",),
            compose_image_changed=False,
        )
        self.assertIn("scheduler-host", shared_queue.targets)
        self.assertIn("weekly-review-web", shared_queue.targets)

    def test_rendered_scheduler_host_ignores_host_database_overrides(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker Compose is unavailable")
        environment = {
            **os.environ,
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": "55432",
            "COMMAND_API_TOKEN": "test-only-placeholder",
            "DINGTALK_STREAM_CLIENT_ID": "test-only-placeholder",
            "DINGTALK_STREAM_CLIENT_SECRET": "test-only-placeholder",
        }

        result = subprocess.run(
            (
                docker,
                "compose",
                "-f",
                "docker-compose.prod.yml",
                "config",
                "--format",
                "json",
            ),
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        scheduler = json.loads(result.stdout)["services"]["scheduler-host"]

        self.assertEqual("postgres", scheduler["environment"]["POSTGRES_HOST"])
        self.assertEqual("5432", scheduler["environment"]["POSTGRES_PORT"])

    def test_all_application_services_ignore_host_database_overrides(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker Compose is unavailable")
        environment = {
            **os.environ,
            "POSTGRES_HOST": "host-db-override.invalid",
            "POSTGRES_PORT": "65530",
            "POSTGRES_HOST_PORT": "55432",
            "APP_ACCESS_TOKEN": "test-only-placeholder",
            "DINGTALK_STREAM_CLIENT_ID": "test-only-placeholder",
            "DINGTALK_STREAM_CLIENT_SECRET": "test-only-placeholder",
        }

        result = subprocess.run(
            (
                docker,
                "compose",
                "-f",
                "docker-compose.prod.yml",
                "--profile",
                "*",
                "config",
                "--format",
                "json",
            ),
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        services = json.loads(result.stdout)["services"]

        for service in APPLICATION_SERVICES:
            with self.subTest(service=service):
                self.assertEqual("postgres", services[service]["environment"]["POSTGRES_HOST"])
                self.assertEqual("5432", services[service]["environment"]["POSTGRES_PORT"])
        self.assertIn(
            {"host_ip": "127.0.0.1", "published": "55432", "target": 5432},
            [
                {
                    "host_ip": port.get("host_ip"),
                    "published": port.get("published"),
                    "target": port.get("target"),
                }
                for port in services["postgres"]["ports"]
            ],
        )

    def test_rendered_gateway_owns_both_ports_and_derives_canonical_access_token(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker Compose is unavailable")
        environment = {
            **os.environ,
            "COMMAND_API_TOKEN": "compatible-legacy-placeholder",
            "DINGTALK_STREAM_CLIENT_ID": "test-only-placeholder",
            "DINGTALK_STREAM_CLIENT_SECRET": "test-only-placeholder",
        }
        environment.pop("APP_ACCESS_TOKEN", None)
        environment.pop("WEEKLY_REVIEW_WEB_TOKEN", None)

        result = subprocess.run(
            (
                docker,
                "compose",
                "-f",
                "docker-compose.prod.yml",
                "--profile",
                "http",
                "--profile",
                "stream",
                "config",
                "--format",
                "json",
            ),
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        services = json.loads(result.stdout)["services"]
        gateway = services["weekly-review-web"]

        self.assertNotIn("command-api", services)
        self.assertEqual(
            {("8010", 8010), ("8001", 8010)},
            {(port["published"], port["target"]) for port in gateway["ports"]},
        )
        self.assertEqual(
            "compatible-legacy-placeholder",
            gateway["environment"]["APP_ACCESS_TOKEN"],
        )
        self.assertEqual(
            "compatible-legacy-placeholder",
            gateway["environment"]["COMMAND_API_TOKEN"],
        )
        self.assertEqual(
            "compatible-legacy-placeholder",
            gateway["environment"]["WEEKLY_REVIEW_WEB_TOKEN"],
        )
        self.assertEqual("postgres", gateway["environment"]["POSTGRES_HOST"])
        self.assertEqual("5432", gateway["environment"]["POSTGRES_PORT"])

    def test_rendered_gateway_unifies_conflicting_legacy_values_to_canonical_precedence(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker Compose is unavailable")
        environment = {
            **os.environ,
            "APP_ACCESS_TOKEN": "canonical-test-placeholder",
            "COMMAND_API_TOKEN": "different-command-placeholder",
            "WEEKLY_REVIEW_WEB_TOKEN": "different-weekly-placeholder",
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": "55432",
            "DINGTALK_STREAM_CLIENT_ID": "test-only-placeholder",
            "DINGTALK_STREAM_CLIENT_SECRET": "test-only-placeholder",
        }

        result = subprocess.run(
            (
                docker,
                "compose",
                "-f",
                "docker-compose.prod.yml",
                "--profile",
                "http",
                "--profile",
                "stream",
                "config",
                "--format",
                "json",
            ),
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        gateway = json.loads(result.stdout)["services"]["weekly-review-web"]
        configured = gateway["environment"]

        self.assertEqual(
            {"canonical-test-placeholder"},
            {
                configured["APP_ACCESS_TOKEN"],
                configured["COMMAND_API_TOKEN"],
                configured["WEEKLY_REVIEW_WEB_TOKEN"],
            },
        )
        self.assertEqual("postgres", configured["POSTGRES_HOST"])
        self.assertEqual("5432", configured["POSTGRES_PORT"])


if __name__ == "__main__":
    unittest.main()
