from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, TypeVar
from urllib.parse import parse_qsl, urlparse


class PanoramaReleaseError(ValueError):
    """Raised when a panorama release violates its public data contract."""


@dataclass(frozen=True)
class PanoramaTaxonomyNode:
    taxonomy_id: str
    parent_id: str | None
    label: str
    definition: str
    standards_context: str
    coverage_gaps: str
    layer: str
    sort_order: int


@dataclass(frozen=True)
class PanoramaGeography:
    geography_id: str
    label: str
    country_code: str | None
    region: str


@dataclass(frozen=True)
class PanoramaResearchLink:
    kind: str
    label: str
    canonical_stock_id: str
    internal_path: str
    command_hint: str


@dataclass(frozen=True)
class PanoramaEntity:
    entity_id: str
    kind: str
    label: str
    aliases: tuple[str, ...]
    summary: str
    taxonomy_ids: tuple[str, ...]
    geography_ids: tuple[str, ...]
    capability_roles: tuple[str, ...]
    coverage_gaps: str
    freshness_state: str
    last_reviewed_at: str
    is_demand_anchor: bool
    research_links: tuple[PanoramaResearchLink, ...]


@dataclass(frozen=True)
class PanoramaRelationship:
    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str


@dataclass(frozen=True)
class PanoramaAssertion:
    assertion_id: str
    relationship_id: str
    text: str
    assertion_kind: str
    lifecycle_state: str
    effective_from: str | None
    effective_to: str | None
    time_precision: str
    observed_at: str
    reporting_period_start: str | None
    reporting_period_end: str | None
    reviewed_at: str
    freshness_state: str
    geography_roles: tuple[tuple[str, str], ...]
    confidence_inputs: tuple[tuple[str, str], ...]
    confidence_rationale: str
    confidence_label: str
    limitations: str
    evidence_ids: tuple[str, ...]
    premise_assertion_ids: tuple[str, ...]
    review_state: str
    supersedes_assertion_id: str | None


@dataclass(frozen=True)
class PanoramaSourceSnapshot:
    source_id: str
    tier: str
    publisher: str
    document_title: str
    url: str
    publication_date: str | None
    retrieval_date: str
    immutable_locator: str
    content_hash: str
    license_class: str


@dataclass(frozen=True)
class PanoramaEvidence:
    evidence_id: str
    source_id: str
    locator: str
    bounded_excerpt: str
    extraction_method: str
    review_state: str


@dataclass(frozen=True)
class PanoramaReleaseDiff:
    added: tuple[str, ...]
    changed: tuple[str, ...]
    expired: tuple[str, ...]
    removed: tuple[str, ...]
    reasons: Mapping[str, str]


@dataclass(frozen=True)
class PanoramaRelease:
    schema_version: str
    release_id: str
    prior_release_id: str | None
    taxonomy_version: str
    published_at: str
    evidence_cutoff: str
    review_state: str
    change_summary: tuple[str, ...]
    release_diff: PanoramaReleaseDiff
    curator: str
    reviewer: str
    taxonomy: tuple[PanoramaTaxonomyNode, ...]
    geographies: tuple[PanoramaGeography, ...]
    entities: tuple[PanoramaEntity, ...]
    sources: tuple[PanoramaSourceSnapshot, ...]
    evidence: tuple[PanoramaEvidence, ...]
    relationships: tuple[PanoramaRelationship, ...]
    assertions: tuple[PanoramaAssertion, ...]


def compute_source_content_hash(
    source: PanoramaSourceSnapshot,
    evidence: tuple[PanoramaEvidence, ...],
) -> str:
    """Hash the canonical reviewed-evidence snapshot, not a remote page body.

    V1 has no acquisition step. The digest therefore covers the retained source
    metadata and reviewed evidence material that the release can reproduce.
    """

    source_material = {
        field.name: getattr(source, field.name)
        for field in fields(PanoramaSourceSnapshot)
        if field.name != "content_hash"
    }
    evidence_material = sorted(
        (
            {
                "evidence_id": item.evidence_id,
                "locator": item.locator,
                "bounded_excerpt": item.bounded_excerpt,
                "extraction_method": item.extraction_method,
                "review_state": item.review_state,
            }
            for item in evidence
        ),
        key=lambda item: item["evidence_id"],
    )
    digest = hashlib.sha256(
        _compact_json(
            {
                "source": source_material,
                "evidence": evidence_material,
            }
        )
    ).hexdigest()
    return f"sha256:{digest}"


def _source_authority_classification(
    source: PanoramaSourceSnapshot,
) -> str:
    source_kind = source.license_class.partition(";")[0].strip().lower()
    if source.tier == "T1" and source_kind == "regulator-hosted issuer filing":
        return "T1 regulator filing"
    if source.tier == "T3" and source_kind == "official program page":
        return "T3 official program"
    if source.tier == "T2":
        if source_kind in {
            "official earnings-call transcript",
            "official results release",
        }:
            return "T2 issuer IR"
        if source_kind in {
            "official annual-report chapter",
            "official annual-report web section",
        }:
            return "T2 issuer annual report"
        if source_kind in {
            "official results announcement",
            "official image/video media entry",
        }:
            return "T2 issuer newsroom"
        if source_kind == "official supplier announcement":
            return "T2 supplier announcement"
        if source_kind == "official company announcement":
            return "T2 company announcement"
    raise PanoramaReleaseError(
        "source authority classification is not admitted"
    )


_RELEASE_PATH = Path(__file__).parent / "releases" / "2026-07-24.v1.json"
_SCHEMA_VERSION = "ai_industry_panorama_release.v1"
_PUBLIC_SCHEMA_VERSION = "ai_industry_panorama_public.v1"
_MAX_PROJECTION_BYTES = 2 * 1024 * 1024

