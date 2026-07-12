from __future__ import annotations

from http import HTTPStatus
import json
import unittest
from unittest import mock

from investment_knowledge_mcp import weekly_review_web as web
from investment_knowledge_mcp.command_router import CommandResult
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

    def test_execute_boundary_sanitizes_schema_failure_in_response_and_audit(self) -> None:
        raw_error = "postgresql://admin:fake-password@db/investment SELECT * FROM private_table"
        preview = {
            "status": "parsed",
            "supports_execution": True,
            "exact_command": "每日市场简报任务 123",
            "confirmation_required": False,
        }
        handler = object.__new__(web.WeeklyReviewWebHandler)
        handler._write_json = mock.Mock()
        with (
            mock.patch.object(web, "parse_workbench_command", return_value=preview),
            mock.patch.object(web, "execution_blocker", return_value=None),
            mock.patch.object(web, "run_schema", side_effect=RuntimeError(raw_error)),
            mock.patch.object(web, "_record_workbench_event", return_value={"id": 77}) as record,
            mock.patch.object(web.logger, "exception") as log_exception,
        ):
            handler._handle_workbench_execute({"text": "每日市场简报任务 123"})

        status, response = handler._write_json.call_args.args
        self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, status)
        public_text = json.dumps(response, ensure_ascii=False)
        audit_message = record.call_args.kwargs["message"]
        self.assertIn("Command execution failed", public_text)
        for secret in ("fake-password", "postgresql://", "SELECT *", "private_table"):
            self.assertNotIn(secret, public_text)
            self.assertNotIn(secret, audit_message)
        log_exception.assert_called_once()

    def test_execute_boundary_sanitizes_failed_command_result_response_and_audit(self) -> None:
        raw_error = "读取失败 postgresql://admin:fake-password@db SELECT * FROM private_table"
        preview = {
            "status": "parsed",
            "supports_execution": True,
            "exact_command": "每日市场简报任务 123",
            "confirmation_required": False,
        }
        handler = object.__new__(web.WeeklyReviewWebHandler)
        handler._write_json = mock.Mock()
        with (
            mock.patch.object(web, "parse_workbench_command", return_value=preview),
            mock.patch.object(web, "execution_blocker", return_value=None),
            mock.patch.object(web, "run_schema"),
            mock.patch.object(web, "handle_command", return_value=CommandResult(ok=False, message=raw_error)),
            mock.patch.object(web, "record_command_event", return_value={"id": 88}) as record,
        ):
            handler._handle_workbench_execute({"text": "每日市场简报任务 123"})

        status, response = handler._write_json.call_args.args
        self.assertEqual(HTTPStatus.BAD_REQUEST, status)
        public_text = json.dumps(response, ensure_ascii=False)
        audit_message = record.call_args.kwargs["message"]
        self.assertIn("Command execution failed", public_text)
        for secret in ("fake-password", "postgresql://", "SELECT *", "private_table"):
            self.assertNotIn(secret, public_text)
            self.assertNotIn(secret, audit_message)


if __name__ == "__main__":
    unittest.main()
