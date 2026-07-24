from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from unittest import TestCase

from investment_knowledge_mcp.data_sources.crowding import (
    FUTU_CROWDING_APPROVAL,
    FutuCrowdingSource,
    SourceApproval,
    default_crowding_source_pool,
    source_is_approved,
    source_runtime_is_enabled,
)
from investment_knowledge_mcp.data_sources.contracts import (
    DataRequest,
    DataStatus,
    SourceCapability,
)
from investment_knowledge_mcp.futu_provider import FutuCrowdingSnapshot


def complete_approval() -> SourceApproval:
    return SourceApproval(
        source_id="futu_crowding",
        access_tier="account_entitled",
        permitted_uses=("private_internal_research",),
        redistribution_allowed=False,
        enabled_markets=("US", "HK"),
        runtime_activation_env="FUTU_CROWDING_PRIVATE_USE_APPROVED",
        approved_environments=("production",),
        credential_owner="operations",
        approved_rights=(
            "internal_display",
            "derived_results",
            "storage",
            "retention",
        ),
        retention_policy="retain derived results for 30 days",
        expires_on=date(2099, 12, 31),
        legal_review_reference="LEGAL-TEST-001",
        approved_capabilities=(
            SourceCapability.OWNERSHIP_CONCENTRATION,
            SourceCapability.SHORT_INTEREST,
            SourceCapability.OPTIONS_POSITIONING,
            SourceCapability.EVENT_CALENDAR,
        ),
    )


