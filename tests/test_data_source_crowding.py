from __future__ import annotations

from datetime import date, datetime, timezone
from unittest import TestCase

from investment_knowledge_mcp.data_sources.crowding import (
    FUTU_CROWDING_APPROVAL,
    FutuCrowdingSource,
    SourceApproval,
    default_crowding_source_pool,
    source_is_approved,
)
from investment_knowledge_mcp.data_sources.contracts import (
    DataRequest,
    DataStatus,
    SourceCapability,
)
from investment_knowledge_mcp.futu_provider import FutuCrowdingSnapshot


class CrowdingSourceApprovalTests(TestCase):
    def test_futu_approval_is_private_internal_and_non_redistributable(self) -> None:
        self.assertTrue(source_is_approved("futu_crowding", "private_internal_research"))
        self.assertFalse(source_is_approved("futu_crowding", "public_redistribution"))
        self.assertEqual("account_entitled", FUTU_CROWDING_APPROVAL.access_tier)
        self.assertFalse(FUTU_CROWDING_APPROVAL.redistribution_allowed)
        self.assertEqual(("US", "HK"), FUTU_CROWDING_APPROVAL.enabled_markets)

    def test_unknown_source_or_use_is_not_approved(self) -> None:
        self.assertFalse(source_is_approved("unknown", "private_internal_research"))
        self.assertFalse(source_is_approved("futu_crowding", ""))

    def test_source_approval_rejects_empty_or_duplicate_contract_values(self) -> None:
        with self.assertRaises(ValueError):
            SourceApproval("", "account_entitled", ("private_internal_research",), False, ("US",))
        with self.assertRaises(ValueError):
            SourceApproval("futu", "account_entitled", ("internal", "INTERNAL"), False, ("US",))
        with self.assertRaises(ValueError):
            SourceApproval("futu", "account_entitled", ("internal",), False, ("US", "us"))


class FutuCrowdingSourceTests(TestCase):
    def setUp(self) -> None:
        self.fetched_at = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)

    def _snapshot(self) -> FutuCrowdingSnapshot:
        return FutuCrowdingSnapshot(
            ownership_by_code={
                "US.NVDA": [
                    {"name": "Holder A", "holder_pct": 40.0, "observed_at": "2026-06-30"},
                    {"name": "Holder B", "holder_pct": 21.0, "observed_at": "2026-06-30"},
                ]
            },
            short_interest_by_code={
                "US.NVDA": [
                    {
                        "short_percent": 3.2,
                        "days_to_cover": 1.8,
                        "shares_short": 30_000_000,
                        "observed_at": "2026-07-15",
                    }
                ]
            },
            options_by_code={
                "US.NVDA": [
                    {
                        "option_type": "CALL",
                        "volume": 1_000,
                        "open_interest": 5_000,
                        "implied_volatility": 42.0,
                        "expiry_date": "2026-07-31",
                    },
                    {
                        "option_type": "PUT",
                        "volume": 600,
                        "open_interest": 3_000,
                        "implied_volatility": 45.0,
                        "expiry_date": "2026-07-31",
                    },
                ]
            },
            events_by_code={
                "US.NVDA": [
                    {"event_type": "earnings", "event_date": "2026-07-29", "date_status": "estimated"}
                ]
            },
            failures_by_code={},
            fetched_at=self.fetched_at,
        )

    def _request(self, capability: SourceCapability, *, market: str = "US") -> DataRequest:
        return DataRequest(
            capability,
            market,
            ("US.NVDA",),
            start=date(2026, 7, 24),
            end=date(2026, 8, 7),
            freshness="end_of_day",
        )

    def test_one_provider_registers_all_crowding_capabilities(self) -> None:
        source = FutuCrowdingSource(loader=lambda codes, start, end: self._snapshot())
        self.assertEqual("futu_crowding", source.descriptor.source_id)
        self.assertEqual(
            {
                SourceCapability.OWNERSHIP_CONCENTRATION,
                SourceCapability.SHORT_INTEREST,
                SourceCapability.OPTIONS_POSITIONING,
                SourceCapability.EVENT_CALENDAR,
            },
            set(source.descriptor.capabilities),
        )
        pool = default_crowding_source_pool(loader=lambda codes, start, end: self._snapshot())
        result = pool.fetch(
            self._request(SourceCapability.SHORT_INTEREST),
            source_plan(SourceCapability.SHORT_INTEREST),
        )
        self.assertIs(result.status, DataStatus.OK)

    def test_source_normalizes_each_semantic_family(self) -> None:
        source = FutuCrowdingSource(loader=lambda codes, start, end: self._snapshot())
        expected = {
            SourceCapability.OWNERSHIP_CONCENTRATION: ("ownership_top_holders_pct", 61.0),
            SourceCapability.SHORT_INTEREST: ("short_percent", 3.2),
            SourceCapability.OPTIONS_POSITIONING: ("options_open_interest", 8_000.0),
            SourceCapability.EVENT_CALENDAR: ("earnings_event", "2026-07-29"),
        }
        for capability, (metric, value) in expected.items():
            with self.subTest(capability=capability):
                result = source.fetch(self._request(capability))
                self.assertIs(result.status, DataStatus.OK)
                self.assertEqual("futu_crowding", result.selected_source)
                self.assertEqual(metric, result.records[0]["metric"])
                self.assertEqual(value, result.records[0]["value"])
                self.assertEqual("account_entitled", result.records[0]["access_tier"])

    def test_source_returns_typed_unavailable_for_family_failure_without_detail(self) -> None:
        snapshot = self._snapshot()
        failed = FutuCrowdingSnapshot(
            ownership_by_code={},
            short_interest_by_code=snapshot.short_interest_by_code,
            options_by_code=snapshot.options_by_code,
            events_by_code=snapshot.events_by_code,
            failures_by_code={"US.NVDA": {"ownership": "provider_unavailable"}},
            fetched_at=self.fetched_at,
        )
        result = FutuCrowdingSource(loader=lambda codes, start, end: failed).fetch(
            self._request(SourceCapability.OWNERSHIP_CONCENTRATION)
        )
        self.assertIs(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual("provider_unavailable", result.failures[0].code)
        self.assertIsNone(result.failures[0].detail)

    def test_source_rejects_unsupported_market_without_calling_loader(self) -> None:
        called = False

        def loader(codes: list[str], start: str, end: str) -> FutuCrowdingSnapshot:
            nonlocal called
            called = True
            return self._snapshot()

        result = FutuCrowdingSource(loader=loader).fetch(
            DataRequest(
                SourceCapability.SHORT_INTEREST,
                "KR",
                ("KR.000660",),
                start=date(2026, 7, 24),
                end=date(2026, 8, 7),
                freshness="end_of_day",
            )
        )
        self.assertIs(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual("unsupported_market", result.failures[0].code)
        self.assertFalse(called)


def source_plan(capability: SourceCapability):
    from investment_knowledge_mcp.data_sources.contracts import SourcePlan

    return SourcePlan(
        capability,
        ("futu_crowding",),
        ("futu_crowding",),
        (),
        False,
        True,
    )
