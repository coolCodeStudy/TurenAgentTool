from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.decision_repository import (
    get_active_constraint_profile,
    latest_account_snapshot,
    list_constraint_profile_changes,
    list_latest_observations,
    upsert_default_constraint_profile,
)
from investment_knowledge_mcp.display import build_stock_decision_card
from investment_knowledge_mcp.research.jobs import list_research_jobs_for_stock


OBSERVATION_TYPES = [
    "technical_snapshot",
    "valuation_snapshot",
    "chip_event_snapshot",
    "sector_relative_strength",
    "market_relative_strength",
    "latest_quote_snapshot",
]

OBSERVATION_TO_PACK = {
    "technical_snapshot": "technical_pack",
    "valuation_snapshot": "valuation_pack",
    "chip_event_snapshot": "chip_event_pack",
    "sector_relative_strength": "sector_pack",
    "market_relative_strength": "market_pack",
    "latest_quote_snapshot": "quote_pack",
}


def build_decision_context_pack(symbol: str, market: str, mode: str = "focused") -> dict[str, Any]:
    graph_context = repository.get_stock_context(symbol=symbol, market=market)
    stock = graph_context.get("stock")
    if not stock:
        raise ValueError(f"stock not found: {symbol} {market}")

    latest_job = _latest_research_job(symbol=symbol, market=market)
    stock_card = build_stock_decision_card(graph_context, latest_research_job=latest_job)
    profile = get_active_constraint_profile() or upsert_default_constraint_profile()
    observations = list_latest_observations(stock_id=int(stock["id"]), types=OBSERVATION_TYPES)
    observation_packs = build_observation_packs(observations)
    portfolio_pack = build_portfolio_exposure_pack(symbol=symbol, market=market, graph_context=graph_context)
    user_constraint_pack = build_user_constraint_pack(profile)
    freshness_report = build_freshness_report(
        profile=profile,
        portfolio_pack=portfolio_pack,
        observation_packs=observation_packs,
        graph_context=graph_context,
    )
    evidence_index = build_evidence_index(graph_context=graph_context, observations=observations, latest_job=latest_job)

    context_pack = {
        "mode": mode,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "stock": {
            "id": stock.get("id"),
            "symbol": stock.get("symbol"),
            "market": stock.get("market"),
            "name": stock.get("name"),
        },
        "user_constraints": user_constraint_pack,
        "portfolio_exposure": portfolio_pack,
        "stock_card": stock_card,
        "valuation_pack": observation_packs.get("valuation_pack"),
        "technical_pack": observation_packs.get("technical_pack"),
        "chip_event_pack": observation_packs.get("chip_event_pack"),
        "sector_pack": _sector_pack(graph_context, observation_packs.get("sector_pack")),
        "market_pack": _market_pack(stock.get("market"), observation_packs.get("market_pack")),
        "quote_pack": observation_packs.get("quote_pack"),
        "freshness_report": freshness_report,
        "open_questions": _open_questions(freshness_report, graph_context),
        "evidence_index": evidence_index,
        "pending_profile_changes": list_constraint_profile_changes(status="pending", limit=20),
        "graph_counts": {
            "stock_knowledge": len(graph_context.get("stock_knowledge") or []),
            "sector_knowledge": len(graph_context.get("sector_knowledge") or []),
            "sources": len(graph_context.get("sources") or []),
            "stock_candidate_insights": len(graph_context.get("stock_candidate_insights") or []),
            "sector_candidate_insights": len(graph_context.get("sector_candidate_insights") or []),
            "global_candidate_insights": len(graph_context.get("global_candidate_insights") or []),
        },
    }
    context_pack["input_context_hash"] = context_hash(context_pack)
    return context_pack


