from __future__ import annotations

from datetime import date
import unittest

from investment_knowledge_mcp.data_sources import (
    DataRequest,
    DataStatus,
    SourceCapability,
)
from investment_knowledge_mcp.data_sources.market_activity import (
    MarketActivitySource,
    load_activity_section,
)


def activity_request(market: str = "CN") -> DataRequest:
    session = date(2026, 7, 10)
    return DataRequest(
        capability=SourceCapability.MARKET_ACTIVITY,
        market=market,
        start=session,
        end=session,
        freshness="session_close",
    )


def full_activity() -> dict:
    return {
        "sectors": [{"name": "Semiconductors"}],
        "gainers": [{"code": "000001"}],
        "capital_flow": [{"name": "Semiconductors", "flow_value": 10}],
        "source_status": {
            "sectors": {"status": "ok", "provider": "akshare_eastmoney", "count": 1},
            "gainers": {"status": "ok", "provider": "akshare_eastmoney", "count": 1},
            "capital_flow": {"status": "ok", "provider": "akshare_eastmoney", "count": 1},
        },
    }


class MarketActivitySourceTests(unittest.TestCase):
    def test_adapter_returns_one_result_with_section_level_coverage(self) -> None:
        source = MarketActivitySource("daily_market_activity", lambda market, session: full_activity())

        result = source.fetch(activity_request())

        self.assertIs(DataStatus.OK, result.status)
        self.assertEqual(1.0, result.coverage)
        self.assertEqual("daily_market_activity", result.selected_source)
        self.assertEqual(("daily_market_activity",), result.attempted_sources)
        self.assertEqual(
            ["sectors", "gainers", "capital_flow"],
            [record["section"] for record in result.records],
        )
        self.assertTrue(all(record["covered"] for record in result.records))

    def test_adapter_normalizes_partial_and_failure_vocabulary(self) -> None:
        activity = full_activity()
        activity["sectors"] = []
        activity["source_status"]["sectors"] = {
            "status": "not_available",
            "provider": "akshare_eastmoney",
            "count": 0,
        }
        source = MarketActivitySource("daily_market_activity", lambda market, session: activity)

        result = source.fetch(activity_request("HK"))

        self.assertIs(DataStatus.PARTIAL, result.status)
        self.assertEqual(2 / 3, result.coverage)
        self.assertEqual(["not_available"], [failure.code for failure in result.failures])
        self.assertEqual("sectors", result.failures[0].detail)

    def test_adapter_normalizes_provider_exception_without_raw_detail(self) -> None:
        def unavailable(market: str, session: date) -> dict:
            raise ConnectionError("private upstream response")

        result = MarketActivitySource("daily_market_activity", unavailable).fetch(activity_request())

        self.assertIs(DataStatus.UNAVAILABLE, result.status)
        self.assertIsNone(result.selected_source)
        self.assertEqual(["provider_unavailable"], [failure.code for failure in result.failures])
        self.assertEqual("ConnectionError", result.failures[0].detail)
        self.assertNotIn("private", repr(result))

    def test_adapter_marks_cancellation_for_feature_layer_propagation(self) -> None:
        class Cancelled(Exception):
            pass

        def cancelled(market: str, session: date) -> dict:
            raise Cancelled()

        result = MarketActivitySource(
            "historical_market_activity",
            cancelled,
            cancellation_exceptions=(Cancelled,),
        ).fetch(activity_request())

        self.assertIs(DataStatus.UNAVAILABLE, result.status)
        self.assertEqual(["cancelled"], [failure.code for failure in result.failures])
        self.assertFalse(result.failures[0].fallback_allowed)

    def test_section_fallback_preserves_transport_provenance(self) -> None:
        rows, status = load_activity_section(
            provider="akshare_eastmoney",
            section="gainers",
            fallback_message="not available",
            loader=lambda: (_ for _ in ()).throw(ConnectionError("private")),
            fallback_provider="public_http_fallback",
            fallback_loader=lambda: [{"code": "000001"}],
        )

        self.assertEqual([{"code": "000001"}], rows)
        self.assertEqual("ok", status["status"])
        self.assertEqual("public_http_fallback", status["provider"])
        self.assertEqual("akshare_eastmoney", status["fallback_from"])
        self.assertEqual("ConnectionError", status["fallback_reason"])


if __name__ == "__main__":
    unittest.main()
