from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

import pandas as pd

from investment_knowledge_mcp.config import AppConfig
from investment_knowledge_mcp.futu_provider import _fetch_futu_crowding_snapshot


class FakeQuoteContext:
    def __init__(self) -> None:
        self.closed = False

    def get_shareholders_overview(self, code: str, period_id: int = 0):
        return 0, {
            "main_holder": pd.DataFrame(
                [
                    {"name": "Holder A", "holder_pct": 40.0, "static_date_str": "2026-06-30"},
                    {"name": "Holder B", "holder_pct": 21.0, "static_date_str": "2026-06-30"},
                    {"name": "Other", "holder_pct": 39.0, "static_date_str": "2026-06-30"},
                ]
            ),
            "holder_type": pd.DataFrame(),
            "holding_period": pd.DataFrame(),
        }

    def get_short_interest(self, code: str):
        us = pd.DataFrame(
            [
                {
                    "shares_short": 30_000_000,
                    "short_percent": 3.2,
                    "days_to_cover": 1.8,
                    "timestamp_str": "2026-07-15",
                }
            ]
        )
        return 0, us, pd.DataFrame()

    def get_option_chain(self, code: str, start: str, end: str):
        return 0, pd.DataFrame(
            [
                {
                    "code": "US.NVDA260731C200000",
                    "option_type": "CALL",
                    "strike_time": "2026-07-31",
                    "strike_price": 200.0,
                    "lot_size": 100,
                },
                {
                    "code": "US.NVDA260731P180000",
                    "option_type": "PUT",
                    "strike_time": "2026-07-31",
                    "strike_price": 180.0,
                    "lot_size": 100,
                },
            ]
        )

    def get_market_snapshot(self, codes: list[str]):
        return 0, pd.DataFrame(
            [
                {
                    "code": codes[0],
                    "volume": 1_000,
                    "option_open_interest": 5_000,
                    "option_implied_volatility": 42.0,
                    "data_date": "2026-07-24",
                },
                {
                    "code": codes[1],
                    "volume": 600,
                    "option_open_interest": 3_000,
                    "option_implied_volatility": 45.0,
                    "data_date": "2026-07-24",
                },
            ]
        )

    def get_earnings_calendar(self, market: str, begin_date: str, end_date: str):
        return 0, pd.DataFrame(
            [
                {
                    "security": "US.NVDA",
                    "earnings_date": "2026-07-29",
                    "pub_type": "estimated",
                }
            ]
        )

    def close(self) -> None:
        self.closed = True