def build_user_constraint_pack(profile: dict[str, Any]) -> dict[str, Any]:
    missing = [
        field
        for field in (
            "max_single_stock_position_pct",
            "preferred_starter_position_pct",
            "cash_reserve_min_pct",
            "max_theme_exposure_pct",
        )
        if profile.get(field) is None
    ]
    unconfirmed = not bool(profile.get("confirmed_by_user"))
    return {
        "profile_id": profile.get("id"),
        "profile_name": profile.get("profile_name"),
        "confirmed_by_user": bool(profile.get("confirmed_by_user")),
        "missing_fields": missing,
        "unconfirmed_defaults": unconfirmed,
        "max_single_stock_position_pct": _num(profile.get("max_single_stock_position_pct"), 0.06),
        "preferred_starter_position_pct": _num(profile.get("preferred_starter_position_pct"), 0.02),
        "cash_reserve_min_pct": _num(profile.get("cash_reserve_min_pct"), 0.10),
        "max_positions_target": int(profile.get("max_positions_target") or 12),
        "max_positions_hard_cap": int(profile.get("max_positions_hard_cap") or 20),
        "daily_monitoring_minutes": int(profile.get("daily_monitoring_minutes") or 30),
        "weekly_research_hours": _num(profile.get("weekly_research_hours"), 3.0),
        "max_theme_exposure_pct": _num(profile.get("max_theme_exposure_pct"), 0.30),
        "max_market_exposure": profile.get("max_market_exposure_json") or {},
        "volatility_tolerance": profile.get("volatility_tolerance") or "medium",
        "drawdown_tolerance": profile.get("drawdown_tolerance") or "medium",
        "missed_opportunity_vs_drawdown_bias": profile.get("missed_opportunity_vs_drawdown_bias") or "drawdown",
        "event_stock_allowed": bool(profile.get("event_stock_allowed")),
    }


def build_portfolio_exposure_pack(
    *,
    symbol: str,
    market: str,
    graph_context: dict[str, Any],
) -> dict[str, Any]:
    snapshot = latest_account_snapshot()
    if not snapshot:
        return {
            "status": "missing",
            "snapshot": None,
            "position_count": 0,
            "target_holding": None,
            "market_exposure": [],
            "currency_exposure": [],
            "warnings": ["No account snapshot is available; portfolio fit is provisional."],
        }

    positions = list(snapshot.get("positions") or [])
    normalized = [_normalize_position(item) for item in positions]
    by_currency = _group_sum(normalized, "currency")
    total_by_currency = {item["key"]: item["market_value"] for item in by_currency}
    for item in normalized:
        total = total_by_currency.get(item["currency"]) or 0
        item["currency_weight"] = item["market_value"] / total if total else None

    target = _find_target_holding(normalized, symbol=symbol, market=market)
    market_exposure = _group_sum(normalized, "market")
    sector_names = [sector.get("sector_name") or sector.get("name") for sector in graph_context.get("sectors") or []]

    return {
        "status": "ok",
        "snapshot": {
            "id": snapshot.get("id"),
            "snapshot_date": snapshot.get("snapshot_date"),
            "fetched_at": snapshot.get("fetched_at"),
            "source": snapshot.get("source"),
        },
        "position_count": len(normalized),
        "target_holding": target,
        "market_exposure": market_exposure,
        "currency_exposure": by_currency,
        "stock_sector_names": [name for name in sector_names if name],
        "warnings": _portfolio_warnings(normalized),
    }


def build_observation_packs(observations: list[dict[str, Any]]) -> dict[str, Any]:
    packs: dict[str, Any] = {
        "technical_pack": _missing_pack("technical_snapshot"),
        "valuation_pack": _missing_pack("valuation_snapshot"),
        "chip_event_pack": _missing_pack("chip_event_snapshot"),
        "sector_pack": _missing_pack("sector_relative_strength"),
        "market_pack": _missing_pack("market_relative_strength"),
        "quote_pack": _missing_pack("latest_quote_snapshot"),
    }
    for observation in observations:
        key = OBSERVATION_TO_PACK.get(str(observation.get("observation_type") or ""))
        if not key:
            continue
        packs[key] = {
            "status": _freshness_status(observation.get("stale_after")),
            "observation_id": observation.get("id"),
            "observation_type": observation.get("observation_type"),
            "observed_at": observation.get("observed_at"),
            "stale_after": observation.get("stale_after"),
            "confidence": observation.get("confidence"),
            "value": observation.get("value_json") or {},
            "source_id": observation.get("source_id"),
        }
    return packs


