from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlparse


class EarningsBriefReleaseError(ValueError):
    """Raised when a release violates the public evidence contract."""


class EarningsBriefNotFound(LookupError):
    """Raised when an exact company/period release is unavailable."""


_RELEASE_PATH = (
    Path(__file__).parent / "releases" / "2026-07-24.apple-fy2025-q1.v1.json"
)
_CATALOG = (
    {
        "company_id": "US.AAPL",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "period_id": "FY2025-Q1",
        "period_label": "Fiscal 2025 Q1",
        "release_id": "earnings-brief:US.AAPL:FY2025-Q1:v1",
    },
)
_EVIDENCE_STATES = {
    "available",
    "missing",
    "not_disclosed",
    "not_applicable",
    "conflict",
    "secondary_only",
    "stale",
}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID = re.compile(r"^[a-z][a-z0-9-]*:[A-Za-z0-9.:-]+$")
_CLAIM_KINDS = {"disclosed_fact", "management_claim", "analytical_inference"}
_SOURCE_TIERS = {"regulatory_filing", "issuer_ir", "exchange_filing", "official_transcript", "consensus_secondary"}
_SOURCE_FAMILIES = {"regulatory_filing", "earnings_release", "presentation", "prepared_remarks", "earnings_call", "secondary_consensus"}
_UNITS = {"billion", "per_share", "percent"}
_UNSAFE_CONTENT = re.compile(
    r"(?:/Users/|/var/|/private/|localhost|127\.0\.0\.1|"
    r"access[_ -]?token|api[_ -]?key|authorization:\s*bearer|raw[_ -]?document[_ -]?body)",
    re.IGNORECASE,
)
_BRIEF_KEYS = {
    "judgment",
    "kpis",
    "management_signals",
    "financial_flow",
    "quarterly_trends",
    "gross_margin_trends",
    "revenue_mix",
    "market_focus",
    "structural_signals",
    "scenarios",
}
_ITEM_KEYS = {
    "id",
    "label",
    "text",
    "claim_kind",
    "value",
    "display",
    "currency",
    "unit",
    "formula",
    "input_ids",
    "evidence_state",
    "as_of",
    "source_ids",
    "candidates",
    "supporting_claim_ids",
}


def list_catalog() -> list[dict[str, str]]:
    return [dict(item) for item in _CATALOG]


def load_release(company_id: str, period_id: str) -> dict[str, Any]:
    if (company_id, period_id) != ("US.AAPL", "FY2025-Q1"):
        raise EarningsBriefNotFound(f"unsupported release: {company_id}:{period_id}")
    payload = json.loads(_RELEASE_PATH.read_text(encoding="utf-8"))
    return validate_release(payload)


