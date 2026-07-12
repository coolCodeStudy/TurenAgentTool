from __future__ import annotations

import unittest

from investment_knowledge_mcp.command_workbench import execution_blocker, parse_workbench_command


class DailyMarketBriefWorkbenchTests(unittest.TestCase):
    def test_approved_history_phrases_parse_to_executable_exact_commands(self) -> None:
        cases = (
            ("补齐每日市场简报 CN 2026-07-01 到 2026-07-10", "daily_market_history_backfill", True),
            ("补齐每日市场简报 CN,HK,US 最近20个交易日", "daily_market_history_backfill", True),
            ("取消每日市场简报任务 123", "daily_market_history_cancel", True),
            ("每日市场简报任务 123", "daily_market_history_status", False),
        )
        for phrase, action_id, confirmation_required in cases:
            with self.subTest(phrase=phrase):
                preview = parse_workbench_command(phrase, allow_llm=False)
                self.assertEqual("parsed", preview["status"])
                self.assertEqual(action_id, preview["action_id"])
                self.assertEqual(phrase, preview["exact_command"])
                self.assertEqual(confirmation_required, preview["confirmation_required"])
                self.assertIsNone(execution_blocker(preview, confirmed=confirmation_required))

    def test_history_write_actions_are_registered_but_require_confirmation(self) -> None:
        preview = parse_workbench_command(
            "",
            action_id="daily_market_history_cancel",
            fields={"job_id": "123"},
            allow_llm=False,
        )

        self.assertEqual("取消每日市场简报任务 123", preview["exact_command"])
        self.assertIsNotNone(execution_blocker(preview, confirmed=False))
        self.assertIsNone(execution_blocker(preview, confirmed=True))


if __name__ == "__main__":
    unittest.main()
