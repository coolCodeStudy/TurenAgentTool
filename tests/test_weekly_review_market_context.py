from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from investment_knowledge_mcp.data_sources import (
    DataResult,
    DataSourcePool,
    DataStatus,
    FutuMarketBarsSource,
    YahooMarketBarsSource,
)
from investment_knowledge_mcp.futu_provider import FutuProviderError
from investment_knowledge_mcp.market_data_provider import MarketDataProviderError
from investment_knowledge_mcp.weekly_review import REQUIRED_INDEXES, _load_index_summary


START = date(2026, 7, 6)
END = date(2026, 7, 10)
FETCHED_AT = datetime(2026, 7, 10, 16, tzinfo=timezone.utc)


def _bars(codes: list[str] | tuple[str, ...]) -> dict[str, list[dict[str, object]]]:
    return {
        code: [
            {"date": START.isoformat(), "close": float(index + 100)},
            {"date": END.isoformat(), "close": float(index + 101)},
        ]
        for index, code in enumerate(codes)
    }


def _snapshot(source: str, codes: list[str] | tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(source=source, fetched_at=FETCHED_AT, bars_by_code=_bars(codes))


class WeeklyReviewMarketContextTests(TestCase):
    def _pool(self, futu_loader, yahoo_loader) -> DataSourcePool:
        pool = DataSourcePool(now=lambda: FETCHED_AT)
        pool.register(FutuMarketBarsSource(loader=futu_loader))
        pool.register(YahooMarketBarsSource(loader=yahoo_loader))
        return pool

    def _load(self, pool: DataSourcePool, *, active_markets: set[str] | None = None):
        source_status: dict[str, object] = {}
        warnings: list[str] = []
        rows = _load_index_summary(
            start=START,
            end=END,
            source_status=source_status,
            warnings=warnings,
            active_markets=active_markets or set(),
            detected_themes=["组合持仓"],
            data_source_pool=pool,
        )
        return rows, source_status["indexes"], warnings

    def test_full_futu_snapshot_keeps_legacy_metrics_and_normalized_provenance(self) -> None:
        calls = {"futu": 0, "yahoo": 0}
        codes = [index["code"] for index in REQUIRED_INDEXES]

        def futu_loader(received_codes: list[str], start: str, end: str):
            calls["futu"] += 1
            self.assertEqual(received_codes, codes)
            self.assertEqual((start, end), (START.isoformat(), END.isoformat()))
            return _snapshot("futu", received_codes)

        def yahoo_loader(received_codes: list[str], start: str, end: str):
            calls["yahoo"] += 1
            raise AssertionError("fallback must not run after full Futu coverage")

        rows, status, warnings = self._load(self._pool(futu_loader, yahoo_loader), active_markets={"US", "HK", "CN"})

        self.assertEqual(calls, {"futu": 1, "yahoo": 0})
        self.assertEqual(len(rows), len(REQUIRED_INDEXES))
        self.assertEqual(rows[0]["weekly_change_pct"], 1.0)
        self.assertEqual(rows[0]["source"]["provider"], "futu")
        self.assertEqual(
            status,
            {
                "status": "ok",
                "provider": "futu",
                "providers": ["futu"],
                "count": len(REQUIRED_INDEXES),
                "fetched_at": FETCHED_AT.isoformat(),
                "metric": "close_to_close",
                "missing": [],
                "active_markets": ["CN", "HK", "US"],
                "uncovered_active_markets": [],
                "provider_errors": [],
                "reason": "必需指数篮子已读取。",
                "attempted_sources": ["futu"],
                "selected_source": "futu",
                "coverage": 1.0,
                "from_cache": False,
                "failures": [],
            },
        )
        self.assertEqual(warnings, [])

    def test_malformed_normalized_records_return_safe_contract_unavailable_status(self) -> None:
        class ResultPool:
            def __init__(self) -> None:
                self.calls = 0

            def fetch(self, request, plan) -> DataResult:
                self.calls += 1
                return DataResult(
                    DataStatus.OK,
                    ({"symbol": "US.SPX", "bars": [], "raw_sensitive": "token=do-not-expose"},),
                    "futu",
                    ("futu",),
                    1.0,
                    FETCHED_AT,
                    False,
                    (),
                )

        pool = ResultPool()
        rows, status, warnings = self._load(pool, active_markets={"US"})

        self.assertEqual(pool.calls, 1)
        self.assertEqual(rows, [])
        self.assertEqual(
            status,
            {
                "status": "provider_unavailable",
                "provider": None,
                "providers": ["futu"],
                "count": 0,
                "fetched_at": FETCHED_AT.isoformat(),
                "metric": "close_to_close",
                "missing": [index["name"] for index in REQUIRED_INDEXES],
                "active_markets": ["US"],
                "uncovered_active_markets": ["US"],
                "provider_errors": ["futu: provider_contract_error"],
                "reason": "指数行情数据源暂不可用。",
                "attempted_sources": ["futu"],
                "selected_source": None,
                "coverage": 0.0,
                "from_cache": False,
                "failures": [
                    {
                        "code": "provider_contract_error",
                        "source": "futu",
                        "retryable": False,
                        "fallback_allowed": False,
                    }
                ],
            },
        )
        self.assertEqual(warnings, ["指数行情读取失败：指数行情数据源暂不可用。"])
        self.assertNotIn("do-not-expose", " ".join(str(item) for item in [status, warnings]))

    def test_typed_futu_unavailable_uses_yahoo_with_safe_fallback_provenance(self) -> None:
        calls = {"futu": 0, "yahoo": 0}
        codes = [index["code"] for index in REQUIRED_INDEXES]

        def futu_loader(received_codes: list[str], start: str, end: str):
            calls["futu"] += 1
            raise FutuProviderError("token=do-not-expose")

        def yahoo_loader(received_codes: list[str], start: str, end: str):
            calls["yahoo"] += 1
            return _snapshot("yahoo_chart", received_codes)

        rows, status, warnings = self._load(self._pool(futu_loader, yahoo_loader))

        self.assertEqual(calls, {"futu": 1, "yahoo": 1})
        self.assertEqual(len(rows), len(REQUIRED_INDEXES))
        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["provider"], "yahoo_chart")
        self.assertEqual(status["providers"], ["futu", "yahoo_chart"])
        self.assertEqual(status["attempted_sources"], ["futu", "yahoo_chart"])
        self.assertEqual(status["selected_source"], "yahoo_chart")
        self.assertEqual(status["coverage"], 1.0)
        self.assertEqual(status["count"], len(REQUIRED_INDEXES))
        self.assertEqual(status["fetched_at"], FETCHED_AT.isoformat())
        self.assertEqual(status["metric"], "close_to_close")
        self.assertEqual(status["missing"], [])
        self.assertEqual(status["active_markets"], [])
        self.assertEqual(status["uncovered_active_markets"], [])
        self.assertEqual(status["provider_errors"], ["futu: provider_unavailable"])
        self.assertEqual(status["reason"], "指数数据部分可用。")
        self.assertEqual(
            status["failures"],
            [{"code": "provider_unavailable", "source": "futu", "retryable": True, "fallback_allowed": True}],
        )
        self.assertEqual(warnings, ["富途指数行情不可用，已使用 Yahoo chart 作为云端备用指数源。"])
        self.assertNotIn("do-not-expose", " ".join(str(item) for item in [status, warnings]))

    def test_partial_futu_snapshot_keeps_missing_indexes_without_yahoo_fallback(self) -> None:
        calls = {"futu": 0, "yahoo": 0}
        partial_codes = [index["code"] for index in REQUIRED_INDEXES if index["market"] != "HK"]

        def futu_loader(received_codes: list[str], start: str, end: str):
            calls["futu"] += 1
            return _snapshot("futu", partial_codes)

        def yahoo_loader(received_codes: list[str], start: str, end: str):
            calls["yahoo"] += 1
            raise AssertionError("partial Futu coverage must not trigger Yahoo")

        rows, status, warnings = self._load(self._pool(futu_loader, yahoo_loader), active_markets={"HK"})

        self.assertEqual(calls, {"futu": 1, "yahoo": 0})
        self.assertEqual(len(rows), len(partial_codes))
        self.assertEqual(status["status"], "source_blocked")
        self.assertEqual(status["selected_source"], "futu")
        self.assertEqual(status["coverage"], len(partial_codes) / len(REQUIRED_INDEXES))
        self.assertEqual(status["missing"], ["Hang Seng Index", "Hang Seng Tech Index", "Hang Seng China Enterprises Index"])
        self.assertEqual(status["uncovered_active_markets"], ["HK"])
        self.assertEqual(status["provider_errors"], ["futu: incomplete_coverage"])
        self.assertEqual(status["failures"][0]["code"], "incomplete_coverage")
        self.assertEqual(warnings, [status["reason"]])

    def test_partial_futu_snapshot_without_active_market_gap_remains_partial(self) -> None:
        calls = {"futu": 0, "yahoo": 0}
        partial_codes = [index["code"] for index in REQUIRED_INDEXES if index["market"] != "HK"]

        def futu_loader(received_codes: list[str], start: str, end: str):
            calls["futu"] += 1
            return _snapshot("futu", partial_codes)

        def yahoo_loader(received_codes: list[str], start: str, end: str):
            calls["yahoo"] += 1
            raise AssertionError("partial Futu coverage must not trigger Yahoo")

        rows, status, warnings = self._load(self._pool(futu_loader, yahoo_loader))

        self.assertEqual(calls, {"futu": 1, "yahoo": 0})
        self.assertEqual(len(rows), len(partial_codes))
        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["uncovered_active_markets"], [])
        self.assertEqual(status["reason"], "缺少指数：Hang Seng Index、Hang Seng Tech Index、Hang Seng China Enterprises Index")
        self.assertEqual(warnings, [])

    def test_both_typed_providers_unavailable_returns_safe_empty_status(self) -> None:
        calls = {"futu": 0, "yahoo": 0}

        def futu_loader(received_codes: list[str], start: str, end: str):
            calls["futu"] += 1
            raise FutuProviderError("password=do-not-expose")

        def yahoo_loader(received_codes: list[str], start: str, end: str):
            calls["yahoo"] += 1
            raise MarketDataProviderError("secret=do-not-expose")

        rows, status, warnings = self._load(self._pool(futu_loader, yahoo_loader), active_markets={"US"})

        self.assertEqual(calls, {"futu": 1, "yahoo": 1})
        self.assertEqual(rows, [])
        self.assertEqual(status["status"], "provider_unavailable")
        self.assertEqual(status["count"], 0)
        self.assertIsNone(status["provider"])
        self.assertEqual(status["providers"], ["futu", "yahoo_chart"])
        self.assertEqual(status["fetched_at"], FETCHED_AT.isoformat())
        self.assertEqual(status["metric"], "close_to_close")
        self.assertEqual(status["missing"], [index["name"] for index in REQUIRED_INDEXES])
        self.assertEqual(status["active_markets"], ["US"])
        self.assertEqual(status["uncovered_active_markets"], ["US"])
        self.assertEqual(status["attempted_sources"], ["futu", "yahoo_chart"])
        self.assertIsNone(status["selected_source"])
        self.assertEqual(status["coverage"], 0.0)
        self.assertEqual(status["provider_errors"], ["futu: provider_unavailable", "yahoo_chart: provider_unavailable"])
        self.assertEqual([failure["code"] for failure in status["failures"]], ["provider_unavailable", "provider_unavailable"])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(status["reason"], "指数行情数据源暂不可用。")
        self.assertEqual(warnings, ["指数行情读取失败：指数行情数据源暂不可用。"])
        self.assertIn("指数行情读取失败", warnings[0])
        self.assertNotIn("do-not-expose", " ".join(str(item) for item in [status, warnings]))
