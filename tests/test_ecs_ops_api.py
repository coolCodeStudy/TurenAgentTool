from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

import scripts.ecs_ops_api as ops


class EcsOpsApiDeployTests(unittest.TestCase):
    def test_deploy_ref_returns_started_without_running_deploy_inline(self) -> None:
        with TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            app_dir = Path(tmp) / "app"
            (repo_dir / ".git").mkdir(parents=True)
            (repo_dir / "scripts").mkdir()
            (repo_dir / "scripts" / "deploy_from_local_checkout.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            mutex = threading.Lock()
            started_threads: list[dict[str, object]] = []

            class FakeThread:
                def __init__(self, target: object, kwargs: dict[str, object], daemon: bool) -> None:
                    self.target = target
                    self.kwargs = kwargs
                    self.daemon = daemon

                def start(self) -> None:
                    started_threads.append({"target": self.target, "kwargs": self.kwargs, "daemon": self.daemon})
                    mutex.release()

            with (
                patch.object(ops, "REPO_DIR", repo_dir),
                patch.object(ops, "APP_DIR", app_dir),
                patch.object(ops, "DEPLOY_MUTEX", mutex),
                patch.object(ops.threading, "Thread", FakeThread),
                patch.object(ops, "ALLOWED_NAMED_REFS", {"main"}),
                patch.object(ops, "_record_deploy_start", return_value="42"),
                patch.object(ops, "_run_git", side_effect=AssertionError("deploy should run in background")),
            ):
                result = ops.deploy_ref({"ref": "main", "mode": "quick", "source": "codex_app", "requested_by": "codex"})

            self.assertEqual(result["status"], "started")
            self.assertEqual(result["deploy_event_id"], 42)
            self.assertEqual(result["status_url"], "/ops/deploy-status?id=42")
            self.assertEqual(len(started_threads), 1)
            self.assertTrue(started_threads[0]["daemon"])

    def test_run_deploy_with_event_finishes_existing_event(self) -> None:
        with TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            app_dir = Path(tmp) / "app"
            (repo_dir / ".git").mkdir(parents=True)
            (repo_dir / "scripts").mkdir()
            (repo_dir / "scripts" / "deploy_from_local_checkout.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            def fake_run_git(args: list[str], timeout: float | None = None) -> ops.CommandResult:
                if args == ["fetch", "--prune", "origin"]:
                    return ops.CommandResult(True, ["git", *args], "", "", 0)
                if args == ["checkout", "--detach", "origin/main"]:
                    return ops.CommandResult(True, ["git", *args], "", "", 0)
                if args == ["rev-parse", "HEAD"]:
                    return ops.CommandResult(True, ["git", *args], "abc123def456\n", "", 0)
                raise AssertionError(f"unexpected git args: {args}")

            with (
                patch.object(ops, "REPO_DIR", repo_dir),
                patch.object(ops, "APP_DIR", app_dir),
                patch.object(ops, "ALLOWED_NAMED_REFS", {"main"}),
                patch.object(ops, "_ensure_clean_repo"),
                patch.object(ops, "_run_git", side_effect=fake_run_git),
                patch.object(ops, "_run", return_value=ops.CommandResult(True, ["bash"], "deployed\n", "", 0)),
                patch.object(ops, "build_deploy_health", return_value={"ok": True, "checks": []}),
                patch.object(ops, "_record_deploy_finish") as finish,
            ):
                result = ops._run_deploy_with_event(
                    event_id="42",
                    ref="main",
                    mode="quick",
                    requested_by="codex",
                    metadata={"requested_ref": "main"},
                )

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["deploy_event_id"], 42)
            self.assertEqual(result["commit_sha"], "abc123def456")
            finish.assert_called_once()

    def test_read_deploy_event_returns_json_object(self) -> None:
        payload = '{"id": 42, "status": "started"}'
        with patch.object(ops, "_run", return_value=ops.CommandResult(True, ["python"], payload, "", 0)):
            self.assertEqual(ops.read_deploy_event(42), {"id": 42, "status": "started"})

    def test_command_error_summary_prefers_traceback_exception_tail(self) -> None:
        text = "\n".join(
            [
                "Traceback (most recent call last):",
                "  File \"/app/scripts/record_deploy_event.py\", line 1, in <module>",
                "    main()",
                "RuntimeError: deploy_events relation is unavailable",
            ]
        )

        self.assertEqual(
            ops._summarize_command_error(text),
            "RuntimeError: deploy_events relation is unavailable",
        )


if __name__ == "__main__":
    unittest.main()
