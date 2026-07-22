from __future__ import annotations

import unittest

from investment_knowledge_mcp.weekly_review import _build_holder_attribution, render_weekly_review_markdown
from investment_knowledge_mcp.weekly_review_web import render_weekly_review_script, render_weekly_review_workbench_html


def _shenghong_position() -> dict:
    return {
        "code": "HK.02476",
        "market": "HK",
        "symbol": "02476",
        "name": "胜宏科技",
        "currency": "HKD",
        "start": {"qty": 1000, "pl_val": 12000, "market_val": 44000},
        "end": {"qty": 1000, "pl_val": 5080, "market_val": 37080},
        "qty_delta": 0,
        "current_market_val": 37080,
        "current_pl_val": 5080,
        "current_pl_ratio": 0.12,
        "pl_val_delta": -6920,
        "period_pl": -6920,
        "movement": "持仓未变",
        "confidence": "高",
        "themes": ["AI PCB/服务器供应链"],
        "knowledge_note": "AI PCB demand growth is the core thesis; margin tolerance still needs validation.",
        "knowledge_evidence": [
            {
                "source_type": "stock_insight",
                "id": 2476,
                "code": "HK.02476",
                "name": "胜宏科技",
                "summary": "AI PCB demand growth is the core thesis; margin pressure is a watch item.",
                "citation": "stock_insight:2476",
            }
        ],
        "trade_summary": {
            "code": "HK.02476",
            "currency": "HKD",
            "count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "buy_amount": 0,
            "sell_amount": 0,
            "records": [],
        },
    }


def _base_inputs(events: list[dict] | None = None, knowledge: list[dict] | None = None) -> dict:
    position = _shenghong_position()
    return {
        "position_changes": [position],
        "highlights": [],
        "blowups": [
            {
                "code": "HK.02476",
                "name": "胜宏科技",
                "currency": "HKD",
                "amount": -6920,
                "movement": "持仓未变",
                "confidence": "高",
            }
        ],
        "holdings_table": [
            {
                "code": "HK.02476",
                "name": "胜宏科技",
                "currency": "HKD",
                "market": "HK",
                "market_val": 37080,
                "status": "核心持仓、本周拖累",
            }
        ],
        "event_summary": events or [],
        "index_summary": [],
        "knowledge_evidence": knowledge if knowledge is not None else position["knowledge_evidence"],
        "trades_by_code": {"HK.02476": position["trade_summary"]},
        "source_status": {
            "events": {"status": "partial", "count": len(events or [])},
            "local_knowledge": {"status": "ok", "count": 1},
        },
    }


class WeeklyReviewHolderAttributionTests(unittest.TestCase):
    def test_shenghong_fixture_separates_rumor_and_cost_candidates(self) -> None:
        events = [
            {
                "category": "manual_market_discussion",
                "code": "HK.02476",
                "name": "胜宏科技",
                "source_name": "Xueqiu manual source",
                "source_type": "social_rumor",
                "source_id": "fixture:xueqiu:02476-q2-miss",
                "published_at": "2026-06-30",
                "title": "Q2 performance miss rumor discussed by market participants",
                "summary": "Unverified Xueqiu-style discussion claims Q2 performance may miss expectations.",
                "url": "https://example.test/xueqiu/02476-q2-miss",
                "freshness": "review_week",
                "citation": "fixture:xueqiu:02476-q2-miss",
            },
            {
                "category": "dated_industry_news",
                "code": "HK.02476",
                "name": "胜宏科技",
                "source_name": "PCB industry source",
                "source_type": "news_or_industry",
                "source_id": "fixture:industry:pcb-cost-pressure",
                "published_at": "2026-06-30",
                "title": "Upstream copper and laminate cost inflation pressure for PCB supply chain",
                "summary": "Industry source notes upstream copper, laminate, and fiberglass cost inflation may pressure PCB margins.",
                "url": "https://example.test/industry/pcb-cost-pressure",
                "freshness": "review_week",
                "citation": "fixture:industry:pcb-cost-pressure",
            },
        ]
        cards = _build_holder_attribution(**_base_inputs(events=events))

        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["code"], "HK.02476")
        candidates = card["cause_candidates"]
        rumor = next(candidate for candidate in candidates if candidate["source_type"] == "social_rumor")
        cost = next(candidate for candidate in candidates if candidate["lens"] == "fundamentals_cost_drivers")

        self.assertEqual(rumor["confidence"], "rumor_watch")
        self.assertEqual(rumor["thesis_impact"], "needs_research")
        self.assertIn("Unverified", rumor["claim"])
        self.assertEqual(cost["source_type"], "news_or_industry")
        self.assertEqual(cost["confidence"], "medium")
        self.assertEqual(cost["thesis_impact"], "challenges_thesis")
        self.assertNotEqual(rumor["title"], cost["title"])
        self.assertEqual(card["thesis_impact"], "challenges_thesis")

    def test_provider_missing_fallback_does_not_invent_external_cause(self) -> None:
        inputs = _base_inputs(events=[], knowledge=[])
        inputs["source_status"] = {
            "events": {"status": "source_blocked", "count": 0},
            "local_knowledge": {"status": "checked_empty", "count": 0},
        }
        cards = _build_holder_attribution(**inputs)

        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertTrue(card["no_supported_external_cause"])
        self.assertTrue(card["source_gaps"])
        self.assertFalse(any(candidate["lens"] == "single_stock_event" for candidate in card["cause_candidates"]))
        self.assertFalse(any(candidate["lens"] == "fundamentals_cost_drivers" for candidate in card["cause_candidates"]))

    def test_markdown_and_web_render_attribution_surfaces(self) -> None:
        cards = _build_holder_attribution(**_base_inputs(events=[]))
        markdown = render_weekly_review_markdown(
            {
                "period": {"label": "2026-06-29 至 2026-07-05"},
                "highlights": [],
                "blowups": [],
                "index_summary": [],
                "source_status": {},
                "story": {},
                "next_week": [],
                "holdings_table": [],
                "holder_attribution": cards,
                "warnings": [],
            }
        )
        html = render_weekly_review_workbench_html()

        self.assertIn("## 7. 持仓归因卡", markdown)
        self.assertIn("持仓归因卡：HK.02476 胜宏科技", markdown)
        self.assertIn("Source gaps:", markdown)
        self.assertIn('data-slot="attribution"', html)
        self.assertIn('<script src="/assets/weekly-review.js"></script>', html)
        self.assertIn("function attributionCards", render_weekly_review_script())


if __name__ == "__main__":
    unittest.main()
