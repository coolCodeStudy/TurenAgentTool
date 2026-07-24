from __future__ import annotations

import ast
import copy
import dataclasses
import json
from pathlib import Path
import re
import unittest
from unittest import mock

from investment_knowledge_mcp.ai_industry_panorama.release import (
    PanoramaReleaseError,
    build_public_projection,
    diff_releases,
    load_release,
    validate_release,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "investment_knowledge_mcp" / "ai_industry_panorama"
CANONICAL_RELEASE = PACKAGE / "releases" / "2026-07-24.v1.json"


def canonical_payload() -> dict[str, object]:
    return json.loads(CANONICAL_RELEASE.read_text(encoding="utf-8"))


def next_release_payload(previous: object) -> dict[str, object]:
    payload = canonical_payload()
    payload["release_id"] = "ai-industry-panorama.2026-07-25.v2"
    payload["prior_release_id"] = previous.release_id
    payload["published_at"] = "2026-07-25T00:00:00Z"
    payload["evidence_cutoff"] = "2026-07-25"
    payload["change_summary"] = ["Test-only correction to one reviewed assertion."]
    assertion = payload["assertions"][0]
    assertion["text"] = f'{assertion["text"]} Reviewed without changing classification.'
    payload["release_diff"] = {
        "added": [],
        "changed": [assertion["assertion_id"]],
        "expired": [],
        "removed": [],
        "reasons": {
            assertion["assertion_id"]: "Test-only assertion wording correction.",
        },
    }
    return payload


class PanoramaReleaseTests(unittest.TestCase):
    def test_canonical_release_has_reviewed_manifest_counts(self) -> None:
        release = load_release()
        covered_entities = [
            entity
            for entity in release.entities
            if entity.kind in {"organization", "project"}
        ]

        self.assertEqual(6, len(release.taxonomy))
        self.assertEqual(35, len(release.entities))
        self.assertEqual(25, len(covered_entities))
        self.assertEqual(48, len(release.relationships))
        self.assertEqual(48, len(release.assertions))
        self.assertEqual(48, len(release.evidence))
        self.assertEqual(16, len(release.sources))
        self.assertEqual(6, sum(entity.is_demand_anchor for entity in release.entities))
        self.assertEqual("published", release.review_state)
        self.assertNotEqual(release.curator, release.reviewer)

    def test_release_and_nested_records_are_frozen(self) -> None:
        release = load_release()

        with self.assertRaises(dataclasses.FrozenInstanceError):
            release.review_state = "draft"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            release.entities[0].label = "changed"

    def test_first_release_diff_contains_every_admitted_stable_id(self) -> None:
        release = load_release()
        stable_ids = {
            *(item.taxonomy_id for item in release.taxonomy),
            *(item.geography_id for item in release.geographies),
            *(item.entity_id for item in release.entities),
            *(item.source_id for item in release.sources),
            *(item.evidence_id for item in release.evidence),
            *(item.relationship_id for item in release.relationships),
            *(item.assertion_id for item in release.assertions),
        }

        self.assertEqual(stable_ids, set(release.release_diff.added))
        self.assertEqual((), release.release_diff.changed)
        self.assertEqual((), release.release_diff.expired)
        self.assertEqual((), release.release_diff.removed)
        self.assertEqual({}, release.release_diff.reasons)
        self.assertEqual(
            {
                "added": sorted(stable_ids),
                "changed": [],
                "expired": [],
                "removed": [],
                "reasons": {},
            },
            diff_releases(None, release),
        )

    def test_six_demand_anchors_have_supported_two_hop_paths(self) -> None:
        release = load_release()
        outgoing: dict[str, set[str]] = {}
        for relationship in release.relationships:
            outgoing.setdefault(relationship.source_entity_id, set()).add(
                relationship.target_entity_id
            )

        for anchor in (entity for entity in release.entities if entity.is_demand_anchor):
            first_hop = outgoing.get(anchor.entity_id, set())
            second_hop = {
                target
                for intermediate in first_hop
                for target in outgoing.get(intermediate, set())
            }
            self.assertTrue(second_hop, anchor.entity_id)

    def test_inference_requires_visible_derivation(self) -> None:
        payload = canonical_payload()
        inferred = next(
            item
            for item in payload["assertions"]
            if item["assertion_kind"] == "inferred_exposure"
        )
        inferred["premise_assertion_ids"] = []

        with self.assertRaisesRegex(PanoramaReleaseError, "inference derivation"):
            validate_release(payload)

    def test_inference_premises_must_be_non_inferred_reviewed_assertions(self) -> None:
        payload = canonical_payload()
        inferred = next(
            item
            for item in payload["assertions"]
            if item["assertion_kind"] == "inferred_exposure"
        )
        inferred["premise_assertion_ids"] = [inferred["assertion_id"]]

        with self.assertRaisesRegex(PanoramaReleaseError, "inference derivation"):
            validate_release(payload)

    def test_inference_and_premises_resolve_both_reviewed_source_paths(self) -> None:
        release = load_release()
        assertions = {item.assertion_id: item for item in release.assertions}
        evidence = {item.evidence_id: item for item in release.evidence}
        inference = next(
            item
            for item in release.assertions
            if item.assertion_kind == "inferred_exposure"
        )
        assertion_ids = {inference.assertion_id, *inference.premise_assertion_ids}
        source_ids = {
            evidence[evidence_id].source_id
            for assertion_id in assertion_ids
            for evidence_id in assertions[assertion_id].evidence_ids
        }

        self.assertEqual(
            {"source:SRC-003", "source:SRC-016"},
            source_ids,
        )
        inference_evidence = evidence[inference.evidence_ids[0]]
        self.assertIn("premise assertions", inference_evidence.locator)

    def test_confidence_label_is_derived_from_structured_inputs(self) -> None:
        payload = canonical_payload()
        payload["assertions"][0]["confidence_label"] = "high"

        with self.assertRaisesRegex(PanoramaReleaseError, "confidence label"):
            validate_release(payload)

    def test_published_assertion_requires_reviewed_evidence(self) -> None:
        payload = canonical_payload()
        payload["evidence"][0]["review_state"] = "curated_pending_review"

        with self.assertRaisesRegex(PanoramaReleaseError, "reviewed evidence"):
            validate_release(payload)

    def test_unknown_keys_and_credential_looking_fields_are_rejected(self) -> None:
        payload = canonical_payload()
        payload["entities"][0]["api_token"] = "not-a-real-secret"

        with self.assertRaisesRegex(PanoramaReleaseError, "unknown keys"):
            validate_release(payload)

    def test_invalid_foreign_key_and_unsafe_source_url_are_rejected(self) -> None:
        payload = canonical_payload()
        payload["relationships"][0]["target_entity_id"] = "entity:missing"
        with self.assertRaisesRegex(PanoramaReleaseError, "foreign key"):
            validate_release(payload)

        payload = canonical_payload()
        payload["sources"][0]["url"] = "http://example.com/source"
        with self.assertRaisesRegex(PanoramaReleaseError, "HTTPS"):
            validate_release(payload)

    def test_unsafe_research_link_is_rejected(self) -> None:
        payload = canonical_payload()
        payload["entities"][0]["research_links"] = [
            {
                "kind": "stock_research",
                "label": "Unsafe",
                "canonical_stock_id": "GOOGL:US",
                "internal_path": "/admin",
                "command_hint": "execute now",
            }
        ]

        with self.assertRaisesRegex(PanoramaReleaseError, "research link"):
            validate_release(payload)

    def test_duplicate_json_keys_are_rejected_by_loader(self) -> None:
        raw = CANONICAL_RELEASE.read_text(encoding="utf-8")
        duplicate = raw.replace(
            '"schema_version": "ai_industry_panorama_release.v1",',
            '"schema_version": "ai_industry_panorama_release.v1", '
            '"schema_version": "ai_industry_panorama_release.v1",',
            1,
        )
        path = self._temp_file(duplicate)

        with self.assertRaisesRegex(PanoramaReleaseError, "duplicate JSON key"):
            load_release(path)

    def test_second_fixture_produces_diff_without_mutating_history(self) -> None:
        previous_bytes = CANONICAL_RELEASE.read_bytes()
        previous = load_release()
        current = validate_release(next_release_payload(previous), previous=previous)
        change = diff_releases(previous, current)

        self.assertEqual([previous.assertions[0].assertion_id], change["changed"])
        self.assertEqual([], change["removed"])
        self.assertEqual(previous_bytes, CANONICAL_RELEASE.read_bytes())

    def test_prior_release_is_required_and_must_match(self) -> None:
        previous = load_release()
        payload = next_release_payload(previous)

        with self.assertRaisesRegex(PanoramaReleaseError, "prior release"):
            validate_release(payload)

        mismatched = copy.deepcopy(payload)
        mismatched["prior_release_id"] = "ai-industry-panorama.missing"
        with self.assertRaisesRegex(PanoramaReleaseError, "prior release"):
            validate_release(mismatched, previous=previous)

    def test_same_release_id_cannot_be_reused_with_changed_content(self) -> None:
        previous = load_release()
        payload = canonical_payload()
        payload["change_summary"] = ["mutated under the same release ID"]

        with self.assertRaisesRegex(PanoramaReleaseError, "release ID reuse"):
            validate_release(payload, previous=previous)

    def test_projection_is_bounded_allow_list_with_one_assertion_per_edge(self) -> None:
        projection = build_public_projection(load_release())
        self.assertEqual(
            {
                "ok",
                "schema_version",
                "release",
                "taxonomy",
                "entities",
                "relationships",
                "evidence",
                "sources",
                "facets",
            },
            set(projection),
        )
        self.assertEqual("ai_industry_panorama_public.v1", projection["schema_version"])
        self.assertLessEqual(
            len(
                json.dumps(
                    projection,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ),
            2 * 1024 * 1024,
        )
        self.assertEqual(48, len(projection["relationships"]))
        self.assertTrue(
            all(
                "assertion_id" in item and "assertions" not in item
                for item in projection["relationships"]
            )
        )
        serialized = json.dumps(projection)
        self.assertNotIn("curator", serialized)
        self.assertNotIn("reviewer", serialized)
        self.assertNotIn("supersedes_assertion_id", serialized)

    def test_zero_or_multiple_active_assertions_for_relationship_is_rejected(self) -> None:
        payload = canonical_payload()
        payload["assertions"][0]["review_state"] = "superseded"
        with self.assertRaisesRegex(PanoramaReleaseError, "active assertion"):
            validate_release(payload)

        payload = canonical_payload()
        duplicate = copy.deepcopy(payload["assertions"][0])
        duplicate["assertion_id"] = "assertion:AST-AIP-9999"
        payload["assertions"].append(duplicate)
        payload["release_diff"]["added"].append(duplicate["assertion_id"])
        with self.assertRaisesRegex(PanoramaReleaseError, "active assertion"):
            validate_release(payload)

    def test_domain_has_no_forbidden_imports_or_calls(self) -> None:
        forbidden = {
            "repository",
            "portfolio_graph",
            "stock_valuation",
            "candidate_insights",
            "scheduler_jobs",
            "daily_market_jobs",
            "research.jobs",
        }
        for path in PACKAGE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            self.assertFalse(
                any(any(part in name for part in forbidden) for name in imported),
                f"forbidden dependency in {path}: {sorted(imported)}",
            )

    def test_canonical_stable_ids_equal_reviewed_manifest_rows(self) -> None:
        manifest = (
            ROOT
            / "docs"
            / "changes"
            / "ai-industry-panorama"
            / "v1-source-manifest.md"
        ).read_text(encoding="utf-8")
        release = load_release()

        expected_by_prefix = {
            "entity": set(re.findall(r"^\| (ENT-[A-Z0-9-]+) \|", manifest, re.MULTILINE)),
            "source": set(re.findall(r"^\| (SRC-\d{3}) \|", manifest, re.MULTILINE)),
            "relationship": set(
                re.findall(r"^\| (REL-AIP-\d{4}) \|", manifest, re.MULTILINE)
            ),
            "assertion": set(re.findall(r"\| (AST-AIP-\d{4}) \|", manifest)),
            "evidence": set(re.findall(r"\| (EVD-AIP-\d{4}) \|", manifest)),
        }
        actual_by_prefix = {
            "entity": {item.entity_id.split(":", 1)[1] for item in release.entities},
            "source": {item.source_id.split(":", 1)[1] for item in release.sources},
            "relationship": {
                item.relationship_id.split(":", 1)[1] for item in release.relationships
            },
            "assertion": {
                item.assertion_id.split(":", 1)[1] for item in release.assertions
            },
            "evidence": {
                item.evidence_id.split(":", 1)[1] for item in release.evidence
            },
        }

        self.assertEqual(expected_by_prefix, actual_by_prefix)
        reviewed_rows = re.findall(
            r"^\| REL-AIP-\d{4} .+ \| (reviewed_for_implementation) \|$",
            manifest,
            re.MULTILINE,
        )
        self.assertEqual(48, len(reviewed_rows))

    def test_release_operations_do_not_touch_existing_domain_entrypoints(self) -> None:
        targets = [
            "investment_knowledge_mcp.repository.get_stock_context",
            "investment_knowledge_mcp.repository.record_user_insight",
            "investment_knowledge_mcp.portfolio_graph.build_portfolio_graph_queue",
            "investment_knowledge_mcp.stock_valuation.load_latest_valuation_artifact",
            "investment_knowledge_mcp.repository.create_coding_task",
        ]
        patches = [
            mock.patch(target, side_effect=AssertionError(f"unexpected call: {target}"))
            for target in targets
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        release = load_release()
        self.assertTrue(build_public_projection(release)["ok"])

    def _temp_file(self, content: str) -> Path:
        from tempfile import NamedTemporaryFile

        handle = NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".json")
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        with handle:
            handle.write(content)
        return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
