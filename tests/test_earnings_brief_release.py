from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest


class EarningsBriefReleaseTests(unittest.TestCase):
    def test_canonical_release_is_reviewed_and_every_fact_is_sourced(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import load_release

        release = load_release("US.AAPL", "FY2025-Q1")

        self.assertEqual("earnings-brief:US.AAPL:FY2025-Q1:v1", release["release_id"])
        self.assertEqual("published", release["review_state"])
        source_ids = {item["source_id"] for item in release["sources"]}
        facts = [
            *release["brief"]["kpis"],
            *release["brief"]["quarterly_trends"],
            *release["brief"]["revenue_mix"],
        ]
        claims = [
            release["brief"]["judgment"],
            *release["brief"]["management_signals"],
            *release["brief"]["market_focus"],
            *release["brief"]["structural_signals"],
        ]
        for item in [*facts, *claims]:
            with self.subTest(item=item["id"]):
                self.assertIn(item["evidence_state"], {"available", "not_disclosed"})
                self.assertTrue(item["as_of"])
                self.assertTrue(set(item["source_ids"]).issubset(source_ids))
                if item["evidence_state"] == "available":
                    self.assertTrue(item["source_ids"])

    def test_non_available_numeric_field_cannot_carry_a_value(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            EarningsBriefReleaseError,
            validate_release,
        )

        payload = self._payload()
        payload["brief"]["kpis"][0]["evidence_state"] = "missing"

        with self.assertRaisesRegex(EarningsBriefReleaseError, "non-available field"):
            validate_release(payload)

    def test_available_numeric_field_requires_decimal_value(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            EarningsBriefReleaseError,
            validate_release,
        )

        payload = self._payload()
        payload["brief"]["kpis"][0].pop("value")

        with self.assertRaisesRegex(EarningsBriefReleaseError, "numeric field requires"):
            validate_release(payload)

    def test_non_available_numeric_field_cannot_keep_numeric_display(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            EarningsBriefReleaseError,
            validate_release,
        )

        payload = self._payload()
        field = payload["brief"]["kpis"][0]
        field["value"] = None
        field["evidence_state"] = "missing"

        with self.assertRaisesRegex(EarningsBriefReleaseError, "non-available field"):
            validate_release(payload)

    def test_conflict_requires_candidates_and_no_canonical_value(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            EarningsBriefReleaseError,
            validate_release,
        )

        payload = self._payload()
        field = payload["brief"]["kpis"][0]
        field["evidence_state"] = "conflict"
        field["value"] = None
        field["display"] = None
        field["candidates"] = []

        with self.assertRaisesRegex(EarningsBriefReleaseError, "conflict candidates"):
            validate_release(payload)

    def test_derived_field_result_matches_declared_inputs(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            EarningsBriefReleaseError,
            validate_release,
        )

        payload = self._payload()
        derived = next(item for item in payload["brief"]["kpis"] if item.get("formula"))
        derived["value"] = "99.9"

        with self.assertRaisesRegex(EarningsBriefReleaseError, "derived value"):
            validate_release(payload)

    def test_public_projection_is_bounded_and_excludes_source_hashes(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            build_public_projection,
            load_release,
        )

        projection = build_public_projection(load_release("US.AAPL", "FY2025-Q1"))
        serialized = json.dumps(projection)

        self.assertEqual("earnings_brief_public.v1", projection["schema_version"])
        self.assertLess(len(serialized.encode("utf-8")), 1024 * 1024)
        self.assertNotIn("content_hash", serialized)
        self.assertNotIn("/var/", serialized)
        self.assertNotIn("twitter", serialized.lower())

    def test_unknown_nested_key_is_rejected_before_public_projection(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            EarningsBriefReleaseError,
            validate_release,
        )

        payload = self._payload()
        payload["brief"]["access_token"] = "must-never-project"

        with self.assertRaisesRegex(EarningsBriefReleaseError, "brief keys"):
            validate_release(payload)

    def test_sensitive_or_internal_string_is_rejected_inside_allowed_field(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            EarningsBriefReleaseError,
            validate_release,
        )

        payload = self._payload()
        payload["brief"]["judgment"]["text"] = "Read /Users/example/private/raw_document_body"

        with self.assertRaisesRegex(EarningsBriefReleaseError, "unsafe content"):
            validate_release(payload)

    def test_flow_values_are_sourced_metrics_and_margin_has_comparative_trend(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import load_release

        release = load_release("US.AAPL", "FY2025-Q1")
        kpi_ids = {item["id"] for item in release["brief"]["kpis"]}

        self.assertTrue(
            {
                release["brief"]["financial_flow"]["cost_of_sales_id"],
                release["brief"]["financial_flow"]["operating_expenses_id"],
            }.issubset(kpi_ids)
        )
        self.assertEqual(2, len(release["brief"]["gross_margin_trends"]))

    def test_catalog_resolves_only_exact_supported_selector(self) -> None:
        from investment_knowledge_mcp.earnings_brief_studio.release import (
            EarningsBriefNotFound,
            list_catalog,
            load_release,
        )

        self.assertEqual(
            [("US.AAPL", "FY2025-Q1")],
            [(item["company_id"], item["period_id"]) for item in list_catalog()],
        )
        with self.assertRaises(EarningsBriefNotFound):
            load_release("US.INTC", "2026-Q2")

    @staticmethod
    def _payload() -> dict[str, object]:
        path = (
            Path(__file__).parents[1]
            / "investment_knowledge_mcp"
            / "earnings_brief_studio"
            / "releases"
            / "2026-07-24.apple-fy2025-q1.v1.json"
        )
        return copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
