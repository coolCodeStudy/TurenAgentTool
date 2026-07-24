from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest import TestCase

from investment_knowledge_mcp.crowding_intelligence import (
    CrowdingBand,
    EvidenceDirection,
    EvidenceQuality,
    build_crowding_assessment,
    evidence_from_record,
    render_crowding_assessment,
)
from investment_knowledge_mcp.data_sources.contracts import (
    DataResult,
    DataStatus,
    ProviderFailure,
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
            "underlying_equivalent_open_interest": 800_000_000.0,
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
        options = next(item for item in assessment.families if item.name == "options")
        self.assertGreater(
            options.evidence[0].metadata["open_interest_to_underlying_volume"],
            200.0,
        )

    def test_missing_family_is_unknown_and_suppresses_only_affected_band(self) -> None:
        families = full_family_results()
        del families[SourceCapability.OWNERSHIP_CONCENTRATION]
        assessment = build_crowding_assessment("NVDA", "US", bars_result(), families, as_of=AS_OF)

        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)
        self.assertIsNone(assessment.long_crowding.score)
        self.assertIn("ownership", assessment.long_crowding.missing_families)
        self.assertNotEqual(CrowdingBand.INSUFFICIENT, assessment.short_squeeze.band)

    def test_evidence_quality_cannot_be_high_when_price_family_is_missing(self) -> None:
        assessment = build_crowding_assessment(
            "NVDA",
            "US",
            DataResult(
                DataStatus.UNAVAILABLE,
                (),
                None,
                ("futu",),
                0.0,
                FETCHED_AT,
                False,
                (),
            ),
            full_family_results(),
            as_of=AS_OF,
        )

        self.assertEqual(EvidenceQuality.INSUFFICIENT, assessment.evidence_quality)
        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)

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

    def test_future_evidence_is_rejected_from_historical_assessment(self) -> None:
        future = ownership_record(observed_at="2026-07-25")
        with self.assertRaises(ValueError):
            evidence_from_record(future, AS_OF)

    def test_later_fetch_is_provenance_not_lookahead_when_evidence_was_already_published(self) -> None:
        historical = ownership_record(observed_at="2026-06-30")
        historical["fetched_at"] = "2026-07-25T08:00:00+00:00"

        evidence = evidence_from_record(historical, AS_OF)

        self.assertEqual(date(2026, 6, 30), evidence.observed_at.date())
        self.assertIn("fetched_after_as_of", evidence.quality_flags)

    def test_unknown_publication_time_cannot_enter_historical_replay_after_fetch(self) -> None:
        historical = ownership_record(observed_at="2026-06-30")
        historical.pop("published_at")
        historical["fetched_at"] = "2026-07-25T08:00:00+00:00"

        with self.assertRaises(ValueError):
            evidence_from_record(historical, AS_OF)

    def test_future_market_bar_cannot_leak_into_historical_score(self) -> None:
        baseline_bars = bars_result()
        future_bar = {
            "date": "2026-07-25",
            "open": 1_000.0,
            "high": 1_100.0,
            "low": 900.0,
            "close": 1_050.0,
            "volume": 999_000_000,
        }
        leaked = DataResult(
            baseline_bars.status,
            (
                {
                    "symbol": "US.NVDA",
                    "bars": (*baseline_bars.records[0]["bars"], future_bar),
                },
            ),
            baseline_bars.selected_source,
            baseline_bars.attempted_sources,
            baseline_bars.coverage,
            baseline_bars.fetched_at,
            baseline_bars.from_cache,
            baseline_bars.failures,
        )

        baseline = build_crowding_assessment(
            "NVDA",
            "US",
            baseline_bars,
            full_family_results(),
            as_of=AS_OF,
        )
        replay = build_crowding_assessment(
            "NVDA",
            "US",
            leaked,
            full_family_results(),
            as_of=AS_OF,
        )

        baseline_price = next(item for item in baseline.families if item.name == "price_volume")
        replay_price = next(item for item in replay.families if item.name == "price_volume")
        self.assertEqual(baseline_price.score, replay_price.score)

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

    def test_falling_price_fragility_does_not_inflate_both_directional_bands(self) -> None:
        assessment = build_crowding_assessment(
            "NVDA",
            "US",
            bars_result(rising=False),
            full_family_results(),
            as_of=AS_OF,
        )

        price = next(item for item in assessment.families if item.name == "price_volume")
        self.assertEqual(EvidenceDirection.FRAGILITY, price.evidence[0].direction)
        self.assertNotEqual(CrowdingBand.HIGH, assessment.long_crowding.band)
        self.assertNotEqual(CrowdingBand.HIGH, assessment.short_squeeze.band)
        self.assertIn("price_volume", assessment.long_crowding.counterevidence)
        self.assertIn("price_volume", assessment.short_squeeze.counterevidence)

    def test_two_sided_option_oi_does_not_raise_signed_bands(self) -> None:
        families = full_family_results()
        families[SourceCapability.OWNERSHIP_CONCENTRATION] = result_for(
            ownership_record(value=0.0)
        )
        short = short_record()
        short["value"] = 0.0
        short["metadata"] = {"days_to_cover": 0.0}
        families[SourceCapability.SHORT_INTEREST] = result_for(short)
        assessment = build_crowding_assessment(
            "NVDA",
            "US",
            bars_result(rising=False),
            families,
            as_of=AS_OF,
        )

        self.assertEqual(CrowdingBand.LOW, assessment.long_crowding.band)
        self.assertEqual(CrowdingBand.LOW, assessment.short_squeeze.band)
        self.assertNotIn("options", assessment.long_crowding.contributors)
        self.assertNotIn("options", assessment.short_squeeze.contributors)

    def test_low_partial_option_coverage_suppresses_directional_bands_and_is_rendered(self) -> None:
        families = full_family_results()
        families[SourceCapability.OPTIONS_POSITIONING] = DataResult(
            DataStatus.PARTIAL,
            (options_record(),),
            "futu_crowding",
            ("futu_crowding",),
            0.01,
            FETCHED_AT,
            False,
            (
                ProviderFailure(
                    "option_chain_truncated",
                    "futu_crowding",
                    False,
                    False,
                ),
            ),
        )

        assessment = build_crowding_assessment(
            "NVDA",
            "US",
            bars_result(),
            families,
            as_of=AS_OF,
        )
        rendered = render_crowding_assessment(assessment)

        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)
        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.short_squeeze.band)
        options = next(item for item in assessment.families if item.name == "options")
        self.assertFalse(options.current)
        self.assertEqual(0.01, options.coverage)
        self.assertIn("coverage_below_threshold", options.quality_flags)
        self.assertIn("coverage=0.01", rendered)

    def test_low_partial_bar_coverage_suppresses_all_directional_bands(self) -> None:
        bars = bars_result()
        partial_bars = DataResult(
            DataStatus.PARTIAL,
            bars.records,
            bars.selected_source,
            bars.attempted_sources,
            0.01,
            bars.fetched_at,
            bars.from_cache,
            (
                ProviderFailure(
                    "partial_history",
                    "futu",
                    False,
                    False,
                ),
            ),
        )

        assessment = build_crowding_assessment(
            "NVDA",
            "US",
            partial_bars,
            full_family_results(),
            as_of=AS_OF,
        )

        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.long_crowding.band)
        self.assertEqual(CrowdingBand.INSUFFICIENT, assessment.short_squeeze.band)
        price = next(item for item in assessment.families if item.name == "price_volume")
        self.assertFalse(price.current)
        self.assertEqual(0.01, price.coverage)
        self.assertIn("coverage_below_threshold", price.quality_flags)

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
        self.assertIn("market=US", rendered)
        self.assertIn("published=2026-06-30", rendered)
        self.assertIn("use_tier=account_entitled", rendered)
        self.assertIn("不是投资建议", rendered)
        self.assertNotIn("应该买", rendered)
        self.assertNotIn("应该卖", rendered)
