from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.futu_provider import FutuProviderError, get_futu_index_history


@dataclass(frozen=True)
class SourceDefinition:
    source_type: str
    status_key: str
    context_key: str
    env_prefix: str
    payload_keys: tuple[str, ...]


SOURCE_DEFINITIONS = (
    SourceDefinition(
        source_type="indexes",
        status_key="indexes",
        context_key="index_summary",
        env_prefix="WEEKLY_REVIEW_INDEX",
        payload_keys=("indexes", "index_summary", "items"),
    ),
    SourceDefinition(
        source_type="macro",
        status_key="macro",
        context_key="macro_events",
        env_prefix="WEEKLY_REVIEW_MACRO",
        payload_keys=("macro", "macro_events", "events", "items"),
    ),
    SourceDefinition(
        source_type="news_themes",
        status_key="news_themes",
        context_key="news_themes",
        env_prefix="WEEKLY_REVIEW_NEWS_THEMES",
        payload_keys=("news_themes", "themes", "items"),
    ),
    SourceDefinition(
        source_type="opportunities",
        status_key="opportunities",
        context_key="opportunity_items",
        env_prefix="WEEKLY_REVIEW_OPPORTUNITIES",
        payload_keys=("opportunities", "opportunity_items", "items"),
    ),
)


DEFAULT_INDEX_BASKET = (
    {
        "market": "US",
        "name": "Nasdaq 100",
        "codes": [
            {
                "code": "US.QQQ",
                "instrument_type": "proxy_etf",
                "proxy_for": "Nasdaq 100",
                "source_note": "Futu OpenD does not provide direct US index K-line data in this environment; QQQ is used as a tradable Nasdaq 100 proxy.",
            }
        ],
        "portfolio_relevance": "观察美股大型科技和 AI 成长股风险偏好。",
    },
    {
        "market": "US",
        "name": "S&P 500",
        "codes": [
            {
                "code": "US.SPY",
                "instrument_type": "proxy_etf",
                "proxy_for": "S&P 500",
                "source_note": "Futu OpenD does not provide direct US index K-line data in this environment; SPY is used as a tradable S&P 500 proxy.",
            }
        ],
        "portfolio_relevance": "观察美股大盘风险偏好和组合美元资产背景。",
    },
    {
        "market": "US",
        "name": "Dow Jones",
        "codes": [
            {
                "code": "US.DIA",
                "instrument_type": "proxy_etf",
                "proxy_for": "Dow Jones",
                "source_note": "Futu OpenD does not provide direct US index K-line data in this environment; DIA is used as a tradable Dow Jones proxy.",
            }
        ],
        "portfolio_relevance": "观察美股传统蓝筹和风险偏好是否扩散。",
    },
    {
        "market": "HK",
        "name": "恒生指数",
        "codes": ["HK.HSI"],
        "portfolio_relevance": "观察港股大盘和南向资金情绪背景。",
    },
    {
        "market": "HK",
        "name": "恒生科技",
        "codes": ["HK.HSTECH"],
        "portfolio_relevance": "影响港股科技成长仓和中概相关情绪。",
    },
    {
        "market": "CN",
        "name": "沪深300",
        "codes": ["SH.000300", "SZ.399300"],
        "portfolio_relevance": "观察 A 股核心资产风险偏好。",
    },
    {
        "market": "CN",
        "name": "创业板指",
        "codes": ["SZ.399006"],
        "portfolio_relevance": "观察 A 股成长和题材风险偏好。",
    },
    {
        "market": "CN",
        "name": "科创50",
        "codes": ["SH.000688"],
        "portfolio_relevance": "观察半导体、硬科技和 AI 供应链情绪。",
    },
)


def diagnose_default_index_provider(*, start: date, end: date) -> dict[str, Any]:
    warnings: list[str] = []
    payload, provider, reason = _fetch_default_index_payload(start=start, end=end, warnings=warnings)
    items = _extract_items(payload, SOURCE_DEFINITIONS[0])
    status = "ok" if items else "missing"
    errors: list[Any] = []
    if isinstance(payload, dict):
        errors = list(payload.get("errors") or [])
        if items and errors:
            status = "partial"
        elif payload is not None and not items:
            status = "empty"
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "provider": provider,
        "status": status,
        "count": len(items),
        "indexes": items,
        "errors": errors,
        "reason": reason,
        "warnings": warnings,
        "basket": [dict(item) for item in DEFAULT_INDEX_BASKET],
    }


