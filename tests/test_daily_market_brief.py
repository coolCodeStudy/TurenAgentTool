from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import inspect
import sys
import types
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import command_router
from investment_knowledge_mcp import daily_market_brief as dmb
from investment_knowledge_mcp import weekly_review_web as web
from investment_knowledge_mcp.market_data_provider import MarketBarSnapshot, MarketDataProviderError
from investment_knowledge_mcp.weekly_review_web import (
    _daily_market_brief_response,
    _resolve_daily_market,
    _validate_public_daily_market_brief_date,
    render_daily_market_brief_html,
)


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


class FakeFrame:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict]:
        self.assert_orient(orient)
        return self.rows

    @staticmethod
    def assert_orient(orient: str) -> None:
        if orient != "records":
            raise AssertionError(f"unexpected orient: {orient}")


class FakeAkshareModule(types.SimpleNamespace):
    def stock_board_industry_name_em(self) -> FakeFrame:
        return FakeFrame(
            [
                {"序号": 1, "板块代码": "BK1001", "板块名称": "机器人", "涨跌幅": 4.2, "成交额": 21_000_000_000},
                {"序号": 2, "板块代码": "BK1002", "板块名称": "半导体", "涨跌幅": 5.1, "成交额": 19_000_000_000},
                {"序号": 3, "板块代码": "BK1003", "板块名称": "银行", "涨跌幅": 1.2, "成交额": 15_000_000_000},
                {"序号": 4, "板块代码": "BK1004", "板块名称": "传媒", "涨跌幅": 2.2, "成交额": 11_000_000_000},
                {"序号": 5, "板块代码": "BK1005", "板块名称": "电力设备", "涨跌幅": 3.0, "成交额": 12_000_000_000},
                {"序号": 6, "板块代码": "BK1006", "板块名称": "煤炭", "涨跌幅": 0.3, "成交额": 8_000_000_000},
            ]
        )

    def stock_zh_a_spot_em(self) -> FakeFrame:
        return FakeFrame(
            [
                {"代码": "300001", "名称": "样本科技", "涨跌幅": 12.4, "成交额": 180_000_000},
                {"代码": "600001", "名称": "样本制造", "涨跌幅": 10.2, "成交额": 95_000_000},
                {"代码": "000001", "名称": "样本银行", "涨跌幅": 7.1, "成交额": 80_000_000},
                {"代码": "002001", "名称": "样本消费", "涨跌幅": 6.8, "成交额": 70_000_000},
                {"代码": "688001", "名称": "样本芯片", "涨跌幅": 6.1, "成交额": 60_000_000},
                {"代码": "000002", "名称": "ST样本", "涨跌幅": 20.0, "成交额": 100_000_000},
                {"代码": "000003", "名称": "低流动性", "涨跌幅": 19.0, "成交额": 1_000_000},
            ]
        )

    def stock_sector_fund_flow_rank(self, *, indicator: str, sector_type: str) -> FakeFrame:
        self.last_flow_args = {"indicator": indicator, "sector_type": sector_type}
        return FakeFrame(
            [
                {"序号": 1, "名称": "半导体", "今日涨跌幅": 5.1, "今日主力净流入-净额": 3_200_000_000},
                {"序号": 2, "名称": "机器人", "今日涨跌幅": 4.2, "今日主力净流入-净额": 2_700_000_000},
                {"序号": 3, "名称": "电力设备", "今日涨跌幅": 3.0, "今日主力净流入-净额": 2_100_000_000},
                {"序号": 4, "名称": "传媒", "今日涨跌幅": 2.2, "今日主力净流入-净额": 1_100_000_000},
                {"序号": 5, "名称": "银行", "今日涨跌幅": 1.2, "今日主力净流入-净额": 700_000_000},
            ]
        )


class DailyMarketBriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_repository = dmb.repository
        self.fake_repository = FakeDailyBriefRepository()
        dmb.repository = self.fake_repository

    def tearDown(self) -> None:
        dmb.repository = self.original_repository
        sys.modules.pop("akshare", None)

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
        self.assertIn("上证指数", second.markdown)
        self.assertIn("不构成买卖建议", second.markdown)

    def test_cn_indexes_use_chinese_display_names(self) -> None:
        result = dmb.build_daily_market_brief(
            market="CN", market_date=date(2026, 7, 9), save=False,
            market_bar_loader=fake_market_bar_loader, use_fixture=True,
            now=datetime(2026, 7, 9, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertEqual(
            ["上证指数", "深证成指", "沪深300", "创业板指", "科创50"],
            [row["name"] for row in result.context["indexes"]],
        )
        self.assertIn("上证指数", result.markdown)
        self.assertNotIn("Shanghai Composite", result.markdown)

    def test_format_market_amount_uses_currency_and_chinese_units(self) -> None:
        self.assertEqual("50.93 亿元 CNY", dmb.format_market_amount(5_093_000_000, "CN"))
        self.assertEqual("6310.44 万港元 HKD", dmb.format_market_amount(63_104_400, "HK"))
        self.assertEqual("6.33 亿美元 USD", dmb.format_market_amount(633_303_877.53, "US"))
        self.assertEqual("-", dmb.format_market_amount(None, "US"))

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
        self.assertEqual(result.context["provider_mode"], "live")

    def test_akshare_cn_activity_populates_live_leadership_and_flow(self) -> None:
        fake_ak = FakeAkshareModule()
        sys.modules["akshare"] = fake_ak

        result = dmb.build_daily_market_brief(
            market="CN",
            market_date=date(2026, 6, 30),
            save=False,
            market_bar_loader=fake_market_bar_loader,
            now=datetime(2026, 6, 30, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertEqual(result.context["provider_mode"], "live")
        self.assertEqual(len(result.context["sectors"]), 5)
        self.assertEqual(result.context["sectors"][0]["name"], "半导体")
        self.assertEqual(len(result.context["gainers"]), 5)
        self.assertEqual(result.context["gainers"][0]["name"], "样本科技")
        self.assertNotIn("ST样本", {item["name"] for item in result.context["gainers"]})
        self.assertEqual(len(result.context["capital_flow"]), 5)
        self.assertEqual(result.context["capital_flow"][0]["name"], "半导体")
        self.assertEqual(result.context["source_status"]["sectors"]["provider"], dmb.AKSHARE_PROVIDER)
        self.assertEqual(result.context["source_status"]["capital_flow"]["status"], "ok")
        self.assertEqual(fake_ak.last_flow_args, {"indicator": "今日", "sector_type": "行业资金流"})

    def test_hk_and_us_gainers_fall_back_to_direct_eastmoney_http(self) -> None:
        class UnavailableAkshare:
            def stock_hk_main_board_spot_em(self):
                raise ConnectionError("AKShare HK unavailable")

            def stock_us_spot_em(self):
                raise ConnectionError("AKShare US unavailable")

        fallback_rows = [
            {
                "rank": rank,
                "code": f"SAMPLE{rank}",
                "name": f"Sample {rank}",
                "change_pct": 10 - rank,
                "turnover": 100_000_000,
                "provider": dmb.EASTMONEY_HTTP_PROVIDER,
            }
            for rank in range(1, 6)
        ]
        with (
            mock.patch.object(dmb, "_hk_gainers_http_fallback", return_value=fallback_rows),
            mock.patch.object(dmb, "_us_gainers_http_fallback", return_value=fallback_rows),
        ):
            hk = dmb._akshare_hk_activity(UnavailableAkshare(), date(2026, 7, 10))
            us = dmb._akshare_us_activity(UnavailableAkshare(), date(2026, 7, 10))

        for activity in (hk, us):
            self.assertEqual(5, len(activity["gainers"]))
            self.assertEqual(
                dmb.PUBLIC_HTTP_FALLBACK_PROVIDER,
                activity["source_status"]["gainers"]["provider"],
            )
            self.assertEqual(
                dmb.AKSHARE_PROVIDER,
                activity["source_status"]["gainers"]["fallback_from"],
            )

    def test_direct_eastmoney_hk_us_gainers_keep_liquid_common_equities(self) -> None:
        hk_rows = [
            {"f12": f"00{rank:03d}", "f14": f"港股样本{rank}", "f3": 12 - rank, "f6": 30_000_000}
            for rank in range(1, 7)
        ] + [{"f12": "00999", "f14": "低流动性", "f3": 99, "f6": 1_000}]
        us_rows = [
            {"f12": f"TEST{rank}", "f14": f"US Sample {rank}", "f3": 12 - rank, "f6": 20_000_000}
            for rank in range(1, 7)
        ] + [
            {"f12": "TESTW", "f14": "Example Warrant", "f3": 99, "f6": 50_000_000},
            {"f12": "LOW", "f14": "Low Turnover", "f3": 98, "f6": 1_000},
        ]
        with mock.patch.object(dmb, "_eastmoney_clist", side_effect=(hk_rows, us_rows)):
            hk = dmb._eastmoney_hk_gainers()
            us = dmb._eastmoney_us_gainers()

        self.assertEqual(5, len(hk))
        self.assertEqual(5, len(us))
        self.assertNotIn("00999", {row["code"] for row in hk})
        self.assertNotIn("TESTW", {row["code"] for row in us})
        self.assertTrue(
            all(row["provider"] == dmb.EASTMONEY_HTTP_PROVIDER for row in hk + us)
        )

    def test_sina_hk_us_rows_are_normalized_and_filtered(self) -> None:
        hk = dmb._normalize_sina_hk_gainers(
            [
                {"symbol": f"00{rank:03d}", "name": f"港股样本{rank}", "changepercent": 20 - rank, "amount": 30_000_000}
                for rank in range(1, 7)
            ]
            + [{"symbol": "00999", "name": "低流动性", "changepercent": 99, "amount": 1_000}]
        )
        us = dmb._normalize_sina_us_gainers(
            [
                {"symbol": f"TEST{rank}", "name": f"US Sample {rank}", "cname": f"美股样本{rank}", "chg": 20 - rank, "price": 10, "volume": 2_000_000}
                for rank in range(1, 7)
            ]
            + [
                {"symbol": "TESTW", "name": "Example Warrant", "cname": "Example Warrant", "chg": 99, "price": 1, "volume": 50_000_000},
                {"symbol": "LOW", "name": "Low Turnover", "cname": "Low Turnover", "chg": 98, "price": 1, "volume": 1_000},
            ]
        )

        self.assertEqual(5, len(hk))
        self.assertEqual(5, len(us))
        self.assertNotIn("00999", {row["code"] for row in hk})
        self.assertNotIn("TESTW", {row["code"] for row in us})
        self.assertTrue(all(row["provider"] == dmb.SINA_FINANCE_PROVIDER for row in hk + us))

    def test_akshare_missing_dependency_degrades_without_raw_error(self) -> None:
        sys.modules.pop("akshare", None)
        empty_activity = dmb._empty_activity(
            "CN",
            provider=dmb.EASTMONEY_HTTP_PROVIDER,
            status="provider_unavailable",
            message="Eastmoney 未返回可用的 A 股市场榜单。",
        )
        with (
            mock.patch.object(dmb.importlib, "import_module", side_effect=ImportError("missing akshare")),
            mock.patch.object(dmb, "_eastmoney_cn_activity", return_value=empty_activity),
        ):
            result = dmb.build_daily_market_brief(
                market="CN",
                market_date=date(2026, 6, 30),
                save=False,
                market_bar_loader=fake_market_bar_loader,
                now=datetime(2026, 6, 30, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

        self.assertEqual(result.context["source_status"]["sectors"]["status"], "provider_unavailable")
        self.assertIn("Eastmoney", result.context["source_status"]["sectors"]["message"])
        self.assertNotIn("Traceback", result.markdown)

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

    def test_command_fixture_generation_uses_fixture_indexes(self) -> None:
        generated = command_router.handle_command("生成每日市场简报 CN 2026-06-30 fixture")
        rerun = command_router.handle_command("重跑每日市场简报 CN 2026-06-30 fixture")

        self.assertTrue(generated.ok)
        self.assertTrue(rerun.ok)
        self.assertIn("上证指数", generated.message)
        self.assertIn("深证成指", generated.message)
        self.assertIn("沪深300", generated.message)
        self.assertIn("创业板指", generated.message)
        self.assertIn("科创50", generated.message)
        self.assertNotIn("暂无可用核心指数数据", generated.message)
        self.assertIn("review_reports #1", generated.message)
        self.assertIn("review_reports #1", rerun.message)

    def test_cross_market_fixture_generation_coexists_for_same_date(self) -> None:
        for market, required_index in (
            ("CN", "上证指数"),
            ("HK", "Hang Seng Index"),
            ("US", "S&P 500"),
        ):
            result = command_router.handle_command(f"生成每日市场简报 {market} 2026-06-30 fixture")
            self.assertTrue(result.ok)
            self.assertIn(required_index, result.message)

        self.assertEqual(len(self.fake_repository.rows), 3)
        self.assertIn(("CN", "2026-06-30"), self.fake_repository.rows)
        self.assertIn(("HK", "2026-06-30"), self.fake_repository.rows)
        self.assertIn(("US", "2026-06-30"), self.fake_repository.rows)

    def test_degraded_index_output_uses_product_language(self) -> None:
        def blocked_loader(codes: list[str], start: str, end: str) -> MarketBarSnapshot:
            raise MarketDataProviderError("Yahoo chart fallback returned no usable bars: CERTIFICATE_VERIFY_FAILED")

        result = dmb.build_daily_market_brief(
            market="HK",
            market_date=date(2026, 6, 30),
            save=False,
            market_bar_loader=blocked_loader,
            now=datetime(2026, 6, 30, 18, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
        )

        self.assertIn(dmb.INDEX_DEGRADED_COPY, result.markdown)
        self.assertNotIn("Yahoo chart fallback", result.markdown)
        self.assertNotIn("CERTIFICATE_VERIFY_FAILED", result.markdown)
        self.assertIn("核心指数：数据源暂不可用", result.markdown)

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

    def test_daily_market_brief_web_page_exposes_user_acceptance_surface(self) -> None:
        html = render_daily_market_brief_html()

        self.assertIn("每日市场简报", html)
        self.assertIn("/api/daily-market-brief", html)
        self.assertIn("/api/daily-market-brief/generate", html)
        self.assertIn('data-market="CN"', html)
        self.assertIn('data-market="HK"', html)
        self.assertIn('data-market="US"', html)
        self.assertIn("核心指数", html)
        self.assertIn("Markdown 原文", html)
        self.assertNotIn("api-token", html)
        self.assertNotIn("生成 fixture", html)
        self.assertIn('$("#market-date").value = "";', html)
        self.assertIn('if (data.market_date) $("#market-date").value = data.market_date;', html)

    def test_public_generation_date_window_is_bounded(self) -> None:
        now = datetime(2026, 7, 11, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        _validate_public_daily_market_brief_date("CN", None, now=now)
        _validate_public_daily_market_brief_date("CN", date(2026, 7, 10), now=now)
        with self.assertRaisesRegex(ValueError, "未来日期"):
            _validate_public_daily_market_brief_date("CN", date(2026, 7, 12), now=now)
        with self.assertRaisesRegex(ValueError, "最近 31 天"):
            _validate_public_daily_market_brief_date("CN", date(2026, 6, 9), now=now)
        with self.assertRaisesRegex(ValueError, "最近一个已收盘交易日"):
            _validate_public_daily_market_brief_date("CN", date(2026, 7, 9), now=now)

    def test_historical_live_generation_does_not_use_spot_rankings(self) -> None:
        def unexpected_activity(market: str, market_date: date) -> dict:
            raise AssertionError(f"spot activity called for {market} {market_date}")

        result = dmb.build_daily_market_brief(
            market="CN",
            market_date=date(2026, 6, 30),
            save=False,
            market_bar_loader=fake_market_bar_loader,
            activity_provider=unexpected_activity,
            now=datetime(2026, 7, 1, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertEqual([], result.context["sectors"])
        self.assertEqual("historical_not_supported", result.context["source_status"]["sectors"]["status"])
        self.assertIn("历史榜单", result.markdown)

    def test_historical_live_rerun_cannot_overwrite_saved_rankings(self) -> None:
        original = dmb.build_daily_market_brief(
            market="CN",
            market_date=date(2026, 6, 30),
            save=True,
            market_bar_loader=fake_market_bar_loader,
            use_fixture=True,
            now=datetime(2026, 6, 30, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        with self.assertRaisesRegex(ValueError, "不能用实时榜单重跑历史日期"):
            dmb.build_daily_market_brief(
                market="CN",
                market_date=date(2026, 6, 30),
                save=True,
                market_bar_loader=fake_market_bar_loader,
                now=datetime(2026, 7, 1, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            )

        saved = self.fake_repository.get_daily_market_brief_report(market="CN", market_date="2026-06-30")
        self.assertEqual(original.saved_report["id"], saved["id"])
        self.assertEqual(5, len(saved["portfolio_snapshot"]["sectors"]))

    def test_missing_requested_index_session_is_recorded_as_no_session(self) -> None:
        def prior_session_loader(codes: list[str], start: str, end: str) -> MarketBarSnapshot:
            snapshot = fake_market_bar_loader(codes, start, end)
            for code in codes:
                snapshot.bars_by_code[code] = [row for row in snapshot.bars_by_code[code] if row["date"] < end]
            return snapshot

        activity = mock.Mock(side_effect=AssertionError("spot activity must not run for a closed market"))
        result = dmb.build_daily_market_brief(
            market="CN",
            market_date=date(2026, 7, 1),
            save=False,
            market_bar_loader=prior_session_loader,
            activity_provider=activity,
            now=datetime(2026, 7, 1, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertTrue(result.context["no_session"])
        self.assertEqual("no_session", result.context["source_status"]["session"]["status"])
        activity.assert_not_called()

    def test_public_generation_gate_single_flight_and_cooldown(self) -> None:
        current = [100.0]
        gate = web._DailyBriefGenerationGate(cooldown_seconds=60, clock=lambda: current[0])

        first = gate.try_acquire(("CN", "2026-07-10"))
        self.assertIsNotNone(first)
        self.assertIsNone(gate.try_acquire(("CN", "2026-07-10")))
        first.release()
        self.assertIsNone(gate.try_acquire(("CN", "2026-07-10")))
        current[0] += 61
        second = gate.try_acquire(("CN", "2026-07-10"))
        self.assertIsNotNone(second)
        second.release()

    def test_schema_and_repository_keep_daily_brief_upsert_concurrency_safe(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema = (root / "db/schema.sql").read_text(encoding="utf-8")
        repository_source = (root / "investment_knowledge_mcp/repository.py").read_text(encoding="utf-8")

        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_review_reports_report_key", schema)
        self.assertIn("pg_advisory_xact_lock", repository_source)

    def test_public_daily_read_does_not_run_schema_migrations(self) -> None:
        source = inspect.getsource(web.WeeklyReviewWebHandler._handle_daily_market_brief_read)
        self.assertNotIn("run_schema", source)

    def test_daily_market_brief_web_response_normalizes_saved_report(self) -> None:
        result = dmb.build_daily_market_brief(
            market="US",
            market_date=date(2026, 6, 30),
            save=True,
            market_bar_loader=fake_market_bar_loader,
            use_fixture=True,
            now=datetime(2026, 6, 30, 17, 0, tzinfo=ZoneInfo("America/New_York")),
        )

        payload = _daily_market_brief_response(result.saved_report, status="existing")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["market"]["code"], "US")
        self.assertEqual(payload["market_date"], "2026-06-30")
        self.assertEqual(len(payload["context"]["indexes"]), 4)
        self.assertIn("S&P 500", payload["markdown"])

    def test_daily_market_brief_web_rejects_unknown_market(self) -> None:
        with self.assertRaisesRegex(ValueError, "CN、HK、US"):
            _resolve_daily_market({"market": "JP"})


if __name__ == "__main__":
    unittest.main()