def validate_release(payload: Mapping[str, object]) -> dict[str, Any]:
    release = json.loads(json.dumps(payload))
    required = {
        "schema_version",
        "release_id",
        "review_state",
        "generated_at",
        "evidence_as_of",
        "company",
        "reporting_period",
        "sources",
        "brief",
    }
    if set(release) != required:
        raise EarningsBriefReleaseError("release keys are invalid")
    if release["schema_version"] != "earnings_brief_release.v1":
        raise EarningsBriefReleaseError("schema version is invalid")
    if release["review_state"] != "published":
        raise EarningsBriefReleaseError("release is not published")
    if set(release["company"]) != {"company_id", "ticker", "name", "exchange", "currency"}:
        raise EarningsBriefReleaseError("company keys are invalid")
    if set(release["reporting_period"]) != {"period_id", "label", "period_end"}:
        raise EarningsBriefReleaseError("reporting period keys are invalid")
    if set(release["brief"]) != _BRIEF_KEYS:
        raise EarningsBriefReleaseError("brief keys are invalid")

    sources = release["sources"]
    source_ids: set[str] = set()
    for source in sources:
        if set(source) != {
            "source_id",
            "family",
            "tier",
            "publisher",
            "document_title",
            "url",
            "publication_date",
            "retrieved_at",
            "as_of",
            "locator",
            "content_hash",
            "review_state",
        }:
            raise EarningsBriefReleaseError("source keys are invalid")
        if source["source_id"] in source_ids:
            raise EarningsBriefReleaseError("duplicate source")
        if not _ID.fullmatch(source["source_id"]):
            raise EarningsBriefReleaseError("source ID is invalid")
        source_ids.add(source["source_id"])
        parsed = urlparse(source["url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise EarningsBriefReleaseError("source URL must use HTTPS")
        if source["review_state"] != "reviewed":
            raise EarningsBriefReleaseError("source is not reviewed")
        if source["tier"] not in _SOURCE_TIERS or source["family"] not in _SOURCE_FAMILIES:
            raise EarningsBriefReleaseError("source classification is invalid")
        if not all(_DATE.fullmatch(source[key]) for key in ("publication_date", "retrieved_at", "as_of")):
            raise EarningsBriefReleaseError("source date is invalid")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", source["content_hash"]):
            raise EarningsBriefReleaseError("source hash is invalid")

    brief = release["brief"]
    items = [
        brief["judgment"],
        *brief["kpis"],
        *brief["management_signals"],
        *brief["quarterly_trends"],
        *brief["gross_margin_trends"],
        *brief["revenue_mix"],
        *brief["market_focus"],
        *brief["structural_signals"],
    ]
    ids = {item["id"] for item in items}
    if len(ids) != len(items):
        raise EarningsBriefReleaseError("duplicate evidence item")
    for item in items:
        if not set(item).issubset(_ITEM_KEYS):
            raise EarningsBriefReleaseError("evidence item keys are invalid")
        if not {"id", "label", "evidence_state", "as_of", "source_ids"}.issubset(item):
            raise EarningsBriefReleaseError("evidence item fields are incomplete")
        if not _ID.fullmatch(item["id"]) or not _DATE.fullmatch(item["as_of"]):
            raise EarningsBriefReleaseError("evidence identity or date is invalid")
        if item.get("claim_kind") is not None and item["claim_kind"] not in _CLAIM_KINDS:
            raise EarningsBriefReleaseError("claim kind is invalid")
        if item.get("text") is not None and item.get("claim_kind") is None:
            raise EarningsBriefReleaseError("claim kind is required")
        if item.get("unit") is not None and item["unit"] not in _UNITS:
            raise EarningsBriefReleaseError("unit is invalid")
        if item.get("currency") not in {None, "USD"}:
            raise EarningsBriefReleaseError("currency is invalid")
        state = item.get("evidence_state")
        if state not in _EVIDENCE_STATES:
            raise EarningsBriefReleaseError("evidence state is invalid")
        if not item.get("as_of"):
            raise EarningsBriefReleaseError("evidence as-of is required")
        if not set(item.get("source_ids", ())).issubset(source_ids):
            raise EarningsBriefReleaseError("unknown source reference")
        has_value = item.get("value") is not None
        is_numeric = item.get("unit") is not None
        if is_numeric and state == "available":
            if not has_value or not item.get("display"):
                raise EarningsBriefReleaseError("numeric field requires value and display")
            try:
                Decimal(str(item["value"]))
            except Exception as exc:
                raise EarningsBriefReleaseError("numeric field requires decimal value") from exc
        if state == "available" and "value" in item and not has_value:
            raise EarningsBriefReleaseError("available field requires value")
        if state != "available" and (has_value or item.get("display")):
            raise EarningsBriefReleaseError("non-available field cannot carry value")
        if state == "conflict" and len(item.get("candidates", ())) < 2:
            raise EarningsBriefReleaseError("conflict candidates are required")
        if state == "conflict":
            for candidate in item["candidates"]:
                if set(candidate) != {"value", "display", "as_of", "source_ids"}:
                    raise EarningsBriefReleaseError("conflict candidate keys are invalid")
                if (
                    not _DATE.fullmatch(candidate["as_of"])
                    or not candidate["source_ids"]
                    or not set(candidate["source_ids"]).issubset(source_ids)
                ):
                    raise EarningsBriefReleaseError("conflict candidate evidence is invalid")
                try:
                    Decimal(str(candidate["value"]))
                except Exception as exc:
                    raise EarningsBriefReleaseError("conflict candidate value is invalid") from exc
        if state == "available" and not item.get("source_ids"):
            raise EarningsBriefReleaseError("available evidence requires source")
        if item.get("formula"):
            if item["formula"] != "metric:gross-profit / metric:revenue * 100":
                raise EarningsBriefReleaseError("derived formula is invalid")
            input_ids = item.get("input_ids", ())
            if not input_ids or not set(input_ids).issubset(ids):
                raise EarningsBriefReleaseError("derived inputs are invalid")
            by_id = {entry["id"]: entry for entry in items}
            inputs = [Decimal(str(by_id[field_id]["value"])) for field_id in input_ids]
            expected = (inputs[0] / inputs[1] * Decimal("100")).quantize(Decimal("0.1"))
            if Decimal(str(item["value"])).quantize(Decimal("0.1")) != expected:
                raise EarningsBriefReleaseError("derived value does not match inputs")
        if item.get("claim_kind") == "analytical_inference":
            supporting = item.get("supporting_claim_ids", ())
            if not supporting or not set(supporting).issubset(ids - {item["id"]}):
                raise EarningsBriefReleaseError("analytical inference support is invalid")
        for key in ("label", "text", "display"):
            if key in item and item[key] is not None and len(str(item[key])) > 800:
                raise EarningsBriefReleaseError("evidence text is too long")

    flow = brief["financial_flow"]
    if set(flow) != {
        "revenue_id",
        "gross_profit_id",
        "net_income_id",
        "cost_of_sales_id",
        "operating_expenses_id",
    }:
        raise EarningsBriefReleaseError("financial flow keys are invalid")
    if not set(flow.values()).issubset(ids):
        raise EarningsBriefReleaseError("financial flow references are invalid")

    for scenario in brief["scenarios"]:
        if set(scenario) != {
            "id",
            "kind",
            "label",
            "summary",
            "validation_conditions",
        }:
            raise EarningsBriefReleaseError("scenario keys are invalid")
        if scenario["kind"] not in {"bull", "base", "bear"}:
            raise EarningsBriefReleaseError("scenario kind is invalid")
        if not scenario["validation_conditions"]:
            raise EarningsBriefReleaseError("scenario validation is required")
    serialized = json.dumps(release, ensure_ascii=False).encode("utf-8")
    if _UNSAFE_CONTENT.search(serialized.decode("utf-8")):
        raise EarningsBriefReleaseError("unsafe content is not admitted")
    if len(serialized) > 1024 * 1024:
        raise EarningsBriefReleaseError("release is too large")
    return release


def build_public_projection(release: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_release(release)
    sources = [
        {key: value for key, value in source.items() if key != "content_hash"}
        for source in validated["sources"]
    ]
    return {
        "ok": True,
        "schema_version": "earnings_brief_public.v1",
        "release": {
            "release_id": validated["release_id"],
            "review_state": validated["review_state"],
            "generated_at": validated["generated_at"],
            "evidence_as_of": validated["evidence_as_of"],
        },
        "catalog": list_catalog(),
        "brief": {
            "company": validated["company"],
            "reporting_period": validated["reporting_period"],
            "generated_at": validated["generated_at"],
            "evidence_as_of": validated["evidence_as_of"],
            **validated["brief"],
            "sources": sources,
        },
    }
