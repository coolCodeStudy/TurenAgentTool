from __future__ import annotations

from http import HTTPStatus
import json
import unittest
from unittest import mock

from investment_knowledge_mcp import command_http
from investment_knowledge_mcp import weekly_review_web as web
from investment_knowledge_mcp.command_router import CommandResult
from investment_knowledge_mcp.command_workbench import (
    execution_blocker,
    list_workbench_actions,
    parse_workbench_command,
    render_command_workbench_html,
)


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
            mock.patch.object(command_http, "parse_workbench_command", return_value=preview),
            mock.patch.object(command_http, "execution_blocker", return_value=None),
            mock.patch.object(command_http, "run_schema", side_effect=RuntimeError(raw_error)),
            mock.patch.object(command_http, "record_command_event", return_value={"id": 77}) as record,
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
            mock.patch.object(command_http, "parse_workbench_command", return_value=preview),
            mock.patch.object(command_http, "execution_blocker", return_value=None),
            mock.patch.object(command_http, "run_schema"),
            mock.patch.object(command_http, "handle_command", return_value=CommandResult(ok=False, message=raw_error)),
            mock.patch.object(command_http, "record_command_event", return_value={"id": 88}) as record,
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


class StockValuationWorkbenchTests(unittest.TestCase):
    def test_catalog_registers_four_valuation_actions_with_exact_side_effect_metadata(self) -> None:
        actions = {action["id"]: action for action in list_workbench_actions()}
        valuation_action_ids = {
            "stock_valuation",
            "stock_valuation_latest",
            "stock_valuation_artifact_evidence",
            "valuation_methods",
        }

        self.assertTrue(valuation_action_ids <= set(actions))
        creation = actions["stock_valuation"]
        self.assertEqual("writes_artifact", creation["safety_level"])
        self.assertFalse(creation["confirmation_required"])
        self.assertIn("local valuation artifact", creation["side_effects"])
        self.assertIn("does not write formal user insights", creation["side_effects"].lower())
        for action_id in valuation_action_ids - {"stock_valuation"}:
            self.assertEqual("read_only", actions[action_id]["safety_level"])
            self.assertFalse(actions[action_id]["confirmation_required"])

    def test_supported_name_aliases_normalize_before_generic_stock_bootstrap(self) -> None:
        cases = (
            ("valuation Intel", "stock_valuation", "stock valuation US.INTC", "US.INTC"),
            ("value SK Hynix", "stock_valuation", "stock valuation KR.000660", "KR.000660"),
            ("估值 建滔積層板", "stock_valuation", "stock valuation HK.01888", "HK.01888"),
            ("latest valuation Intel Corporation", "stock_valuation_latest", "查看估值 US.INTC", "US.INTC"),
            ("查看估值 海力士", "stock_valuation_latest", "查看估值 KR.000660", "KR.000660"),
            ("valuation evidence Kingboard Laminates", "stock_valuation_artifact_evidence", "valuation artifact evidence HK.01888", "HK.01888"),
            ("估值证据 建滔积层板", "stock_valuation_artifact_evidence", "valuation artifact evidence HK.01888", "HK.01888"),
        )
        with mock.patch(
            "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
            return_value=[],
        ):
            for phrase, action_id, exact_command, canonical in cases:
                with self.subTest(phrase=phrase):
                    preview = parse_workbench_command(phrase, allow_llm=False)
                    self.assertEqual("parsed", preview["status"])
                    self.assertEqual(action_id, preview["action_id"])
                    self.assertEqual(exact_command, preview["exact_command"])
                    self.assertEqual(canonical, preview["target"]["canonical"])
                    self.assertFalse(preview["confirmation_required"])
                    self.assertIsNone(execution_blocker(preview, confirmed=False))

    def test_prd_natural_valuation_phrase_normalizes_supported_name_alias(self) -> None:
        with mock.patch(
            "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
            return_value=[],
        ):
            preview = parse_workbench_command("how is SK Hynix valued", allow_llm=False)

        self.assertEqual("parsed", preview["status"])
        self.assertEqual("stock_valuation", preview["action_id"])
        self.assertEqual("stock valuation KR.000660", preview["exact_command"])
        self.assertEqual("KR.000660", preview["target"]["canonical"])
        self.assertFalse(preview["confirmation_required"])
        self.assertIsNone(execution_blocker(preview, confirmed=False))

    def test_market_qualified_unknown_symbol_keeps_current_bootstrap_recovery(self) -> None:
        with mock.patch(
            "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
            return_value=[],
        ):
            preview = parse_workbench_command("valuation US.MSTR", allow_llm=False)

        self.assertEqual("parsed", preview["status"])
        self.assertEqual("bootstrap_stock_profile", preview["action_id"])
        self.assertEqual("创建股票档案 MSTR US", preview["exact_command"])
        self.assertTrue(preview["confirmation_required"])
        self.assertIn("not in the stock profile database", preview["recovery_message"])

    def test_profiled_targets_and_all_command_aliases_emit_stable_exact_commands(self) -> None:
        profile = {"symbol": "INTC", "market": "US", "name": "Intel Corporation"}
        with mock.patch(
            "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
            return_value=[profile],
        ):
            creation = [
                parse_workbench_command(f"{alias} US.INTC", allow_llm=False)
                for alias in ("valuation", "value", "估值")
            ]
            latest = [
                parse_workbench_command(f"{alias} US.INTC", allow_llm=False)
                for alias in ("latest valuation", "查看估值")
            ]
            evidence = [
                parse_workbench_command(f"{alias} US.INTC", allow_llm=False)
                for alias in ("valuation artifact evidence", "valuation evidence", "估值证据")
            ]
            methods = [
                parse_workbench_command(alias, allow_llm=False)
                for alias in ("valuation methods", "估值方法")
            ]

        self.assertEqual({item["exact_command"] for item in creation}, {"valuation US.INTC"})
        self.assertEqual({item["exact_command"] for item in latest}, {"查看估值 US.INTC"})
        self.assertEqual(
            {item["exact_command"] for item in evidence},
            {"valuation artifact evidence US.INTC"},
        )
        self.assertEqual({item["exact_command"] for item in methods}, {"估值方法"})
        self.assertTrue(all(not item["confirmation_required"] for item in (*creation, *latest, *evidence, *methods)))

    def test_path_like_valuation_target_returns_bounded_recovery(self) -> None:
        with mock.patch(
            "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
            return_value=[],
        ):
            preview = parse_workbench_command(
                "valuation artifact evidence ../../etc/passwd",
                allow_llm=False,
            )

        self.assertEqual("needs_entity", preview["status"])
        self.assertEqual("stock_valuation_artifact_evidence", preview["action_id"])
        self.assertNotIn("/etc/passwd", preview["recovery_message"])
        self.assertNotIn("..", preview["recovery_message"])

    def test_existing_access_recovery_shell_is_preserved(self) -> None:
        html = render_command_workbench_html()

        self.assertIn('id="access-panel"', html)
        self.assertIn("InvestmentKnowledgeAccess", html)
        self.assertIn("access_required", html)
        self.assertIn("retryPendingRequest", html)


