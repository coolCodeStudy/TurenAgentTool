from __future__ import annotations

from datetime import date
import unittest

from investment_knowledge_mcp.daily_market_history import load_historical_market_activity


class FakeFrame:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict]:
        if orient != "records":
            raise AssertionError(f"unexpected orient: {orient}")
        return self.rows


class FakeHistoricalAkshare:
    def __init__(self, *, universe: list[dict], histories: dict[str, list[dict]]) -> None:
        self.universe = universe
        self.histories = histories
        self.history_calls: list[tuple[str, dict[str, str]]] = []

    def stock_zh_a_spot_em(self) -> FakeFrame:
        return FakeFrame(self.universe)

    def stock_hk_main_board_spot_em(self) -> FakeFrame:
        return FakeFrame(self.universe)

    def stock_us_spot_em(self) -> FakeFrame:
        return FakeFrame(self.universe)

    def stock_zh_a_hist(self, **kwargs: str) -> FakeFrame:
        return self._history("stock_zh_a_hist", kwargs)

    def stock_hk_hist(self, **kwargs: str) -> FakeFrame:
        return self._history("stock_hk_hist", kwargs)

    def stock_us_hist(self, **kwargs: str) -> FakeFrame:
        return self._history("stock_us_hist", kwargs)

    def _history(self, method: str, kwargs: dict[str, str]) -> FakeFrame:
        self.history_calls.append((method, kwargs))
        return FakeFrame(self.histories.get(kwargs["symbol"], []))


class HistoricalActivityProviderTests(unittest.TestCase):
    def test_cn_historical_gainers_rank_exact_date_bars(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[
                {"代码": "000001", "名称": "甲", "成交额": 90_000_000},
                {"代码": "000002", "名称": "乙", "成交额": 100_000_000},
            ],
            histories={
                "000001": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 80_000_000},
                    {"日期": "2026-07-09", "收盘": 11, "成交额": 90_000_000},
                ],
                "000002": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 90_000_000},
                    {"日期": "2026-07-09", "收盘": 12, "成交额": 100_000_000},
                ],
            },
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual("000002", result.gainers[0]["code"])
        self.assertEqual(20.0, result.gainers[0]["change_pct"])
        self.assertEqual(100_000_000, result.gainers[0]["turnover"])
        self.assertEqual("2026-07-09", result.gainers[0]["session_date"])
        self.assertEqual("current_liquid_top_200", result.source_status["gainers"]["universe_basis"])
        self.assertEqual(
            {"period": "daily", "start_date": "20260702", "end_date": "20260709", "adjust": ""},
            {key: fake.history_calls[0][1][key] for key in ("period", "start_date", "end_date", "adjust")},
        )

    def test_history_without_requested_row_cannot_use_a_later_bar(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[{"代码": "000001", "名称": "甲", "成交额": 100_000_000}],
            histories={
                "000001": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 90_000_000},
                    {"日期": "2026-07-10", "收盘": 15, "成交额": 100_000_000},
                ]
            },
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual([], result.gainers)
        self.assertEqual(1, result.source_status["gainers"]["queried"])
        self.assertEqual(0, result.source_status["gainers"]["usable"])

    def test_partial_coverage_records_queried_and_usable_counts(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[
                {"代码": "000001", "名称": "甲", "成交额": 100_000_000},
                {"代码": "000002", "名称": "乙", "成交额": 90_000_000},
                {"代码": "000003", "名称": "丙", "成交额": 80_000_000},
            ],
            histories={
                "000001": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 90_000_000},
                    {"日期": "2026-07-09", "收盘": 11, "成交额": 100_000_000},
                ],
                "000002": [{"日期": "2026-07-09", "收盘": 12, "成交额": 90_000_000}],
                "000003": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 40_000_000},
                    {"日期": "2026-07-09", "收盘": 13, "成交额": 40_000_000},
                ],
            },
        )

        result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual(3, result.source_status["gainers"]["queried"])
        self.assertEqual(1, result.source_status["gainers"]["usable"])
        self.assertEqual("partial", result.source_status["gainers"]["status"])
        self.assertEqual(["000001"], [row["code"] for row in result.gainers])

    def test_us_uses_provider_symbol_and_keeps_sections_explicitly_unavailable(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[{"代码": "105.MSFT", "名称": "Microsoft", "成交额": 20_000_000}],
            histories={
                "105.MSFT": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 20_000_000},
                    {"日期": "2026-07-09", "收盘": 11, "成交额": 20_000_000},
                ]
            },
        )

        result = load_historical_market_activity("US", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual("105.MSFT", result.gainers[0]["code"])
        self.assertEqual("105.MSFT", fake.history_calls[0][1]["symbol"])
        self.assertEqual("historical_not_supported", result.source_status["sectors"]["status"])
        self.assertEqual("historical_not_supported", result.source_status["capital_flow"]["status"])

    def test_hk_keeps_historical_sections_explicitly_unavailable(self) -> None:
        fake = FakeHistoricalAkshare(
            universe=[{"代码": "00700", "名称": "Tencent", "成交额": 30_000_000}],
            histories={
                "00700": [
                    {"日期": "2026-07-08", "收盘": 10, "成交额": 30_000_000},
                    {"日期": "2026-07-09", "收盘": 11, "成交额": 30_000_000},
                ]
            },
        )

        result = load_historical_market_activity("HK", date(2026, 7, 9), akshare_module=fake, max_workers=1)

        self.assertEqual("stock_hk_hist", fake.history_calls[0][0])
        self.assertEqual("historical_not_supported", result.source_status["sectors"]["status"])
        self.assertEqual("historical_not_supported", result.source_status["capital_flow"]["status"])


if __name__ == "__main__":
    unittest.main()
