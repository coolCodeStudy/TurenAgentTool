from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import unittest
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import command_router
from investment_knowledge_mcp import daily_market_brief as dmb
from investment_knowledge_mcp import repository
from investment_knowledge_mcp.market_data_provider import MarketBarSnapshot, MarketDataProviderError


class FakeDailyBriefRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}
        self.next_id = 1

    def upsert_daily_market_brief_report(
        self,
        *,
        market: str,
        market_date: str,
        summary: str,
        context: dict,
        source_status: dict | None = None,
        story: dict | None = None,
    ) -> dict:
        key = (market, market_date)
        row = self.rows.get(key)
        if row is None:
            row = {"id": self.next_id, "report_type": "daily_market_brief"}
            self.next_id += 1
        row.update(
            {
                "report_date": market_date,
                "summary": summary,
                "portfolio_snapshot": context,
                "source_status": source_status or {},
                "story": story or {},
            }
        )
        self.rows[key] = row
        return row

    def get_daily_market_brief_report(self, *, market: str, market_date: str) -> dict | None:
        return self.rows.get((market, market_date))

    def get_latest_daily_market_brief_report(self, *, market: str) -> dict | None:
        rows = [row for (row_market, _), row in self.rows.items() if row_market == market]
        return sorted(rows, key=lambda item: item["report_date"], reverse=True)[0] if rows else None


def fake_market_bar_loader(codes: list[str], start: str, end: str) -> MarketBarSnapshot:
    end_date = date.fromisoformat(end)
    bars_by_code: dict[str, list[dict]] = {}
    for offset, code in enumerate(codes):
        bars: list[dict] = []
        current = end_date - timedelta(days=35)
        close = 1000.0 + offset * 10
        while current <= end_date:
            if current.weekday() < 5:
                close += 3.0 + offset
                bars.append(
                    {
                        "date": current.isoformat(),
                        "close": close,
                        "volume": 1000000 + len(bars) * 10000 + offset * 1000,
                        "raw": {"provider_symbol": f"fixture:{code}"},
                    }
                )
            current += timedelta(days=1)
        bars_by_code[code] = bars
    return MarketBarSnapshot(
        bars_by_code=bars_by_code,
        fetched_at=datetime(2026, 6, 30, 8, 0, tzinfo=timezone.utc),
        start=start,
        end=end,
        source="fixture_bars",
    )


def failing_market_bar_loader(codes: list[str], start: str, end: str) -> MarketBarSnapshot:
    raise MarketDataProviderError(
        "Yahoo chart fallback returned no usable bars: "
        "SH.000001: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>"
    )


class DailyMarketBriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_repository = dmb.repository
        self.fake_repository = FakeDailyBriefRepository()
        dmb.repository = self.fake_repository

    def tearDown(self) -> None:
        dmb.repository = self.original_repository

    def test_fixture_generation_has_required_cn_shape_and_idempotent_storage(self) -> None:
        first = dmb.build_daily_market_brief(
            market="CN",
            market_date=date(2026, 6, 30),
            save=True,
            market_bar_loader=fake_market_bar_loader,
            use_fixture=True,
            now=datetime(2026, 6, 30, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        second = dmb.build_daily_market_brief(
            market="CN",
            market_date=date(2026, 6, 30),
            save=True,
            market_bar_loader=fake_market_bar_loader,
            use_fixture=True,
            now=datetime(2026, 6, 30, 18, 5, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertEqual(first.saved_report["id"], second.saved_report["id"])
        self.assertEqual(len(self.fake_repository.rows), 1)
        self.assertEqual(len(second.context["indexes"]), 5)
        self.assertEqual(len(second.context["sectors"]), 5)
        self.assertEqual(len(second.context["gainers"]), 5)
        self.assertEqual(second.context["source_status"]["capital_flow"]["status"], "ok")
        self.assertIn("Shanghai Composite", second.markdown)
        self.assertIn("不构成买卖建议", second.markdown)

    def test_live_us_defaults_to_explicit_capital_flow_degraded_state(self) -> None:
        result = dmb.build_daily_market_brief(
            market="US",
            market_date=date(2026, 6, 30),
            save=False,
            market_bar_loader=fake_market_bar_loader,
            now=datetime(2026, 6, 30, 17, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        self.assertEqual(len(result.context["indexes"]), 4)
        self.assertEqual(result.context["source_status"]["capital_flow"]["status"], "not_available")
        self.assertIn(dmb.CAPITAL_FLOW_DEGRADED_COPY, result.markdown)
        self.assertIn("需要注意的数据缺口：", result.markdown)
        self.assertIn("资金流", result.markdown)
        self.assertNotIn("capital_flow", result.markdown)
        self.assertEqual(result.context["provider_mode"], "live")

    def test_command_retrieves_specific_and_latest_saved_brief(self) -> None:
        generated = dmb.build_daily_market_brief(
            market="HK",
            market_date=date(2026, 6, 30),
            save=True,
            market_bar_loader=fake_market_bar_loader,
            use_fixture=True,
            now=datetime(2026, 6, 30, 18, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
        )

        specific = command_router.handle_command("每日市场简报 HK 2026-06-30")
        latest = command_router.handle_command("最新每日市场简报 HK")

        self.assertTrue(specific.ok)
        self.assertTrue(latest.ok)
        self.assertEqual(specific.message, generated.markdown)
        self.assertIn("每日市场简报｜港股", latest.message)

    def test_command_fixture_generation_uses_deterministic_index_bars(self) -> None:
        result = command_router.handle_command("生成每日市场简报 CN 2026-06-30 fixture")

        self.assertTrue(result.ok)
        self.assertIn("Shanghai Composite", result.message)
        self.assertIn("Shenzhen Component", result.message)
        self.assertIn("CSI 300", result.message)
        self.assertIn("ChiNext Index", result.message)
        self.assertIn("STAR 50", result.message)
        self.assertNotIn("暂无可用核心指数数据", result.message)
        self.assertIn("核心指数：可用，来源：fixture_bars", result.message)

    def test_provider_errors_are_sanitized_in_user_facing_status(self) -> None:
        result = dmb.build_daily_market_brief(
            market="CN",
            market_date=date(2026, 6, 30),
            save=False,
            market_bar_loader=failing_market_bar_loader,
            use_fixture=True,
            now=datetime(2026, 6, 30, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertIn(dmb.INDEX_PROVIDER_DEGRADED_COPY, result.markdown)
        self.assertNotIn("Yahoo chart fallback", result.markdown)
        self.assertNotIn("CERTIFICATE_VERIFY_FAILED", result.markdown)
        self.assertEqual(result.context["source_status"]["indexes"]["message"], dmb.INDEX_PROVIDER_DEGRADED_COPY)
        self.assertNotIn("Yahoo chart fallback", " ".join(result.context["warnings"]))
        self.assertNotIn("CERTIFICATE_VERIFY_FAILED", " ".join(result.context["warnings"]))

    def test_daily_market_brief_report_key_is_market_aware(self) -> None:
        self.assertEqual(
            repository._daily_market_brief_report_key("HK", "2026-06-30"),
            "daily_market_brief:HK:2026-06-30:2026-06-30",
        )

    def test_scheduler_session_date_respects_market_close_timezone(self) -> None:
        before_us_close = datetime(2026, 6, 30, 12, 0, tzinfo=ZoneInfo("Asia/Singapore"))
        after_us_close = datetime(2026, 7, 1, 5, 0, tzinfo=ZoneInfo("Asia/Singapore"))

        self.assertEqual(dmb.resolve_latest_completed_session_date("US", now=before_us_close), date(2026, 6, 29))
        self.assertEqual(dmb.resolve_latest_completed_session_date("US", now=after_us_close), date(2026, 6, 30))
        self.assertFalse(dmb.should_run_daily_market_brief("US", now=before_us_close))
        self.assertTrue(dmb.should_run_daily_market_brief("US", now=after_us_close, last_attempted_date=date(2026, 6, 29)))

    def test_weekend_no_session_records_skipped_state(self) -> None:
        result = dmb.build_daily_market_brief(
            market="CN",
            market_date=date(2026, 6, 27),
            save=False,
            market_bar_loader=fake_market_bar_loader,
            now=datetime(2026, 6, 27, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertTrue(result.context["no_session"])
        self.assertEqual(result.context["source_status"]["session"]["status"], "no_session")
        self.assertIn("休市状态", result.markdown)


if __name__ == "__main__":
    unittest.main()
