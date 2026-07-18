from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
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
from investment_knowledge_mcp.data_sources.pool import DataSourcePool, MemoryResultCache


NOW = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)


def descriptor(source_id: str, *, markets: tuple[str, ...] = ("US",)) -> ProviderDescriptor:
    return ProviderDescriptor(
        source_id, (SourceCapability.MARKET_BARS,), markets, 1.0, 0, "test", 60
    )


def request() -> DataRequest:
    return DataRequest(SourceCapability.MARKET_BARS, "US", ("AAPL",), freshness="1h")


def plan(*, partial_allowed: bool = False) -> SourcePlan:
    return SourcePlan(
        SourceCapability.MARKET_BARS,
        ("primary",),
        ("primary", "fallback"),
        ("fallback",),
        True,
        partial_allowed,
    )


class Provider:
    def __init__(self, source_id: str, result: DataResult | Exception) -> None:
        self.descriptor = descriptor(source_id)
        self.result = result
        self.calls = 0

    def fetch(self, request: DataRequest) -> DataResult:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def result(
    status: DataStatus,
    source_id: str,
    *,
    coverage: float | None = None,
    failures: tuple[ProviderFailure, ...] = (),
) -> DataResult:
    return DataResult(
        status,
        (source_id,),
        source_id if status is not DataStatus.UNAVAILABLE else None,
        (source_id,),
        1.0 if coverage is None and status is DataStatus.OK else (0.5 if coverage is None else coverage),
        NOW,
        False,
        failures,
    )


