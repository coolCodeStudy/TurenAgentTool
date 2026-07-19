from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

    def _build(self, context: dict[str, object] | None = None, snapshot: dict[str, object] | None = None) -> dict[str, object]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        packet, _ = build_valuation_artifact(
            context or self._context(),
            symbol="ACME",
            market="US",
            output_dir=Path(temporary.name),
            command="valuation US.ACME",
            provider_snapshot=snapshot or self._snapshot(),
            now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
        )
        return packet

    def _assert_public_refs_resolve(self, public: dict[str, object]) -> None:
        facts = public.get("facts")
        self.assertIsInstance(facts, list)
        fact_ids = {item["id"] for item in facts if isinstance(item, dict)}
        source_coverage = public.get("source_coverage")
        self.assertIsInstance(source_coverage, dict)
        registry = source_coverage.get("source_registry")
        self.assertIsInstance(registry, list)
        source_ids = {item["id"] for item in registry if isinstance(item, dict)}
        for fact in facts:
            self.assertIn(fact["source_id"], source_ids)
        for section in ("deterministic_calculations", "internal_frame_scores", "selected_frames"):
            records = public.get(section)
            self.assertIsInstance(records, list)
            for record in records:
                for reference in record.get("input_refs", []):
                    self.assertTrue(reference in fact_ids or reference.startswith("packet:"), reference)
        bridge = public.get("market_implied_bridge")
        self.assertIsInstance(bridge, dict)
        for record in bridge.get("bridge_lines", []):
            for reference in record.get("input_refs", []):
                self.assertTrue(reference in fact_ids or reference.startswith("packet:"), reference)

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
            self.assertRegex(facts["revenue"]["source_id"], r"^source:[0-9a-f]{16}$")
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
        self.assertEqual(evidence["source_coverage"]["market_snapshot_status"], "present")
        self.assertEqual(evidence["source_coverage"]["financial_fact_status"], "present")
        for unsafe in ("artifact_path", "authorization", "secret", "provider.example", "exception", "traceback"):
            self.assertNotIn(unsafe, serialized)
        with self.assertRaises((TypeError, ValueError)):
            build_valuation_artifact_evidence(Path("../../etc/passwd"))  # type: ignore[arg-type]
        card = render_valuation_card(packet)
        self.assertIn("no formal user insight was written", card)
        self.assertNotIn("provider.example", card)

    def test_evidence_recursively_projects_hostile_provider_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        coverage = packet["source_coverage"]
        assert isinstance(coverage, dict)
        coverage["provider_statuses"] = {
            "market_snapshot": {
                "status": "available",
                "headers": {"Authorization": "Bearer provider-secret"},
                "exception": "provider exception detail",
                "endpoint": "https://provider.example/diagnostic",
                "configuration": {"api_key": "configuration-secret"},
                "diagnostics": {"nested": {"raw": "nested-provider-diagnostic"}},
            },
        }
        coverage["source_attempts"] = {
            "official_financial": {
                "family": "official_financial",
                "status": "unavailable",
                "headers": {"X-Api-Key": "attempt-secret"},
                "exception_text": "attempt exception detail",
                "endpoint_url": "https://attempt.example/raw",
                "configuration": {"token": "attempt-configuration"},
                "diagnostics": {"raw": "attempt-diagnostic"},
            },
        }

        evidence = build_valuation_artifact_evidence(packet)
        serialized = json.dumps(evidence).lower()

        self.assertEqual(
            evidence["source_coverage"]["provider_statuses"],
            {"market_snapshot": {"status": "available"}},
        )
        self.assertEqual(
            evidence["source_coverage"]["source_attempts"],
            [{"family": "official_financial", "status": "unavailable"}],
        )
        for unsafe in (
            "authorization", "provider-secret", "exception detail", "provider.example",
            "configuration-secret", "nested-provider-diagnostic", "attempt-secret",
            "attempt.example", "attempt-configuration", "attempt-diagnostic",
        ):
            self.assertNotIn(unsafe, serialized)

    def test_evidence_preserves_safe_stale_source_status(self) -> None:
        snapshot = self._snapshot()
        snapshot["market_snapshot_status"] = "stale"
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=snapshot,
            )
        evidence = build_valuation_artifact_evidence(packet)
        self.assertEqual(evidence["source_coverage"]["market_snapshot_status"], "stale")

    def test_derived_calculations_flatten_all_upstream_fact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
        self.assertEqual(
            calculations["free_cash_flow"]["input_refs"],
            ("fact:operating_cash_flow", "fact:capex"),
        )
        self.assertEqual(
            calculations["fcf_margin"]["input_refs"],
            ("fact:operating_cash_flow", "fact:capex", "fact:revenue"),
        )
        self.assertEqual(
            calculations["ev_fcf"]["input_refs"],
            (
                "fact:price", "fact:shares_outstanding",
                "fact:debt", "fact:cash",
                "fact:operating_cash_flow", "fact:capex",
            ),
        )

    def test_evidence_projects_every_branch_through_typed_safe_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        hostile = json.loads(json.dumps(packet))
        hostile["target_resolution"].update({
            "input_target": {"endpoint": "https://evil.example/target"},
            "normalized_target": "https://evil.example/target",
            "company_name": "Bearer evidence-secret",
        })
        hostile["stock"].update({
            "symbol": {"path": "/private/stock"},
            "name": "Authorization: evidence-secret",
        })
        hostile["facts"].append({
            "id": {"headers": "evidence-secret"}, "metric": "revenue", "value": {"raw": 1},
            "display_value": ["https://evil.example/fact"], "source_id": "Bearer evidence-secret",
            "provider": "https://evil.example/provider",
        })
        hostile["deterministic_calculations"].append({
            "metric": "ps", "value": {"raw": 1}, "raw_value": [1],
            "display_value": "https://evil.example/calculation", "formula": {"config": "evidence-secret"},
            "inputs": [{"metric": "revenue"}], "input_refs": [{"traceback": "evidence-secret"}],
        })
        hostile["market_implied_bridge"]["bridge_lines"].append({
            "type": {"header": "evidence-secret"}, "display": "https://evil.example/bridge",
            "input_refs": ["/private/bridge"],
        })
        hostile["market_implied_bridge"]["frame_fit_ranking"].append({
            "id": "fcf", "name": "https://evil.example/frame", "score": {"raw": 1},
            "fit_to_current_market_value": ["fits"], "why_it_fits_or_not": "Bearer evidence-secret",
            "main_data_gaps": [{"exception": "evidence-secret"}], "confidence": {"raw": "medium"},
        })
        hostile["source_coverage"].update({
            "fact_count": {"raw": 1}, "market_snapshot_status": "https://evil.example/status",
            "provider_statuses": {"market_snapshot": {"status": "Bearer evidence-secret"}},
            "source_attempts": {"secret": {"family": "https://evil.example/family", "status": "Bearer evidence-secret"}},
        })
        hostile["degraded_state"] = {
            "degraded": "yes", "reasons": ["safe gap", {"path": "/private/gap"}],
            "data_gaps": ["https://evil.example/gap", "safe data gap", "../relative/path"],
        }
        hostile["safety"] = {
            "direct_investment_advice": "yes", "writes_formal_user_insight": {"raw": True},
            "research_aid_only": True,
        }
        hostile["input"] = {"symbol": "https://evil.example/input", "market": {"raw": "US"}, "created_at": ["evidence-secret"]}

        evidence = build_valuation_artifact_evidence(hostile)
        serialized = json.dumps(evidence).lower()

        revenue = next(item for item in evidence["facts"] if item.get("id") == "fact:revenue")
        self.assertEqual(revenue["value"], 1000.0)
        self.assertEqual(revenue["display_value"], "$1.0K")
        self.assertEqual(evidence["target"]["currency"], "USD")
        self.assertEqual(evidence["degraded_state"], {"reasons": ["safe gap"], "data_gaps": ["safe data gap"]})
        self.assertEqual(evidence["safety"]["research_aid_only"], True)
        self.assertNotIn("direct_investment_advice", evidence["safety"])
        for unsafe in ("evil.example", "evidence-secret", "authorization", "bearer", "private/", "relative/path", "traceback", "headers", "config"):
            self.assertNotIn(unsafe, serialized)

    def test_bridge_lines_and_frame_scores_have_bounded_input_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary), command="valuation US.ACME", provider_snapshot=self._snapshot(),
            )
        bridge_lines = {item["type"]: item for item in packet["market_implied_bridge"]["bridge_lines"]}
        self.assertEqual(
            bridge_lines["sales_anchor"]["input_refs"],
            ("fact:price", "fact:shares_outstanding", "fact:revenue"),
        )
        self.assertEqual(
            bridge_lines["ev_sales_anchor"]["input_refs"],
            (
                "fact:price", "fact:shares_outstanding",
                "fact:debt", "fact:cash", "fact:revenue",
            ),
        )
        self.assertEqual(
            bridge_lines["fcf_yield"]["input_refs"],
            (
                "fact:operating_cash_flow", "fact:capex",
                "fact:price", "fact:shares_outstanding",
            ),
        )
        scores = {item["id"]: item for item in packet["internal_frame_scores"]}
        self.assertEqual(
            scores["fcf"]["input_refs"],
            ("packet:method_library:fcf", "fact:operating_cash_flow", "fact:capex"),
        )
        self.assertIn("packet:stock:core_business", scores["cyclical"]["input_refs"])
        self.assertNotIn("Cyclical semiconductor business", json.dumps(packet["internal_frame_scores"]))

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

    def test_explicit_target_identity_cannot_be_overridden_by_context_or_snapshot(self) -> None:
        context = self._context()
        context["stock"] = {
            "id": 7,
            "symbol": "EVIL",
            "market": "HK",
            "name": "Wrong identity",
            "core_business": "Semiconductor manufacturing.",
            "stock_character": "Cyclical.",
        }
        snapshot = self._snapshot()
        snapshot["target_resolution"] = {
            "normalized_target": "KR.000660",
            "normalized_symbol": "000660",
            "normalized_market": "KR",
            "provider_market_ticker": "../wrong/path",
            "company_name": "Wrong identity",
            "currency": "USD",
        }

        packet = self._build(context, snapshot)

        self.assertEqual(packet["input"]["symbol"], "ACME")
        self.assertEqual(packet["input"]["market"], "US")
        self.assertEqual(packet["stock"]["symbol"], "ACME")
        self.assertEqual(packet["stock"]["market"], "US")
        self.assertEqual(packet["target_resolution"]["normalized_target"], "US.ACME")
        self.assertEqual(packet["target_resolution"]["normalized_symbol"], "ACME")
        self.assertEqual(packet["target_resolution"]["normalized_market"], "US")
        self.assertNotIn("provider_market_ticker", packet["target_resolution"])
        self.assertNotIn("EVIL", json.dumps(packet))
        self.assertNotIn("000660", json.dumps(packet))

        invalid_context = self._context()
        invalid_context["stock"]["symbol"] = "../wrong-stock"
        invalid_snapshot = self._snapshot()
        invalid_snapshot["target_resolution"] = {"normalized_target": "https://evil.example/wrong"}
        invalid = self._build(invalid_context, invalid_snapshot)
        self.assertEqual(invalid["facts"], [])
        self.assertNotIn("core_business", invalid["stock"])
        self.assertIn("context stock identity mismatched the explicit target and was omitted", invalid["degraded_state"]["reasons"])
        self.assertIn("provider snapshot identity mismatched the explicit target and was omitted", invalid["degraded_state"]["reasons"])

    def test_untrusted_ingress_is_normalized_before_packet_persistence(self) -> None:
        context = self._context()
        context["command_context"] = {
            "private_key": "PRIVATE-KEY-SENTINEL",
            "endpoint": "https://evil.example/context",
            "local_path": "../context/private.json",
        }
        context["stock"]["core_business"] = "Semiconductor notes in reports/private.json"
        context["stock_insights"].append({"content": "Bearer RAW-CONTEXT-SENTINEL"})
        snapshot = self._snapshot()
        snapshot["errors"] = ["PRIVATE-KEY-SENTINEL https://evil.example/provider"]
        snapshot["source_attempts"] = {
            "bad": {
                "family": "official_financial",
                "status": "failed",
                "diagnostic": "../provider/debug.log",
            },
        }
        snapshot["sources"] = [{
            "id": "https://evil.example/source/PRIVATE-KEY-SENTINEL",
            "source_type": "sec_companyfacts",
            "local_path": "reports/source.json",
        }]
        snapshot["facts"][0]["provider"] = "https://evil.example/PRIVATE-KEY-SENTINEL"

        with tempfile.TemporaryDirectory() as temporary:
            packet, _ = build_valuation_artifact(
                context,
                symbol="ACME",
                market="US",
                output_dir=Path(temporary),
                command="valuation US.ACME --token PRIVATE-KEY-SENTINEL ../command.txt",
                provider_snapshot=snapshot,
                now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
            )
        persisted = json.dumps(packet, allow_nan=False)

        for unsafe in (
            "PRIVATE-KEY-SENTINEL", "RAW-CONTEXT-SENTINEL", "evil.example",
            "../context", "../provider", "reports/source.json", "reports/private.json",
        ):
            self.assertNotIn(unsafe, persisted)
        self.assertEqual(packet["input"]["command"], "valuation US.ACME")
        self.assertGreater(len(packet["facts"]), 0)

    def test_bool_nan_inf_and_numeric_strings_are_rejected_before_calculation(self) -> None:
        snapshot = self._snapshot()
        snapshot["facts"] = [
            {"metric": "revenue", "value": "1000", "source_id": "raw-revenue", "source_type": "sec_companyfacts"},
            {"metric": "net_income", "value": True, "source_id": "raw-income", "source_type": "sec_companyfacts"},
            {"metric": "ebitda", "value": float("nan"), "source_id": "raw-ebitda", "source_type": "sec_companyfacts"},
            {"metric": "debt", "value": float("inf"), "source_id": "raw-debt", "source_type": "sec_companyfacts"},
            {"metric": "price", "value": 10, "source_id": "raw-price", "source_type": "market_snapshot", "currency": "USD"},
            {"metric": "shares_outstanding", "value": 100, "source_id": "raw-shares", "source_type": "market_snapshot"},
        ]

        packet = self._build(snapshot=snapshot)

        fact_metrics = {fact["metric"] for fact in packet["facts"]}
        self.assertEqual(fact_metrics, {"price", "shares_outstanding"})
        calculations = {item["metric"]: item for item in packet["deterministic_calculations"]}
        self.assertIn("market_cap", calculations)
        for metric in ("ps", "pe", "ev_ebitda", "enterprise_value"):
            self.assertNotIn(metric, calculations)
        json.dumps(packet, allow_nan=False)

    def test_single_utc_timestamp_drives_packet_and_filename(self) -> None:
        supplied = datetime(2026, 7, 19, 9, 2, 3, 987654, tzinfo=timezone(timedelta(hours=8)))
        with tempfile.TemporaryDirectory() as temporary:
            packet, path = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=Path(temporary),
                command="valuation US.ACME", provider_snapshot=self._snapshot(), now=supplied,
            )
            self.assertEqual(packet["input"]["created_at"], "2026-07-19T01:02:03+00:00")
            self.assertEqual(path.name, "ACME_US_valuation_20260719T010203Z.json")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build_valuation_artifact(
                    self._context(), symbol="ACME", market="US", output_dir=Path(temporary),
                    command="valuation US.ACME", provider_snapshot=self._snapshot(),
                    now=datetime(2026, 7, 19, 1, 2, 3),
                )

    def test_fact_and_source_ids_are_stable_opaque_and_all_refs_resolve(self) -> None:
        first_snapshot = self._snapshot()
        second_snapshot = self._snapshot()
        for index, fact in enumerate(first_snapshot["facts"]):
            fact["source_id"] = f"Bearer secret/{index}"
        for index, fact in enumerate(second_snapshot["facts"]):
            fact["source_id"] = f"https://evil.example/raw/{index}"

        first = self._build(snapshot=first_snapshot)
        second = self._build(snapshot=second_snapshot)
        first_facts = {item["metric"]: item for item in first["facts"]}
        second_facts = {item["metric"]: item for item in second["facts"]}

        self.assertEqual(
            {metric: item["id"] for metric, item in first_facts.items()},
            {metric: item["id"] for metric, item in second_facts.items()},
        )
        self.assertEqual(
            {metric: item["source_id"] for metric, item in first_facts.items()},
            {metric: item["source_id"] for metric, item in second_facts.items()},
        )
        for fact in first_facts.values():
            self.assertRegex(fact["id"], r"^fact:[a-z_]+$")
            self.assertRegex(fact["source_id"], r"^source:[0-9a-f]{16}$")
        self._assert_public_refs_resolve(build_valuation_artifact_evidence(first))

    def test_evidence_preserves_resolvable_provenance_for_hostile_raw_source_ids(self) -> None:
        snapshot = self._snapshot()
        for index, fact in enumerate(snapshot["facts"]):
            fact["source_id"] = f"../private/{index}/Bearer-PROVENANCE-SENTINEL"

        evidence = build_valuation_artifact_evidence(self._build(snapshot=snapshot))
        serialized = json.dumps(evidence)

        self._assert_public_refs_resolve(evidence)
        self.assertIn("source_registry", evidence["source_coverage"])
        self.assertNotIn("PROVENANCE-SENTINEL", serialized)
        self.assertNotIn("../private", serialized)

    def test_scoring_reads_only_declared_stock_fields_and_cites_exact_field(self) -> None:
        context = self._context()
        context["stock"]["core_business"] = "A cyclical memory manufacturer."
        context["stock"]["stock_character"] = "Established cash generator."
        context["untrusted_notes"] = "growth TAM asset holding segment AI"

        packet = self._build(context=context)
        scores = {item["id"]: item for item in packet["internal_frame_scores"]}

        self.assertIn("packet:stock:core_business", scores["cyclical"]["input_refs"])
        self.assertNotIn("packet:stock:stock_character", scores["cyclical"]["input_refs"])
        for frame in ("growth_scenario", "sotp_asset_value"):
            self.assertFalse(any(ref.startswith("packet:stock:") for ref in scores[frame]["input_refs"]))

    def test_card_and_evidence_share_the_same_safe_public_projection(self) -> None:
        packet = self._build()
        calculation = next(item for item in packet["deterministic_calculations"] if item["metric"] == "ps")
        calculation["display_value"] = "https://evil.example/PRIVATE-CARD-SENTINEL"
        packet["stock"]["name"] = "Bearer PRIVATE-CARD-SENTINEL"

        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)
        projected_ps = next(item for item in evidence["deterministic_calculations"] if item["metric"] == "ps")

        self.assertEqual(projected_ps["display_value"], "1.0x")
        self.assertIn("P/S: 1.0x", card)
        self.assertNotIn("PRIVATE-CARD-SENTINEL", json.dumps(evidence))
        self.assertNotIn("PRIVATE-CARD-SENTINEL", card)
        self.assertNotIn("evil.example", card)
        self.assertNotIn("Cyclical semiconductor business with growth optionality", json.dumps(evidence))
        self.assertNotIn("Cyclical semiconductor business with growth optionality", card)

    def test_public_projection_preserves_assumptions_interpretation_watch_and_degraded_sections(self) -> None:
        packet = self._build()

        evidence = build_valuation_artifact_evidence(packet)
        card = render_valuation_card(packet)

        for key in ("assumptions", "interpretation", "watch_items", "degraded_state", "selected_frames", "internal_frame_scores"):
            self.assertIn(key, evidence)
        self.assertEqual(evidence["assumptions"]["user_confirmed_valuation_case"], True)
        self.assertGreater(len(evidence["interpretation"]), 0)
        self.assertGreater(len(evidence["watch_items"]), 0)
        for heading in ("Assumptions:", "Interpretation:", "Watch items:", "Data gaps:"):
            self.assertIn(heading, card)

    def test_latest_loader_rejects_nonfinite_or_unresolved_packet_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            packet, _ = build_valuation_artifact(
                self._context(), symbol="ACME", market="US", output_dir=output_dir,
                command="valuation US.ACME", provider_snapshot=self._snapshot(),
                now=datetime(2026, 7, 19, 1, 2, 3, tzinfo=timezone.utc),
            )
            latest = output_dir / "valuation" / "ACME_US_valuation_latest.json"
            unsafe_number = json.loads(json.dumps(packet))
            unsafe_number["facts"][0]["value"] = float("nan")
            latest.write_text(json.dumps(unsafe_number), encoding="utf-8")
            self.assertIsNone(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir))

            unresolved = json.loads(json.dumps(packet))
            unresolved["deterministic_calculations"][0]["input_refs"] = ["fact:not_emitted"]
            latest.write_text(json.dumps(unresolved), encoding="utf-8")
            self.assertIsNone(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir))

            unsafe = json.loads(json.dumps(packet))
            unsafe["facts"][0]["provider_explanation"] = "https://evil.example/../raw-diagnostic"
            latest.write_text(json.dumps(unsafe), encoding="utf-8")
            self.assertIsNone(load_latest_valuation_artifact(symbol="ACME", market="US", output_dir=output_dir))


if __name__ == "__main__":
    unittest.main()
