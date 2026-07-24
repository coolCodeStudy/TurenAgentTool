from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest import TestCase

from investment_knowledge_mcp.crowding_intelligence import (
    CrowdingBand,
    CrowdingAssessment,
    DirectionalAssessment,
    EvidenceQuality,
)
from investment_knowledge_mcp.crowding_service import (
    investigate_portfolio_crowding,
    investigate_symbol_crowding,
    normalize_crowding_target,
    render_portfolio_crowding,
)
from investment_knowledge_mcp.data_sources.contracts import (
    DataResult,
    DataStatus,
    SourceCapability,
)


AS_OF = date(2026, 7, 24)
FETCHED_AT = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def unavailable() -> DataResult:
    return DataResult(DataStatus.UNAVAILABLE, (), None, (), 0.0, FETCHED_AT, False, ())


def bars_result(symbol: str) -> DataResult:
    start = AS_OF - timedelta(days=159)
    bars = tuple(
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.0 + index,
            "volume": 1_000_000 + index * 10_000,
        }
        for index in range(160)
    )
    return DataResult(
        DataStatus.OK,
        ({"symbol": symbol, "bars": bars},),
        "futu",
        ("futu",),
        1.0,
        FETCHED_AT,
        False,
        (),
    )


class RecordingPool:
    def __init__(self, result_factory) -> None:
        self.requests = []
        self.plans = []
        self._result_factory = result_factory

    def fetch(self, request, plan):
        self.requests.append(request)
        self.plans.append(plan)
        return self._result_factory(request)


def insufficient_assessment(canonical: str) -> CrowdingAssessment:
    market = canonical.split(".", 1)[0]
    direction = DirectionalAssessment(
        CrowdingBand.INSUFFICIENT,
        None,
        (),
        (),
        ("ownership",),
        "fixture",
    )
    return CrowdingAssessment(
        canonical,
        market,
        AS_OF,
        EvidenceQuality.INSUFFICIENT,
        direction,
        direction,
        direction,
        (),
        ("ownership", "short_interest", "options"),
        (),
        None,
    )


class CrowdingServiceTests(TestCase):
    def test_single_symbol_requests_each_semantic_capability_with_futu_only_plans(self) -> None:
        bars_pool = RecordingPool(lambda request: bars_result(request.symbols[0]))
        evidence_pool = RecordingPool(lambda request: unavailable())

        result = investigate_symbol_crowding(
            "NVDA",
            "US",
            as_of=AS_OF,
            bars_pool=bars_pool,
            evidence_pool=evidence_pool,
        )

        requested = [request.capability for request in bars_pool.requests + evidence_pool.requests]
        self.assertEqual(
            [
                SourceCapability.MARKET_BARS,
                SourceCapability.OWNERSHIP_CONCENTRATION,
                SourceCapability.SHORT_INTEREST,
                SourceCapability.OPTIONS_POSITIONING,
                SourceCapability.EVENT_CALENDAR,
            ],
            requested,
        )
        self.assertEqual("US.NVDA", result.canonical)
        self.assertEqual(("futu",), bars_pool.plans[0].allowed_sources)
        self.assertTrue(all(plan.allowed_sources == ("futu_crowding",) for plan in evidence_pool.plans))
        self.assertGreaterEqual((bars_pool.requests[0].end - bars_pool.requests[0].start).days, 395)

    def test_cn_target_preserves_provider_exchange_code_but_returns_product_identity(self) -> None:
        target = normalize_crowding_target("600519", "CN")
        self.assertEqual("CN", target.market)
        self.assertEqual("CN.600519", target.canonical)
        self.assertEqual("SH.600519", target.provider_code)
        bars_pool = RecordingPool(lambda request: bars_result(request.symbols[0]))
        evidence_pool = RecordingPool(lambda request: unavailable())

        result = investigate_symbol_crowding(
            "600519",
            "CN",
            as_of=AS_OF,
            bars_pool=bars_pool,
            evidence_pool=evidence_pool,
        )

        self.assertEqual("SH.600519", bars_pool.requests[0].symbols[0])
        self.assertEqual("CN.600519", result.canonical)
        self.assertEqual(CrowdingBand.INSUFFICIENT, result.long_crowding.band)
        self.assertEqual([], evidence_pool.requests)

    def test_partial_or_unavailable_results_still_return_an_assessment(self) -> None:
        bars_pool = RecordingPool(lambda request: unavailable())
        evidence_pool = RecordingPool(lambda request: unavailable())

        result = investigate_symbol_crowding(
            "NVDA",
            "US",
            as_of=AS_OF,
            bars_pool=bars_pool,
            evidence_pool=evidence_pool,
        )

        self.assertEqual(CrowdingBand.INSUFFICIENT, result.long_crowding.band)
        self.assertIn("price_volume", result.missing_families)

    def test_portfolio_is_bounded_deduplicated_and_grouped_without_global_ranking(self) -> None:
        positions = [
            {
                "code": f"{'US' if index % 2 == 0 else 'HK'}.{index:05d}",
                "stock_name": f"Stock {index}",
                "market_val": 1000 - index,
                "currency": "USD" if index % 2 == 0 else "HKD",
            }
            for index in range(12)
        ]
        positions.append(dict(positions[0]))
        calls = []

        def analyzer(symbol, market, *, as_of):
            calls.append((market, symbol))
            return insufficient_assessment(f"{market}.{symbol}")

        report = investigate_portfolio_crowding(
            positions,
            as_of=AS_OF,
            max_positions=8,
            analyzer=analyzer,
        )

        self.assertEqual(8, len(report.assessments))
        self.assertEqual(4, report.omitted_count)
        self.assertEqual(("HK", "US"), tuple(report.by_market))
        self.assertEqual(8, len(set(calls)))
        rendered = render_portfolio_crowding(report)
        self.assertIn("### HK", rendered)
        self.assertIn("### US", rendered)
        self.assertNotIn("跨市场排名", rendered)
        self.assertNotIn("总排名", rendered)
        self.assertIn("不是投资建议", rendered)

    def test_malformed_unsupported_and_per_symbol_failures_are_isolated(self) -> None:
        positions = [
            {"code": "", "market_val": 200},
            {"code": "JP.7203", "market_val": 190},
            {"code": "US.FAIL", "market_val": 180},
            {"code": "US.OK", "market_val": 170},
        ]

        def analyzer(symbol, market, *, as_of):
            if symbol == "FAIL":
                raise RuntimeError("secret provider details")
            return insufficient_assessment(f"{market}.{symbol}")

        report = investigate_portfolio_crowding(
            positions,
            as_of=AS_OF,
            analyzer=analyzer,
        )

        self.assertEqual(1, len(report.assessments))
        self.assertEqual("US.OK", report.assessments[0].canonical)
        self.assertIn("malformed_position", report.failures)
        self.assertIn("unsupported_market:JP", report.failures)
        self.assertIn("analysis_failed:US.FAIL", report.failures)
        self.assertNotIn("secret", "|".join(report.failures))

    def test_portfolio_order_is_deterministic_within_market_currency_group(self) -> None:
        positions = [
            {"code": "US.B", "market_val": 100, "currency": "USD"},
            {"code": "US.A", "market_val": 100, "currency": "USD"},
            {"code": "US.C", "market_val": 200, "currency": "USD"},
        ]
        report = investigate_portfolio_crowding(
            positions,
            as_of=AS_OF,
            analyzer=lambda symbol, market, *, as_of: insufficient_assessment(f"{market}.{symbol}"),
        )
        self.assertEqual(
            ["US.C", "US.A", "US.B"],
            [entry.canonical for entry in report.by_market["US"]],
        )

