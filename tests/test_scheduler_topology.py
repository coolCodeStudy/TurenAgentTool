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
    "command-api",
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
    def test_application_inventory_is_exact_six_service_compatibility_topology(self) -> None:
        self.assertEqual(EXPECTED_APPLICATION_SERVICES, APPLICATION_SERVICES)

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


if __name__ == "__main__":
    unittest.main()
