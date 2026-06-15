from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import scripts.ecs_ops_api as ops


class EcsOpsApiDeployTests(unittest.TestCase):
    def test_deploy_continues_when_start_event_recording_fails(self) -> None:
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
                patch.object(
                    ops,
                    "_record_deploy_start",
                    side_effect=RuntimeError("record deploy start failed: RuntimeError: deploy_events unavailable"),
                ),
                patch.object(ops, "_ensure_clean_repo"),
                patch.object(ops, "_run_git", side_effect=fake_run_git),
                patch.object(ops, "_run", return_value=ops.CommandResult(True, ["bash"], "deployed\n", "", 0)),
                patch.object(ops, "build_deploy_health", return_value={"ok": True, "checks": []}),
            ):
                result = ops._deploy_ref_locked(ref="main", mode="quick", source="codex_app", requested_by="codex")

            self.assertEqual(result["status"], "succeeded")
            self.assertIsNone(result["deploy_event_id"])
            self.assertEqual(result["commit_sha"], "abc123def456")
            self.assertIn("deploy event start recording failed", result["warnings"][0])

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
