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
    build_valuation_artifact_evidence,
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

    def test_p0_3_kr_provider_snapshot_maps_ticker_currency_and_source_categories(self) -> None:
        yahoo_quote = {
            "quoteResponse": {
                "result": [
                    {
                        "regularMarketPrice": 281000,
                        "marketCap": 204568000000000,
                        "sharesOutstanding": 728002365,
                        "currency": "KRW",
                        "regularMarketTime": 1783123200,
                        "totalRevenue": 66000000000000,
                        "netIncomeToCommon": 19000000000000,
                        "operatingCashflow": 29000000000000,
                        "capitalExpenditures": -17000000000000,
                        "totalCash": 14000000000000,
                        "totalDebt": 25000000000000,
                    }
                ]
            }
        }

        with patch("investment_knowledge_mcp.valuation_data_provider._get_json", return_value=yahoo_quote):
            snapshot = fetch_provider_snapshot("000660", "KR")

        self.assertEqual(snapshot["target_resolution"]["normalized_target"], "KR.000660")
        self.assertEqual(snapshot["target_resolution"]["provider_market_ticker"], "000660.KS")
        self.assertEqual(snapshot["target_resolution"]["company_name"], "SK hynix Inc.")
        self.assertEqual(snapshot["currency"], "KRW")
        self.assertEqual(snapshot["market_snapshot_status"], "present")
        self.assertEqual(snapshot["financial_fact_status"], "fallback_used")
        self.assertEqual(snapshot["source_attempts"]["official_financials"]["family"], "DART/FSS and company IR")

        context = {
            "stock": {
                "id": 12,
                "symbol": "000660",
                "market": "KR",
                "name": "SK hynix Inc.",
                "core_business": "Memory semiconductor company with HBM and memory cycle exposure.",
                "stock_character": "Cyclical AI infrastructure memory beta.",
            },
            "stock_knowledge": [],
            "stock_insights": [],
            "sources": [],
            "sectors": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            packet, _ = build_valuation_artifact(
                context,
                symbol="000660",
                market="KR",
                output_dir=Path(tmp),
                command="valuation KR.000660",
                now=datetime(2026, 7, 5, tzinfo=timezone.utc),
                provider_snapshot=snapshot,
            )

        self.assertEqual(packet["target_resolution"]["provider_market_ticker"], "000660.KS")
        self.assertEqual(packet["source_coverage"]["provider_statuses"]["official_financials"]["status"], "complete_missing")
        self.assertEqual(packet["source_coverage"]["provider_statuses"]["fallback_fundamentals"]["status"], "fallback_used")
        self.assertTrue(packet["market_implied_bridge"]["bridge_lines"])
        card = render_valuation_card(packet)
        self.assertIn("Input: valuation KR.000660 -> resolved: KR.000660 SK hynix Inc. -> market snapshot ticker: 000660.KS", card)
        self.assertIn("Market cap: KRW 204568.0B", card)
        self.assertIn("Revenue: KRW 66000.0B", card)
        self.assertIn("Official/company financials: complete missing", card)
        self.assertIn("Fallback fundamentals: fallback used", card)
        self.assertIn("DART/FSS and company IR", card)
        self.assertNotIn("unknown currency", card)
        self.assertNotIn("HTTP Error", card)

    def test_p0_3_hk_alias_maps_to_kingboard_and_evidence_preserves_mapping(self) -> None:
        yahoo_quote = {
            "quoteResponse": {
                "result": [
                    {
                        "regularMarketPrice": 8.15,
                        "marketCap": 25400000000,
                        "sharesOutstanding": 3116000000,
                        "currency": "HKD",
                        "regularMarketTime": 1783123200,
                        "totalRevenue": 17500000000,
                        "netIncomeToCommon": 1900000000,
                        "operatingCashflow": 2500000000,
                        "capitalExpenditures": -800000000,
                        "totalCash": 4200000000,
                        "totalDebt": 5100000000,
                    }
                ]
            }
        }

        with patch("investment_knowledge_mcp.valuation_data_provider._get_json", return_value=yahoo_quote):
            snapshot = fetch_provider_snapshot("01888", "HK")

        self.assertEqual(snapshot["target_resolution"]["normalized_target"], "HK.01888")
        self.assertEqual(snapshot["target_resolution"]["provider_market_ticker"], "1888.HK")
        self.assertEqual(snapshot["currency"], "HKD")
        self.assertEqual(snapshot["source_attempts"]["official_financials"]["family"], "HKEXnews and official company reports")

        context = {
            "stock": {
                "id": 13,
                "symbol": "01888",
                "market": "HK",
                "name": "Kingboard Laminates Holdings Limited",
                "core_business": "Copper clad laminate and PCB material supplier with cyclical laminate exposure.",
                "stock_character": "Cyclical materials and electronics supply-chain company.",
            },
            "stock_knowledge": [],
            "stock_insights": [],
            "sources": [],
            "sectors": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            packet, _ = build_valuation_artifact(
                context,
                symbol="01888",
                market="HK",
                output_dir=Path(tmp),
                command="valuation 建滔积层板 HK",
                now=datetime(2026, 7, 5, tzinfo=timezone.utc),
                provider_snapshot=snapshot,
            )
            evidence = build_valuation_artifact_evidence(packet)

        self.assertEqual(evidence["target_resolution"]["normalized_target"], "HK.01888")
        self.assertEqual(evidence["target_resolution"]["provider_market_ticker"], "1888.HK")
        self.assertEqual(evidence["source_coverage"]["source_attempts"]["official_financials"]["family"], "HKEXnews and official company reports")
        card = render_valuation_card(packet)
        self.assertIn("Input: valuation 建滔积层板 HK -> resolved: HK.01888 Kingboard Laminates Holdings Limited -> market snapshot ticker: 1888.HK", card)
        self.assertIn("Market cap: HK$25.4B", card)
        self.assertIn("HKEXnews and official company reports", card)
        self.assertNotIn("unknown currency", card)

    def test_p0_3_hk_and_kr_command_forms_normalize_in_workbench_and_router(self) -> None:
        with patch(
            "investment_knowledge_mcp.command_router.repository.get_stock_context",
            return_value={
                "stock": {"id": 13, "symbol": "01888", "market": "HK", "name": "Kingboard Laminates Holdings Limited"},
                "stock_knowledge": [],
                "stock_insights": [],
                "sources": [],
                "sectors": [],
            },
        ) as get_context, patch(
            "investment_knowledge_mcp.command_router.fetch_provider_snapshot",
            return_value={
                "facts": [],
                "sources": [],
                "errors": [],
                "market_snapshot_status": "missing",
                "financial_fact_status": "missing",
                "currency": "HKD",
                "target_resolution": {
                    "input_target": "建滔积层板 HK",
                    "normalized_target": "HK.01888",
                    "company_name": "Kingboard Laminates Holdings Limited",
                    "provider_market_ticker": "1888.HK",
                    "mapping_confidence": "fixture",
                    "mapping_source": "p0_3_fixture",
                },
                "source_attempts": {
                    "official_financials": {"family": "HKEXnews and official company reports", "status": "not_attempted"},
                    "market_snapshot": {"family": "Yahoo/yfinance market snapshot", "status": "not_attempted"},
                },
            },
        ):
            with tempfile.TemporaryDirectory() as tmp:
                result = handle_command("valuation 建滔积层板 HK", output_dir=Path(tmp))

        self.assertTrue(result.ok)
        get_context.assert_called_once_with(symbol="01888", market="HK")
        self.assertIn("resolved: HK.01888 Kingboard Laminates Holdings Limited", result.message)

        self.assertEqual(parse_workbench_command("valuation 1888 HK")["exact_command"], "valuation HK.01888")
        self.assertEqual(parse_workbench_command("valuation HK.01888")["exact_command"], "valuation HK.01888")
        self.assertEqual(parse_workbench_command("valuation 000660 KR")["exact_command"], "valuation KR.000660")

    def test_p0_3_supported_fixture_runs_with_minimal_context_when_profile_missing(self) -> None:
        with patch(
            "investment_knowledge_mcp.command_router.repository.get_stock_context",
            return_value={"stock": None},
        ), patch(
            "investment_knowledge_mcp.command_router.fetch_provider_snapshot",
            return_value={
                "facts": [
                    {
                        "metric": "market_cap",
                        "value": 204568000000000,
                        "source_id": "yahoo:000660.KS:market_cap",
                        "source_type": "yahoo_quote",
                        "timestamp": "2026-07-05T00:00:00+00:00",
                        "currency": "KRW",
                    }
                ],
                "sources": [{"id": "yahoo:000660.KS:quote", "source_type": "yahoo_quote", "title": "Yahoo quote 000660.KS"}],
                "errors": [],
                "market_snapshot_status": "present",
                "financial_fact_status": "missing",
                "currency": "KRW",
                "target_resolution": {
                    "input_target": "valuation KR.000660",
                    "normalized_symbol": "000660",
                    "normalized_market": "KR",
                    "normalized_target": "KR.000660",
                    "company_name": "SK hynix Inc.",
                    "provider_market_ticker": "000660.KS",
                    "provider": "yahoo_quote",
                    "currency": "KRW",
                    "mapping_confidence": "fixture",
                    "mapping_source": "p0_3_fixture",
                },
                "source_attempts": {
                    "provider_mapping": {"family": "P0.3 fixture ticker/entity map", "status": "available"},
                    "market_snapshot": {"family": "Yahoo/yfinance market snapshot", "status": "available"},
                    "official_financials": {"family": "DART/FSS and company IR", "status": "complete_missing"},
                    "fallback_fundamentals": {"family": "Yahoo/yfinance vendor-labeled fallback fundamentals", "status": "complete_missing"},
                },
            },
        ):
            with tempfile.TemporaryDirectory() as tmp:
                result = handle_command("valuation KR.000660", output_dir=Path(tmp))

        self.assertTrue(result.ok)
        self.assertIn("SK hynix Inc.", result.message)
        self.assertIn("Market cap: KRW 204568.0B", result.message)
        self.assertIn("DART/FSS and company IR", result.message)
        self.assertNotIn("未找到股票", result.message)

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

    def test_user_facing_card_sanitizes_provider_http_diagnostics(self) -> None:
        context = {
            "stock": {
                "id": 11,
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
                {"metric": "market_cap", "value": 601100000000, "source_id": "yahoo:INTC:market_cap", "source_type": "yahoo_quote", "timestamp": "2026-07-04T00:00:00+00:00", "currency": "USD"},
                {"metric": "price", "value": 136.61, "source_id": "yahoo:INTC:price", "source_type": "yahoo_quote", "timestamp": "2026-07-04T00:00:00+00:00", "currency": "USD"},
            ],
            "sources": [
                {"id": "sec:INTC:companyfacts", "source_type": "sec_companyfacts", "title": "SEC companyfacts INTC"},
                {"id": "yahoo:INTC:quote", "source_type": "yahoo_quote", "title": "Yahoo quote INTC"},
            ],
            "errors": [
                "Yahoo quote unavailable: HTTP Error 401: Unauthorized",
                "Yahoo chart unavailable: <HTTPError url=https://query1.finance.yahoo.com/v8/finance/chart/INTC>",
            ],
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

        self.assertIn("HTTP Error 401: Unauthorized", packet["source_coverage"]["provider_errors"][0])
        evidence_serialized = json.dumps(build_valuation_artifact_evidence(packet), sort_keys=True)
        self.assertNotIn("HTTP Error", evidence_serialized)
        self.assertNotIn("Unauthorized", evidence_serialized)
        self.assertNotIn("query1.finance.yahoo.com", evidence_serialized)

        card = render_valuation_card(packet)
        self.assertIn("Market snapshot: partial provider gap", card)
        self.assertIn("provider data gap: market snapshot provider is partially unavailable", card)
        self.assertNotIn("HTTP Error", card)
        self.assertNotIn("Unauthorized", card)
        self.assertNotIn("HTTPError", card)
        self.assertNotIn("query1.finance.yahoo.com", card)
        self.assertNotIn("https://", card)

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


if __name__ == "__main__":
    unittest.main()