class FutuCrowdingTransportTests(TestCase):
    def test_transport_normalizes_supported_families_and_closes_context(self) -> None:
        context = FakeQuoteContext()
        ft = SimpleNamespace(RET_OK=0, Market=SimpleNamespace(US="US", HK="HK"))

        snapshot = _fetch_futu_crowding_snapshot(
            AppConfig(),
            ["US.NVDA"],
            "2026-07-24",
            "2026-08-07",
            futu_module=ft,
            context_factory=lambda **kwargs: context,
            now=lambda: datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(61.0, sum(row["holder_pct"] for row in snapshot.ownership_by_code["US.NVDA"]))
        self.assertEqual(100.0, snapshot.options_by_code["US.NVDA"][0]["contract_multiplier"])
        self.assertEqual(3.2, snapshot.short_interest_by_code["US.NVDA"][0]["short_percent"])
        self.assertEqual(5_000, snapshot.options_by_code["US.NVDA"][0]["open_interest"])
        self.assertEqual("2026-07-24", snapshot.options_by_code["US.NVDA"][0]["observed_at"])
        self.assertEqual("2026-07-29", snapshot.events_by_code["US.NVDA"][0]["event_date"])
        self.assertEqual({}, snapshot.failures_by_code)
        self.assertTrue(context.closed)

    def test_one_family_failure_is_isolated_and_raw_error_is_not_retained(self) -> None:
        class PartialContext(FakeQuoteContext):
            def get_shareholders_overview(self, code: str, period_id: int = 0):
                raise RuntimeError("authorization token=secret")

        context = PartialContext()
        ft = SimpleNamespace(RET_OK=0, Market=SimpleNamespace(US="US", HK="HK"))
        snapshot = _fetch_futu_crowding_snapshot(
            AppConfig(),
            ["US.NVDA"],
            "2026-07-24",
            "2026-08-07",
            futu_module=ft,
            context_factory=lambda **kwargs: context,
        )

        self.assertEqual("provider_unavailable", snapshot.failures_by_code["US.NVDA"]["ownership"])
        self.assertIn("US.NVDA", snapshot.short_interest_by_code)
        self.assertNotIn("secret", repr(snapshot))
        self.assertTrue(context.closed)

    def test_entitlement_failure_is_typed_without_retaining_provider_text(self) -> None:
        class EntitlementContext(FakeQuoteContext):
            def get_short_interest(self, code: str):
                return -1, "No right: token=secret", None

        snapshot = _fetch_futu_crowding_snapshot(
            AppConfig(),
            ["US.NVDA"],
            "2026-07-24",
            "2026-08-07",
            futu_module=SimpleNamespace(
                RET_OK=0,
                Market=SimpleNamespace(US="US", HK="HK"),
            ),
            context_factory=lambda **kwargs: EntitlementContext(),
        )

        self.assertEqual(
            "entitlement_required",
            snapshot.failures_by_code["US.NVDA"]["short_interest"],
        )
        self.assertNotIn("token", repr(snapshot))

    def test_large_option_chain_is_nearest_expiry_bounded_and_marked_partial(self) -> None:
        class LargeChainContext(FakeQuoteContext):
            def get_option_chain(self, code: str, start: str, end: str):
                rows = []
                for index in range(201):
                    rows.append(
                        {
                            "code": f"US.NVDA{index:06d}",
                            "option_type": "CALL" if index % 2 == 0 else "PUT",
                            "strike_time": "2026-08-07" if index < 101 else "2026-07-31",
                            "strike_price": 100.0 + index,
                            "lot_size": 100,
                        }
                    )
                return 0, pd.DataFrame(rows)

            def get_market_snapshot(self, codes: list[str]):
                return 0, pd.DataFrame(
                    [
                        {
                            "code": code,
                            "volume": 10,
                            "option_open_interest": 20,
                            "option_implied_volatility": 40.0,
                            "data_date": "2026-07-24",
                        }
                        for code in codes
                    ]
                )

        snapshot = _fetch_futu_crowding_snapshot(
            AppConfig(),
            ["US.NVDA"],
            "2026-07-24",
            "2026-08-07",
            futu_module=SimpleNamespace(
                RET_OK=0,
                Market=SimpleNamespace(US="US", HK="HK"),
            ),
            context_factory=lambda **kwargs: LargeChainContext(),
        )

        rows = snapshot.options_by_code["US.NVDA"]
        self.assertEqual(200, len(rows))
        self.assertEqual("2026-07-31", rows[0]["expiry_date"])
        self.assertEqual(
            "option_chain_truncated",
            snapshot.failures_by_code["US.NVDA"]["options"],
        )
        self.assertAlmostEqual(
            200 / 201,
            snapshot.coverage_by_code["US.NVDA"]["options"],
        )

    def test_transport_rejects_non_us_hk_symbols_before_context_creation(self) -> None:
        created = False

        def factory(**kwargs):
            nonlocal created
            created = True
            return FakeQuoteContext()

        with self.assertRaises(ValueError):
            _fetch_futu_crowding_snapshot(
                AppConfig(),
                ["KR.000660"],
                "2026-07-24",
                "2026-08-07",
                futu_module=SimpleNamespace(RET_OK=0),
                context_factory=factory,
            )
        self.assertFalse(created)