class PortfolioHoldingResolutionTests(unittest.TestCase):
    def test_named_current_holding_requires_explicit_profile_setup_when_unprofiled(self) -> None:
        snapshots = [{"positions": [{"code": "US.SPCX", "stock_name": "SpaceX", "qty": 1}]}]
        with (
            mock.patch(
                "investment_knowledge_mcp.command_workbench.repository.list_account_snapshots",
                return_value=snapshots,
            ),
            mock.patch(
                "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
                return_value=[],
            ),
            mock.patch("investment_knowledge_mcp.command_workbench.repository.upsert_stock_profile") as upsert_stock,
        ):
            preview = parse_workbench_command("决策 SpaceX", allow_llm=False)

        self.assertEqual("parsed", preview["status"])
        self.assertEqual("bootstrap_stock_profile", preview["action_id"])
        self.assertEqual("创建股票档案 SPCX US", preview["exact_command"])
        self.assertEqual("US.SPCX", preview["target"]["canonical"])
        self.assertEqual("portfolio_holding", preview["target"]["source"])
        self.assertTrue(preview["confirmation_required"])
        self.assertIn("current holding", preview["recovery_message"])
        upsert_stock.assert_not_called()

    def test_named_current_holding_uses_existing_profile_without_bootstrap(self) -> None:
        snapshots = [{"positions": [{"code": "US.SPCX", "stock_name": "SpaceX", "qty": 1}]}]
        profile = {"symbol": "SPCX", "market": "US", "name": "SpaceX"}
        with (
            mock.patch(
                "investment_knowledge_mcp.command_workbench.repository.list_account_snapshots",
                return_value=snapshots,
            ),
            mock.patch(
                "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
                side_effect=lambda query: [profile] if query == "SPCX" else [],
            ),
        ):
            preview = parse_workbench_command("决策 SpaceX", allow_llm=False)

        self.assertEqual("parsed", preview["status"])
        self.assertEqual("decision_card", preview["action_id"])
        self.assertEqual("决策 US.SPCX", preview["exact_command"])
        self.assertEqual("US.SPCX", preview["target"]["canonical"])
        self.assertEqual("portfolio_holding", preview["target"]["source"])

    def test_market_qualified_holding_code_uses_the_same_portfolio_match(self) -> None:
        snapshots = [{"positions": [{"code": "US.SPCX", "stock_name": "SpaceX", "qty": 1}]}]
        with (
            mock.patch(
                "investment_knowledge_mcp.command_workbench.repository.list_account_snapshots",
                return_value=snapshots,
            ),
            mock.patch(
                "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
                return_value=[],
            ),
        ):
            preview = parse_workbench_command("决策 US.SPCX", allow_llm=False)

        self.assertEqual("bootstrap_stock_profile", preview["action_id"])
        self.assertEqual("US.SPCX", preview["target"]["canonical"])
        self.assertEqual("portfolio_holding", preview["target"]["source"])


if __name__ == "__main__":
    unittest.main()
