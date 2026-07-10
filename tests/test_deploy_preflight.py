from __future__ import annotations

import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest import TestCase

from scripts.deploy_contract import DeployMode
from scripts.deploy_preflight import (
    GIB,
    MIB,
    DeployPreflightError,
    ResourceSnapshot,
    collect_resources,
    deployment_lock,
    evaluate_preflight,
    validate_runtime,
)
from scripts.deploy_support import CommandResult


def ok(stdout: str = "") -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr="")


class FakeRunner:
    def __init__(self, results: dict[tuple[str, ...], CommandResult | BaseException]) -> None:
        self.results = results
        self.calls: list[tuple[tuple[str, ...], int | None]] = []

    def run(self, command: tuple[str, ...], timeout: int | None = None) -> CommandResult:
        self.calls.append((command, timeout))
        result = self.results.get(command)
        if result is None:
            raise AssertionError(f"unexpected command: {command}")
        if isinstance(result, BaseException):
            raise result
        return result


def _hold_lock(path: str, ready: multiprocessing.synchronize.Event, release: multiprocessing.synchronize.Event) -> None:
    with deployment_lock(Path(path)):
        ready.set()
        release.wait(5)


class PreflightTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.directory = Path(self.tempdir.name)
        self.lock_path = self.directory / "deploy.lock"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_quick_accepts_exact_minimums(self) -> None:
        snapshot = ResourceSnapshot(
            free_disk_bytes=8 * GIB,
            disk_used_percent=80.0,
            available_memory_bytes=512 * MIB,
        )

        self.assertTrue(evaluate_preflight(snapshot, DeployMode.TARGETED_QUICK, None).ok)

    def test_full_accepts_exact_archive_headroom(self) -> None:
        archive_bytes = 3 * GIB
        snapshot = ResourceSnapshot(
            free_disk_bytes=archive_bytes * 2 + 2 * GIB,
            disk_used_percent=50.0,
            available_memory_bytes=2 * GIB,
        )

        self.assertTrue(evaluate_preflight(snapshot, DeployMode.FULL_IMAGE, archive_bytes).ok)

    def test_full_requires_archive_headroom(self) -> None:
        snapshot = ResourceSnapshot(
            free_disk_bytes=5 * GIB,
            disk_used_percent=50.0,
            available_memory_bytes=2 * GIB,
        )

        result = evaluate_preflight(snapshot, DeployMode.FULL_IMAGE, int(1.6 * GIB))

        self.assertFalse(result.ok)
        self.assertIn("full image requires", " ".join(result.errors))

    def test_thresholds_reject_one_unit_below_each_minimum_or_above_maximum(self) -> None:
        cases = (
            ResourceSnapshot(8 * GIB - 1, 80.0, 512 * MIB),
            ResourceSnapshot(8 * GIB, 80.0001, 512 * MIB),
            ResourceSnapshot(8 * GIB, 80.0, 512 * MIB - 1),
        )

        for snapshot in cases:
            with self.subTest(snapshot=snapshot):
                self.assertFalse(evaluate_preflight(snapshot, DeployMode.TARGETED_QUICK, None).ok)

    def test_collect_resources_parses_stable_linux_command_output(self) -> None:
        runner = FakeRunner(
            {
                ("df", "-Pk", "/"): ok(
                    "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                    "/dev/root 1000000 200000 800000 20% /\n"
                ),
                ("free", "-b"): ok(
                    "              total        used        free      shared  buff/cache   available\n"
                    "Mem:     4294967296 1073741824 1073741824 0 2147483648 2147483648\n"
                ),
            }
        )

        snapshot = collect_resources(runner)

        self.assertEqual(ResourceSnapshot(800000 * 1024, 20.0, 2147483648), snapshot)

    def test_collect_resources_hides_command_failure_details(self) -> None:
        runner = FakeRunner(
            {
                ("df", "-Pk", "/"): CommandResult(7, "", "PASSWORD=secret TOKEN=abc raw environment"),
            }
        )

        with self.assertRaises(DeployPreflightError) as context:
            collect_resources(runner)

        self.assertEqual("resource disk probe failed (exit code 7)", str(context.exception))
        self.assertNotIn("password", str(context.exception).lower())
        self.assertNotIn("token", str(context.exception).lower())
        self.assertNotIn("raw environment", str(context.exception))

    def test_validate_runtime_uses_ten_second_docker_timeout_and_returns_labels(self) -> None:
        compose_file = self.directory / "docker-compose.prod.yml"
        runner = FakeRunner(
            {
                ("docker", "info"): ok(),
                ("docker", "compose", "-f", str(compose_file), "config", "--quiet"): ok(),
                (
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "ps",
                    "--status",
                    "running",
                    "--format",
                    "json",
                    "postgres",
                ): ok(
                    '{"ID":"container-id","Name":"project-postgres-1",'
                    '"Service":"postgres","State":"running","Status":"Up 10 seconds"}\n'
                ),
                (
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "exec",
                    "-T",
                    "postgres",
                    "pg_isready",
                ): ok("accepting connections\n"),
            }
        )

        labels = validate_runtime(runner, compose_file)

        self.assertEqual(("docker_health", "compose_valid", "postgresql_health"), labels)
        self.assertEqual(("docker", "info"), runner.calls[0][0])
        self.assertEqual(10, runner.calls[0][1])

    def test_validate_runtime_rejects_empty_postgres_rows_before_health_probe(self) -> None:
        compose_file = self.directory / "compose.yml"
        postgres_command = (
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "ps",
            "--status",
            "running",
            "--format",
            "json",
            "postgres",
        )
        health_command = (
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "exec",
            "-T",
            "postgres",
            "pg_isready",
        )

        for output in ("", " \n\t"):
            with self.subTest(output=repr(output)):
                runner = FakeRunner(
                    {
                        ("docker", "info"): ok(),
                        ("docker", "compose", "-f", str(compose_file), "config", "--quiet"): ok(),
                        postgres_command: ok(output),
                        health_command: ok("accepting connections\n"),
                    }
                )

                with self.assertRaises(DeployPreflightError) as context:
                    validate_runtime(runner, compose_file)

                self.assertEqual("postgresql container is not running", str(context.exception))
                self.assertNotIn(health_command, [command for command, _ in runner.calls])

    def test_validate_runtime_rejects_docker_timeout_without_stderr(self) -> None:
        compose_file = self.directory / "compose.yml"
        runner = FakeRunner({("docker", "info"): TimeoutError("password=secret TOKEN=abc")})

        with self.assertRaises(DeployPreflightError) as context:
            validate_runtime(runner, compose_file)

        self.assertEqual("docker preflight timed out after 10 seconds", str(context.exception))
        self.assertNotIn("password", str(context.exception).lower())
        self.assertNotIn("token", str(context.exception).lower())

    def test_validate_runtime_rejects_invalid_compose_with_one_safe_message(self) -> None:
        compose_file = self.directory / "compose.yml"
        runner = FakeRunner(
            {
                ("docker", "info"): ok(),
                ("docker", "compose", "-f", str(compose_file), "config", "--quiet"): CommandResult(
                    14, "", "PASSWORD=secret token=abc invalid interpolation"
                ),
            }
        )

        with self.assertRaises(DeployPreflightError) as context:
            validate_runtime(runner, compose_file)

        self.assertEqual("compose configuration is invalid (exit code 14)", str(context.exception))
        self.assertNotIn("password", str(context.exception).lower())
        self.assertNotIn("token", str(context.exception).lower())
        self.assertEqual(2, len(runner.calls))

    def test_validate_runtime_rejects_unhealthy_postgresql(self) -> None:
        compose_file = self.directory / "compose.yml"
        runner = FakeRunner(
            {
                ("docker", "info"): ok(),
                ("docker", "compose", "-f", str(compose_file), "config", "--quiet"): ok(),
                (
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "ps",
                    "--status",
                    "running",
                    "--format",
                    "json",
                    "postgres",
                ): ok(
                    '{"ID":"container-id","Name":"project-postgres-1",'
                    '"Service":"postgres","State":"running","Status":"Up 10 seconds"}\n'
                ),
                (
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "exec",
                    "-T",
                    "postgres",
                    "pg_isready",
                ): CommandResult(2, "", "password=secret database refused"),
            }
        )

        with self.assertRaises(DeployPreflightError) as context:
            validate_runtime(runner, compose_file)

        self.assertEqual("postgresql health check failed (exit code 2)", str(context.exception))
        self.assertNotIn("password", str(context.exception).lower())
        self.assertNotIn("token", str(context.exception).lower())

    def test_lock_is_non_reentrant(self) -> None:
        with deployment_lock(self.lock_path):
            with self.assertRaisesRegex(DeployPreflightError, "another deployment is active"):
                with deployment_lock(self.lock_path):
                    pass

    def test_lock_is_exclusive_across_processes(self) -> None:
        context = multiprocessing.get_context("fork")
        ready = context.Event()
        release = context.Event()
        process = context.Process(target=_hold_lock, args=(str(self.lock_path), ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaisesRegex(DeployPreflightError, "another deployment is active"):
                with deployment_lock(self.lock_path):
                    pass
        finally:
            release.set()
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join()
        self.assertEqual(0, process.exitcode)


if __name__ == "__main__":
    unittest.main()
