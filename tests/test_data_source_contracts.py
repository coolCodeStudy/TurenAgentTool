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


class DataSourceContractTests(TestCase):
    def test_capability_and_status_values_are_provider_neutral(self) -> None:
        self.assertEqual(SourceCapability.MARKET_BARS.value, "market_bars")
        self.assertEqual(DataStatus.PARTIAL.value, "partial")

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

    def test_contract_annotations_do_not_include_credentials(self) -> None:
        contracts = (ProviderFailure, DataRequest, SourcePlan, ProviderDescriptor, DataResult)
        forbidden = {"token", "api_key", "password", "credential", "secret"}
        for contract in contracts:
            self.assertTrue(forbidden.isdisjoint(contract.__annotations__))
