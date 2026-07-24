from __future__ import annotations

from datetime import date, datetime, timezone
import unittest
from unittest import mock

from investment_knowledge_mcp import command_router


class CrowdingCommandTests(unittest.TestCase):
    def test_single_symbol_crowding_is_a_read_only_evidence_query(self) -> None:
        assessment = object()
        with (
            mock.patch.object(
                command_router,
                "investigate_symbol_crowding",
                return_value=assessment,
            ) as investigate,
            mock.patch.object(
                command_router,
                "render_crowding_assessment",
                return_value="US.NVDA evidence report",
            ),
        ):
            result = command_router.handle_command("拥挤度 US.NVDA")

        self.assertTrue(result.ok)
        self.assertIn("US.NVDA", result.message)
        investigate.assert_called_once_with("NVDA", "US")
        self.assertTrue(command_router.is_query_command("拥挤度 US.NVDA"))
        self.assertTrue(command_router.is_query_command("crowding NVDA US"))
        self.assertFalse(command_router.is_query_command("拥挤度 NVDA"))

    def test_invalid_or_unsupported_single_symbol_is_rejected_before_fetch(self) -> None:
        with mock.patch.object(command_router, "investigate_symbol_crowding") as investigate:
            unqualified = command_router.handle_command("拥挤度 NVDA")
            unsupported = command_router.handle_command("crowding JP.7203")

        self.assertFalse(unqualified.ok)
        self.assertFalse(unsupported.ok)
        self.assertIn("市场限定", unqualified.message)
        self.assertIn("US/HK/KR/CN", unsupported.message)
        investigate.assert_not_called()

    def test_portfolio_crowding_reads_positions_and_never_exposes_provider_errors(self) -> None:
        snapshot = mock.Mock(positions=[{"code": "US.NVDA"}])
        report = object()
        with (
            mock.patch.object(command_router, "get_futu_positions", return_value=snapshot),
            mock.patch.object(
                command_router,
                "investigate_portfolio_crowding",
                return_value=report,
            ) as investigate,
            mock.patch.object(
                command_router,
                "render_portfolio_crowding",
                return_value="按市场分组；不是投资建议",
            ),
        ):
            result = command_router.handle_command("持仓拥挤度")

        self.assertTrue(result.ok)
        self.assertIn("不是投资建议", result.message)
        investigate.assert_called_once_with(snapshot.positions)
        self.assertTrue(command_router.is_query_command("持仓拥挤度"))
        self.assertTrue(command_router.is_query_command("portfolio crowding"))

        with mock.patch.object(
            command_router,
            "get_futu_positions",
            side_effect=RuntimeError("password=secret /private/path"),
        ):
            failed = command_router.handle_command("拥挤交易")
        self.assertFalse(failed.ok)
        self.assertIn("持仓暂时不可用", failed.message)
        self.assertNotIn("secret", failed.message)
        self.assertNotIn("/private", failed.message)

    def test_help_includes_both_crowding_entry_points(self) -> None:
        result = command_router.handle_command("help")
        self.assertIn("持仓拥挤度", result.message)
        self.assertIn("拥挤度 US.NVDA", result.message)