def build_freshness_report(
    *,
    profile: dict[str, Any],
    portfolio_pack: dict[str, Any],
    observation_packs: dict[str, Any],
    graph_context: dict[str, Any],
) -> dict[str, Any]:
    components = []
    components.append(
        {
            "component": "user_constraints",
            "status": "ok" if profile.get("confirmed_by_user") else "unconfirmed",
            "reason": "profile confirmed by user" if profile.get("confirmed_by_user") else "using conservative unconfirmed defaults",
            "critical": True,
        }
    )
    components.append(
        {
            "component": "portfolio_exposure",
            "status": portfolio_pack.get("status"),
            "reason": "latest account snapshot found" if portfolio_pack.get("status") == "ok" else "no account snapshot available",
            "critical": True,
        }
    )
    for pack_name in ("technical_pack", "valuation_pack", "chip_event_pack", "sector_pack", "market_pack"):
        pack = observation_packs.get(pack_name) or {}
        components.append(
            {
                "component": pack_name,
                "status": pack.get("status", "missing"),
                "reason": pack.get("observation_type") or "no stored observation",
                "critical": pack_name in {"technical_pack", "valuation_pack"},
            }
        )
    source_count = len(graph_context.get("sources") or [])
    components.append(
        {
            "component": "source_coverage",
            "status": "ok" if source_count else "missing",
            "reason": f"{source_count} linked sources",
            "critical": False,
        }
    )
    overall = "ok"
    if any(item["status"] == "missing" and item["critical"] for item in components):
        overall = "missing_critical"
    elif any(item["status"] in {"missing", "stale", "unconfirmed"} for item in components):
        overall = "degraded"
    return {"overall_status": overall, "components": components}


