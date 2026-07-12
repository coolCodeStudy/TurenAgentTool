from __future__ import annotations

import unittest
from unittest import mock

from investment_knowledge_mcp import server
from investment_knowledge_mcp.command_router import CommandResult


class DailyMarketBriefAgentCommandTests(unittest.TestCase):
    def test_controlled_agent_allowlist_includes_approved_history_commands(self) -> None:
        for command in (
            "补齐每日市场简报 CN 2026-07-01 到 2026-07-10",
            "补齐每日市场简报 CN,HK,US 最近20个交易日",
            "取消每日市场简报任务 123",
            "每日市场简报任务 123",
        ):
            with self.subTest(command=command):
                self.assertTrue(server._is_safe_agent_command(command))

        self.assertFalse(server._is_safe_agent_command("删除每日市场简报任务 123"))

    def test_controlled_agent_entry_point_executes_all_approved_history_phrases(self) -> None:
        commands = (
            "补齐每日市场简报 CN 2026-07-01 到 2026-07-10",
            "补齐每日市场简报 CN,HK,US 最近20个交易日",
            "取消每日市场简报任务 123",
            "每日市场简报任务 123",
        )
        for command in commands:
            with self.subTest(command=command):
                with (
                    mock.patch.object(server, "run_schema") as run_schema,
                    mock.patch.object(server, "handle_command", return_value=CommandResult(ok=True, message="任务 #88")) as handle,
                    mock.patch.object(server, "_record_agent_command"),
                ):
                    result = server.run_investment_command(command, sender="coordinator")

                self.assertEqual({"ok": True, "message": "任务 #88"}, result)
                run_schema.assert_called_once_with()
                handle.assert_called_once_with(command, include_artifact_path=False)

    def test_controlled_agent_exception_never_returns_sensitive_details(self) -> None:
        raw_error = "postgresql://admin:fake-secret@db/investment SELECT * FROM private_table"
        with (
            mock.patch.object(server, "run_schema"),
            mock.patch.object(server, "handle_command", side_effect=RuntimeError(raw_error)),
            mock.patch.object(server, "_record_agent_command") as record,
            mock.patch.object(server.logger, "exception") as log_exception,
        ):
            result = server.run_investment_command("每日市场简报任务 123", sender="coordinator")

        self.assertFalse(result["ok"])
        self.assertIn("执行 InvestmentKnowledge 指令失败，请稍后重试", result["message"])
        self.assertIn("Investment command failed", result["message"])
        for secret in ("fake-secret", "postgresql://", "SELECT *", "private_table"):
            self.assertNotIn(secret, result["message"])
            self.assertNotIn(secret, record.call_args.kwargs["message"])
        log_exception.assert_called_once()

    def test_controlled_agent_failed_result_never_returns_sensitive_details(self) -> None:
        raw_error = "读取失败 postgresql://admin:fake-secret@db/investment SELECT * FROM private_table"
        with (
            mock.patch.object(server, "run_schema"),
            mock.patch.object(server, "handle_command", return_value=CommandResult(ok=False, message=raw_error)),
            mock.patch.object(server, "_record_agent_command") as record,
        ):
            result = server.run_investment_command("每日市场简报任务 123", sender="coordinator")

        self.assertFalse(result["ok"])
        self.assertIn("执行 InvestmentKnowledge 指令失败，请稍后重试", result["message"])
        for secret in ("fake-secret", "postgresql://", "SELECT *", "private_table"):
            self.assertNotIn(secret, result["message"])
            self.assertNotIn(secret, record.call_args.kwargs["message"])


if __name__ == "__main__":
    unittest.main()
