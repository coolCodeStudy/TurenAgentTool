from __future__ import annotations

from datetime import date, datetime, timezone
from unittest import TestCase

from investment_knowledge_mcp.data_sources.contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    ProviderDescriptor,
    ProviderFailure,
    SourceCapability,
    SourcePlan,
)
from investment_knowledge_mcp.data_sources.pool import DataSourcePool
from investment_knowledge_mcp.data_sources.valuation import (
    ValuationFactsSource,
    valuation_financial_plan,
)


class DataSourceContractTests(TestCase):
    def test_capability_and_status_values_are_provider_neutral(self) -> None:
        self.assertEqual(SourceCapability.MARKET_BARS.value, "market_bars")
        self.assertEqual(SourceCapability.OFFICIAL_FINANCIAL_FACTS.value, "official_financial_facts")
        self.assertEqual(SourceCapability.MARKET_SNAPSHOT.value, "market_snapshot")
        self.assertEqual(DataStatus.PARTIAL.value, "partial")

    def test_crowding_capabilities_are_explicit(self) -> None:
        self.assertEqual(SourceCapability.OWNERSHIP_CONCENTRATION.value, "ownership_concentration")
        self.assertEqual(SourceCapability.SHORT_INTEREST.value, "short_interest")
        self.assertEqual(SourceCapability.OPTIONS_POSITIONING.value, "options_positioning")
        self.assertEqual(SourceCapability.EVENT_CALENDAR.value, "event_calendar")

    def test_valuation_source_normalizes_fact_metadata_and_coverage(self) -> None:
        calls: list[tuple[str, str]] = []

        def loader(symbol: str, market: str) -> dict[str, object]:
            calls.append((symbol, market))
            return {
                "facts": [
                    {
                        "metric": "revenue",
                        "value": 52_600_000_000,
                        "currency": "usd",
                        "period_end": "2025-12-31",
                        "timestamp": "2026-02-01T01:02:03Z",
                        "source_type": "vendor_financial",
                        "provider": "vendor",
                        "raw": {"authorization": "Bearer secret"},
                    }
                ],
                "fetched_at": datetime(2026, 2, 1, 1, 2, 3, tzinfo=timezone.utc),
            }

        source = ValuationFactsSource(
            "sec_companyfacts",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "sec_companyfacts",
            "sec",
            loader,
        )
        request = DataRequest(
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "US",
            ("INTC",),
            freshness="latest_filing",
            required_fields=("revenue", "net_income"),
        )

        result = source.fetch(request)

        self.assertEqual(calls, [("INTC", "US")])
        self.assertIs(result.status, DataStatus.PARTIAL)
        self.assertEqual(result.coverage, 0.5)
        self.assertEqual(
            result.records,
            ({
                "metric": "revenue",
                "value": 52_600_000_000.0,
                "source_type": "sec_companyfacts",
                "provider": "sec",
                "currency": "USD",
                "period_end": "2025-12-31",
                "timestamp": "2026-02-01T01:02:03+00:00",
                "freshness": "latest_filing",
            },),
        )
        self.assertNotIn("secret", repr(result))

    def test_valuation_plan_uses_ordered_vendor_fallback_and_redacted_failures(self) -> None:
        calls: list[str] = []

        def missing(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append("sec_companyfacts")
            return []

        def vendor(symbol: str, market: str) -> list[dict[str, object]]:
            calls.append("vendor_financial")
            return [{"metric": "revenue", "value": 10.0, "currency": "USD"}]

        pool = DataSourcePool(now=lambda: datetime(2026, 7, 19, tzinfo=timezone.utc))
        pool.register(ValuationFactsSource(
            "sec_companyfacts", SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "sec_companyfacts", "sec", missing,
        ))
        pool.register(ValuationFactsSource(
            "vendor_financial", SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "vendor_financial", "vendor", vendor,
        ))
        request = DataRequest(
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "US",
            ("INTC",),
            freshness="latest_filing",
            required_fields=("revenue",),
        )

        result = pool.fetch(request, valuation_financial_plan("US", available_sources=("sec_companyfacts", "vendor_financial")))

        self.assertEqual(calls, ["sec_companyfacts", "vendor_financial"])
        self.assertEqual(result.attempted_sources, ("sec_companyfacts", "vendor_financial"))
        self.assertEqual(result.selected_source, "vendor_financial")
        self.assertEqual(result.records[0]["source_type"], "vendor_financial")
        self.assertEqual(result.failures[0].code, "empty_result")
        self.assertIsNone(result.failures[0].detail)

    def test_valuation_source_returns_safe_unavailable_result_for_loader_failure(self) -> None:
        def broken(symbol: str, market: str) -> object:
            raise RuntimeError("token=secret https://private.example/raw")

        source = ValuationFactsSource(
            "hkexnews",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "hkexnews",
            "hkex",
            broken,
        )
        request = DataRequest(
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "HK",
            ("01888",),
            freshness="latest_filing",
        )

        result = source.fetch(request)

        self.assertIs(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual(result.failures[0].code, "provider_unavailable")
        self.assertEqual(result.failures[0].detail, "RuntimeError")
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("private.example", repr(result))

    def test_valuation_source_admits_only_metrics_for_its_capability(self) -> None:
        payload = [
            {"metric": "revenue", "value": 10.0, "currency": "USD"},
            {"metric": "price", "value": 2.0, "currency": "USD"},
        ]
        financial = ValuationFactsSource(
            "sec_companyfacts",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "sec_companyfacts",
            "sec",
            lambda symbol, market: payload,
        ).fetch(DataRequest(
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "US",
            ("INTC",),
            freshness="latest_filing",
        ))
        market = ValuationFactsSource(
            "yahoo",
            SourceCapability.MARKET_SNAPSHOT,
            "market_snapshot",
            "yahoo",
            lambda symbol, market: payload,
        ).fetch(DataRequest(
            SourceCapability.MARKET_SNAPSHOT,
            "US",
            ("INTC",),
            freshness="latest_market_session",
        ))

        self.assertEqual([record["metric"] for record in financial.records], ["revenue"])
        self.assertEqual([record["metric"] for record in market.records], ["price"])

    def test_empty_completed_probe_has_distinct_failure_code(self) -> None:
        source = ValuationFactsSource(
            "dart_filing",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "dart_filing",
            "dart",
            lambda symbol, market: {
                "facts": [],
                "attempt_status": "complete_missing",
                "fetched_at": datetime(2026, 7, 19, tzinfo=timezone.utc),
            },
        )

        result = source.fetch(DataRequest(
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "KR",
            ("000660",),
            freshness="latest_filing",
        ))

        self.assertIs(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual(result.failures[0].code, "complete_missing")

    def test_provider_failure_is_immutable_and_redacts_sensitive_detail(self) -> None:
        failure = ProviderFailure(
            code="timeout",
            source_id=" Acme ",
            retryable=True,
            fallback_allowed=True,
            detail="token=secret authorization: Bearer abc",
        )
        self.assertEqual(failure.source_id, "acme")
        self.assertNotIn("secret", repr(failure))
        self.assertNotIn("abc", repr(failure))
        with self.assertRaises(AttributeError):
            failure.code = "other"  # type: ignore[misc]

    def test_provider_failure_repr_never_includes_supplied_detail(self) -> None:
        failure = ProviderFailure("error", "source", False, False, "ordinary internal detail")
        self.assertNotIn("ordinary internal detail", repr(failure))
        bearer = ProviderFailure("error", "source", False, False, "Bearer opaque-value")
        basic = ProviderFailure("error", "source", False, False, "Basic opaque-value")
        cookie = ProviderFailure("error", "source", False, False, "session=opaque-value; cookie=value")
        self.assertEqual(bearer.detail, "[redacted]")
        self.assertEqual(basic.detail, "[redacted]")
        self.assertEqual(cookie.detail, "[redacted]")

    def test_provider_failure_requires_code_and_source_id(self) -> None:
        with self.assertRaises(ValueError):
            ProviderFailure("", "source", False, False)
        with self.assertRaises(ValueError):
            ProviderFailure("error", "  ", False, False)

    def test_provider_failure_requires_boolean_retry_flags(self) -> None:
        for value in (1, "true"):
            with self.subTest(retryable=value), self.assertRaises(ValueError):
                ProviderFailure("error", "source", value, False)
            with self.subTest(fallback_allowed=value), self.assertRaises(ValueError):
                ProviderFailure("error", "source", False, value)

    def test_request_normalizes_market_symbols_and_required_fields(self) -> None:
        request = DataRequest(
            capability=SourceCapability.MARKET_BARS,
            market=" us ",
            symbols=[" aapl ", "MSFT"],
            freshness=" 5m ",
            required_fields=["close", " volume "],
        )
        self.assertEqual(request.market, "US")
        self.assertEqual(request.symbols, ("AAPL", "MSFT"))
        self.assertEqual(request.required_fields, ("close", "volume"))
        with self.assertRaises(AttributeError):
            request.symbols += ("NVDA",)  # type: ignore[misc]

    def test_request_rejects_invalid_date_range_and_empty_market(self) -> None:
        with self.assertRaises(ValueError):
            DataRequest(SourceCapability.MARKET_BARS, "US", (), date(2026, 2, 2), date(2026, 2, 1), "1h", ())
        with self.assertRaises(ValueError):
            DataRequest(SourceCapability.MARKET_BARS, "", (), freshness="1h")

    def test_request_rejects_datetime_boundaries(self) -> None:
        with self.assertRaises(ValueError):
            DataRequest(SourceCapability.MARKET_BARS, "US", (), datetime.now(timezone.utc), freshness="1h")
        with self.assertRaises(ValueError):
            DataRequest(SourceCapability.MARKET_BARS, "US", (), end=datetime.now(timezone.utc), freshness="1h")

    def test_plan_normalizes_sources_and_requires_allowed_membership(self) -> None:
        plan = SourcePlan(
            SourceCapability.MARKET_BARS,
            preferred_sources=[" Primary "],
            allowed_sources=["primary", "fallback"],
            fallback_sources=[" FALLBACK "],
            required=True,
            partial_allowed=False,
        )
        self.assertEqual(plan.preferred_sources, ("primary",))
        self.assertEqual(plan.fallback_sources, ("fallback",))
        with self.assertRaises(ValueError):
            SourcePlan(SourceCapability.MARKET_BARS, ("missing",), ("known",), (), True, False)

    def test_plan_validates_matching_request_capability(self) -> None:
        plan = SourcePlan(SourceCapability.MARKET_BARS, (), ("primary",), (), True, False)
        request = DataRequest(SourceCapability.OFFICIAL_EVENTS, "US", (), freshness="1d")
        with self.assertRaises(ValueError):
            plan.validate_request(request)

    def test_plan_requires_boolean_policy_flags(self) -> None:
        for value in (1, "true"):
            with self.subTest(required=value), self.assertRaises(ValueError):
                SourcePlan(SourceCapability.MARKET_BARS, (), ("source",), (), value, False)
            with self.subTest(partial_allowed=value), self.assertRaises(ValueError):
                SourcePlan(SourceCapability.MARKET_BARS, (), ("source",), (), False, value)

    def test_provider_descriptor_normalizes_source_and_markets(self) -> None:
        descriptor = ProviderDescriptor(
            source_id=" Provider ",
            capabilities=[SourceCapability.MARKET_BARS],
            markets=[" us ", "hk"],
            timeout_seconds=2.0,
            retry_limit=1,
            rate_group=" market ",
            default_ttl_seconds=60,
        )
        self.assertEqual(descriptor.source_id, "provider")
        self.assertEqual(descriptor.markets, ("US", "HK"))
        self.assertEqual(descriptor.rate_group, "market")

    def test_provider_descriptor_rejects_empty_or_invalid_limits(self) -> None:
        with self.assertRaises(ValueError):
            ProviderDescriptor("", (), (), 1, 0, "group", 1)
        with self.assertRaises(ValueError):
            ProviderDescriptor("source", (), ("",), 0, -1, "group", -1)

    def test_provider_descriptor_rejects_non_finite_fractional_and_boolean_limits(self) -> None:
        valid = ("source", (SourceCapability.MARKET_BARS,), ("US",), 1.0, 0, "group", 1)
        for timeout in (float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                ProviderDescriptor(*valid[:3], timeout, *valid[4:])
        for retry_limit in (0.5, True):
            with self.subTest(retry_limit=retry_limit), self.assertRaises(ValueError):
                ProviderDescriptor(*valid[:4], retry_limit, *valid[5:])
        for ttl in (0.5, True):
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                ProviderDescriptor(*valid[:6], ttl)

    def test_ok_result_requires_selected_source_and_complete_coverage(self) -> None:
        with self.assertRaises(ValueError):
            DataResult(DataStatus.OK, (), None, ("source",), 1.0, datetime.now(timezone.utc), False, ())
        with self.assertRaises(ValueError):
            DataResult(DataStatus.OK, (), "source", ("source",), 0.5, datetime.now(timezone.utc), False, ())

    def test_partial_result_requires_selected_source(self) -> None:
        with self.assertRaises(ValueError):
            DataResult(DataStatus.PARTIAL, (), None, ("source",), 0.5, datetime.now(timezone.utc), False, ())

    def test_unavailable_result_can_omit_selected_source_and_preserves_attempts(self) -> None:
        result = DataResult(
            DataStatus.UNAVAILABLE,
            (),
            None,
            [" primary ", "fallback"],
            0.0,
            datetime.now(timezone.utc),
            False,
            [ProviderFailure("timeout", "primary", True, True)],
        )
        self.assertEqual(result.attempted_sources, ("primary", "fallback"))
        self.assertIsNone(result.selected_source)

    def test_result_requires_selected_source_and_failures_to_be_attempted(self) -> None:
        fetched_at = datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            DataResult(DataStatus.PARTIAL, (), "source", (), 0.5, fetched_at, False, ())
        with self.assertRaises(ValueError):
            DataResult(
                DataStatus.UNAVAILABLE,
                (),
                None,
                ("source",),
                0.0,
                fetched_at,
                False,
                (ProviderFailure("error", "other", False, False),),
            )

    def test_result_rejects_invalid_coverage_and_normalizes_selected_source(self) -> None:
        with self.assertRaises(ValueError):
            DataResult(DataStatus.UNAVAILABLE, (), None, (), 1.1, datetime.now(timezone.utc), False, ())
        result = DataResult(DataStatus.PARTIAL, (), " Primary ", ("primary",), 0.3, datetime.now(timezone.utc), True, ())
        self.assertEqual(result.selected_source, "primary")

    def test_result_requires_timezone_aware_fetch_time(self) -> None:
        with self.assertRaises(ValueError):
            DataResult(DataStatus.UNAVAILABLE, (), None, (), 0.0, datetime.now(), False, ())

    def test_result_requires_boolean_cache_flag_and_real_finite_coverage(self) -> None:
        fetched_at = datetime.now(timezone.utc)
        for value in (1, "false"):
            with self.subTest(from_cache=value), self.assertRaises(ValueError):
                DataResult(DataStatus.UNAVAILABLE, (), None, (), 0.0, fetched_at, value, ())
        for coverage in (True, float("nan"), float("inf"), "0.5"):
            with self.subTest(coverage=coverage), self.assertRaises(ValueError):
                DataResult(DataStatus.UNAVAILABLE, (), None, (), coverage, fetched_at, False, ())

    def test_contract_annotations_do_not_include_credentials(self) -> None:
        contracts = (ProviderFailure, DataRequest, SourcePlan, ProviderDescriptor, DataResult)
        forbidden = {"token", "api_key", "password", "credential", "secret"}
        for contract in contracts:
            self.assertTrue(forbidden.isdisjoint(contract.__annotations__))
