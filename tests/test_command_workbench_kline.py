from __future__ import annotations

import unittest

from investment_knowledge_mcp.command_workbench import (
    execution_blocker,
    list_workbench_actions,
    parse_workbench_command,
)


class CommandWorkbenchKlineTests(unittest.TestCase):
    def test_exact_kline_command_previews_as_read_only_action(self) -> None:
        preview = parse_workbench_command("K线调查 US.NVDA 5年 前复权", allow_llm=False)

        self.assertEqual(preview["status"], "parsed")
        self.assertEqual(preview["action_id"], "kline_investigation")
        self.assertEqual(preview["exact_command"], "K线调查 US.NVDA 5年 前复权")
        self.assertEqual(preview["safety_level"], "read_only")
        self.assertFalse(preview["confirmation_required"])
        self.assertIsNone(execution_blocker(preview, confirmed=False))

    def test_kline_action_is_visible_in_catalog(self) -> None:
        actions = {action["id"]: action for action in list_workbench_actions()}

        self.assertIn("kline_investigation", actions)
        self.assertEqual(actions["kline_investigation"]["action_family"], "Market Behavior")
        self.assertIn("K线调查", actions["kline_investigation"]["aliases"])


if __name__ == "__main__":
    unittest.main()
