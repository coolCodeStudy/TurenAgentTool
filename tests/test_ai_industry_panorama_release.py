from __future__ import annotations

import ast
import copy
import dataclasses
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping
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


def plain_record(value: object) -> object:
    if dataclasses.is_dataclass(value):
        return {
            field.name: plain_record(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {key: plain_record(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain_record(item) for item in value]
    return value


def replace_confidence_input(
    assertion: dict[str, object],
    key: str,
    value: str,
) -> None:
    confidence = dict(assertion["confidence_inputs"])
    confidence[key] = value
    assertion["confidence_inputs"] = [
        [name, confidence[name]] for name in sorted(confidence)
    ]
    assertion["confidence_rationale"] = "; ".join(
        f"{name}={confidence[name]}"
        for name in (
            "auth",
            "explicit",
            "corr",
            "time",
            "geo",
            "extraction",
            "conflict",
        )
    )


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

    def test_canonical_release_preserves_reviewed_year_and_unknown_geography(self) -> None:
        release = load_release()
        assertions = {item.assertion_id: item for item in release.assertions}
        sources = {item.source_id: item for item in release.sources}

        for assertion_id in ("assertion:AST-AIP-0015", "assertion:AST-AIP-0028"):
            with self.subTest(assertion_id=assertion_id):
                assertion = assertions[assertion_id]
                self.assertEqual("2027", assertion.effective_from)
                self.assertEqual("year", assertion.time_precision)
        for assertion_id in ("assertion:AST-AIP-0015", "assertion:AST-AIP-0016"):
            with self.subTest(assertion_id=assertion_id):
                self.assertEqual(
                    (("geography:unknown", "cloud-capacity provider to demand anchor"),),
                    assertions[assertion_id].geography_roles,
                )
        self.assertIsNone(sources["source:SRC-016"].publication_date)

    def test_canonical_payload_round_trips_without_field_loss(self) -> None:
        payload = canonical_payload()
        release = validate_release(payload)

        self.assertEqual(payload, plain_record(release))
        self.assertIsInstance(release.release_diff.reasons, MappingProxyType)

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

    def test_confidence_inputs_are_exact_and_evidence_derived(self) -> None:
        mutations = []

        payload = canonical_payload()
        payload["assertions"][0]["confidence_inputs"][0][0] = "authority"
        mutations.append(("keys", payload))

        payload = canonical_payload()
        payload["assertions"][0]["confidence_inputs"][0][1] = "T1 regulator filing"
        mutations.append(("authority tier", payload))

        payload = canonical_payload()
        payload["assertions"][0]["confidence_inputs"][4][1] = (
            "manual derivation unreviewed"
        )
        mutations.append(("extraction shape", payload))

        payload = canonical_payload()
        inferred = next(
            item
            for item in payload["assertions"]
            if item["assertion_kind"] == "inferred_exposure"
        )
        confidence = dict(inferred["confidence_inputs"])
        confidence["corr"] = "single primary"
        inferred["confidence_inputs"] = [
            [key, confidence[key]] for key in sorted(confidence)
        ]
        mutations.append(("inference corroboration", payload))

        payload = canonical_payload()
        payload["assertions"][0]["confidence_inputs"][1][1] = "contradicted"
        mutations.append(("conflict", payload))

        payload = canonical_payload()
        confidence = dict(payload["assertions"][0]["confidence_inputs"])
        confidence["geo"] = "specific"
        payload["assertions"][0]["confidence_inputs"] = [
            [key, confidence[key]] for key in sorted(confidence)
        ]
        payload["assertions"][0]["confidence_rationale"] = "; ".join(
            f"{key}={confidence[key]}"
            for key in (
                "auth",
                "explicit",
                "corr",
                "time",
                "geo",
                "extraction",
                "conflict",
            )
        )
        mutations.append(("geography relationship", payload))

        payload = canonical_payload()
        payload["assertions"][0]["geography_roles"] = []
        mutations.append(("missing geography role", payload))

        for label, mutation in mutations:
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    PanoramaReleaseError,
                    "confidence",
                ):
                    validate_release(mutation)

    def test_confidence_authority_is_exactly_derived_from_source_role(self) -> None:
        payload = canonical_payload()
        replace_confidence_input(
            payload["assertions"][0],
            "auth",
            "T2 company announcement",
        )

        with self.assertRaisesRegex(PanoramaReleaseError, "confidence authority"):
            validate_release(payload)

    def test_single_primary_requires_exactly_one_resolved_source(self) -> None:
        payload = canonical_payload()
        payload["assertions"][0]["evidence_ids"].append("evidence:EVD-AIP-0005")

        with self.assertRaisesRegex(
            PanoramaReleaseError,
            "confidence corroboration",
        ):
            validate_release(payload)

    def test_confidence_explicitness_is_limited_to_reviewed_categories(self) -> None:
        payload = canonical_payload()
        replace_confidence_input(
            payload["assertions"][0],
            "explicit",
            "arbitrary source prose",
        )

        with self.assertRaisesRegex(
            PanoramaReleaseError,
            "confidence explicit",
        ):
            validate_release(payload)

    def test_inference_confidence_requires_exact_premise_source_set(self) -> None:
        payload = canonical_payload()
        inferred = next(
            item
            for item in payload["assertions"]
            if item["assertion_kind"] == "inferred_exposure"
        )
        inferred["premise_assertion_ids"] = [
            "assertion:AST-AIP-0014",
            "assertion:AST-AIP-0045",
        ]

        with self.assertRaisesRegex(PanoramaReleaseError, "confidence authority"):
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

    def test_load_release_supports_v3_with_immediate_v2_snapshot(self) -> None:
        v1 = load_release()
        v2_payload = next_release_payload(v1)
        v2 = validate_release(v2_payload, previous=v1)
        v3_payload = copy.deepcopy(v2_payload)
        v3_payload["release_id"] = "ai-industry-panorama.2026-07-26.v3"
        v3_payload["prior_release_id"] = v2.release_id
        v3_payload["published_at"] = "2026-07-26T00:00:00Z"
        v3_payload["evidence_cutoff"] = "2026-07-26"
        v3_payload["change_summary"] = ["Test-only third release."]
        changed = v3_payload["assertions"][1]
        changed["text"] = f'{changed["text"]} Third-release review.'
        v3_payload["release_diff"] = {
            "added": [],
            "changed": [changed["assertion_id"]],
            "expired": [],
            "removed": [],
            "reasons": {
                changed["assertion_id"]: "Test-only third-release correction.",
            },
        }
        v2_path = self._temp_file(json.dumps(v2_payload))
        v3_path = self._temp_file(json.dumps(v3_payload))

        loaded = load_release(v3_path, prior_path=v2_path)

        self.assertEqual(v3_payload, plain_record(loaded))
        self.assertEqual(v2.release_id, loaded.prior_release_id)

    def test_relationship_identity_cannot_change_across_releases(self) -> None:
        previous = load_release()
        for field, value in (
            ("source_entity_id", "entity:ENT-ORG-WISTRON"),
            ("target_entity_id", "entity:ENT-ORG-MICRON"),
            ("relationship_type", "partners_with"),
        ):
            payload = next_release_payload(previous)
            relationship = payload["relationships"][45]
            relationship[field] = value
            changed_ids = sorted(
                {
                    payload["assertions"][0]["assertion_id"],
                    relationship["relationship_id"],
                }
            )
            payload["release_diff"]["changed"] = changed_ids
            payload["release_diff"]["reasons"][
                relationship["relationship_id"]
            ] = "Test-only relationship identity mutation."
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    PanoramaReleaseError,
                    "relationship identity",
                ):
                    validate_release(payload, previous=previous)

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

    def test_taxonomy_freshness_capability_and_time_enums_are_bounded(self) -> None:
        mutations = []

        payload = canonical_payload()
        payload["taxonomy"][0]["layer"] = "layer-99"
        mutations.append(("taxonomy layer", payload))

        payload = canonical_payload()
        payload["entities"][0]["freshness_state"] = "fresh"
        mutations.append(("entity freshness", payload))

        payload = canonical_payload()
        payload["assertions"][0]["freshness_state"] = "fresh"
        mutations.append(("assertion freshness", payload))

        payload = canonical_payload()
        payload["assertions"][0]["time_precision"] = "quarter-ish"
        mutations.append(("time precision", payload))

        payload = canonical_payload()
        capability = copy.deepcopy(
            next(item for item in payload["entities"] if item["kind"] == "capability")
        )
        capability["entity_id"] = "entity:ENT-CAP-EXTRA"
        capability["label"] = "Unreviewed extra capability"
        payload["entities"].append(capability)
        payload["release_diff"]["added"].append(capability["entity_id"])
        payload["release_diff"]["added"].sort()
        mutations.append(("capability maximum", payload))

        for label, mutation in mutations:
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    PanoramaReleaseError,
                    "taxonomy|freshness|time precision|capability",
                ):
                    validate_release(mutation)

    def test_temporal_precision_and_ranges_are_consistent(self) -> None:
        mutations = []

        payload = canonical_payload()
        payload["assertions"][0]["effective_to"] = "2025-01-01"
        mutations.append(("reversed effective range", payload))

        payload = canonical_payload()
        period = next(
            item
            for item in payload["assertions"]
            if item["time_precision"] == "reporting_period"
        )
        period["reporting_period_end"] = None
        mutations.append(("incomplete reporting period", payload))

        payload = canonical_payload()
        payload["assertions"][0]["time_precision"] = "year"
        mutations.append(("year with day value", payload))

        for label, mutation in mutations:
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    PanoramaReleaseError,
                    "time|reporting|effective",
                ):
                    validate_release(mutation)

    def test_supersession_reference_must_exist_be_nonself_and_same_relationship(
        self,
    ) -> None:
        for value in (
            "assertion:AST-AIP-9999",
            "assertion:AST-AIP-0001",
            "assertion:AST-AIP-0002",
        ):
            payload = canonical_payload()
            payload["assertions"][0]["supersedes_assertion_id"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(PanoramaReleaseError, "supersed"):
                    validate_release(payload)

    def test_source_urls_and_valid_fields_reject_credentials(self) -> None:
        mutations = []

        payload = canonical_payload()
        payload["sources"][0]["url"] = "https://user:password@example.com/source"
        mutations.append(("userinfo", payload))

        payload = canonical_payload()
        payload["sources"][0]["url"] = "https://example.com/source?api_key=secret"
        mutations.append(("sensitive query", payload))

        payload = canonical_payload()
        payload["sources"][0]["publisher"] = "token=private-value"
        mutations.append(("credential-looking value", payload))

        for label, mutation in mutations:
            with self.subTest(label=label):
                with self.assertRaisesRegex(PanoramaReleaseError, "credential"):
                    validate_release(mutation)

    def test_source_publication_date_preserves_explicit_undated_state(self) -> None:
        payload = canonical_payload()
        payload["sources"][0]["publication_date"] = None
        with self.assertRaisesRegex(PanoramaReleaseError, "publication date"):
            validate_release(payload)

        payload = canonical_payload()
        source = next(
            item
            for item in payload["sources"]
            if item["source_id"] == "source:SRC-016"
        )
        source["publication_date"] = source["retrieval_date"]
        with self.assertRaisesRegex(PanoramaReleaseError, "publication date"):
            validate_release(payload)

    def test_research_links_are_allowlisted_safe_and_nonexecuting(self) -> None:
        safe_link = {
            "kind": "research",
            "label": "NVIDIA research workspace",
            "canonical_stock_id": "US.NVDA",
            "internal_path": "/command",
            "command_hint": "Open the workspace and formulate a stock question.",
        }
        payload = canonical_payload()
        nvidia = next(
            item
            for item in payload["entities"]
            if item["entity_id"] == "entity:ENT-ORG-NVIDIA"
        )
        nvidia["research_links"] = [safe_link]
        self.assertEqual("published", validate_release(payload).review_state)

        mutations = []
        for entity_id in (
            "entity:ENT-CAP-HBM",
            "entity:ENT-ORG-OPENAI",
        ):
            payload = canonical_payload()
            entity = next(
                item for item in payload["entities"] if item["entity_id"] == entity_id
            )
            entity["research_links"] = [copy.deepcopy(safe_link)]
            mutations.append((entity_id, payload))

        for field, value in (
            ("canonical_stock_id", "US.AMZN"),
            ("canonical_stock_id", "NVDA"),
            ("kind", "external"),
            ("internal_path", "/command?run=valuation"),
            ("command_hint", "valuation US.NVDA"),
        ):
            payload = canonical_payload()
            entity = next(
                item
                for item in payload["entities"]
                if item["entity_id"] == "entity:ENT-ORG-NVIDIA"
            )
            link = copy.deepcopy(safe_link)
            link[field] = value
            entity["research_links"] = [link]
            mutations.append((field, payload))

        for label, mutation in mutations:
            with self.subTest(label=label):
                with self.assertRaisesRegex(PanoramaReleaseError, "research link"):
                    validate_release(mutation)

    def test_valuation_links_admit_only_supported_market_specific_ids(self) -> None:
        valid_links = (
            (
                "entity:ENT-ORG-NVIDIA",
                "US.NVDA",
            ),
            (
                "entity:ENT-ORG-SKHYNIX",
                "KR.000660",
            ),
        )
        for entity_id, stock_id in valid_links:
            with self.subTest(valid=stock_id):
                payload = canonical_payload()
                entity = next(
                    item
                    for item in payload["entities"]
                    if item["entity_id"] == entity_id
                )
                entity["research_links"] = [
                    {
                        "kind": "valuation",
                        "label": f"{entity['label']} valuation workspace",
                        "canonical_stock_id": stock_id,
                        "internal_path": "/command",
                        "command_hint": "Open the workspace and formulate a valuation question.",
                    }
                ]
                self.assertEqual("published", validate_release(payload).review_state)

        unsupported_links = (
            ("entity:ENT-ORG-HONHAI", "TW.2317"),
            ("entity:ENT-ORG-SCHNEIDER", "FR.SU"),
            ("entity:ENT-ORG-SOFTBANK", "JP.9984"),
        )
        for entity_id, stock_id in unsupported_links:
            with self.subTest(unsupported=stock_id):
                payload = canonical_payload()
                entity = next(
                    item
                    for item in payload["entities"]
                    if item["entity_id"] == entity_id
                )
                entity["research_links"] = [
                    {
                        "kind": "valuation",
                        "label": f"{entity['label']} valuation workspace",
                        "canonical_stock_id": stock_id,
                        "internal_path": "/command",
                        "command_hint": "Open the workspace and formulate a valuation question.",
                    }
                ]
                with self.assertRaisesRegex(
                    PanoramaReleaseError,
                    "research link",
                ):
                    validate_release(payload)

    def test_research_links_admit_reviewed_korean_public_ids(self) -> None:
        reviewed_links = (
            ("entity:ENT-ORG-SKHYNIX", "KR.000660"),
            ("entity:ENT-ORG-SAMSUNG", "KR.005930"),
        )
        for entity_id, stock_id in reviewed_links:
            with self.subTest(stock_id=stock_id):
                payload = canonical_payload()
                entity = next(
                    item
                    for item in payload["entities"]
                    if item["entity_id"] == entity_id
                )
                entity["research_links"] = [
                    {
                        "kind": "research",
                        "label": f"{entity['label']} research workspace",
                        "canonical_stock_id": stock_id,
                        "internal_path": "/command",
                        "command_hint": "Open the workspace and formulate a stock question.",
                    }
                ]

                try:
                    release = validate_release(payload)
                except PanoramaReleaseError as error:
                    self.fail(f"reviewed Korean research link was rejected: {error}")
                self.assertEqual("published", release.review_state)

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
