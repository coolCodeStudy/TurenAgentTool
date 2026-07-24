from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest import TestCase

from investment_knowledge_mcp.crowding_intelligence import (
    CrowdingBand,
    EvidenceDirection,
    build_crowding_assessment,
    evidence_from_record,
    render_crowding_assessment,
)
from investment_knowledge_mcp.data_sources.contracts import (
    DataResult,
    DataStatus,
    SourceCapability,
)


AS_OF = date(2026, 7, 24)
FETCHED_AT = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def result_for(record: dict[str, object], source: str = "futu_crowding") -> DataResult:
    return DataResult(DataStatus.OK, (record,), source, (source,), 1.0, FETCHED_AT, False, ())


def bars_result(*, count: int = 160, rising: bool = True) -> DataResult:
    start = AS_OF - timedelta(days=count - 1)
    bars = []
    for index in range(count):
        close = 100.0 + (index * 0.8 if rising else index * -0.2)
        bars.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.4,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000 + index * 15_000,
            }
        )
    return DataResult(
        DataStatus.OK,
        ({"symbol": "US.NVDA", "bars": tuple(bars)},),
        "futu",
        ("futu",),
        1.0,
        FETCHED_AT,
        False,
        (),
    )


def ownership_record(*, observed_at: str = "2026-06-30", value: float = 61.0) -> dict[str, object]:
    return {
        "symbol": "US.NVDA",
        "market": "US",
        "family": "ownership",
        "metric": "ownership_top_holders_pct",
        "value": value,
        "unit": "percent",
        "direction": "long",
        "observed_at": observed_at,
        "published_at": observed_at,
        "fetched_at": FETCHED_AT.isoformat(),
        "source_id": "futu_crowding",
        "provider": "futu",
        "access_tier": "account_entitled",
        "freshness": "end_of_day",
        "cohort": "reported_top_holders",
        "metadata": {"holder_count": 10},
    }


def short_record(*, metric: str = "short_percent") -> dict[str, object]:
    return {
        "symbol": "US.NVDA",
        "market": "US",
        "family": "short_interest",
        "metric": metric,
        "value": 12.0,
        "unit": "percent",
        "direction": "short",
        "observed_at": "2026-07-15",
        "published_at": "2026-07-15",
        "fetched_at": FETCHED_AT.isoformat(),
        "source_id": "futu_crowding",
        "provider": "futu",
        "access_tier": "account_entitled",
        "freshness": "end_of_day",
        "cohort": "provider_reported_outstanding_short",
        "metadata": {"days_to_cover": 4.0},
    }


def options_record() -> dict[str, object]:
    return {
        "symbol": "US.NVDA",
        "market": "US",
        "family": "options",
        "metric": "options_open_interest",
        "value": 8_000_000.0,
        "unit": "contracts",
        "direction": "two_sided",
        "observed_at": "2026-07-24",
        "published_at": "2026-07-24",
        "fetched_at": FETCHED_AT.isoformat(),
        "source_id": "futu_crowding",
        "provider": "futu",
        "access_tier": "account_entitled",
        "freshness": "end_of_day",
        "cohort": "listed_chain_near_expiries",
        "metadata": {
            "total_volume": 2_000_000.0,
            "call_open_interest_ratio": 0.72,
            "call_volume_ratio": 0.70,
            "expiry_concentration": 0.62,
        },
    }


def event_record() -> dict[str, object]:
    return {
        "symbol": "US.NVDA",
        "market": "US",
        "family": "events",
        "metric": "earnings_event",
        "value": "2026-07-29",
        "unit": "date",
        "direction": "context",
        "observed_at": "2026-07-24",
        "published_at": "2026-07-24",
        "fetched_at": FETCHED_AT.isoformat(),
        "source_id": "futu_crowding",
        "provider": "futu",
        "access_tier": "account_entitled",
        "freshness": "end_of_day",
        "cohort": "issuer_event_calendar",
        "metadata": {"date_status": "estimated"},
    }


