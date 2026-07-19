from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import tempfile
import unittest

from investment_knowledge_mcp.stock_valuation import (
    CORE_FRAMES,
    SPECIALIST_FRAMES,
    build_valuation_artifact,
    build_valuation_artifact_evidence,
    load_latest_valuation_artifact,
    render_valuation_card,
    render_valuation_methods,
    valuation_method_library,
)


class StockValuationTests(unittest.TestCase):
    def _context(self) -> dict[str, object]:
        return {
            "stock": {
                "id": 7,
                "symbol": "ACME",
                "market": "US",
                "name": "Acme Semiconductor",
                "core_business": "Cyclical semiconductor business with growth optionality.",
                "stock_character": "Cyclical growth.",
            },
            "stock_knowledge": [],
            "stock_insights": [{"confirmed_by_user": True, "content": "Track cash flow and cycle."}],
            "sources": [{"id": "sec:ACME", "source_type": "sec_companyfacts"}],
        }

    def _snapshot(self) -> dict[str, object]:
        return {
            "facts": [
                {"metric": "revenue", "value": 1000.0, "source_id": "sec:revenue", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "gross_profit", "value": 450.0, "source_id": "sec:gross", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "operating_income", "value": 200.0, "source_id": "sec:op", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "net_income", "value": -50.0, "source_id": "sec:income", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "operating_cash_flow", "value": 250.0, "source_id": "sec:ocf", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "capex", "value": 100.0, "source_id": "sec:capex", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "cash", "value": 75.0, "source_id": "sec:cash", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "debt", "value": 275.0, "source_id": "sec:debt", "source_type": "sec_companyfacts", "currency": "USD"},
                {"metric": "price", "value": 10.0, "source_id": "quote:price", "source_type": "market_snapshot", "currency": "USD", "timestamp": "2026-07-19T00:00:00+00:00"},
                {"metric": "shares_outstanding", "value": 100.0, "source_id": "quote:shares", "source_type": "market_snapshot", "currency": "USD"},
                {"metric": "ebitda", "value": 300.0, "source_id": "sec:ebitda", "source_type": "sec_companyfacts", "currency": "USD"},
            ],
            "sources": [{"id": "sec:ACME", "source_type": "sec_companyfacts"}],
            "errors": ["Authorization: secret https://provider.example/error"],
            "target_resolution": {"normalized_target": "US.ACME", "provider_market_ticker": "ACME", "currency": "USD"},
            "market_snapshot_status": "present",
            "financial_fact_status": "present",
        }

    def test_public_interfaces_and_eight_method_definitions(self) -> None:
        for function in (
            build_valuation_artifact,
            load_latest_valuation_artifact,
            build_valuation_artifact_evidence,
            render_valuation_card,
            render_valuation_methods,
        ):
            self.assertTrue(callable(function))
        self.assertEqual(len(CORE_FRAMES), 5)
        self.assertEqual(len(SPECIALIST_FRAMES), 3)
        self.assertEqual(len(valuation_method_library()), 8)
        self.assertEqual(list(inspect.signature(load_latest_valuation_artifact).parameters), ["symbol", "market", "output_dir"])

    def test_builds_deterministic_packet_with_all_metrics_and_fact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, path = build_valuation_artifact(
                self._context(), symbol="acme", market="us", output_dir=Path(temporary), command="valuation US.ACME",
                provider_snapshot=self._snapshot(), now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
            )
            self.assertTrue(path.name.startswith("ACME_US_valuation_20260719T010203Z"))
            self.assertTrue((Path(temporary) / "valuation" / "ACME_US_valuation_latest.json").exists())
            self.assertEqual(packet["schema"], "stock_valuation_packet.v1")
            self.assertEqual(set(packet), {
                "schema", "input", "stock", "target_resolution", "facts", "assumptions", "deterministic_calculations",
                "internal_frame_scores", "selected_frames", "market_implied_bridge", "interpretation", "watch_items",
                "source_coverage", "degraded_state", "safety",
            })
            self.assertEqual(len(packet["internal_frame_scores"]), 5)
            self.assertGreaterEqual(len(packet["selected_frames"]), 1)
            self.assertLessEqual(len(packet["selected_frames"]), 3)
            self.assertTrue(set(item["id"] for item in packet["selected_frames"]).issubset({item["id"] for item in CORE_FRAMES}))
            facts = {item["metric"]: item for item in packet["facts"]}
            self.assertEqual(facts["revenue"]["value"], 1000.0)
            self.assertIn("display_value", facts["revenue"])
            self.assertEqual(facts["revenue"]["source_id"], "sec:revenue")
            calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
            for metric in ("free_cash_flow", "net_debt", "market_cap", "enterprise_value", "gross_margin", "operating_margin", "fcf_margin", "pe", "ps", "ev_ebitda", "ev_fcf"):
                self.assertIn(metric, calculations)
                self.assertIsInstance(calculations[metric]["input_refs"], tuple)
            self.assertEqual(calculations["free_cash_flow"]["value"], 150.0)
            self.assertEqual(calculations["net_debt"]["value"], 200.0)
            self.assertEqual(calculations["market_cap"]["value"], 1000.0)
            self.assertEqual(calculations["enterprise_value"]["value"], 1200.0)
            self.assertFalse(calculations["pe"]["meaningful"])
            self.assertEqual(calculations["pe"]["raw_value"], -20.0)
            self.assertIn("negative earnings", calculations["pe"]["display_value"])
            self.assertFalse(calculations["ev_fcf"]["meaningful"] is False)
            self.assertEqual(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=Path(temporary))["schema"], "stock_valuation_packet.v1")

    def test_evidence_is_an_allow_list_without_paths_or_provider_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        evidence = build_valuation_artifact_evidence(packet)
        serialized = json.dumps(evidence).lower()
        self.assertIn("display_value", serialized)
        self.assertIn("meaningful", serialized)
        for unsafe in ("artifact_path", "authorization", "secret", "provider.example", "exception", "traceback"):
            self.assertNotIn(unsafe, serialized)
        with self.assertRaises((TypeError, ValueError)):
            build_valuation_artifact_evidence(Path("../../etc/passwd"))  # type: ignore[arg-type]
        card = render_valuation_card(packet)
        self.assertIn("no formal user insight was written", card)
        self.assertNotIn("provider.example", card)

    def test_negative_fcf_multiples_are_explicitly_not_meaningful(self) -> None:
        snapshot = self._snapshot()
        facts = snapshot["facts"]
        assert isinstance(facts, list)
        for fact in facts:
            if fact["metric"] == "operating_cash_flow":
                fact["value"] = 50.0
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=snapshot,
            )
        calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
        for metric in ("fcf_yield", "ev_fcf"):
            self.assertFalse(calculations[metric]["meaningful"])
            self.assertIsNotNone(calculations[metric]["raw_value"])
            self.assertIn("negative FCF", calculations[metric]["display_value"])

    def test_path_like_targets_are_rejected_without_file_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build_valuation_artifact(
                    {}, symbol="../../etc/passwd", market="US", output_dir=Path(temporary), command="valuation ../../etc/passwd",
                )
            with self.assertRaises(ValueError):
                load_latest_valuation_artifact(symbol="../../etc/passwd", market="US", output_dir=Path(temporary))

    def test_missing_data_degrades_explicitly_without_fabricating_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                {"stock": {"symbol": "EMPTY", "market": "US"}}, symbol="EMPTY", market="US", output_dir=Path(temporary), command="valuation US.EMPTY",
            )
        self.assertTrue(packet["degraded_state"]["degraded"])
        self.assertEqual(packet["facts"], [])
        self.assertIn("revenue is missing", packet["degraded_state"]["reasons"])
        self.assertFalse(packet["safety"]["writes_formal_user_insight"])


if __name__ == "__main__":
    unittest.main()