class CrowdingSourceApprovalTests(TestCase):
    def test_futu_register_is_private_internal_non_redistributable_and_incomplete(self) -> None:
        self.assertFalse(source_is_approved("futu_crowding", "private_internal_research"))
        self.assertFalse(source_is_approved("futu_crowding", "public_redistribution"))
        self.assertEqual("account_entitled", FUTU_CROWDING_APPROVAL.access_tier)
        self.assertFalse(FUTU_CROWDING_APPROVAL.redistribution_allowed)
        self.assertEqual(("US", "HK"), FUTU_CROWDING_APPROVAL.enabled_markets)
        self.assertEqual((), FUTU_CROWDING_APPROVAL.approved_environments)
        self.assertIsNone(FUTU_CROWDING_APPROVAL.credential_owner)
        self.assertEqual((), FUTU_CROWDING_APPROVAL.approved_capabilities)
        self.assertEqual(
            "FUTU_CROWDING_PRIVATE_USE_APPROVED",
            FUTU_CROWDING_APPROVAL.runtime_activation_env,
        )
        self.assertFalse(source_runtime_is_enabled(FUTU_CROWDING_APPROVAL, environ={}))
        self.assertFalse(
            source_runtime_is_enabled(
                FUTU_CROWDING_APPROVAL,
                environ={"FUTU_CROWDING_PRIVATE_USE_APPROVED": "approved"},
            )
        )

    def test_complete_register_and_runtime_switch_are_both_required(self) -> None:
        approval = complete_approval()

        self.assertFalse(source_runtime_is_enabled(approval, environ={}))
        self.assertTrue(
            source_runtime_is_enabled(
                approval,
                environ={
                    "CROWDING_RUNTIME_ENVIRONMENT": "production",
                    "FUTU_CROWDING_PRIVATE_USE_APPROVED": "approved",
                },
            )
        )
        self.assertFalse(
            source_runtime_is_enabled(
                approval,
                environ={
                    "CROWDING_RUNTIME_ENVIRONMENT": "development",
                    "FUTU_CROWDING_PRIVATE_USE_APPROVED": "approved",
                },
            )
        )

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
                        "contract_multiplier": 100.0,
                        "observed_at": "2026-07-24",
                    },
                    {
                        "option_type": "PUT",
                        "volume": 600,
                        "open_interest": 3_000,
                        "implied_volatility": 45.0,
                        "expiry_date": "2026-07-31",
                        "contract_multiplier": 100.0,
                        "observed_at": "2026-07-24",
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
        source = FutuCrowdingSource(
            loader=lambda codes, start, end: self._snapshot(),
            runtime_approved=lambda: True,
            approval=complete_approval(),
        )
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
        pool = default_crowding_source_pool(
            loader=lambda codes, start, end: self._snapshot(),
            runtime_approved=lambda: True,
            approval=complete_approval(),
        )
        result = pool.fetch(
            self._request(SourceCapability.SHORT_INTEREST),
            source_plan(SourceCapability.SHORT_INTEREST),
        )
        self.assertIs(result.status, DataStatus.OK)

    def test_source_normalizes_each_semantic_family(self) -> None:
        source = FutuCrowdingSource(
            loader=lambda codes, start, end: self._snapshot(),
            runtime_approved=lambda: True,
            approval=complete_approval(),
        )
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
                self.assertNotIn("published_at", result.records[0])
                if capability is SourceCapability.OPTIONS_POSITIONING:
                    self.assertEqual(
                        800_000.0,
                        result.records[0]["metadata"]["underlying_equivalent_open_interest"],
                    )

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
        result = FutuCrowdingSource(
            loader=lambda codes, start, end: failed,
            runtime_approved=lambda: True,
            approval=complete_approval(),
        ).fetch(
            self._request(SourceCapability.OWNERSHIP_CONCENTRATION)
        )
        self.assertIs(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual("provider_unavailable", result.failures[0].code)
        self.assertIsNone(result.failures[0].detail)

    def test_truncated_option_chain_returns_partial_with_measured_coverage(self) -> None:
        snapshot = self._snapshot()
        partial = FutuCrowdingSnapshot(
            ownership_by_code=snapshot.ownership_by_code,
            short_interest_by_code=snapshot.short_interest_by_code,
            options_by_code=snapshot.options_by_code,
            events_by_code=snapshot.events_by_code,
            failures_by_code={"US.NVDA": {"options": "option_chain_truncated"}},
            fetched_at=self.fetched_at,
            coverage_by_code={"US.NVDA": {"options": 0.8}},
        )

        result = FutuCrowdingSource(
            loader=lambda codes, start, end: partial,
            runtime_approved=lambda: True,
            approval=complete_approval(),
        ).fetch(self._request(SourceCapability.OPTIONS_POSITIONING))

        self.assertIs(result.status, DataStatus.PARTIAL)
        self.assertEqual(0.8, result.coverage)
        self.assertEqual("option_chain_truncated", result.failures[0].code)

    def test_source_rejects_unsupported_market_without_calling_loader(self) -> None:
        called = False

        def loader(codes: list[str], start: str, end: str) -> FutuCrowdingSnapshot:
            nonlocal called
            called = True
            return self._snapshot()

        result = FutuCrowdingSource(
            loader=loader,
            runtime_approved=lambda: True,
            approval=complete_approval(),
        ).fetch(
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

    def test_bundle_requires_all_capabilities_and_rejects_unapproved_market(self) -> None:
        approval = complete_approval()
        us_short_only = replace(
            approval,
            enabled_markets=("US",),
            approved_capabilities=(SourceCapability.SHORT_INTEREST,),
        )
        source = FutuCrowdingSource(
            loader=lambda codes, start, end: self._snapshot(),
            runtime_approved=lambda: True,
            approval=us_short_only,
        )

        self.assertFalse(
            source_runtime_is_enabled(
                us_short_only,
                environ={
                    "CROWDING_RUNTIME_ENVIRONMENT": "production",
                    "FUTU_CROWDING_PRIVATE_USE_APPROVED": "approved",
                },
            )
        )
        hk_request = DataRequest(
            SourceCapability.SHORT_INTEREST,
            "HK",
            ("HK.00700",),
            start=date(2026, 7, 24),
            end=date(2026, 8, 7),
            freshness="end_of_day",
        )
        self.assertEqual(
            "approval_required",
            source.fetch(hk_request).failures[0].code,
        )
        self.assertEqual(
            "approval_required",
            source.fetch(
                self._request(SourceCapability.OPTIONS_POSITIONING)
            ).failures[0].code,
        )

    def test_runtime_approval_gate_blocks_loader_with_explicit_code(self) -> None:
        called = False

        def loader(codes: list[str], start: str, end: str) -> FutuCrowdingSnapshot:
            nonlocal called
            called = True
            return self._snapshot()

        result = FutuCrowdingSource(
            loader=loader,
            runtime_approved=lambda: False,
            approval=complete_approval(),
        ).fetch(self._request(SourceCapability.SHORT_INTEREST))

        self.assertIs(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual("approval_required", result.failures[0].code)
        self.assertFalse(called)

    def test_environment_switch_cannot_bypass_incomplete_approval_register(self) -> None:
        called = False

        def loader(codes: list[str], start: str, end: str) -> FutuCrowdingSnapshot:
            nonlocal called
            called = True
            return self._snapshot()

        result = FutuCrowdingSource(
            loader=loader,
            runtime_approved=lambda: True,
        ).fetch(self._request(SourceCapability.SHORT_INTEREST))

        self.assertIs(result.status, DataStatus.UNAVAILABLE)
        self.assertEqual("approval_required", result.failures[0].code)
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