def build_evidence_index(
    *,
    graph_context: dict[str, Any],
    observations: list[dict[str, Any]],
    latest_job: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in graph_context.get("stock_knowledge") or []:
        evidence.append(_evidence("knowledge_item", item.get("id"), item.get("knowledge_type"), item.get("content")))
    for item in graph_context.get("sector_knowledge") or []:
        evidence.append(_evidence("knowledge_item", item.get("id"), item.get("knowledge_type"), item.get("content")))
    for item in graph_context.get("stock_insights") or []:
        evidence.append(_evidence("user_insight", item.get("id"), "stock", item.get("normalized_summary") or item.get("insight")))
    for item in graph_context.get("sector_insights") or []:
        evidence.append(_evidence("user_insight", item.get("id"), "sector", item.get("normalized_summary") or item.get("insight")))
    for item in graph_context.get("global_insights") or []:
        evidence.append(_evidence("user_insight", item.get("id"), item.get("target_type"), item.get("normalized_summary") or item.get("insight")))
    for item in graph_context.get("sources") or []:
        evidence.append(_evidence("source", item.get("id"), item.get("source_type"), item.get("title") or item.get("url")))
    for item in observations:
        evidence.append(_evidence("stock_observation", item.get("id"), item.get("observation_type"), item.get("observed_at")))
    if latest_job:
        evidence.append(_evidence("research_job", latest_job.get("id"), latest_job.get("status"), latest_job.get("result_summary")))
    return [item for item in evidence if item.get("summary")][:80]


def context_hash(context_pack: dict[str, Any]) -> str:
    stable = {key: value for key, value in context_pack.items() if key not in {"built_at", "input_context_hash"}}
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _latest_research_job(symbol: str, market: str) -> dict[str, Any] | None:
    jobs = list_research_jobs_for_stock(symbol=symbol, market=market, limit=1)
    return jobs[0] if jobs else None


def _sector_pack(graph_context: dict[str, Any], observation_pack: dict[str, Any] | None) -> dict[str, Any]:
    sectors = graph_context.get("sectors") or []
    return {
        **(observation_pack or _missing_pack("sector_relative_strength")),
        "linked_sectors": [
            {
                "sector_id": sector.get("sector_id"),
                "name": sector.get("sector_name") or sector.get("name"),
                "path": sector.get("path"),
                "relation_type": sector.get("relation_type"),
            }
            for sector in sectors
        ],
    }


def _market_pack(market: str | None, observation_pack: dict[str, Any] | None) -> dict[str, Any]:
    return {**(observation_pack or _missing_pack("market_relative_strength")), "market": market}


def _open_questions(freshness_report: dict[str, Any], graph_context: dict[str, Any]) -> list[str]:
    questions = []
    for item in freshness_report.get("components") or []:
        if item.get("status") in {"missing", "stale", "unconfirmed"}:
            questions.append(f"Refresh or confirm {item['component']}: {item.get('reason')}")
    if not graph_context.get("stock_knowledge"):
        questions.append("Add stock-level facts before trusting a high-conviction decision.")
    return questions[:10]


def _normalize_position(item: dict[str, Any]) -> dict[str, Any]:
    code = str(item.get("code") or item.get("stock_code") or item.get("symbol") or "").upper()
    market = _market_from_code(code)
    currency = str(item.get("currency") or "").upper() or _currency_for_market(market)
    market_value = _num(
        item.get("market_val")
        or item.get("market_value")
        or item.get("val")
        or item.get("position_market_value"),
        0.0,
    )
    return {
        "code": code,
        "name": item.get("stock_name") or item.get("name") or item.get("stockName"),
        "market": market,
        "currency": currency,
        "market_value": market_value,
        "pl_ratio": _optional_num(item.get("pl_ratio") or item.get("plRatio")),
        "raw": item,
    }


def _find_target_holding(positions: list[dict[str, Any]], *, symbol: str, market: str) -> dict[str, Any] | None:
    symbol = symbol.upper()
    market = market.upper()
    for item in positions:
        code = str(item.get("code") or "").upper()
        if code.endswith(f".{symbol}") or code.startswith(f"{market}.{symbol}") or code == symbol:
            return item
        if symbol in code and (market == item.get("market") or "." not in code):
            return item
    return None


def _group_sum(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in items:
        value = str(item.get(key) or "UNKNOWN")
        bucket = grouped.setdefault(value, {"key": value, "market_value": 0.0, "position_count": 0})
        bucket["market_value"] += _num(item.get("market_value"), 0.0)
        bucket["position_count"] += 1
    return sorted(grouped.values(), key=lambda row: row["market_value"], reverse=True)


def _portfolio_warnings(positions: list[dict[str, Any]]) -> list[str]:
    currencies = {item.get("currency") for item in positions if item.get("currency") and item.get("currency") != "UNKNOWN"}
    if len(currencies) > 1:
        return ["Portfolio contains multiple currencies; V1 uses currency-level weights instead of a single converted total."]
    return []


def _market_from_code(code: str) -> str:
    if "." in code:
        return code.split(".", 1)[0].upper()
    return "UNKNOWN"


def _currency_for_market(market: str) -> str:
    return {"US": "USD", "HK": "HKD", "KR": "KRW", "SH": "CNY", "SZ": "CNY"}.get(market, "UNKNOWN")


def _missing_pack(observation_type: str) -> dict[str, Any]:
    return {
        "status": "missing",
        "observation_type": observation_type,
        "observed_at": None,
        "stale_after": None,
        "confidence": 0.0,
        "value": {},
    }


def _freshness_status(stale_after: Any) -> str:
    if not stale_after:
        return "unknown"
    try:
        stale_at = datetime.fromisoformat(str(stale_after).replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    if stale_at.tzinfo is None:
        stale_at = stale_at.replace(tzinfo=timezone.utc)
    return "stale" if stale_at < datetime.now(timezone.utc) else "ok"


def _evidence(evidence_type: str, evidence_id: Any, component: Any, summary: Any) -> dict[str, Any]:
    text = " ".join(str(summary or "").split())
    return {
        "evidence_type": evidence_type,
        "evidence_id": evidence_id,
        "component": str(component or ""),
        "summary": text[:220],
    }


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
