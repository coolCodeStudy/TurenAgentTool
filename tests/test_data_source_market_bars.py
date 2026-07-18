from __future__ import annotations

from datetime import date, datetime, timezone
from unittest import TestCase

from investment_knowledge_mcp.data_sources.contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    SourceCapability,
    SourcePlan,
)
from investment_knowledge_mcp.data_sources.market_bars import (
    FutuMarketBarsSource,
    YahooMarketBarsSource,
    default_market_bar_pool,
    market_bar_records_by_symbol,
)
from investment_knowledge_mcp.data_sources.pool import DataSourcePool
from investment_knowledge_mcp.futu_provider import FutuProviderError, MarketBarSnapshot as FutuMarketBarSnapshot
from investment_knowledge_mcp.market_data_provider import (
    MarketBarSnapshot as YahooMarketBarSnapshot,
    MarketDataProviderError,
)


NOW = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)
START = date(2026, 7, 1)
END = date(2026, 7, 3)


def request(*, market: str = "US", symbols: tuple[str, ...] = ("US.SPX", "US.IXIC")) -> DataRequest:
    return DataRequest(SourceCapability.MARKET_BARS, market, symbols, START, END, "1d")


class MarketBarSourceTests(TestCase):
    def test_each_source_normalizes_complete_snapshots_and_loader_arguments(self) -> None:
        cases = (
            (FutuMarketBarsSource, FutuMarketBarSnapshot),
            (YahooMarketBarsSource, YahooMarketBarSnapshot),
        )
        for source_type, snapshot_type in cases:
            with self.subTest(source=source_type.__name__):
                calls: list[tuple[list[str], str, str]] = []

                def loader(codes: list[str], start: str, end: str):
                    calls.append((codes, start, end))
                    return snapshot_type(
                        {"US.SPX": [{"date": "2026-07-01", "close": 1.0}], "US.IXIC": [{"date": "2026-07-01", "close": 2.0}]},
                        NOW,
                        start,
                        end,
                    )

                source = source_type(loader=loader)
                result = source.fetch(request())

                self.assertEqual(calls, [(["US.SPX", "US.IXIC"], "2026-07-01", "2026-07-03")])
                self.assertEqual(result.status, DataStatus.OK)
                self.assertEqual(result.coverage, 1.0)
                self.assertEqual(result.selected_source, source.descriptor.source_id)
                self.assertEqual(result.attempted_sources, (source.descriptor.source_id,))
                self.assertEqual(result.fetched_at, NOW)
                self.assertEqual(result.failures, ())
                self.assertEqual(
                    result.records,
                    (
                        {"symbol": "US.SPX", "bars": ({"date": "2026-07-01", "close": 1.0},)},
                        {"symbol": "US.IXIC", "bars": ({"date": "2026-07-01", "close": 2.0},)},
                    ),
                )

    def test_partial_and_empty_snapshots_have_typed_coverage_failures(self) -> None:
        source = YahooMarketBarsSource(
            loader=lambda codes, start, end: YahooMarketBarSnapshot(
                {"US.SPX": [{"date": "2026-07-01", "close": 1.0}]}, NOW, start, end
            )
        )

        partial = source.fetch(request())

        self.assertEqual(partial.status, DataStatus.PARTIAL)
        self.assertEqual(partial.coverage, 0.5)
        self.assertEqual(partial.selected_source, "yahoo_chart")
        self.assertEqual(partial.failures[0].code, "incomplete_coverage")
        self.assertTrue(partial.failures[0].fallback_allowed)
        self.assertIsNone(partial.failures[0].detail)

        empty = YahooMarketBarsSource(
            loader=lambda codes, start, end: YahooMarketBarSnapshot({}, NOW, start, end)
        ).fetch(request())

        self.assertEqual(empty.status, DataStatus.UNAVAILABLE)
        self.assertEqual(empty.coverage, 0.0)
        self.assertIsNone(empty.selected_source)
        self.assertEqual(empty.failures[0].code, "empty_result")
        self.assertTrue(empty.failures[0].fallback_allowed)

    def test_known_provider_errors_are_normalized_without_detail(self) -> None:
        cases = (
            (FutuMarketBarsSource, FutuProviderError),
            (YahooMarketBarsSource, MarketDataProviderError),
        )
        for source_type, error_type in cases:
            with self.subTest(source=source_type.__name__):
                def loader(codes: list[str], start: str, end: str):
                    raise error_type("token=do-not-expose")

                result = source_type(loader=loader).fetch(request())

                self.assertEqual(result.status, DataStatus.UNAVAILABLE)
                self.assertEqual(result.failures[0].code, "provider_unavailable")
                self.assertTrue(result.failures[0].fallback_allowed)
                self.assertIsNone(result.failures[0].detail)

    def test_unexpected_provider_errors_escape_the_adapter_for_pool_sanitization(self) -> None:
        def loader(codes: list[str], start: str, end: str):
            raise RuntimeError("token=do-not-expose")

        source = YahooMarketBarsSource(loader=loader)
        with self.assertRaises(RuntimeError):
            source.fetch(request())

        pool = DataSourcePool()
        pool.register(source)
        plan = SourcePlan(SourceCapability.MARKET_BARS, ("yahoo_chart",), ("yahoo_chart",), (), True, False)
        result = pool.fetch(request(), plan)

        self.assertEqual(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual(result.failures[0].code, "provider_exception")
        self.assertIsNone(result.failures[0].detail)

    def test_invalid_requests_return_non_fallback_failure_without_calling_loader(self) -> None:
        calls = 0

        def loader(codes: list[str], start: str, end: str):
            nonlocal calls
            calls += 1
            raise AssertionError("invalid request must not call the loader")

        source = FutuMarketBarsSource(loader=loader)
        invalid_requests = (
            DataRequest(SourceCapability.MARKET_ACTIVITY, "US", ("US.SPX",), START, END, "1d"),
            DataRequest(SourceCapability.MARKET_BARS, "US", (), START, END, "1d"),
            DataRequest(SourceCapability.MARKET_BARS, "US", ("US.SPX",), None, END, "1d"),
            DataRequest(SourceCapability.MARKET_BARS, "US", ("US.SPX",), START, None, "1d"),
        )

        for invalid_request in invalid_requests:
            with self.subTest(request=invalid_request):
                result = source.fetch(invalid_request)
                self.assertEqual(result.status, DataStatus.UNAVAILABLE)
                self.assertEqual(result.failures[0].code, "invalid_request")
                self.assertFalse(result.failures[0].retryable)
                self.assertFalse(result.failures[0].fallback_allowed)
        self.assertEqual(calls, 0)

    def test_source_mismatch_returns_contract_failure(self) -> None:
        source = FutuMarketBarsSource(
            loader=lambda codes, start, end: FutuMarketBarSnapshot(
                {"US.SPX": [{"date": "2026-07-01"}]}, NOW, start, end, source="yahoo_chart"
            )
        )

        result = source.fetch(request(symbols=("US.SPX",)))

        self.assertEqual(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual(result.failures[0].code, "provider_contract_error")
        self.assertIsNone(result.failures[0].detail)

    def test_records_converter_validates_contract_and_returns_deep_container_copies(self) -> None:
        bars = {"date": "2026-07-01", "close": 1.0}
        result = DataResult(
            DataStatus.OK,
            ({"symbol": "US.SPX", "bars": (bars,)},),
            "futu",
            ("futu",),
            1.0,
            NOW,
            False,
            (),
        )

        converted = market_bar_records_by_symbol(result)
        converted["US.SPX"][0]["close"] = 2.0

        self.assertEqual(converted, {"US.SPX": [{"date": "2026-07-01", "close": 2.0}]})
        self.assertEqual(bars["close"], 1.0)

        invalid_records = (
            ({"symbol": "US.SPX", "bars": []},),
            ({"symbol": "US.SPX", "bars": ()},),
            ({"symbol": " US.SPX ", "bars": ()},),
            ({"symbol": "US.SPX", "bars": ()}, {"symbol": "US.SPX", "bars": ()}),
            ({"symbol": "US.SPX", "bars": ({"date": "2026-07-01"},), "extra": True},),
            ({"symbol": "US.SPX", "bars": ("not-a-mapping",)},),
        )
        for records in invalid_records:
            with self.subTest(records=records):
                malformed = DataResult(DataStatus.OK, records, "futu", ("futu",), 1.0, NOW, False, ())
                with self.assertRaises(ValueError):
                    market_bar_records_by_symbol(malformed)

    def test_multi_market_requests_are_compatible_and_pool_registration_is_lazy(self) -> None:
        calls = 0

        def loader(codes: list[str], start: str, end: str):
            nonlocal calls
            calls += 1
            return FutuMarketBarSnapshot(
                {code: [{"date": "2026-07-01"}] for code in codes}, NOW, start, end
            )

        source = FutuMarketBarsSource(loader=loader)
        multi_request = request(market="MULTI", symbols=("US.SPX", "HK.HSI", "SH.000300"))
        plan = SourcePlan(SourceCapability.MARKET_BARS, ("futu",), ("futu",), (), True, False)
        from_pool = default_market_bar_pool()

        self.assertEqual(tuple(from_pool._providers), ("futu", "yahoo_chart"))
        self.assertEqual(calls, 0)

        pool = DataSourcePool()
        pool.register(source)
        result = pool.fetch(multi_request, plan)

        self.assertEqual(result.status, DataStatus.OK)
        self.assertEqual(calls, 1)
