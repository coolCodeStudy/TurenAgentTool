from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from investment_knowledge_mcp.research.source_facts import extract_numbers
from investment_knowledge_mcp.research.validation import validate_research_draft


OFFICIAL_PUBLISHERS = {
    "HKEX",
    "HKEXnews",
    "SEC",
    "Lumentum",
    "Alibaba Group",
    "SMIC",
    "iShares",
    "Roundhill Investments",
    "Sprott",
    "Meituan",
    "巨子生物",
    "Hang Seng Indexes Company",
    "Hang Seng Indexes Company Limited",
}
SECONDARY_PUBLISHER_PATTERNS = [
    re.compile(r"etnet|经济通|經濟通", re.I),
]
OFFICIAL_PUBLISHER_PATTERNS = [
    re.compile(r"\b(investor relations|issuer ir)\b", re.I),
    re.compile(r"(国家市场监督管理总局|市场监督管理局|SAMR)", re.I),
]


@dataclass
class AuditResult:
    status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok_for_auto_import(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "notes": self.notes,
        }


def audit_research_draft(draft: dict[str, Any], source_facts: dict[str, Any] | None = None) -> AuditResult:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    validation = validate_research_draft(draft)
    errors.extend(validation.errors)
    warnings.extend(validation.warnings)

    sources = {source.get("key"): source for source in draft.get("sources") or [] if isinstance(source, dict)}
    if not sources:
        errors.append("no sources found")

    non_official = [str(source.get("publisher") or "") for source in sources.values() if not _is_official_source(source)]
    if non_official:
        warnings.append(f"non-official publishers present: {sorted(set(non_official))}")

    empty_excerpts = [key for key, source in sources.items() if not source.get("content_excerpt")]
    if empty_excerpts:
        warnings.append(f"sources without content_excerpt: {empty_excerpts}")

    referenced_keys = _referenced_source_keys(draft)
    unknown_keys = sorted(key for key in referenced_keys if key not in sources)
    if unknown_keys:
        errors.append(f"unknown source_key references: {unknown_keys}")

    untraceable = _find_untraceable_numbers(draft, sources)
    if untraceable:
        warnings.append(f"numbers not found in referenced source excerpts: {untraceable[:12]}")

    if source_facts is not None:
        fact_count = int(source_facts.get("fact_count") or 0)
        notes.append(f"source_facts extracted: {fact_count}")
        if fact_count == 0:
            warnings.append("no source facts extracted from source excerpts")

    if errors:
        status = "fail"
    elif warnings:
        status = "needs_review"
    else:
        status = "pass"

    return AuditResult(status=status, errors=errors, warnings=warnings, notes=notes)


def build_audit_markdown(
    draft: dict[str, Any],
    source_facts: dict[str, Any],
    audit: AuditResult,
) -> str:
    stock = draft.get("stock") or {}
    lines = [
        f"# {stock.get('name') or stock.get('symbol') or 'Unknown'} 研究草稿审核",
        "",
        f"- audit_status: `{audit.status}`",
        f"- errors: {len(audit.errors)}",
        f"- warnings: {len(audit.warnings)}",
        f"- source_facts: {source_facts.get('fact_count', 0)}",
        "",
    ]

    if audit.errors:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {item}" for item in audit.errors)
        lines.append("")

    if audit.warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in audit.warnings)
        lines.append("")

    if audit.notes:
        lines.extend(["## Notes", ""])
        lines.extend(f"- {item}" for item in audit.notes)
        lines.append("")

    lines.extend(["## Extracted Source Facts", ""])
    facts = source_facts.get("facts") or []
    if not facts:
        lines.append("- none")
    else:
        for fact in facts[:30]:
            lines.append(
                f"- `{fact.get('source_key')}` {fact.get('fact_type')}: "
                f"{fact.get('excerpt')}"
            )
    lines.append("")
    lines.extend(["## Audit JSON", "", "```json", json.dumps(audit.to_dict(), ensure_ascii=False, indent=2), "```"])
    return "\n".join(lines)


def _referenced_source_keys(draft: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for section in ("sectors", "knowledge_items"):
        for item in draft.get(section) or []:
            if isinstance(item, dict) and isinstance(item.get("source_key"), str):
                keys.add(item["source_key"])
    return keys


def _find_untraceable_numbers(draft: dict[str, Any], sources: dict[str, dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for item in draft.get("knowledge_items") or []:
        if not isinstance(item, dict):
            continue
        source_key = item.get("source_key")
        excerpt = ""
        if isinstance(source_key, str) and isinstance(sources.get(source_key), dict):
            excerpt = str(sources[source_key].get("content_excerpt") or "")
        if not excerpt:
            continue
        excerpt_digits = _digits_only(excerpt)
        for number in extract_numbers(str(item.get("content") or "")):
            if _is_low_signal_number(number):
                continue
            normalized = _digits_only(number)
            if len(normalized) >= 3 and not _number_found(normalized, excerpt_digits):
                missing.append(f"{source_key}:{number}")
    return missing


def _is_official_source(source: dict[str, Any]) -> bool:
    url = str(source.get("url") or "")
    if re.search(r"(hkexnews\.hk|sec\.gov)", url, flags=re.I):
        return True
    publisher = str(source.get("publisher") or "")
    if not publisher:
        return False
    if publisher in OFFICIAL_PUBLISHERS:
        return True
    if any(pattern.search(publisher) for pattern in OFFICIAL_PUBLISHER_PATTERNS):
        return True
    if any(pattern.search(publisher) for pattern in SECONDARY_PUBLISHER_PATTERNS):
        return False
    return False


def _is_low_signal_number(number: str) -> bool:
    value = number.rstrip("%")
    if re.fullmatch(r"20\d{2}|19\d{2}", value):
        return True
    return False


def _number_found(normalized: str, excerpt_digits: str) -> bool:
    candidates = {normalized}
    candidates.add(normalized.lstrip("0") or "0")
    if normalized.endswith("0"):
        candidates.add(normalized.rstrip("0"))
    if normalized.endswith("00"):
        candidates.add(normalized.rstrip("0"))
    return any(candidate and candidate in excerpt_digits for candidate in candidates)


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)