_ENTITY_KINDS = frozenset(
    {
        "organization",
        "project",
        "standards_program",
        "standard",
        "capability",
    }
)
_ASSERTION_KINDS = frozenset(
    {
        "disclosed_fact",
        "company_guidance",
        "management_claim",
        "inferred_exposure",
        "user_hypothesis",
    }
)
_LIFECYCLE_STATES = frozenset(
    {
        "announced",
        "operating",
        "committed",
        "under_development",
        "sampling",
        "mass_production",
        "qualification",
        "unknown",
    }
)
_GEOGRAPHY_ROLES = frozenset(
    {
        "headquarters",
        "demand_region",
        "deployment_region",
        "data_center_site",
        "project_site",
        "fab",
        "packaging_test",
        "equipment_component_manufacturing",
        "grid_utility_region",
        "global_scope",
        "unknown",
    }
)
_REVIEW_STATES = frozenset(
    {
        "curated_pending_review",
        "reviewed_for_implementation",
        "published",
        "superseded",
    }
)
_SOURCE_TIERS = frozenset({"T1", "T2", "T3"})
_TAXONOMY_LAYERS = {
    "taxonomy:TAX-01": "layer-01",
    "taxonomy:TAX-02": "layer-02",
    "taxonomy:TAX-03": "layer-03",
    "taxonomy:TAX-04": "layer-04",
    "taxonomy:TAX-05": "layer-05",
    "taxonomy:TAX-06": "layer-06",
}
_FRESHNESS_STATES = frozenset(
    {"current", "needs_recheck", "stale", "source_unavailable"}
)
_TIME_PRECISIONS = frozenset(
    {"day", "month", "year", "reporting_period", "unknown"}
)
_CONFIDENCE_KEYS = frozenset(
    {"auth", "explicit", "corr", "time", "geo", "extraction", "conflict"}
)
_CONFIDENCE_VALUES = {
    "auth": frozenset(
        {
            "T1 regulator filing",
            "T2 company announcement",
            "T2 issuer IR",
            "T2 issuer annual report",
            "T2 issuer newsroom",
            "T2 issuer plus T3 official-program premises",
            "T2 supplier announcement",
            "T3 official program",
        }
    ),
    "explicit": frozenset(
        {
            "CoWoS/HBM composition",
            "amount, period, and primary business purpose",
            "asset classes and period",
            "category share",
            "cost categories and shared infrastructure role",
            "derived",
            "facility category and future-capacity role",
            "issuer capability description",
            "named amount and calendar period",
            "named amount and period",
            "named chip families and capability",
            "named company, site, and delivery milestone",
            "named contractor within stated activity group",
            "named counterpart, approximate capacity, platform, and start year",
            "named counterpart, upper-bound capacity, and platform",
            "named foundry and activity",
            "named packaging technology",
            "named parties and product scope",
            "named parties and role",
            "named parties, Google Cloud context, technology, and expected start",
            "named parties, capacity, project, and geography",
            "named parties, co-development, and design scope",
            "named partner and hardware family",
            "named partner and product class",
            "named party, technology, and expected start",
            "named platform, parties, and development roles",
            "named platform, site, and partial operating status",
            "named product generation and lifecycle",
            "named range and period",
            "named site and operating milestone",
            "named site, vendor, and product family",
            "named supplier and component class",
            "named variants, function, and variant lifecycles",
            "named vendor and hardware class",
            "partial operating status and workload type",
            "power and cooling scope",
            "product classes and use",
            "scope and bottleneck statements",
            "scope bullets",
            "site online",
            "technology portfolio and development scope",
            "technology, scale class, and expected start year",
            "title-level product and sample-shipment claim",
        }
    ),
    "corr": frozenset({"single primary", "two non-bilateral premises"}),
    "time": frozenset(
        {
            "current",
            "current with month precision",
            "current-page state",
            "current/forward",
            "forward",
            "forward with year precision",
            "recent period",
            "recent/current",
        }
    ),
    "geo": frozenset(
        {"global", "global only", "mostly specific", "partly specific", "specific", "unknown"}
    ),
    "extraction": frozenset(
        {"manual unreviewed", "manual derivation unreviewed"}
    ),
    "conflict": frozenset({"none"}),
}
_CONFIDENCE_RATIONALE_ORDER = (
    "auth",
    "explicit",
    "corr",
    "time",
    "geo",
    "extraction",
    "conflict",
)
_GEOGRAPHY_CONFIDENCE = {
    "geography:global": frozenset({"global", "global only"}),
    "geography:unknown": frozenset({"unknown"}),
    "geography:us": frozenset({"specific", "mostly specific"}),
    "geography:us-wisconsin": frozenset({"specific"}),
    "geography:us-texas": frozenset({"specific"}),
    "geography:asia": frozenset({"partly specific"}),
    "geography:taiwan": frozenset({"partly specific"}),
    "geography:south-korea": frozenset({"partly specific", "global"}),
}
_RELATIONSHIP_TYPES = frozenset(
    {
        "buys_from",
        "invests_in",
        "depends_on",
        "develops_or_operates",
        "enables_capability",
        "partners_with",
        "supplies",
        "co_designs",
        "inferred_exposure_to",
        "leases_or_provides_capacity_to",
        "manufactures_for",
        "packages_or_tests_for",
        "adopts_or_supports_standard",
        "competes_with",
    }
)
_PREFIXES = {
    "taxonomy": "taxonomy:",
    "geography": "geography:",
    "entity": "entity:",
    "source": "source:",
    "evidence": "evidence:",
    "relationship": "relationship:",
    "assertion": "assertion:",
}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_YEAR_RE = re.compile(r"^\d{4}$")
_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
    r"(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$"
)
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENGLISH_RE = re.compile(r"[A-Za-z]")
_STOCK_ID_RE = re.compile(r"^[A-Z]{2}\.[A-Z0-9]{1,10}$")
_CREDENTIAL_VALUE_RE = re.compile(
    r"(?i)(?:password|passphrase|api[_-]?key|access[_-]?token|token|secret|"
    r"credential)\s*[:=]\s*\S+|bearer\s+\S+|ghp_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9]{20,}"
)
_SENSITIVE_QUERY_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "client_secret",
        "credential",
        "key",
        "password",
        "private_key",
        "secret",
        "sig",
        "signature",
        "token",
    }
)
_COMBINED_AUTHORITY_BY_CLASSIFICATION_SET = {
    frozenset(
        {"T2 issuer IR", "T3 official program"}
    ): "T2 issuer plus T3 official-program premises",
}
_PUBLIC_STOCK_IDS_BY_LINK_KIND = {
    "research": {
        "entity:ENT-ORG-ALPHABET": frozenset({"US.GOOGL"}),
        "entity:ENT-ORG-MICROSOFT": frozenset({"US.MSFT"}),
        "entity:ENT-ORG-META": frozenset({"US.META"}),
        "entity:ENT-ORG-AMAZON": frozenset({"US.AMZN"}),
        "entity:ENT-ORG-NVIDIA": frozenset({"US.NVDA"}),
        "entity:ENT-ORG-FABRINET": frozenset({"US.FN"}),
        "entity:ENT-ORG-TSMC": frozenset({"US.TSM"}),
        "entity:ENT-ORG-SAMSUNG": frozenset({"KR.005930"}),
        "entity:ENT-ORG-SKHYNIX": frozenset({"KR.000660"}),
        "entity:ENT-ORG-MICRON": frozenset({"US.MU"}),
        "entity:ENT-ORG-ASML": frozenset({"US.ASML"}),
        "entity:ENT-ORG-BROADCOM": frozenset({"US.AVGO"}),
        "entity:ENT-ORG-CORNING": frozenset({"US.GLW"}),
        "entity:ENT-ORG-ORACLE": frozenset({"US.ORCL"}),
    },
    "valuation": {
        "entity:ENT-ORG-ALPHABET": frozenset({"US.GOOGL"}),
        "entity:ENT-ORG-MICROSOFT": frozenset({"US.MSFT"}),
        "entity:ENT-ORG-META": frozenset({"US.META"}),
        "entity:ENT-ORG-AMAZON": frozenset({"US.AMZN"}),
        "entity:ENT-ORG-NVIDIA": frozenset({"US.NVDA"}),
        "entity:ENT-ORG-FABRINET": frozenset({"US.FN"}),
        "entity:ENT-ORG-TSMC": frozenset({"US.TSM"}),
        "entity:ENT-ORG-SAMSUNG": frozenset({"KR.005930"}),
        "entity:ENT-ORG-SKHYNIX": frozenset({"KR.000660"}),
        "entity:ENT-ORG-MICRON": frozenset({"US.MU"}),
        "entity:ENT-ORG-ASML": frozenset({"US.ASML"}),
        "entity:ENT-ORG-BROADCOM": frozenset({"US.AVGO"}),
        "entity:ENT-ORG-CORNING": frozenset({"US.GLW"}),
        "entity:ENT-ORG-ORACLE": frozenset({"US.ORCL"}),
    },
}
_PUBLIC_STOCK_MARKETS_BY_LINK_KIND = {
    "research": frozenset({"US", "HK", "KR"}),
    "valuation": frozenset({"US", "HK", "KR"}),
}
_T = TypeVar("_T")


