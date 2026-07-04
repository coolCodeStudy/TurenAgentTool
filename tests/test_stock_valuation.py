from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from investment_knowledge_mcp.command_router import handle_command
from investment_knowledge_mcp.command_workbench import parse_workbench_command
from investment_knowledge_mcp.stock_valuation import (
    build_valuation_artifact,
    load_latest_valuation_artifact,
    render_valuation_card,
    render_valuation_methods,
)
from investment_knowledge_mcp.valuation_data_provider import fetch_provider_snapshot


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

    def test_fetches_us_provider_snapshot_from_sec_and_yahoo(self) -> None:
        company_tickers = {
            "0": {"ticker": "INTC", "cik_str": 50863, "title": "Intel Corporation"},
        }
        company_facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-01-26", "end": "2025-12-27", "val": 54000000000}
                            ]
                        }
                    },
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-01-26", "end": "2025-12-27", "val": 4200000000}
                            ]
                        }
                    },
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-01-26", "end": "2025-12-27", "val": 11200000000}
                            ]
                        }
                    },
                    "PaymentsToAcquirePropertyPlantAndEquipment": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-01-26", "end": "2025-12-27", "val": 6800000000}
                            ]
                        }
                    },
                    "CashAndCashEquivalentsAtCarryingValue": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-01-26", "end": "2025-12-27", "val": 8500000000}
                            ]
                        }
                    },
                    "LongTermDebtAndFinanceLeaseObligations": {
                        "units": {
                            "USD": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-01-26", "end": "2025-12-27", "val": 28500000000}
                            ]
                        }
                    },
                }
                ,
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {"form": "10-K", "fy": 2025, "fp": "FY", "filed": "2026-01-26", "end": "2025-12-27", "val": 4400000000}
                            ]
                        }
                    }
                }
            }
        }
        yahoo_quote = {
            "quoteResponse": {
                "result": [
                    {
                        "regularMarketPrice": 31.5,
                        "marketCap": 138600000000,
                        "sharesOutstanding": 4400000000,
                        "currency": "USD",
                        "regularMarketTime": 1783123200,
                    }
                ]
            }
        }

        def fake_get_json(url: str, **_: object) -> dict:
            if url.endswith("/company_tickers.json"):
                return company_tickers
            if url.endswith("/CIK0000050863.json"):
                return company_facts
            if "query1.finance.yahoo.com" in url:
                return yahoo_quote
            raise AssertionError(f"unexpected URL {url}")

        with patch("investment_knowledge_mcp.valuation_data_provider._get_json", side_effect=fake_get_json):
            snapshot = fetch_provider_snapshot("INTC", "US")

        facts = {fact["metric"]: fact["value"] for fact in snapshot["facts"]}
        self.assertEqual(facts["revenue"], 54000000000)
        self.assertEqual(facts["net_income"], 4200000000)
        self.assertEqual(facts["operating_cash_flow"], 11200000000)
        self.assertEqual(facts["capex"], 6800000000)
        self.assertEqual(facts["cash"], 8500000000)
        self.assertEqual(facts["debt"], 28500000000)
        self.assertEqual(facts["price"], 31.5)
        self.assertEqual(facts["market_cap"], 138600000000)
        self.assertEqual(facts["shares_outstanding"], 4400000000)
        self.assertEqual(snapshot["financial_fact_status"], "present")
        self.assertEqual(snapshot["market_snapshot_status"], "present")
        self.assertGreaterEqual(len(snapshot["sources"]), 2)
        self.assertEqual(snapshot["errors"], [])

    def test_provider_snapshot_enriches_valuation_packet(self) -> None:
        context = {
            "stock": {
                "id": 9,
                "symbol": "INTC",
                "market": "US",
                "name": "Intel Corporation",
                "core_business": "Semiconductor company with manufacturing cycle exposure.",
                "stock_character": "Cyclical semiconductor turnaround.",
            },
            "stock_knowledge": [],
            "stock_insights": [],
            "sources": [],
            "sectors": [],
        }
        provider_snapshot = {
            "facts": [
                {"metric": "revenue", "value": 54000000000, "source_id": "sec:INTC:Revenues", "source_type": "sec_companyfacts"},
                {"metric": "net_income", "value": 4200000000, "source_id": "sec:INTC:NetIncomeLoss", "source_type": "sec_companyfacts"},
                {"metric": "operating_cash_flow", "value": 11200000000, "source_id": "sec:INTC:NetCashProvidedByUsedInOperatingActivities", "source_type": "sec_companyfacts"},
                {"metric": "capex", "value": 6800000000, "source_id": "sec:INTC:PaymentsToAcquirePropertyPlantAndEquipment", "source_type": "sec_companyfacts"},
                {"metric": "cash", "value": 8500000000, "source_id": "sec:INTC:CashAndCashEquivalentsAtCarryingValue", "source_type": "sec_companyfacts"},
                {"metric": "debt", "value": 28500000000, "source_id": "sec:INTC:LongTermDebtAndFinanceLeaseObligations", "source_type": "sec_companyfacts"},
                {"metric": "price", "value": 31.5, "source_id": "yahoo:INTC:price", "source_type": "yahoo_quote"},
                {"metric": "market_cap", "value": 138600000000, "source_id": "yahoo:INTC:market_cap", "source_type": "yahoo_quote"},
            ],
            "sources": [
                {"id": "sec:INTC:companyfacts", "source_type": "sec_companyfacts", "title": "SEC companyfacts INTC"},
                {"id": "yahoo:INTC:quote", "source_type": "yahoo_quote", "title": "Yahoo quote INTC"},
            ],
            "errors": [],
            "market_snapshot_status": "present",
            "financial_fact_status": "present",
        }
        with tempfile.TemporaryDirectory() as tmp:
            packet, _ = build_valuation_artifact(
                context,
                symbol="INTC",
                market="US",
                output_dir=Path(tmp),
                command="valuation US.INTC",
                now=datetime(2026, 7, 4, tzinfo=timezone.utc),
                provider_snapshot=provider_snapshot,
            )

        facts = {fact["metric"]: fact["value"] for fact in packet["facts"]}
        calculations = {item["metric"]: item["value"] for item in packet["deterministic_calculations"]}
        self.assertEqual(facts["revenue"], 54000000000)
        self.assertEqual(calculations["free_cash_flow"], 4400000000)
        self.assertAlmostEqual(calculations["pe"], 33.0)
        self.assertEqual(packet["source_coverage"]["financial_fact_status"], "present")
        self.assertEqual(packet["source_coverage"]["market_snapshot_status"], "present")
        self.assertNotIn("source metadata is missing", packet["degraded_state"]["reasons"])
        self.assertFalse(any("P0 uses existing local stock context" in item for item in packet["assumptions"]["items"]))

    def test_p0_2_formats_output_and_labels_negative_multiples(self) -> None:
        context = {
            "stock": {
                "id": 10,
                "symbol": "LOSS",
                "market": "US",
                "name": "Loss Making Semis",
                "core_business": "Semiconductor platform with AI growth and manufacturing cycle exposure.",
                "stock_character": "Cyclical growth turnaround.",
            },
            "stock_knowledge": [],
            "stock_insights": [],
            "sources": [],
            "sectors": [],
        }
        provider_snapshot = {
            "facts": [
                {"metric": "revenue", "value": 52600000000, "source_id": "sec:LOSS:Revenues", "source_type": "sec_companyfacts"},
                {"metric": "net_income", "value": -18000000000, "source_id": "sec:LOSS:NetIncomeLoss", "source_type": "sec_companyfacts"},
                {"metric": "operating_cash_flow", "value": 900000000, "source_id": "sec:LOSS:OCF", "source_type": "sec_companyfacts"},
                {"metric": "capex", "value": 5800000000, "source_id": "sec:LOSS:Capex", "source_type": "sec_companyfacts"},
                {"metric": "cash", "value": 19000000000, "source_id": "sec:LOSS:Cash", "source_type": "sec_companyfacts"},
                {"metric": "debt", "value": 13000000000, "source_id": "sec:LOSS:Debt", "source_type": "sec_companyfacts"},
                {"metric": "market_cap", "value": 601100000000, "source_id": "yahoo:LOSS:market_cap", "source_type": "yahoo_quote", "timestamp": "2026-07-04T00:00:00+00:00", "currency": "USD"},
                {"metric": "price", "value": 136.61, "source_id": "yahoo:LOSS:price", "source_type": "yahoo_quote", "timestamp": "2026-07-04T00:00:00+00:00", "currency": "USD"},
            ],
            "sources": [
                {"id": "sec:LOSS:companyfacts", "source_type": "sec_companyfacts", "title": "SEC companyfacts LOSS"},
                {"id": "yahoo:LOSS:quote", "source_type": "yahoo_quote", "title": "Yahoo quote LOSS"},
            ],
            "errors": ["Yahoo quote detail unavailable: unauthorized"],
            "market_snapshot_status": "present",
            "financial_fact_status": "present",
        }
        with tempfile.TemporaryDirectory() as tmp:
            packet, _ = build_valuation_artifact(
                context,
                symbol="LOSS",
                market="US",
                output_dir=Path(tmp),
                command="valuation US.LOSS",
                now=datetime(2026, 7, 4, tzinfo=timezone.utc),
                provider_snapshot=provider_snapshot,
            )

        calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
        self.assertEqual(calculations["free_cash_flow"]["display_value"], "-$4.9B")
        self.assertEqual(calculations["fcf_margin"]["display_value"], "-9.3%")
        self.assertEqual(calculations["ps"]["display_value"], "11.4x")
        self.assertFalse(calculations["pe"]["meaningful"])
        self.assertEqual(calculations["pe"]["display_value"], "not meaningful (negative earnings)")
        self.assertFalse(calculations["ev_fcf"]["meaningful"])
        self.assertEqual(calculations["ev_fcf"]["display_value"], "not meaningful (negative FCF)")
        self.assertIn("raw_value", calculations["ev_fcf"])

        status = packet["source_coverage"]["provider_statuses"]["market_snapshot"]
        self.assertEqual(status["status"], "partial_provider_gap")
        self.assertIn("market-cap and price fields are available", status["explanation"])

        bridge = packet["market_implied_bridge"]
        self.assertTrue(any("P/S: 11.4x" in line["display"] for line in bridge["bridge_lines"]))
        self.assertTrue(any("5% market-cap yield" in line["display"] for line in bridge["bridge_lines"]))
        self.assertIn(bridge["frame_fit_ranking"][0]["fit_to_current_market_value"], {"fits", "partial_fit"})
        self.assertIn("assumptions_that_must_become_true", bridge["frame_fit_ranking"][0])

        card = render_valuation_card(packet)
        self.assertIn("Market cap: $601.1B", card)
        self.assertIn("Enterprise value: $595.1B", card)
        self.assertIn("FCF margin: -9.3%", card)
        self.assertIn("PE: not meaningful (negative earnings)", card)
        self.assertIn("EV/FCF: not meaningful (negative FCF)", card)
        self.assertIn("Market snapshot: partial provider gap", card)
        self.assertIn("Market-implied bridge:", card)
        self.assertNotIn("601100000000", card)
        self.assertNotIn("-0.093156", card)

    def test_renders_method_library(self) -> None:
        text = render_valuation_methods()
        self.assertIn("Free Cash Flow", text)
        self.assertIn("Comparable Multiples", text)
        self.assertIn("Growth / Scenario", text)

    def test_artifact_evidence_command_returns_raw_and_display_fields(self) -> None:
        context = {
            "stock": {
                "id": 10,
                "symbol": "INTC",
                "market": "US",
                "name": "Intel Corporation",
                "core_business": "Semiconductor manufacturing turnaround.",
                "stock_character": "Cyclical semiconductor recovery.",
            },
            "stock_knowledge": [],
            "stock_insights": [],
            "sources": [],
            "sectors": [],
        }
        provider_snapshot = {
            "facts": [
                {"metric": "revenue", "value": 52600000000, "source_id": "sec:INTC:Revenues", "source_type": "sec_companyfacts"},
                {"metric": "net_income", "value": -18000000000, "source_id": "sec:INTC:NetIncomeLoss", "source_type": "sec_companyfacts"},
                {"metric": "operating_cash_flow", "value": 900000000, "source_id": "sec:INTC:OCF", "source_type": "sec_companyfacts"},
                {"metric": "capex", "value": 5800000000, "source_id": "sec:INTC:Capex", "source_type": "sec_companyfacts"},
                {"metric": "cash", "value": 19000000000, "source_id": "sec:INTC:Cash", "source_type": "sec_companyfacts"},
                {"metric": "debt", "value": 13000000000, "source_id": "sec:INTC:Debt", "source_type": "sec_companyfacts"},
                {"metric": "market_cap", "value": 601100000000, "source_id": "yahoo:INTC:market_cap", "source_type": "yahoo_quote", "timestamp": "2026-07-04T00:00:00+00:00", "currency": "USD"},
                {"metric": "price", "value": 136.61, "source_id": "yahoo:INTC:price", "source_type": "yahoo_quote", "timestamp": "2026-07-04T00:00:00+00:00", "currency": "USD"},
            ],
            "sources": [
                {"id": "sec:INTC:companyfacts", "source_type": "sec_companyfacts", "title": "SEC companyfacts INTC"},
                {"id": "yahoo:INTC:quote", "source_type": "yahoo_quote", "title": "Yahoo quote INTC"},
            ],
            "errors": ["Yahoo quote detail unavailable: unauthorized"],
            "market_snapshot_status": "present",
            "financial_fact_status": "present",
        }
        with tempfile.TemporaryDirectory() as tmp:
            build_valuation_artifact(
                context,
                symbol="INTC",
                market="US",
                output_dir=Path(tmp),
                command="valuation US.INTC",
                now=datetime(2026, 7, 4, tzinfo=timezone.utc),
                provider_snapshot=provider_snapshot,
            )

            result = handle_command("valuation artifact evidence US.INTC", output_dir=Path(tmp))

        self.assertTrue(result.ok)
        evidence = json.loads(result.message)
        self.assertEqual(evidence["artifact"]["symbol"], "INTC")
        facts = {item["metric"]: item for item in evidence["facts"]}
        self.assertEqual(facts["market_cap"]["value"], 601100000000)
        self.assertEqual(facts["market_cap"]["display_value"], "$601.1B")
        calculations = {item["metric"]: item for item in evidence["deterministic_calculations"]}
        self.assertFalse(calculations["pe"]["meaningful"])
        self.assertEqual(calculations["pe"]["raw_value"], -33.394444)
        self.assertEqual(calculations["pe"]["display_value"], "not meaningful (negative earnings)")
        self.assertTrue(evidence["market_implied_bridge"]["bridge_lines"])
        self.assertIn("fit_to_current_market_value", evidence["market_implied_bridge"]["frame_fit_ranking"][0])
        serialized = result.message.lower()
        self.assertNotIn("command_api_token", serialized)
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("traceback", serialized)
        self.assertNotIn("unauthorized", serialized)

    def test_artifact_evidence_command_rejects_path_like_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = handle_command("valuation artifact evidence ../../etc/passwd", output_dir=Path(tmp))

        self.assertFalse(result.ok)
        self.assertIn("需要股票标的", result.message)
        self.assertNotIn("/etc/passwd", result.message)

    def test_workbench_parses_artifact_evidence_without_file_path_field(self) -> None:
        with patch(
            "investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference",
            return_value=[{"symbol": "INTC", "market": "US", "name": "Intel Corporation"}],
        ):
            preview = parse_workbench_command("valuation artifact evidence US.INTC")

        self.assertEqual(preview["status"], "parsed")
        self.assertEqual(preview["action_id"], "stock_valuation_artifact_evidence")
        self.assertEqual(preview["exact_command"], "valuation artifact evidence US.INTC")
        self.assertEqual(preview["safety_level"], "read_only")
        self.assertNotIn("path", {field["id"] for field in preview["action"]["required_fields"]})

    def test_workbench_artifact_evidence_rejects_path_like_input_without_echo(self) -> None:
        with patch("investment_knowledge_mcp.command_workbench.repository.resolve_stock_reference", return_value=[]):
            preview = parse_workbench_command("valuation artifact evidence ../../etc/passwd")

        self.assertEqual(preview["status"], "needs_entity")
        message = preview["recovery_message"]
        self.assertIn("does not look like a stock symbol", message)
        self.assertNotIn("/etc/passwd", message)
        self.assertNotIn("..", message)


if __name__ == "__main__":
    unittest.main()