def load_weekly_review_external_sources(
    *,
    start: date,
    end: date,
    force_refresh: bool = False,
    run_id: int | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_status": {},
        "source_summary": {},
    }
    cached_by_type = {
        row["source_type"]: row
        for row in repository.list_weekly_review_sources(start.isoformat(), end.isoformat())
    }
    file_payload = _load_external_source_file(warnings=warnings)
    for definition in SOURCE_DEFINITIONS:
        cached = cached_by_type.get(definition.source_type)
        if cached and not force_refresh and _cache_is_valid(cached):
            items = _extract_items(cached.get("payload"), definition)
            status = _status_from_items(items, cached=True, provider=cached.get("provider"), reason=cached.get("reason"))
            result[definition.context_key] = items
            result["source_status"][definition.status_key] = status
            result["source_summary"][definition.source_type] = {
                "status": status["status"],
                "count": len(items),
                "provider": cached.get("provider"),
                "cached": True,
            }
            continue

        payload, provider, reason = _fetch_source_payload(
            definition,
            file_payload=file_payload,
            start=start,
            end=end,
            warnings=warnings,
        )
        items = _extract_items(payload, definition)
        status_text = "ok" if items else "missing"
        if payload is not None and not items:
            status_text = "empty"
            reason = reason or "payload contained no items"
        if isinstance(payload, dict) and items and payload.get("errors"):
            status_text = "partial"
            reason = reason or "; ".join(str(item) for item in (payload.get("errors") or [])[:3])
        cache_row = repository.upsert_weekly_review_source(
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            source_type=definition.source_type,
            provider=provider,
            source_key="default",
            status=status_text,
            payload=payload if payload is not None else {},
            reason=reason,
            run_id=run_id,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        )
        status = _status_from_items(
            items,
            cached=False,
            provider=provider,
            reason=reason,
            fetched_at=cache_row.get("fetched_at"),
            status_override=status_text,
        )
        result[definition.context_key] = items
        result["source_status"][definition.status_key] = status
        result["source_summary"][definition.source_type] = {
            "status": status["status"],
            "count": len(items),
            "provider": provider,
            "cached": False,
        }
    return result