def load_release(
    path: Path | None = None,
    *,
    prior_path: Path | None = None,
) -> PanoramaRelease:
    release_path = path or _RELEASE_PATH
    payload = _read_json(release_path)
    previous = (
        _validate_release(
            _read_json(prior_path),
            previous=None,
            allow_unresolved_prior=True,
        )
        if prior_path
        else None
    )
    return validate_release(payload, previous=previous)


def validate_release(
    payload: Mapping[str, object],
    *,
    previous: PanoramaRelease | None = None,
) -> PanoramaRelease:
    return _validate_release(
        payload,
        previous=previous,
        allow_unresolved_prior=False,
    )


def _validate_release(
    payload: Mapping[str, object],
    *,
    previous: PanoramaRelease | None,
    allow_unresolved_prior: bool,
) -> PanoramaRelease:
    if not isinstance(payload, Mapping):
        raise PanoramaReleaseError("release payload must be a JSON object")
    _reject_unsafe_tree(payload)
    _require_exact_keys(payload, PanoramaRelease, "release")

    release = PanoramaRelease(
        schema_version=_string(payload["schema_version"], "schema_version"),
        release_id=_string(payload["release_id"], "release_id"),
        prior_release_id=_optional_string(payload["prior_release_id"], "prior_release_id"),
        taxonomy_version=_string(payload["taxonomy_version"], "taxonomy_version"),
        published_at=_string(payload["published_at"], "published_at"),
        evidence_cutoff=_string(payload["evidence_cutoff"], "evidence_cutoff"),
        review_state=_string(payload["review_state"], "review_state"),
        change_summary=_string_tuple(payload["change_summary"], "change_summary"),
        release_diff=_parse_release_diff(payload["release_diff"]),
        curator=_string(payload["curator"], "curator"),
        reviewer=_string(payload["reviewer"], "reviewer"),
        taxonomy=_records(payload["taxonomy"], PanoramaTaxonomyNode, _parse_taxonomy),
        geographies=_records(
            payload["geographies"], PanoramaGeography, _parse_geography
        ),
        entities=_records(payload["entities"], PanoramaEntity, _parse_entity),
        sources=_records(
            payload["sources"], PanoramaSourceSnapshot, _parse_source
        ),
        evidence=_records(payload["evidence"], PanoramaEvidence, _parse_evidence),
        relationships=_records(
            payload["relationships"], PanoramaRelationship, _parse_relationship
        ),
        assertions=_records(
            payload["assertions"], PanoramaAssertion, _parse_assertion
        ),
    )

    if release.schema_version != _SCHEMA_VERSION:
        raise PanoramaReleaseError("unsupported schema_version")
    _validate_date(release.published_at, "published_at", timestamp=True)
    _validate_date(release.evidence_cutoff, "evidence_cutoff")
    published_date = datetime.fromisoformat(
        release.published_at.replace("Z", "+00:00")
    ).date()
    if date.fromisoformat(release.evidence_cutoff) > published_date:
        raise PanoramaReleaseError(
            "evidence_cutoff cannot be after published_at date"
        )
    if release.review_state not in _REVIEW_STATES:
        raise PanoramaReleaseError("unsupported review state")
    if not release.change_summary or any(not item.strip() for item in release.change_summary):
        raise PanoramaReleaseError("change_summary must be nonempty")

    if previous is not None and release.release_id == previous.release_id:
        if _plain(release) != _plain(previous):
            raise PanoramaReleaseError(
                "release ID reuse with byte-significant content change"
            )
        return release
    unresolved_prior = (
        allow_unresolved_prior
        and previous is None
        and release.prior_release_id is not None
    )
    if release.prior_release_id is None:
        if previous is not None:
            raise PanoramaReleaseError("prior release must be null for first release")
    elif (
        not unresolved_prior
        and (previous is None or previous.release_id != release.prior_release_id)
    ):
        raise PanoramaReleaseError("prior release is required and must match")

    _validate_release_graph(release)
    if previous is not None:
        _validate_relationship_identity(previous, release)
    if not unresolved_prior:
        expected_diff = _compute_diff(previous, release)
        stored_diff = _diff_to_dict(release.release_diff)
        if expected_diff != stored_diff:
            raise PanoramaReleaseError("stored release diff does not match computed diff")
    _validate_diff_reasons(release.release_diff)

    if release.review_state == "published":
        if release.curator == release.reviewer:
            raise PanoramaReleaseError("published release requires distinct reviewers")
        if any(
            item.review_state != "reviewed_for_implementation"
            for item in release.assertions
            if item.review_state != "superseded"
        ):
            raise PanoramaReleaseError(
                "published release requires independently reviewed assertions"
            )

    projection = _build_public_projection(release, enforce_size=False)
    if len(_compact_json(projection)) > _MAX_PROJECTION_BYTES:
        raise PanoramaReleaseError("public projection exceeds 2 MiB")
    return release


def diff_releases(
    previous: PanoramaRelease | None,
    current: PanoramaRelease,
) -> dict[str, object]:
    return _compute_diff(previous, current)


def build_public_projection(release: PanoramaRelease) -> dict[str, object]:
    projection = _build_public_projection(release, enforce_size=True)
    return projection


def _build_public_projection(
    release: PanoramaRelease,
    *,
    enforce_size: bool,
) -> dict[str, object]:
    active_by_relationship: dict[str, PanoramaAssertion] = {}
    for assertion in release.assertions:
        if assertion.review_state == "superseded":
            continue
        if assertion.relationship_id in active_by_relationship:
            raise PanoramaReleaseError("relationship has multiple active assertions")
        active_by_relationship[assertion.relationship_id] = assertion
    if set(active_by_relationship) != {
        item.relationship_id for item in release.relationships
    }:
        raise PanoramaReleaseError("relationship has zero active assertion")

    assertions = {
        assertion.relationship_id: assertion
        for assertion in active_by_relationship.values()
    }
    relationship_items: list[dict[str, object]] = []
    for relationship in release.relationships:
        assertion = assertions[relationship.relationship_id]
        item = _record_dict(relationship)
        assertion_dict = _record_dict(assertion)
        for excluded in {
            "relationship_id",
            "review_state",
            "supersedes_assertion_id",
        }:
            assertion_dict.pop(excluded)
        item.update(assertion_dict)
        relationship_items.append(item)

    projection: dict[str, object] = {
        "ok": True,
        "schema_version": _PUBLIC_SCHEMA_VERSION,
        "release": {
            key: getattr(release, key)
            for key in (
                "release_id",
                "prior_release_id",
                "taxonomy_version",
                "published_at",
                "evidence_cutoff",
                "change_summary",
                "review_state",
            )
        },
        "taxonomy": [_record_dict(item) for item in release.taxonomy],
        "entities": [_record_dict(item) for item in release.entities],
        "relationships": relationship_items,
        "evidence": [_record_dict(item) for item in release.evidence],
        "sources": [_record_dict(item) for item in release.sources],
        "facets": {
            "layer": _facet(
                (item.layer, item.label) for item in release.taxonomy
            ),
            "geography": _facet(
                (item.geography_id, item.label) for item in release.geographies
            ),
            "geography_role": _facet(
                (role, role.replace("_", " "))
                for item in active_by_relationship.values()
                for _, role in item.geography_roles
            ),
            "time_horizon": _facet(
                (item.time_precision, item.time_precision)
                for item in active_by_relationship.values()
            ),
            "lifecycle": _facet(
                (item.lifecycle_state, item.lifecycle_state)
                for item in active_by_relationship.values()
            ),
            "evidence_tier": _facet(
                (item.tier, item.tier) for item in release.sources
            ),
            "confidence": _facet(
                (item.confidence_label, item.confidence_label)
                for item in active_by_relationship.values()
            ),
        },
    }
    projection = _plain(projection)
    if enforce_size and len(_compact_json(projection)) > _MAX_PROJECTION_BYTES:
        raise PanoramaReleaseError("public projection exceeds 2 MiB")
    return projection


