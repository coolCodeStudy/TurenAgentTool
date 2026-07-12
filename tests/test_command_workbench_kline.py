from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from investment_knowledge_mcp.command_router import CommandResult
from investment_knowledge_mcp.command_workbench import (
    execution_blocker,
    list_workbench_actions,
    parse_workbench_command,
    render_command_workbench_html,
)
from investment_knowledge_mcp.weekly_review_web import WeeklyReviewWebHandler


class CommandWorkbenchKlineTests(unittest.TestCase):
    def test_exact_kline_command_previews_as_read_only_action(self) -> None:
        preview = parse_workbench_command("K线调查 US.NVDA 5年 前复权", allow_llm=False)

        self.assertEqual(preview["status"], "parsed")
        self.assertEqual(preview["action_id"], "kline_investigation")
        self.assertEqual(preview["exact_command"], "K线调查 US.NVDA 5年 前复权")
        self.assertIsNotNone(preview["target"])
        self.assertEqual(preview["target"]["canonical"], "US.NVDA")
        self.assertEqual(preview["safety_level"], "read_only")
        self.assertFalse(preview["confirmation_required"])
        self.assertIsNone(execution_blocker(preview, confirmed=False))

    def test_kline_action_is_visible_in_catalog(self) -> None:
        actions = {action["id"]: action for action in list_workbench_actions()}

        self.assertIn("kline_investigation", actions)
        self.assertEqual(actions["kline_investigation"]["action_family"], "Market Behavior")
        self.assertIn("K线调查", actions["kline_investigation"]["aliases"])

    def test_rendered_command_workbench_script_is_valid_javascript(self) -> None:
        html = render_command_workbench_html()
        match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
        self.assertIsNotNone(match)

        with tempfile.TemporaryDirectory() as tmp_dir:
            script_path = Path(tmp_dir) / "command-workbench.js"
            script_path.write_text(match.group(1), encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_weekly_review_web_executes_kline_without_forcing_degraded_provider(self) -> None:
        captured: dict[str, object] = {}
        handler = object.__new__(WeeklyReviewWebHandler)

        def write_json(status: object, payload: dict[str, object]) -> None:
            captured["status"] = status
            captured["payload"] = payload

        handler._write_json = write_json  # type: ignore[attr-defined]

        with (
            patch("investment_knowledge_mcp.weekly_review_web.run_schema"),
            patch(
                "investment_knowledge_mcp.weekly_review_web.handle_command",
                return_value=CommandResult(ok=True, message="kline report"),
            ) as mock_handle,
            patch(
                "investment_knowledge_mcp.weekly_review_web.record_command_event",
                return_value={"id": 123},
            ),
        ):
            handler._handle_workbench_execute({"text": "K线调查 US.NVDA 5年 前复权"})

        self.assertEqual(captured["payload"]["message"], "kline report")
        self.assertEqual(mock_handle.call_args.args[0], "K线调查 US.NVDA 5年 前复权")
        self.assertNotIn("disable_kline_live_provider", mock_handle.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
