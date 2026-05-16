from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_RELATION_TYPES = {"main", "theme", "related"}
ALLOWED_KNOWLEDGE_TYPES = {
    "announcement",
    "business",
    "equity_structure",
    "history",
    "research_source",
    "risk",
    "sector_logic",
    "watch_item",
}


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_research_draft(draft: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()

    stock = _require_dict(draft, "stock", result)
    sources = _require_list(draft, "sources", result)
    sectors = _require_list(draft, "sectors", result)
    knowledge_items = _require_list(draft, "knowledge_items", result)
    user_insights = _require_list(draft, "user_insights", result)

    if stock:
        _require_non_empty_string(stock, "symbol", "stock.symbol", result)
        _require_non_empty_string(stock, "market", "stock.market", result)
        for field_name in [
            "name",
            "core_business",
            "equity_structure",
            "stock_character",
            "notable_history",
        ]:
            if not _has_text(stock.get(field_name)):
                result.warnings.append(f"stock.{field_name} is empty")

    source_keys = _validate_sources(sources, result)
    _validate_sectors(sectors, source_keys, result)
    _validate_knowledge_items(knowledge_items, source_keys, result)
    _validate_user_insights(user_insights, result)

    return result


def _require_dict(
    payload: dict[str, Any],
    key: str,
    result: ValidationResult,
) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        result.errors.append(f"{key} must be an object")
        return {}
    return value


def _require_list(
    payload: dict[str, Any],
    key: str,
    result: ValidationResult,
) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        result.errors.append(f"{key} must be an array")
        return []
    return value


def _validate_sources(sources: list[Any], result: ValidationResult) -> set[str]:
    source_keys: set[str] = set()
    for index, source in enumerate(sources):
        path = f"sources[{index}]"
        if not isinstance(source, dict):
            result.errors.append(f"{path} must be an object")
            continue

        key = source.get("key")
        if not _has_text(key):
            result.errors.append(f"{path}.key is required")
            continue
        if key in source_keys:
            result.errors.append(f"{path}.key duplicates source key '{key}'")
        source_keys.add(key)

        _require_non_empty_string(source, "source_type", f"{path}.source_type", result)
        _require_non_empty_string(source, "title", f"{path}.title", result)

    if not source_keys:
        result.warnings.append("sources is empty; factual knowledge will not be traceable")
    return source_keys


def _validate_sectors(
    sectors: list[Any],
    source_keys: set[str],
    result: ValidationResult,
) -> None:
    for index, sector in enumerate(sectors):
        path = f"sectors[{index}]"
        if not isinstance(sector, dict):
            result.errors.append(f"{path} must be an object")
            continue

        sector_path = sector.get("path")
        if not isinstance(sector_path, list) or not sector_path:
            result.errors.append(f"{path}.path must be a non-empty array")
        elif any(not _has_text(item) for item in sector_path):
            result.errors.append(f"{path}.path must contain only non-empty strings")

        relation_type = sector.get("relation_type", "related")
        if relation_type not in ALLOWED_RELATION_TYPES:
            result.errors.append(f"{path}.relation_type '{relation_type}' is not allowed")

        _validate_confidence(sector, f"{path}.confidence", result)
        _validate_source_key(sector, f"{path}.source_key", source_keys, result)


def _validate_knowledge_items(
    knowledge_items: list[Any],
    source_keys: set[str],
    result: ValidationResult,
) -> None:
    for index, item in enumerate(knowledge_items):
        path = f"knowledge_items[{index}]"
        if not isinstance(item, dict):
            result.errors.append(f"{path} must be an object")
            continue

        knowledge_type = item.get("knowledge_type")
        if not _has_text(knowledge_type):
            result.errors.append(f"{path}.knowledge_type is required")
        elif knowledge_type not in ALLOWED_KNOWLEDGE_TYPES:
            result.warnings.append(f"{path}.knowledge_type '{knowledge_type}' is not in the known list")

        _require_non_empty_string(item, "content", f"{path}.content", result)
        _validate_confidence(item, f"{path}.confidence", result)
        _validate_source_key(item, f"{path}.source_key", source_keys, result, required=True)


def _validate_user_insights(user_insights: list[Any], result: ValidationResult) -> None:
    for index, insight in enumerate(user_insights):
        path = f"user_insights[{index}]"
        if not isinstance(insight, dict):
            result.errors.append(f"{path} must be an object")
            continue

        _require_non_empty_string(insight, "insight", f"{path}.insight", result)
        tags = insight.get("tags", [])
        if not isinstance(tags, list):
            result.errors.append(f"{path}.tags must be an array when provided")
        elif any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            result.errors.append(f"{path}.tags must contain only non-empty strings")


def _validate_source_key(
    payload: dict[str, Any],
    path: str,
    source_keys: set[str],
    result: ValidationResult,
    required: bool = False,
) -> None:
    source_key = payload.get("source_key")
    if source_key is None:
        if required:
            result.errors.append(f"{path} is required")
        return

    if not _has_text(source_key):
        result.errors.append(f"{path} must be a non-empty string")
    elif source_key not in source_keys:
        result.errors.append(f"{path} references unknown source key '{source_key}'")


def _validate_confidence(
    payload: dict[str, Any],
    path: str,
    result: ValidationResult,
) -> None:
    confidence = payload.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        result.errors.append(f"{path} must be a number")
        return
    if confidence < 0 or confidence > 1:
        result.errors.append(f"{path} must be between 0 and 1")


def _require_non_empty_string(
    payload: dict[str, Any],
    key: str,
    path: str,
    result: ValidationResult,
) -> None:
    if not _has_text(payload.get(key)):
        result.errors.append(f"{path} is required")


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
