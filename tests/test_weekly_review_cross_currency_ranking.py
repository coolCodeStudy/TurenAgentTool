from __future__ import annotations

from unittest import TestCase

from investment_knowledge_mcp.weekly_review import _top_highlights


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