def build_budget_warnings(token_usage: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(token_usage, dict) or not token_usage:
        return []
    warnings: list[dict[str, Any]] = []
    total_tokens = _token_total(token_usage)
    token_threshold = _int_env("WEEKLY_REVIEW_TOKEN_WARNING_TOTAL")
    if token_threshold is not None and total_tokens > token_threshold:
        warnings.append(
            {
                "type": "token_threshold",
                "severity": "warning",
                "message": f"Token usage {total_tokens} exceeded warning threshold {token_threshold}.",
                "actual": total_tokens,
                "threshold": token_threshold,
            }
        )
    cost = _float_or_none(token_usage.get("estimated_cost") or token_usage.get("cost"))
    cost_threshold = _float_env("WEEKLY_REVIEW_COST_WARNING")
    if cost_threshold is not None and cost is not None and cost > cost_threshold:
        warnings.append(
            {
                "type": "cost_threshold",
                "severity": "warning",
                "message": f"Estimated cost {cost} exceeded warning threshold {cost_threshold}.",
                "actual": cost,
                "threshold": cost_threshold,
            }
        )
    return warnings


def _load_external_source_file(*, warnings: list[str] | None) -> dict[str, Any]:
    path_text = os.getenv("WEEKLY_REVIEW_EXTERNAL_SOURCE_FILE")
    if not path_text:
        return {}
    try:
        value = json.loads(Path(path_text).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        if warnings is not None:
            warnings.append(f"weekly review external source file failed: {exc}")
        return {}


def _fetch_source_payload(
    definition: SourceDefinition,
    *,
    file_payload: dict[str, Any],
    start: date,
    end: date,
    warnings: list[str] | None,
) -> tuple[Any | None, str, str | None]:
    for key in (definition.source_type, definition.status_key, *definition.payload_keys):
        if key in file_payload:
            return file_payload[key], "json_file", None

    env_json = os.getenv(f"{definition.env_prefix}_JSON")
    if env_json:
        try:
            return json.loads(env_json), "env_json", None
        except json.JSONDecodeError as exc:
            reason = f"invalid JSON env: {exc}"
            if warnings is not None:
                warnings.append(f"{definition.source_type} {reason}")
            return None, "env_json", reason

    env_url = os.getenv(f"{definition.env_prefix}_URL")
    if env_url:
        try:
            request = Request(env_url, headers={"User-Agent": "InvestmentKnowledgeWeeklyReview/1.0"})
            with urlopen(request, timeout=8) as response:
                return json.loads(response.read().decode("utf-8")), "json_url", None
        except (OSError, URLError, json.JSONDecodeError) as exc:
            reason = f"URL fetch failed: {exc}"
            if warnings is not None:
                warnings.append(f"{definition.source_type} {reason}")
            return None, "json_url", reason

    if definition.source_type == "indexes":
        return _fetch_default_index_payload(start=start, end=end, warnings=warnings)

    return None, "not_configured", "provider not configured"


def _fetch_default_index_payload(
    *,
    start: date,
    end: date,
    warnings: list[str] | None,
) -> tuple[dict[str, Any] | None, str, str | None]:
    try:
        snapshot = get_futu_index_history(
            start=start.isoformat(),
            end=end.isoformat(),
            indexes=[dict(item) for item in DEFAULT_INDEX_BASKET],
        )
    except FutuProviderError as exc:
        reason = str(exc)
        if warnings is not None:
            warnings.append(f"indexes {reason}")
        return None, "futu.request_history_kline", reason
    except Exception as exc:
        reason = f"Futu index provider failed: {exc}"
        if warnings is not None:
            warnings.append(f"indexes {reason}")
        return None, "futu.request_history_kline", reason

    payload = {
        "indexes": snapshot.indexes,
        "errors": snapshot.errors,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "start": snapshot.start,
        "end": snapshot.end,
        "basket": [dict(item) for item in DEFAULT_INDEX_BASKET],
    }
    reason = "; ".join(snapshot.errors[:3]) if snapshot.errors else None
    if snapshot.errors and warnings is not None:
        warnings.append(f"indexes partial: {reason}")
    return payload, "futu.request_history_kline", reason


def _extract_items(payload: Any, definition: SourceDefinition) -> list[dict[str, Any]]:
    if payload is None:
        return []
    raw_items: Any = payload
    if isinstance(payload, dict):
        for key in definition.payload_keys:
            if key in payload:
                raw_items = payload[key]
                break
        else:
            raw_items = payload.get("items", payload)
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []
    return [_normalize_item(item) for item in raw_items if isinstance(item, dict)]


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in item.items() if value is not None}


def _status_from_items(
    items: list[dict[str, Any]],
    *,
    cached: bool,
    provider: str | None,
    reason: str | None = None,
    fetched_at: str | None = None,
    status_override: str | None = None,
) -> dict[str, Any]:
    status = status_override or ("cached" if cached and items else ("ok" if items else "missing"))
    result: dict[str, Any] = {
        "status": status,
        "count": len(items),
        "provider": provider or "unknown",
        "cached": cached,
    }
    if reason:
        result["reason"] = reason
    if fetched_at:
        result["fetched_at"] = fetched_at
    return result


def _cache_is_valid(row: dict[str, Any]) -> bool:
    expires_at = row.get("expires_at")
    if not expires_at:
        return True
    try:
        expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)


def _token_total(token_usage: dict[str, Any]) -> int:
    for key in ("total_tokens", "tokens"):
        value = _int_or_none(token_usage.get(key))
        if value is not None:
            return value
    return sum(
        _int_or_none(token_usage.get(key)) or 0
        for key in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens")
    )


def _int_env(name: str) -> int | None:
    return _int_or_none(os.getenv(name))


def _float_env(name: str) -> float | None:
    return _float_or_none(os.getenv(name))


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
