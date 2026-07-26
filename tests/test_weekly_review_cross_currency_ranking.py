from __future__ import annotations

from unittest import TestCase

from investment_knowledge_mcp.weekly_review import _top_blowups, _top_highlights


class WeeklyReviewCrossCurrencyRankingTests(TestCase):
    def test_highlights_rank_interval_profit_in_usd_not_raw_local_amount(self) -> None:
        position_changes = [
            {
                "code": "HK.00001",
                "name": "HK winner",
                "currency": "HKD",
                "period_pl": 1_800.0,
                "pl_val_delta": 1_800.0,
                "current_pl_val": 1_800.0,
                "movement": "持仓未变",
                "confidence": "高",
            },
            {
                "code": "US.WIN",
                "name": "US winner",
                "currency": "USD",
                "period_pl": 500.0,
                "pl_val_delta": 500.0,
                "current_pl_val": 500.0,
                "movement": "持仓未变",
                "confidence": "高",
            },
        ]

        highlights = _top_highlights(position_changes)

        self.assertEqual(["US.WIN", "HK.00001"], [item["code"] for item in highlights])
        self.assertEqual(500.0, highlights[0]["ranking_amount_usd"])
        self.assertAlmostEqual(1_800.0 / 7.8, highlights[1]["ranking_amount_usd"])

    def test_blowups_exclude_immaterial_weekly_moves(self) -> None:
        position_changes = [
            {
                "code": "US.TSLA",
                "name": "Tesla",
                "currency": "USD",
                "period_pl": -8.83,
                "pl_val_delta": -4.28,
                "current_pl_val": 10.02,
                "movement": "减仓",
                "confidence": "中",
                "start": {"market_val": 1_525.0},
            },
            {
                "code": "HK.02367",
                "name": "Giant Biogene",
                "currency": "HKD",
                "period_pl": -36.0,
                "pl_val_delta": -36.0,
                "current_pl_val": -2_634.36,
                "movement": "持仓未变",
                "confidence": "高",
                "start": {"market_val": 17_400.0},
            },
        ]

        self.assertEqual([], _top_blowups(position_changes))

    def test_blowups_require_material_amount_and_position_impact(self) -> None:
        position_changes = [
            {
                "code": "HK.02476",
                "name": "Shenghong Technology",
                "currency": "HKD",
                "period_pl": -4_000.0,
                "pl_val_delta": -4_000.0,
                "current_pl_val": -8_440.0,
                "movement": "持仓未变",
                "confidence": "高",
                "start": {"market_val": 30_000.0},
            },
            {
                "code": "US.MINOR",
                "name": "Minor move",
                "currency": "USD",
                "period_pl": -70.0,
                "pl_val_delta": -70.0,
                "current_pl_val": -70.0,
                "movement": "持仓未变",
                "confidence": "高",
                "start": {"market_val": 20_000.0},
            },
            {
                "code": "US.EXIT",
                "name": "Exited holding",
                "currency": "USD",
                "period_pl": -600.0,
                "pl_val_delta": -600.0,
                "current_pl_val": 0.0,
                "movement": "清仓",
                "confidence": "高",
                "start": None,
            },
        ]

        blowups = _top_blowups(position_changes)

        self.assertEqual(["US.EXIT", "HK.02476"], [item["code"] for item in blowups])