def full_family_results() -> dict[SourceCapability, DataResult]:
    return {
        SourceCapability.OWNERSHIP_CONCENTRATION: result_for(ownership_record()),
        SourceCapability.SHORT_INTEREST: result_for(short_record()),
        SourceCapability.OPTIONS_POSITIONING: result_for(options_record()),
        SourceCapability.EVENT_CALENDAR: result_for(event_record()),
    }


class CrowdingIntelligenceTests(TestCase):
    def test_full_us_evidence_produces_separate_long_and_short_bands(self) -> None:
        assessment = build_crowding_assessment(
            "NVDA",
            "US",
            bars_result(),
            full_family_results(),
            as_of=AS_OF,
        )

        self.assertNotEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)
        self.assertNotEqual(CrowdingBand.INSUFFICIENT, assessment.short_squeeze.band)
        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.speculative_attention.band)
        self.assertEqual("US.NVDA", assessment.canonical)
        self.assertEqual("2026-07-29", assessment.next_event)
        self.assertIn("attention", assessment.speculative_attention.missing_families)

    def test_missing_family_is_unknown_and_suppresses_only_affected_band(self) -> None:
        families = full_family_results()
        del families[SourceCapability.OWNERSHIP_CONCENTRATION]
        assessment = build_crowding_assessment("NVDA", "US", bars_result(), families, as_of=AS_OF)

        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)
        self.assertIsNone(assessment.long_crowding.score)
        self.assertIn("ownership", assessment.long_crowding.missing_families)
        self.assertNotEqual(CrowdingBand.INSUFFICIENT, assessment.short_squeeze.band)

    def test_stale_ownership_is_not_counted_as_current(self) -> None:
        families = full_family_results()
        families[SourceCapability.OWNERSHIP_CONCENTRATION] = result_for(
            ownership_record(observed_at="2025-12-31")
        )
        assessment = build_crowding_assessment("NVDA", "US", bars_result(), families, as_of=AS_OF)

        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)
        ownership = next(item for item in assessment.families if item.name == "ownership")
        self.assertFalse(ownership.current)
        self.assertIn("stale", ownership.quality_flags)

    def test_kr_and_cn_never_receive_aggregate_band(self) -> None:
        for market in ("KR", "CN"):
            with self.subTest(market=market):
                assessment = build_crowding_assessment(
                    "000660",
                    market,
                    bars_result(),
                    full_family_results(),
                    as_of=AS_OF,
                )
                self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)
                self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.short_squeeze.band)

    def test_short_sale_volume_cannot_masquerade_as_short_interest(self) -> None:
        with self.assertRaises(ValueError):
            evidence_from_record(short_record(metric="short_sale_volume"), AS_OF)

    def test_valuation_record_is_ignored_and_cannot_create_a_band(self) -> None:
        valuation = result_for(
            {
                **ownership_record(),
                "family": "valuation",
                "metric": "pe_ratio",
                "value": 1_000.0,
                "direction": "context",
            }
        )
        assessment = build_crowding_assessment(
            "NVDA",
            "US",
            bars_result(count=20),
            {SourceCapability.MARKET_SNAPSHOT: valuation},
            as_of=AS_OF,
        )
        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)
        self.assertNotIn("valuation", {item.name for item in assessment.families})

    def test_renderer_is_evidence_first_and_contains_safety_boundary(self) -> None:
        assessment = build_crowding_assessment(
            "NVDA",
            "US",
            bars_result(),
            full_family_results(),
            as_of=AS_OF,
        )
        rendered = render_crowding_assessment(assessment)

        self.assertIn("US.NVDA", rendered)
        self.assertIn("多头拥挤", rendered)
        self.assertIn("空头拥挤 / 挤压压力", rendered)
        self.assertIn("futu_crowding", rendered)
        self.assertIn("reported_top_holders", rendered)
        self.assertIn("不是投资建议", rendered)
        self.assertNotIn("应该买", rendered)
        self.assertNotIn("应该卖", rendered)