def _validate_release_graph(release: PanoramaRelease) -> None:
    evidence_cutoff = release.evidence_cutoff
    _unique_ids(release.taxonomy, "taxonomy_id")
    _unique_ids(release.geographies, "geography_id")
    _unique_ids(release.entities, "entity_id")
    _unique_ids(release.sources, "source_id")
    _unique_ids(release.evidence, "evidence_id")
    _unique_ids(release.relationships, "relationship_id")
    _unique_ids(release.assertions, "assertion_id")

    taxonomy_ids = {item.taxonomy_id for item in release.taxonomy}
    geography_ids = {item.geography_id for item in release.geographies}
    entity_ids = {item.entity_id for item in release.entities}
    source_ids = {item.source_id for item in release.sources}
    evidence_ids = {item.evidence_id for item in release.evidence}
    relationship_ids = {item.relationship_id for item in release.relationships}
    assertion_ids = {item.assertion_id for item in release.assertions}

    _prefixes(release.taxonomy, "taxonomy_id", _PREFIXES["taxonomy"])
    _prefixes(release.geographies, "geography_id", _PREFIXES["geography"])
    _prefixes(release.entities, "entity_id", _PREFIXES["entity"])
    _prefixes(release.sources, "source_id", _PREFIXES["source"])
    _prefixes(release.evidence, "evidence_id", _PREFIXES["evidence"])
    _prefixes(release.relationships, "relationship_id", _PREFIXES["relationship"])
    _prefixes(release.assertions, "assertion_id", _PREFIXES["assertion"])

    if len(release.taxonomy) != 6:
        raise PanoramaReleaseError("release requires exactly six taxonomy layers")
    covered = [
        item
        for item in release.entities
        if item.kind
        in {"organization", "project", "standards_program", "standard"}
    ]
    if not 25 <= len(covered) <= 35:
        raise PanoramaReleaseError(
            "organization/project/standards-program/standard count "
            "must be between 25 and 35"
        )
    capabilities = [item for item in release.entities if item.kind == "capability"]
    if len(capabilities) > 10:
        raise PanoramaReleaseError("capability count exceeds reviewed V1 maximum")
    if not 45 <= len(release.relationships) <= 70:
        raise PanoramaReleaseError("relationship count must be between 45 and 70")
    anchors = [item for item in release.entities if item.is_demand_anchor]
    if len(anchors) != 6:
        raise PanoramaReleaseError("release requires exactly six demand anchors")

    for item in release.taxonomy:
        if item.parent_id is not None and item.parent_id not in taxonomy_ids:
            raise PanoramaReleaseError("taxonomy foreign key is invalid")
        if _TAXONOMY_LAYERS.get(item.taxonomy_id) != item.layer:
            raise PanoramaReleaseError("taxonomy layer is not admitted")
        _bounded_english(item.label, 120, "taxonomy label")
        _bounded_english(item.definition, 800, "taxonomy definition")
    for item in release.geographies:
        _bounded_english(item.label, 120, "geography label")
    for item in release.entities:
        if item.kind not in _ENTITY_KINDS:
            raise PanoramaReleaseError("unsupported entity kind")
        if item.freshness_state not in _FRESHNESS_STATES:
            raise PanoramaReleaseError("unsupported entity freshness state")
        _bounded_english(item.label, 120, "entity label")
        _bounded_english(item.summary, 800, "entity summary")
        if not item.taxonomy_ids or not set(item.taxonomy_ids) <= taxonomy_ids:
            raise PanoramaReleaseError("entity taxonomy foreign key is invalid")
        if not item.geography_ids or not set(item.geography_ids) <= geography_ids:
            raise PanoramaReleaseError("entity geography foreign key is invalid")
        _validate_date(item.last_reviewed_at, "entity last_reviewed_at")
        if item.last_reviewed_at > evidence_cutoff:
            raise PanoramaReleaseError(
                "entity last_reviewed_at cannot be after evidence cutoff"
            )
        for link in item.research_links:
            _validate_research_link(item, link)

    for item in release.sources:
        if item.tier not in _SOURCE_TIERS:
            raise PanoramaReleaseError("unsupported source tier")
        _source_authority_classification(item)
        parsed = urlparse(item.url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise PanoramaReleaseError("source URL must use HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise PanoramaReleaseError("source URL contains credentials")
        if any(
            key.lower() in _SENSITIVE_QUERY_NAMES
            for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        ):
            raise PanoramaReleaseError("source URL contains credential query data")
        is_explicitly_undated = (
            "no publication date displayed" in item.license_class.lower()
        )
        if (item.publication_date is None) != is_explicitly_undated:
            raise PanoramaReleaseError(
                "source publication date contradicts undated metadata"
            )
        if item.publication_date is not None:
            _validate_date(item.publication_date, "source publication_date")
            if item.publication_date > evidence_cutoff:
                raise PanoramaReleaseError(
                    "source publication date cannot be after evidence cutoff"
                )
        _validate_date(item.retrieval_date, "source retrieval_date")
        if item.retrieval_date > evidence_cutoff:
            raise PanoramaReleaseError(
                "source retrieval date cannot be after evidence cutoff"
            )
        if (
            item.publication_date is not None
            and item.publication_date > item.retrieval_date
        ):
            raise PanoramaReleaseError(
                "source publication date cannot be after retrieval date"
            )
        _bounded_english(item.publisher, 120, "source publisher")
        _bounded_english(item.document_title, 800, "source title")
        if not item.immutable_locator.strip():
            raise PanoramaReleaseError("source immutable locator is required")
        if not _HASH_RE.fullmatch(item.content_hash):
            raise PanoramaReleaseError("source content_hash must be sha256")

    evidence_by_id = {item.evidence_id: item for item in release.evidence}
    source_by_id = {item.source_id: item for item in release.sources}
    for item in release.evidence:
        if item.source_id not in source_ids:
            raise PanoramaReleaseError("evidence source foreign key is invalid")
        if item.review_state not in _REVIEW_STATES:
            raise PanoramaReleaseError("unsupported evidence review state")
        if not item.locator.strip():
            raise PanoramaReleaseError("evidence locator is required")
        _bounded_english(item.bounded_excerpt, 600, "evidence excerpt")
        source = source_by_id[item.source_id]
        if not source.publisher or not source.retrieval_date:
            raise PanoramaReleaseError("source metadata is incomplete")
    for source in release.sources:
        associated_evidence = tuple(
            item
            for item in release.evidence
            if item.source_id == source.source_id
        )
        if source.content_hash != compute_source_content_hash(
            source,
            associated_evidence,
        ):
            raise PanoramaReleaseError(
                "source content_hash does not match reviewed evidence snapshot"
            )

    for item in release.relationships:
        if (
            item.source_entity_id not in entity_ids
            or item.target_entity_id not in entity_ids
        ):
            raise PanoramaReleaseError("relationship entity foreign key is invalid")
        if item.relationship_type not in _RELATIONSHIP_TYPES:
            raise PanoramaReleaseError("unsupported relationship type")

    assertion_by_id = {item.assertion_id: item for item in release.assertions}
    active_counts = {item.relationship_id: 0 for item in release.relationships}
    for item in release.assertions:
        if item.relationship_id not in relationship_ids:
            raise PanoramaReleaseError("assertion relationship foreign key is invalid")
        if item.assertion_kind not in _ASSERTION_KINDS:
            raise PanoramaReleaseError("unsupported assertion kind")
        if item.lifecycle_state not in _LIFECYCLE_STATES:
            raise PanoramaReleaseError("unsupported lifecycle state")
        if item.review_state not in _REVIEW_STATES:
            raise PanoramaReleaseError("unsupported assertion review state")
        if item.freshness_state not in _FRESHNESS_STATES:
            raise PanoramaReleaseError("unsupported assertion freshness state")
        _bounded_english(item.text, 800, "assertion text")
        _bounded_english(item.limitations, 500, "assertion limitations")
        _validate_temporal_fields(item)
        if item.observed_at > item.reviewed_at:
            raise PanoramaReleaseError(
                "assertion observed_at cannot be after reviewed_at"
            )
        if item.observed_at > evidence_cutoff:
            raise PanoramaReleaseError(
                "assertion observed_at cannot be after evidence cutoff"
            )
        if item.reviewed_at > evidence_cutoff:
            raise PanoramaReleaseError(
                "assertion reviewed_at cannot be after evidence cutoff"
            )
        if not item.evidence_ids or not set(item.evidence_ids) <= evidence_ids:
            raise PanoramaReleaseError("assertion evidence foreign key is invalid")
        if item.review_state != "superseded":
            active_counts[item.relationship_id] += 1
            if any(
                evidence_by_id[evidence_id].review_state
                != "reviewed_for_implementation"
                for evidence_id in item.evidence_ids
            ):
                raise PanoramaReleaseError(
                    "published assertion requires reviewed evidence"
                )
        if item.assertion_kind == "inferred_exposure":
            _validate_inference(item, assertion_by_id)
        elif item.premise_assertion_ids:
            raise PanoramaReleaseError(
                "only inference assertions may have inference derivation"
            )
        if not item.geography_roles:
            raise PanoramaReleaseError(
                "confidence requires a structured geography role"
            )
        if tuple(sorted(item.geography_roles)) != item.geography_roles:
            raise PanoramaReleaseError("geography roles must be sorted")
        if any(key not in geography_ids for key, _ in item.geography_roles):
            raise PanoramaReleaseError("assertion geography foreign key is invalid")
        if any(role not in _GEOGRAPHY_ROLES for _, role in item.geography_roles):
            raise PanoramaReleaseError("unsupported geography role")
        _validate_confidence(
            item,
            assertion_by_id=assertion_by_id,
            evidence_by_id=evidence_by_id,
            source_by_id=source_by_id,
        )
        _validate_supersession(item, assertion_by_id)
    if any(count != 1 for count in active_counts.values()):
        raise PanoramaReleaseError("relationship must have exactly one active assertion")
    _validate_supersession_chains(release.assertions)

    outgoing: dict[str, set[str]] = {}
    for item in release.relationships:
        outgoing.setdefault(item.source_entity_id, set()).add(item.target_entity_id)
    for anchor in anchors:
        if not any(
            outgoing.get(intermediate)
            for intermediate in outgoing.get(anchor.entity_id, set())
        ):
            raise PanoramaReleaseError(
                "demand anchor lacks a supported two-hop path"
            )


def _validate_inference(
    item: PanoramaAssertion,
    assertion_by_id: Mapping[str, PanoramaAssertion],
) -> None:
    if not item.premise_assertion_ids:
        raise PanoramaReleaseError("inference derivation is required")
    for premise_id in item.premise_assertion_ids:
        premise = assertion_by_id.get(premise_id)
        if (
            premise is None
            or premise.assertion_kind
            not in {"disclosed_fact", "company_guidance", "management_claim"}
            or premise.review_state not in {"reviewed_for_implementation", "published"}
        ):
            raise PanoramaReleaseError("inference derivation is invalid")


def _validate_confidence(
    item: PanoramaAssertion,
    *,
    assertion_by_id: Mapping[str, PanoramaAssertion],
    evidence_by_id: Mapping[str, PanoramaEvidence],
    source_by_id: Mapping[str, PanoramaSourceSnapshot],
) -> None:
    if (
        len(item.confidence_inputs) != len(_CONFIDENCE_KEYS)
        or {key for key, _ in item.confidence_inputs} != _CONFIDENCE_KEYS
    ):
        raise PanoramaReleaseError("confidence inputs have invalid keys")
    if tuple(sorted(item.confidence_inputs)) != item.confidence_inputs:
        raise PanoramaReleaseError("confidence inputs must be sorted")
    inputs = dict(item.confidence_inputs)
    for key, allowed in _CONFIDENCE_VALUES.items():
        if inputs[key] not in allowed:
            raise PanoramaReleaseError(f"confidence {key} value is not admitted")
    _bounded_english(inputs["explicit"], 300, "confidence explicitness")
    expected_rationale = "; ".join(
        f"{key}={inputs[key]}" for key in _CONFIDENCE_RATIONALE_ORDER
    )
    if item.confidence_rationale != expected_rationale:
        raise PanoramaReleaseError(
            "confidence rationale contradicts structured inputs"
        )

    referenced = [item]
    referenced.extend(
        assertion_by_id[premise_id]
        for premise_id in item.premise_assertion_ids
    )
    referenced_evidence = [
        evidence_by_id[evidence_id]
        for assertion in referenced
        for evidence_id in assertion.evidence_ids
        if evidence_id in evidence_by_id
    ]
    if not referenced_evidence or any(
        evidence.review_state != "reviewed_for_implementation"
        for evidence in referenced_evidence
    ):
        raise PanoramaReleaseError(
            "confidence requires independently reviewed referenced evidence"
        )
    source_ids = frozenset(evidence.source_id for evidence in referenced_evidence)
    if not source_ids <= set(source_by_id):
        raise PanoramaReleaseError(
            "confidence source set contains an unresolved source"
        )
    source_authorities = {
        _source_authority_classification(source_by_id[source_id])
        for source_id in source_ids
    }
    if item.assertion_kind == "inferred_exposure":
        expected_authority = _COMBINED_AUTHORITY_BY_CLASSIFICATION_SET.get(
            frozenset(source_authorities)
        )
    else:
        expected_authority = (
            next(iter(source_authorities))
            if len(source_authorities) == 1
            else None
        )
    if inputs["auth"] != expected_authority:
        raise PanoramaReleaseError(
            "confidence authority contradicts resolved source classification"
        )
    expected_corroboration = {
        1: "single primary",
        2: "two non-bilateral premises",
    }.get(len(source_ids))
    if inputs["corr"] != expected_corroboration:
        raise PanoramaReleaseError(
            "confidence corroboration contradicts resolved unique source count"
        )

    if item.assertion_kind == "inferred_exposure":
        inference_shape = (
            inputs["explicit"] == "derived"
            and inputs["extraction"] == "manual derivation unreviewed"
            and bool(item.premise_assertion_ids)
        )
        expected_label = "inference" if inference_shape else None
    else:
        primary_shape = (
            inputs["explicit"] != "derived"
            and inputs["extraction"] == "manual unreviewed"
            and not item.premise_assertion_ids
        )
        expected_label = "medium" if primary_shape else None
    if expected_label is None or item.confidence_label != expected_label:
        raise PanoramaReleaseError(
            "confidence label does not match evidence-derived inputs"
        )

    geography_ids = {key for key, _ in item.geography_roles}
    admitted_geography_labels = set.intersection(
        *(
            set(_GEOGRAPHY_CONFIDENCE.get(geography_id, ()))
            for geography_id in geography_ids
        )
    )
    if inputs["geo"] not in admitted_geography_labels:
        raise PanoramaReleaseError(
            "confidence geography contradicts structured geography roles"
        )
    if item.time_precision == "year" and "year precision" not in inputs["time"]:
        raise PanoramaReleaseError(
            "confidence time contradicts year precision"
        )
    if item.time_precision == "month" and "month precision" not in inputs["time"]:
        raise PanoramaReleaseError(
            "confidence time contradicts month precision"
        )


def _validate_supersession(
    item: PanoramaAssertion,
    assertion_by_id: Mapping[str, PanoramaAssertion],
) -> None:
    if item.supersedes_assertion_id is None:
        return
    superseded = assertion_by_id.get(item.supersedes_assertion_id)
    if (
        superseded is None
        or superseded.assertion_id == item.assertion_id
        or superseded.relationship_id != item.relationship_id
        or superseded.review_state != "superseded"
    ):
        raise PanoramaReleaseError("supersedes assertion reference is invalid")


def _validate_supersession_chains(
    assertions: tuple[PanoramaAssertion, ...],
) -> None:
    by_relationship: dict[str, list[PanoramaAssertion]] = {}
    for assertion in assertions:
        by_relationship.setdefault(assertion.relationship_id, []).append(
            assertion
        )

    for relationship_assertions in by_relationship.values():
        by_id = {
            assertion.assertion_id: assertion
            for assertion in relationship_assertions
        }
        active = [
            assertion
            for assertion in relationship_assertions
            if assertion.review_state != "superseded"
        ]
        if len(active) != 1:
            continue
        active_id = active[0].assertion_id
        successor_by_predecessor: dict[str, str] = {}
        for successor in relationship_assertions:
            predecessor_id = successor.supersedes_assertion_id
            if predecessor_id is None:
                continue
            if predecessor_id in successor_by_predecessor:
                raise PanoramaReleaseError(
                    "supersession chain predecessor has multiple successors"
                )
            successor_by_predecessor[predecessor_id] = successor.assertion_id

        for assertion in relationship_assertions:
            if assertion.review_state != "superseded":
                continue
            current_id = assertion.assertion_id
            visited: set[str] = set()
            while by_id[current_id].review_state == "superseded":
                if current_id in visited:
                    raise PanoramaReleaseError(
                        "supersession chain contains a cycle"
                    )
                visited.add(current_id)
                successor_id = successor_by_predecessor.get(current_id)
                if successor_id is None:
                    raise PanoramaReleaseError(
                        "supersession chain does not terminate at the active assertion"
                    )
                current_id = successor_id
            if current_id != active_id:
                raise PanoramaReleaseError(
                    "supersession chain terminates outside the active assertion"
                )


def _validate_temporal_fields(item: PanoramaAssertion) -> None:
    _validate_date(item.observed_at, "assertion observed_at")
    _validate_date(item.reviewed_at, "assertion reviewed_at")
    if item.time_precision not in _TIME_PRECISIONS:
        raise PanoramaReleaseError("assertion time precision is not admitted")
    if item.time_precision == "unknown":
        if any(
            value is not None
            for value in (
                item.effective_from,
                item.effective_to,
                item.reporting_period_start,
                item.reporting_period_end,
            )
        ):
            raise PanoramaReleaseError(
                "unknown time precision cannot carry effective or reporting dates"
            )
        return

    if item.effective_from is None:
        raise PanoramaReleaseError("time precision requires effective_from")
    for name in ("effective_from", "effective_to"):
        value = getattr(item, name)
        if value is not None:
            _validate_date_for_precision(value, item.time_precision, name)

    if item.time_precision == "reporting_period":
        if item.reporting_period_start is None or item.reporting_period_end is None:
            raise PanoramaReleaseError(
                "reporting period requires both start and end"
            )
        _validate_date(item.reporting_period_start, "reporting_period_start")
        _validate_date(item.reporting_period_end, "reporting_period_end")
        if (
            item.reporting_period_start != item.effective_from
            or item.reporting_period_end != item.effective_to
        ):
            raise PanoramaReleaseError(
                "reporting period must match the effective range"
            )
    elif item.reporting_period_start is not None or item.reporting_period_end is not None:
        raise PanoramaReleaseError(
            "non-reporting time precision cannot carry a reporting period"
        )

    if (
        item.effective_from
        and item.effective_to
        and _date_sort_key(item.effective_from) > _date_sort_key(item.effective_to)
    ):
        raise PanoramaReleaseError("assertion effective_from exceeds effective_to")


def _validate_date_for_precision(value: str, precision: str, label: str) -> None:
    if precision == "year":
        _validate_date(value, label, allow_year=True)
    elif precision == "month":
        _validate_date(value, label, allow_month=True)
    else:
        _validate_date(value, label)


def _validate_research_link(
    entity: PanoramaEntity,
    link: PanoramaResearchLink,
) -> None:
    admitted_by_entity = _PUBLIC_STOCK_IDS_BY_LINK_KIND.get(link.kind)
    admitted_stock_ids = (
        admitted_by_entity.get(entity.entity_id)
        if admitted_by_entity is not None
        else None
    )
    market = link.canonical_stock_id.partition(".")[0]
    admitted_markets = _PUBLIC_STOCK_MARKETS_BY_LINK_KIND.get(link.kind)
    executing_hint = link.command_hint.lower().startswith(
        (
            "execute",
            "latest valuation ",
            "research ",
            "run ",
            "stock valuation ",
            "valuation ",
            "/",
        )
    )
    if (
        entity.kind != "organization"
        or admitted_stock_ids is None
        or admitted_markets is None
        or market not in admitted_markets
        or not _STOCK_ID_RE.fullmatch(link.canonical_stock_id)
        or link.canonical_stock_id not in admitted_stock_ids
        or link.internal_path != "/command"
        or "\n" in link.command_hint
        or executing_hint
        or any(character in link.command_hint for character in (";", "|", "`"))
    ):
        raise PanoramaReleaseError("research link is unsafe")
    _bounded_english(link.label, 120, "research link label")


def _compute_diff(
    previous: PanoramaRelease | None,
    current: PanoramaRelease,
) -> dict[str, object]:
    current_records = _stable_records(current)
    if previous is None:
        return {
            "added": sorted(current_records),
            "changed": [],
            "expired": [],
            "removed": [],
            "reasons": {},
        }
    previous_records = _stable_records(previous)
    added = sorted(set(current_records) - set(previous_records))
    removed = sorted(set(previous_records) - set(current_records))
    changed = sorted(
        stable_id
        for stable_id in set(current_records) & set(previous_records)
        if current_records[stable_id] != previous_records[stable_id]
    )
    expired: list[str] = []
    for stable_id in list(changed):
        before = previous_records[stable_id]
        after = current_records[stable_id]
        if (
            stable_id.startswith(_PREFIXES["assertion"])
            and before.get("effective_to") is None
            and after.get("effective_to") is not None
        ):
            expired.append(stable_id)
            changed.remove(stable_id)
    reasons = current.release_diff.reasons
    return {
        "added": added,
        "changed": changed,
        "expired": sorted(expired),
        "removed": removed,
        "reasons": {
            stable_id: reasons[stable_id]
            for stable_id in sorted(changed + expired + removed)
            if stable_id in reasons
        },
    }


def _validate_relationship_identity(
    previous: PanoramaRelease,
    current: PanoramaRelease,
) -> None:
    previous_by_id = {
        item.relationship_id: item for item in previous.relationships
    }
    for relationship in current.relationships:
        prior = previous_by_id.get(relationship.relationship_id)
        if prior is None:
            continue
        if (
            relationship.source_entity_id != prior.source_entity_id
            or relationship.target_entity_id != prior.target_entity_id
            or relationship.relationship_type != prior.relationship_type
        ):
            raise PanoramaReleaseError(
                "relationship identity cannot change under an existing ID"
            )


def _stable_records(release: PanoramaRelease) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for collection, id_field in (
        (release.taxonomy, "taxonomy_id"),
        (release.geographies, "geography_id"),
        (release.entities, "entity_id"),
        (release.sources, "source_id"),
        (release.evidence, "evidence_id"),
        (release.relationships, "relationship_id"),
        (release.assertions, "assertion_id"),
    ):
        for item in collection:
            records[getattr(item, id_field)] = _record_dict(item)
    return records


def _validate_diff_reasons(diff: PanoramaReleaseDiff) -> None:
    expected = set(diff.changed) | set(diff.expired) | set(diff.removed)
    reasons = diff.reasons
    if set(reasons) != expected or any(not value.strip() for value in reasons.values()):
        raise PanoramaReleaseError(
            "release diff reasons must cover changed, expired, and removed IDs"
        )


def _parse_taxonomy(value: Mapping[str, object]) -> PanoramaTaxonomyNode:
    return PanoramaTaxonomyNode(
        taxonomy_id=_string(value["taxonomy_id"], "taxonomy_id"),
        parent_id=_optional_string(value["parent_id"], "parent_id"),
        label=_string(value["label"], "taxonomy label"),
        definition=_string(value["definition"], "taxonomy definition"),
        standards_context=_string(value["standards_context"], "standards_context"),
        coverage_gaps=_string(value["coverage_gaps"], "coverage_gaps"),
        layer=_string(value["layer"], "taxonomy layer"),
        sort_order=_integer(value["sort_order"], "sort_order"),
    )


def _parse_geography(value: Mapping[str, object]) -> PanoramaGeography:
    return PanoramaGeography(
        geography_id=_string(value["geography_id"], "geography_id"),
        label=_string(value["label"], "geography label"),
        country_code=_optional_string(value["country_code"], "country_code"),
        region=_string(value["region"], "geography region"),
    )


def _parse_research_link(value: Mapping[str, object]) -> PanoramaResearchLink:
    _require_exact_keys(value, PanoramaResearchLink, "research link")
    return PanoramaResearchLink(
        kind=_string(value["kind"], "research link kind"),
        label=_string(value["label"], "research link label"),
        canonical_stock_id=_string(
            value["canonical_stock_id"], "canonical_stock_id"
        ),
        internal_path=_string(value["internal_path"], "internal_path"),
        command_hint=_string(value["command_hint"], "command_hint"),
    )


def _parse_entity(value: Mapping[str, object]) -> PanoramaEntity:
    return PanoramaEntity(
        entity_id=_string(value["entity_id"], "entity_id"),
        kind=_string(value["kind"], "entity kind"),
        label=_string(value["label"], "entity label"),
        aliases=_string_tuple(value["aliases"], "aliases"),
        summary=_string(value["summary"], "entity summary"),
        taxonomy_ids=_string_tuple(value["taxonomy_ids"], "taxonomy_ids"),
        geography_ids=_string_tuple(value["geography_ids"], "geography_ids"),
        capability_roles=_string_tuple(
            value["capability_roles"], "capability_roles"
        ),
        coverage_gaps=_string(value["coverage_gaps"], "coverage_gaps"),
        freshness_state=_string(value["freshness_state"], "freshness_state"),
        last_reviewed_at=_string(value["last_reviewed_at"], "last_reviewed_at"),
        is_demand_anchor=_boolean(value["is_demand_anchor"], "is_demand_anchor"),
        research_links=_mapping_records(
            value["research_links"], PanoramaResearchLink, _parse_research_link
        ),
    )


def _parse_relationship(value: Mapping[str, object]) -> PanoramaRelationship:
    return PanoramaRelationship(
        relationship_id=_string(value["relationship_id"], "relationship_id"),
        source_entity_id=_string(
            value["source_entity_id"], "source_entity_id"
        ),
        target_entity_id=_string(
            value["target_entity_id"], "target_entity_id"
        ),
        relationship_type=_string(
            value["relationship_type"], "relationship_type"
        ),
    )


def _parse_assertion(value: Mapping[str, object]) -> PanoramaAssertion:
    return PanoramaAssertion(
        assertion_id=_string(value["assertion_id"], "assertion_id"),
        relationship_id=_string(value["relationship_id"], "relationship_id"),
        text=_string(value["text"], "assertion text"),
        assertion_kind=_string(value["assertion_kind"], "assertion_kind"),
        lifecycle_state=_string(value["lifecycle_state"], "lifecycle_state"),
        effective_from=_optional_string(
            value["effective_from"], "effective_from"
        ),
        effective_to=_optional_string(value["effective_to"], "effective_to"),
        time_precision=_string(value["time_precision"], "time_precision"),
        observed_at=_string(value["observed_at"], "observed_at"),
        reporting_period_start=_optional_string(
            value["reporting_period_start"], "reporting_period_start"
        ),
        reporting_period_end=_optional_string(
            value["reporting_period_end"], "reporting_period_end"
        ),
        reviewed_at=_string(value["reviewed_at"], "reviewed_at"),
        freshness_state=_string(value["freshness_state"], "freshness_state"),
        geography_roles=_pair_tuple(value["geography_roles"], "geography_roles"),
        confidence_inputs=_pair_tuple(
            value["confidence_inputs"], "confidence_inputs"
        ),
        confidence_rationale=_string(
            value["confidence_rationale"], "confidence_rationale"
        ),
        confidence_label=_string(value["confidence_label"], "confidence_label"),
        limitations=_string(value["limitations"], "limitations"),
        evidence_ids=_string_tuple(value["evidence_ids"], "evidence_ids"),
        premise_assertion_ids=_string_tuple(
            value["premise_assertion_ids"], "premise_assertion_ids"
        ),
        review_state=_string(value["review_state"], "review_state"),
        supersedes_assertion_id=_optional_string(
            value["supersedes_assertion_id"], "supersedes_assertion_id"
        ),
    )


def _parse_source(value: Mapping[str, object]) -> PanoramaSourceSnapshot:
    return PanoramaSourceSnapshot(
        source_id=_string(value["source_id"], "source_id"),
        tier=_string(value["tier"], "source tier"),
        publisher=_string(value["publisher"], "source publisher"),
        document_title=_string(value["document_title"], "document_title"),
        url=_string(value["url"], "source url"),
        publication_date=_optional_string(
            value["publication_date"], "publication_date"
        ),
        retrieval_date=_string(value["retrieval_date"], "retrieval_date"),
        immutable_locator=_string(
            value["immutable_locator"], "immutable_locator"
        ),
        content_hash=_string(value["content_hash"], "content_hash"),
        license_class=_string(value["license_class"], "license_class"),
    )


def _parse_evidence(value: Mapping[str, object]) -> PanoramaEvidence:
    return PanoramaEvidence(
        evidence_id=_string(value["evidence_id"], "evidence_id"),
        source_id=_string(value["source_id"], "source_id"),
        locator=_string(value["locator"], "evidence locator"),
        bounded_excerpt=_string(value["bounded_excerpt"], "bounded_excerpt"),
        extraction_method=_string(
            value["extraction_method"], "extraction_method"
        ),
        review_state=_string(value["review_state"], "review_state"),
    )


def _parse_release_diff(value: object) -> PanoramaReleaseDiff:
    mapping = _mapping(value, "release_diff")
    _require_exact_keys(mapping, PanoramaReleaseDiff, "release_diff")
    reasons = _mapping(mapping["reasons"], "release_diff reasons")
    return PanoramaReleaseDiff(
        added=_string_tuple(mapping["added"], "release_diff added"),
        changed=_string_tuple(mapping["changed"], "release_diff changed"),
        expired=_string_tuple(mapping["expired"], "release_diff expired"),
        removed=_string_tuple(mapping["removed"], "release_diff removed"),
        reasons=MappingProxyType(
            dict(
                sorted(
                    (
                        _string(key, "release_diff reason ID"),
                        _string(reason, "release_diff reason"),
                    )
                    for key, reason in reasons.items()
                )
            )
        ),
    )


def _records(
    value: object,
    record_type: type[_T],
    parser: Any,
) -> tuple[_T, ...]:
    return _mapping_records(value, record_type, parser)


def _mapping_records(
    value: object,
    record_type: type[_T],
    parser: Any,
) -> tuple[_T, ...]:
    if not isinstance(value, list):
        raise PanoramaReleaseError(f"{record_type.__name__} collection must be a list")
    result: list[_T] = []
    for raw in value:
        mapping = _mapping(raw, record_type.__name__)
        _require_exact_keys(mapping, record_type, record_type.__name__)
        result.append(parser(mapping))
    return tuple(result)


def _require_exact_keys(
    value: Mapping[str, object],
    record_type: type[object],
    label: str,
) -> None:
    expected = {field.name for field in fields(record_type)}
    actual = set(value)
    if actual != expected:
        raise PanoramaReleaseError(
            f"{label} has unknown keys or missing required keys"
        )


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_unique_object)
    except PanoramaReleaseError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise PanoramaReleaseError("release JSON could not be read") from exc
    return _mapping(value, "release")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PanoramaReleaseError("duplicate JSON key")
        result[key] = value
    return result


def _reject_unsafe_tree(value: object) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_unsafe_tree(item)
    elif isinstance(value, list):
        for item in value:
            _reject_unsafe_tree(item)
    elif isinstance(value, str):
        lowered = value.lower()
        if (
            "file://" in lowered
            or "/users/" in lowered
            or "/home/" in lowered
            or "\\users\\" in lowered
        ):
            raise PanoramaReleaseError("local filesystem path is forbidden")
        if _CREDENTIAL_VALUE_RE.search(value):
            raise PanoramaReleaseError("credential-looking value is forbidden")


def _unique_ids(collection: tuple[object, ...], attribute: str) -> None:
    values = [getattr(item, attribute) for item in collection]
    if len(values) != len(set(values)):
        raise PanoramaReleaseError(f"duplicate stable ID in {attribute}")


def _prefixes(
    collection: tuple[object, ...],
    attribute: str,
    prefix: str,
) -> None:
    if any(not getattr(item, attribute).startswith(prefix) for item in collection):
        raise PanoramaReleaseError(f"invalid stable ID prefix for {attribute}")


def _validate_date(
    value: str,
    label: str,
    *,
    timestamp: bool = False,
    allow_month: bool = False,
    allow_year: bool = False,
) -> None:
    try:
        if timestamp:
            if not _TIMESTAMP_RE.fullmatch(value):
                raise ValueError
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
        elif allow_year and _YEAR_RE.fullmatch(value):
            date.fromisoformat(f"{value}-01-01")
        elif allow_month and _MONTH_RE.fullmatch(value):
            date.fromisoformat(f"{value}-01")
        elif _DATE_RE.fullmatch(value):
            date.fromisoformat(value)
        else:
            raise ValueError
    except ValueError as exc:
        raise PanoramaReleaseError(f"{label} must be ISO-8601") from exc


def _date_sort_key(value: str) -> str:
    if _YEAR_RE.fullmatch(value):
        return f"{value}-01-01"
    if _MONTH_RE.fullmatch(value):
        return f"{value}-01"
    return value


def _bounded_english(value: str, maximum: int, label: str) -> None:
    if not value.strip() or len(value) > maximum or not _ENGLISH_RE.search(value):
        raise PanoramaReleaseError(
            f"{label} must be nonempty English text of at most {maximum} characters"
        )


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise PanoramaReleaseError(f"{label} must be a string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PanoramaReleaseError(f"{label} must be an integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise PanoramaReleaseError(f"{label} must be a boolean")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        raise PanoramaReleaseError(f"{label} must be an object")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PanoramaReleaseError(f"{label} must be a string list")
    return tuple(value)


def _pair_tuple(value: object, label: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise PanoramaReleaseError(f"{label} must be a pair list")
    result: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(part, str) for part in item)
        ):
            raise PanoramaReleaseError(f"{label} must contain string pairs")
        result.append((item[0], item[1]))
    return tuple(result)


def _record_dict(value: object) -> dict[str, object]:
    if not is_dataclass(value):
        raise PanoramaReleaseError("internal record projection failure")
    return {
        field.name: _plain(getattr(value, field.name))
        for field in fields(value)
    }


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _diff_to_dict(value: PanoramaReleaseDiff) -> dict[str, object]:
    return {
        "added": list(value.added),
        "changed": list(value.changed),
        "expired": list(value.expired),
        "removed": list(value.removed),
        "reasons": dict(value.reasons),
    }


def _facet(items: Any) -> list[dict[str, str]]:
    return [
        {"id": identifier, "label": label}
        for identifier, label in sorted(set(items))
    ]


def _compact_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
