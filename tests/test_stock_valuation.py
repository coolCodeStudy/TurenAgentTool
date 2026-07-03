from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from investment_knowledge_mcp.stock_valuation import (
    build_valuation_artifact,
    load_latest_valuation_artifact,
    render_valuation_card,
    render_valuation_methods,
)


class StockValuationTests(unittest.TestCase):
    def test_builds_deterministic_packet_and_artifact(self) -> None:
        context = {
            "stock": {
                "id": 7,
                "symbol": "TST",
                "market": "US",
                "name": "Test Valuation Inc.",
                "core_business": "AI platform with durable cash flow and TAM expansion.",
                "stock_character": "Growth company starting to convert growth into free cash flow.",
            },
            "stock_knowledge": [
                {
                    "id": 11,
                    "knowledge_type": "valuation_facts",
                    "content": (
                        "FY fixture: revenue=1000, net income=125, operating cash flow=210, capex=60, "
                        "cash=300, debt=100, price=25, shares outstanding=100, EBITDA=250, TAM=5000."
                    ),
                    "source_id": 31,
                    "confidence": 0.9,
                    "confirmed_by_user": True,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ],
            "stock_insights": [
                {
                    "id": 12,
                    "insight": "User confirmed valuation case: AI growth should be checked against FCF conversion.",
                }
            ],
            "sources": [
                {
                    "id": 31,
                    "source_type": "official_filing",
                    "title": "Fixture annual filing",
                    "published_at": "2026-01-01",
                }
            ],
            "sectors": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            packet, path = build_valuation_artifact(
                context,
                symbol="TST",
                market="US",
                output_dir=Path(tmp),
                command="valuation US.TST",
                now=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
            latest = load_latest_valuation_artifact(symbol="TST", market="US", output_dir=Path(tmp))

        self.assertTrue(path.name.startswith("TST_US_valuation_"))
        self.assertIsNotNone(latest)
        self.assertFalse(packet["safety"]["direct_investment_advice"])
        self.assertTrue(packet["assumptions"]["user_confirmed_valuation_case"])
        self.assertGreaterEqual(packet["source_coverage"]["official_source_count"], 1)
        calculations = {item["metric"]: item["value"] for item in packet["deterministic_calculations"]}
        self.assertEqual(calculations["free_cash_flow"], 150)
        self.assertEqual(calculations["market_cap"], 2500)
        self.assertEqual(calculations["enterprise_value"], 2300)
        self.assertEqual(calculations["pe"], 20)
        self.assertIn(packet["selected_frames"][0]["id"], {"fcf", "growth_scenario"})
        card = render_valuation_card(packet)
        self.assertIn("估值研究卡", card)
        self.assertIn("Deterministic calculations", card)

    def test_degrades_when_sources_and_market_data_are_missing(self) -> None:
        context = {
            "stock": {
                "id": 8,
                "symbol": "THIN",
                "market": "US",
                "name": "Thin Profile",
                "core_business": "Minimal profile initialized from Command Workbench.",
                "stock_character": "Needs research.",
            },
            "stock_knowledge": [],
            "stock_insights": [],
            "sources": [],
            "sectors": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            packet, _ = build_valuation_artifact(
                context,
                symbol="THIN",
                market="US",
                output_dir=Path(tmp),
                command="valuation US.THIN",
                now=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )

        self.assertTrue(packet["degraded_state"]["degraded"])
        self.assertIn("latest market price or market cap is missing", packet["degraded_state"]["reasons"])
        self.assertIn("no user-confirmed valuation case", packet["degraded_state"]["reasons"])
        self.assertEqual(packet["source_coverage"]["financial_fact_status"], "missing")

    def test_renders_method_library(self) -> None:
        text = render_valuation_methods()
        self.assertIn("Free Cash Flow", text)
        self.assertIn("Comparable Multiples", text)
        self.assertIn("Growth / Scenario", text)


if __name__ == "__main__":
    unittest.main()