class DataSourcePoolTests(TestCase):
    def test_registration_rejects_duplicate_source_ids(self) -> None:
        pool = DataSourcePool(now=lambda: NOW)
        pool.register(Provider("primary", result(DataStatus.OK, "primary")))
        with self.assertRaises(ValueError):
            pool.register(Provider("PRIMARY", result(DataStatus.OK, "primary")))

    def test_preferred_success_returns_without_calling_fallback(self) -> None:
        primary = Provider("primary", result(DataStatus.OK, "primary"))
        fallback = Provider("fallback", result(DataStatus.OK, "fallback"))
        pool = DataSourcePool(now=lambda: NOW)
        pool.register(primary)
        pool.register(fallback)

        actual = pool.fetch(request(), plan())

        self.assertEqual(actual.status, DataStatus.OK)
        self.assertEqual(actual.selected_source, "primary")
        self.assertEqual(fallback.calls, 0)

    def test_admitted_fallback_follows_failure_flag(self) -> None:
        primary = Provider(
            "primary",
            result(DataStatus.UNAVAILABLE, "primary", coverage=0.0, failures=(ProviderFailure("timeout", "primary", True, True),)),
        )
        fallback = Provider("fallback", result(DataStatus.OK, "fallback"))
        pool = DataSourcePool(now=lambda: NOW)
        pool.register(primary)
        pool.register(fallback)

        actual = pool.fetch(request(), plan())

        self.assertEqual(actual.selected_source, "fallback")
        self.assertEqual(actual.attempted_sources, ("primary", "fallback"))

    def test_non_fallback_failure_does_not_call_fallback(self) -> None:
        primary = Provider(
            "primary",
            result(DataStatus.UNAVAILABLE, "primary", coverage=0.0, failures=(ProviderFailure("denied", "primary", False, False),)),
        )
        fallback = Provider("fallback", result(DataStatus.OK, "fallback"))
        pool = DataSourcePool(now=lambda: NOW)
        pool.register(primary)
        pool.register(fallback)

        actual = pool.fetch(request(), plan())

        self.assertEqual(actual.status, DataStatus.UNAVAILABLE)
        self.assertEqual(fallback.calls, 0)

    def test_partial_returns_only_when_plan_allows_it(self) -> None:
        partial = result(DataStatus.PARTIAL, "primary")
        fallback = result(DataStatus.OK, "fallback")
        allowed_pool = DataSourcePool(now=lambda: NOW)
        allowed_pool.register(Provider("primary", partial))
        allowed_pool.register(Provider("fallback", fallback))
        self.assertEqual(allowed_pool.fetch(request(), plan(partial_allowed=True)).selected_source, "primary")

        disallowed_pool = DataSourcePool(now=lambda: NOW)
        disallowed_pool.register(Provider("primary", partial))
        disallowed_pool.register(Provider("fallback", fallback))
        self.assertEqual(disallowed_pool.fetch(request(), plan()).selected_source, "fallback")

    def test_missing_provider_is_non_retryable_and_can_advance_to_fallback(self) -> None:
        fallback = Provider("fallback", result(DataStatus.OK, "fallback"))
        pool = DataSourcePool(now=lambda: NOW)
        pool.register(fallback)

        actual = pool.fetch(request(), plan())

        self.assertEqual(actual.selected_source, "fallback")
        self.assertEqual(actual.failures[0].code, "provider_not_registered")
        self.assertFalse(actual.failures[0].retryable)

    def test_provider_contract_violation_is_aggregated(self) -> None:
        invalid = replace(result(DataStatus.OK, "primary"), selected_source="other", attempted_sources=("other",))
        pool = DataSourcePool(now=lambda: NOW)
        pool.register(Provider("primary", invalid))

        actual = pool.fetch(request(), SourcePlan(SourceCapability.MARKET_BARS, ("primary",), ("primary",), (), True, False))

        self.assertEqual(actual.status, DataStatus.UNAVAILABLE)
        self.assertEqual(actual.failures[0].code, "provider_contract_error")

    def test_provider_exception_is_redacted_and_allows_fallback(self) -> None:
        pool = DataSourcePool(now=lambda: NOW)
        pool.register(Provider("primary", RuntimeError("token=secret")))
        pool.register(Provider("fallback", result(DataStatus.OK, "fallback")))

        actual = pool.fetch(request(), plan())

        self.assertEqual(actual.selected_source, "fallback")
        self.assertEqual(actual.failures[0].code, "provider_exception")
        self.assertIsNone(actual.failures[0].detail)

    def test_cache_hit_expiry_and_request_key_isolation(self) -> None:
        ticks = [0.0]
        cache = MemoryResultCache(clock=lambda: ticks[0])
        provider = Provider("primary", result(DataStatus.OK, "primary"))
        pool = DataSourcePool(cache=cache, now=lambda: NOW)
        pool.register(provider)

        first = pool.fetch(request(), SourcePlan(SourceCapability.MARKET_BARS, ("primary",), ("primary",), (), True, False))
        second = pool.fetch(request(), SourcePlan(SourceCapability.MARKET_BARS, ("primary",), ("primary",), (), True, False))
        other = DataRequest(SourceCapability.MARKET_BARS, "US", ("MSFT",), freshness="1h")
        pool.fetch(other, SourcePlan(SourceCapability.MARKET_BARS, ("primary",), ("primary",), (), True, False))
        ticks[0] = 61.0
        expired = pool.fetch(request(), SourcePlan(SourceCapability.MARKET_BARS, ("primary",), ("primary",), (), True, False))

        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertFalse(expired.from_cache)
        self.assertEqual(provider.calls, 3)

    def test_aggregate_unavailable_has_ordered_attempts_and_aware_time(self) -> None:
        pool = DataSourcePool(now=lambda: NOW)
        pool.register(Provider("primary", result(DataStatus.UNAVAILABLE, "primary", coverage=0.0, failures=(ProviderFailure("down", "primary", False, True),))))
        pool.register(Provider("fallback", result(DataStatus.UNAVAILABLE, "fallback", coverage=0.0, failures=(ProviderFailure("down", "fallback", False, False),))))

        actual = pool.fetch(request(), plan())

        self.assertEqual(actual.status, DataStatus.UNAVAILABLE)
        self.assertEqual(actual.attempted_sources, ("primary", "fallback"))
        self.assertEqual(actual.coverage, 0.0)
        self.assertEqual(actual.fetched_at, NOW)