class DailyMarketBriefHistoryCommandTests(unittest.TestCase):
    def test_date_range_normalizes_markets_and_filters_weekends(self) -> None:
        parsed = command_router._match_daily_market_history_job_command(
            "补齐每日市场简报 A股,港股 2026-07-03 到 2026-07-06",
        )

        self.assertEqual(["CN", "HK"], parsed["markets"])
        self.assertEqual(
            [
                ("CN", date(2026, 7, 3)),
                ("CN", date(2026, 7, 6)),
                ("HK", date(2026, 7, 3)),
                ("HK", date(2026, 7, 6)),
            ],
            parsed["pairs"],
        )
        self.assertFalse(parsed["force_refresh"])

    def test_recent_market_days_stop_before_each_markets_latest_completed_session(self) -> None:
        now = datetime(2026, 7, 13, 8, 30, tzinfo=timezone.utc)
        parsed = command_router._match_daily_market_history_job_command(
            "补齐每日市场简报 CN,US 最近2个交易日",
            now=now,
        )

        self.assertEqual(
            [
                ("CN", date(2026, 7, 9)),
                ("CN", date(2026, 7, 10)),
                ("US", date(2026, 7, 8)),
                ("US", date(2026, 7, 9)),
            ],
            parsed["pairs"],
        )
        self.assertIn("节假日", parsed["calendar_note"])

    def test_recent_multi_market_enqueue_preserves_pairs_without_cross_product(self) -> None:
        now = datetime(2026, 7, 13, 8, 30, tzinfo=timezone.utc)
        jobs = [
            {"id": 401, "total_count": 2, "skipped_count": 0},
            {"id": 402, "total_count": 2, "skipped_count": 0},
        ]
        with (
            mock.patch.object(command_router, "_daily_market_history_now", return_value=now),
            mock.patch.object(command_router.daily_market_jobs, "create_history_job", side_effect=jobs) as create,
        ):
            result = command_router.handle_command("补齐每日市场简报 CN,US 最近2个交易日")

        self.assertTrue(result.ok)
        self.assertEqual(2, create.call_count)
        self.assertEqual((["CN"], [date(2026, 7, 9), date(2026, 7, 10)]), create.call_args_list[0].args)
        self.assertEqual((["US"], [date(2026, 7, 8), date(2026, 7, 9)]), create.call_args_list[1].args)
        self.assertIn("#401", result.message)
        self.assertIn("#402", result.message)

    def test_more_than_120_items_is_rejected_before_repository_call(self) -> None:
        with mock.patch.object(command_router.daily_market_jobs, "create_history_job") as create:
            result = command_router.handle_command("补齐每日市场简报 CN,HK,US 最近41个交易日")

        self.assertFalse(result.ok)
        self.assertIn("最多 120", result.message)
        create.assert_not_called()

    def test_backfill_command_enqueues_without_synchronous_provider_call(self) -> None:
        job = {
            "id": 321,
            "status": "queued",
            "total_count": 5,
            "skipped_count": 2,
            "deduplicated_items": [{"id": 99}],
        }
        with (
            mock.patch.object(command_router.daily_market_jobs, "create_history_job", return_value=job) as create,
            mock.patch.object(command_router, "build_daily_market_brief") as build,
        ):
            result = command_router.handle_command("补齐每日市场简报 cn 2026-07-01 到 2026-07-07")

        self.assertTrue(result.ok)
        create.assert_called_once_with(
            ["CN"],
            [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3), date(2026, 7, 6), date(2026, 7, 7)],
            request_type="batch",
            source="command",
            force_refresh=False,
            max_items=120,
        )
        build.assert_not_called()
        self.assertIn("任务 #321", result.message)
        self.assertIn("项目 5", result.message)
        self.assertIn("已跳过 2", result.message)
        self.assertIn("去重 1", result.message)
        self.assertIn("/daily-market-brief", result.message)

    def test_force_requires_explicit_controlled_command_syntax(self) -> None:
        job = {"id": 322, "status": "queued", "total_count": 1, "skipped_count": 0}
        with mock.patch.object(command_router.daily_market_jobs, "create_history_job", return_value=job) as create:
            result = command_router.handle_command("强制补齐每日市场简报 US 2026-07-09 到 2026-07-09")

        self.assertTrue(result.ok)
        self.assertTrue(create.call_args.kwargs["force_refresh"])
        self.assertFalse(command_router.is_query_command("强制补齐每日市场简报 US 2026-07-09 到 2026-07-09"))

    def test_status_command_renders_progress_and_sanitized_failures(self) -> None:
        job = {
            "id": 123,
            "status": "partial",
            "total_count": 3,
            "completed_count": 3,
            "succeeded_count": 1,
            "skipped_count": 1,
            "failed_count": 1,
            "cancelled_count": 0,
            "current_market": None,
            "current_market_date": None,
            "items": [
                {
                    "market": "US",
                    "market_date": "2026-07-09",
                    "status": "failed",
                    "error_code": "provider_timeout",
                    "error_summary": "password=secret SSL traceback",
                }
            ],
        }
        with mock.patch.object(command_router.daily_market_jobs, "get_history_job", return_value=job):
            result = command_router.handle_command("每日市场简报任务 123")

        self.assertTrue(result.ok)
        self.assertIn("任务 #123", result.message)
        self.assertIn("进度：3/3", result.message)
        self.assertIn("历史数据源响应超时", result.message)
        self.assertNotIn("password", result.message)
        self.assertNotIn("SSL", result.message)
        self.assertTrue(command_router.is_query_command("每日市场简报任务 123"))

    def test_cancel_command_uses_repository_and_handles_missing_job(self) -> None:
        cancelled = {"id": 123, "status": "cancelled", "total_count": 2, "cancelled_count": 2}
        with mock.patch.object(command_router.daily_market_jobs, "request_history_job_cancel", return_value=cancelled):
            result = command_router.handle_command("取消每日市场简报任务 123")
        self.assertTrue(result.ok)
        self.assertIn("已请求取消任务 #123", result.message)
        self.assertFalse(command_router.is_query_command("取消每日市场简报任务 123"))

        with mock.patch.object(command_router.daily_market_jobs, "request_history_job_cancel", return_value=None):
            missing = command_router.handle_command("取消每日市场简报任务 999")
        self.assertFalse(missing.ok)
        self.assertIn("不存在或已结束", missing.message)

    def test_repository_errors_are_not_exposed(self) -> None:
        with mock.patch.object(
            command_router.daily_market_jobs,
            "create_history_job",
            side_effect=RuntimeError("postgresql://root:secret@db raw SQL"),
        ):
            result = command_router.handle_command("补齐每日市场简报 CN 2026-07-01 到 2026-07-02")

        self.assertFalse(result.ok)
        self.assertIn("任务创建失败", result.message)
        self.assertNotIn("secret", result.message)
        self.assertNotIn("SQL", result.message)

    def test_existing_single_report_commands_are_preserved(self) -> None:
        with mock.patch.object(command_router, "get_daily_market_brief_report", return_value={"summary": "saved brief"}):
            result = command_router.handle_command("每日市场简报 HK 2026-06-30")

        self.assertTrue(result.ok)
        self.assertEqual("saved brief", result.message)


if __name__ == "__main__":
    unittest.main()
