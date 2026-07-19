"""Pure, deterministic stock valuation research artifacts.

This module deliberately has no repository, provider, or command-router dependency.
It turns supplied context and normalized facts into a bounded research aid; it does
not create investment recommendations or user insights.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


CORE_FRAMES: tuple[dict[str, Any], ...] = (
    {"id": "fcf", "name": "Free Cash Flow", "core_question": "What durable free cash flow can the business produce?", "triggers": ("FCF turns positive", "cash conversion improves"), "failure_conditions": ("one-time cash release", "higher reinvestment")},
    {"id": "comparable_multiples", "name": "Comparable Multiples", "core_question": "Which multiple can comparable businesses support?", "triggers": ("quality improves", "peer multiple expands"), "failure_conditions": ("wrong peer group", "unsupported multiple expansion")},
    {"id": "sotp_asset_value", "name": "SOTP / Asset Value", "core_question": "Are parts or assets worth more than the consolidated value?", "triggers": ("asset sale", "better segment disclosure"), "failure_conditions": ("assets cannot be monetized", "holding discount persists")},
    {"id": "cyclical", "name": "Cyclical", "core_question": "Are earnings at a cycle peak, trough, or mid-cycle?", "triggers": ("pricing inflects", "inventory clears"), "failure_conditions": ("peak earnings treated as durable", "supply response")},
    {"id": "growth_scenario", "name": "Growth / Scenario", "core_question": "What is the value under explicit growth and milestone scenarios?", "triggers": ("TAM rises", "milestone validates demand"), "failure_conditions": ("TAM overstated", "milestone delayed")},
)

SPECIALIST_FRAMES: tuple[dict[str, Any], ...] = (
    {"id": "dividend", "name": "Dividend", "core_question": "Can distributable cash flows sustain dividends?", "specialist_only": True},
    {"id": "residual_income", "name": "Residual Income", "core_question": "Does return on equity exceed the cost of equity?", "specialist_only": True},
    {"id": "event_driven", "name": "Event-Driven", "core_question": "Does a defined corporate event change value realization?", "specialist_only": True},
)

_SAFE_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_FACT_PATTERNS: dict[str, tuple[str, ...]] = {
    "revenue": (r"\brevenue\b", r"收入", r"营收"),
    "gross_profit": (r"\bgross\s+profit\b", r"毛利"),
    "operating_income": (r"\boperating\s+income\b", r"营业利润", r"经营利润"),
    "net_income": (r"\bnet\s+income\b", r"净利润"),
    "operating_cash_flow": (r"\boperating\s+cash\s+flow\b", r"\bocf\b", r"经营现金流"),
    "capex": (r"\bcapex\b", r"\bcapital\s+expenditure\b", r"资本开支"),
    "free_cash_flow": (r"\bfree\s+cash\s+flow\b", r"\bfcf\b", r"自由现金流"),
    "cash": (r"\bcash\b", r"现金"), "debt": (r"\bdebt\b", r"债务"),
    "net_debt": (r"\bnet\s+debt\b", r"净债务"),
    "shares_outstanding": (r"\bshares\s+outstanding\b", r"总股本"),
    "price": (r"\bprice\b", r"股价"), "market_cap": (r"\bmarket\s+cap\b", r"市值"),
    "enterprise_value": (r"\benterprise\s+value\b", r"\bev\b", r"企业价值"),
    "ebitda": (r"\bebitda\b",),
}
_MONEY_METRICS = frozenset({"revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capex", "free_cash_flow", "cash", "debt", "net_debt", "market_cap", "enterprise_value", "ebitda", "book_value"})
_EVIDENCE_PROVIDER_STATUS_NAMES = ("market_snapshot", "financial_facts")
_EVIDENCE_STATUS_VALUES = frozenset({
    "available", "attempted", "complete_missing", "failed", "failure", "missing",
    "not_attempted", "partial", "success", "unavailable", "unknown",
})
_EVIDENCE_ATTEMPT_FAMILIES = frozenset({
    "company_ir", "market_snapshot", "official_financial", "regulator_filing",
    "unknown", "vendor_financial",
})


def valuation_method_library() -> list[dict[str, Any]]:
    """Return five core and three specialist-only method definitions."""
    methods: list[dict[str, Any]] = []
    for frame in (*CORE_FRAMES, *SPECIALIST_FRAMES):
        methods.append({
            "id": frame["id"], "name": frame["name"], "core_question": frame["core_question"],
            "triggers": list(frame.get("triggers", ())),
            "failure_conditions": list(frame.get("failure_conditions", ())),
            "specialist_only": bool(frame.get("specialist_only")),
        })
    return methods


def render_valuation_methods() -> str:
    lines = ["Valuation method library (P0 ranks only the five core frames):"]
    for index, frame in enumerate(valuation_method_library(), start=1):
        suffix = " [specialist-only]" if frame["specialist_only"] else ""
        lines.append(f"{index}. {frame['name']}{suffix} — {frame['core_question']}")
    lines.append("Specialist frames are metadata only unless an explicit specialist workflow triggers them.")
    return "\n".join(lines)


def build_valuation_artifact(
    context: dict[str, object], *, symbol: str, market: str,
    output_dir: Path, command: str,
    provider_snapshot: dict[str, object] | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, object], Path]:
    """Build and save a stock-scoped valuation packet from supplied inputs only."""
    normalized_symbol, normalized_market = _validate_target(symbol, market)
    if not isinstance(context, dict):
        raise TypeError("context must be a mapping")
    snapshot = provider_snapshot if isinstance(provider_snapshot, dict) else {}
    facts = _extract_facts(context, snapshot)
    currency = _infer_currency(facts, normalized_market)
    _decorate_facts(facts, currency)
    values = {str(item["metric"]): float(item["value"]) for item in facts if _number(item.get("value")) is not None}
    fact_refs = {str(item["metric"]): str(item["id"]) for item in facts}
    calculations = _calculate_metrics(values, fact_refs, currency)
    gaps = _data_gaps(values, calculations, context, snapshot)
    internal_scores = _score_core_frames(context, values, calculations, gaps)
    bridge = _market_implied_bridge(values, calculations, internal_scores, gaps, currency)
    selected_frames = _select_frames(bridge["frame_fit_ranking"])
    coverage = _source_coverage(context, facts, snapshot)
    reasons = _degraded_reasons(gaps, coverage, context)
    stock = context.get("stock") if isinstance(context.get("stock"), dict) else {}
    target = dict(snapshot.get("target_resolution") or {})
    target.update({"input_target": f"{normalized_market}.{normalized_symbol}", "normalized_symbol": normalized_symbol, "normalized_market": normalized_market, "normalized_target": target.get("normalized_target") or f"{normalized_market}.{normalized_symbol}"})
    packet: dict[str, object] = {
        "schema": "stock_valuation_packet.v1",
        "input": {"symbol": normalized_symbol, "market": normalized_market, "command": str(command), "created_at": _timestamp(now)},
        "stock": {"id": stock.get("id"), "symbol": stock.get("symbol") or normalized_symbol, "market": stock.get("market") or normalized_market, "name": stock.get("name"), "core_business": stock.get("core_business"), "stock_character": stock.get("stock_character")},
        "target_resolution": target,
        "facts": facts,
        "assumptions": {"user_confirmed_valuation_case": _has_confirmed_case(context), "items": ["This artifact is deterministic research scaffolding, not a target price.", "Peer sets and analyst estimates require separately sourced evidence."]},
        "deterministic_calculations": calculations,
        "internal_frame_scores": internal_scores,
        "selected_frames": selected_frames,
        "market_implied_bridge": bridge,
        "interpretation": _interpretation(selected_frames, calculations, gaps),
        "watch_items": _watch_items(selected_frames),
        "source_coverage": coverage,
        "degraded_state": {"degraded": bool(reasons), "reasons": reasons, "data_gaps": gaps},
        "safety": {"direct_investment_advice": False, "writes_formal_user_insight": False, "research_aid_only": True},
    }
    return packet, _write_artifact(packet, output_dir, normalized_symbol, normalized_market, now)


def load_latest_valuation_artifact(*, symbol: str, market: str, output_dir: Path) -> dict[str, object] | None:
    normalized_symbol, normalized_market = _validate_target(symbol, market)
    path = Path(output_dir) / "valuation" / f"{normalized_symbol}_{normalized_market}_valuation_latest.json"
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return result if isinstance(result, dict) and result.get("schema") == "stock_valuation_packet.v1" else None


def build_valuation_artifact_evidence(packet: dict[str, object]) -> dict[str, object]:
    """Project a packet through an explicit safe allow-list; never reads paths."""
    if not isinstance(packet, dict):
        raise TypeError("packet must be a mapping")
    input_data = packet.get("input") if isinstance(packet.get("input"), dict) else {}
    stock = packet.get("stock") if isinstance(packet.get("stock"), dict) else {}
    bridge = packet.get("market_implied_bridge") if isinstance(packet.get("market_implied_bridge"), dict) else {}
    coverage = packet.get("source_coverage") if isinstance(packet.get("source_coverage"), dict) else {}
    safety = packet.get("safety") if isinstance(packet.get("safety"), dict) else {}
    return {
        "schema": "stock_valuation_evidence.v1",
        "target": _allow_dict(packet.get("target_resolution"), ("input_target", "normalized_target", "normalized_symbol", "normalized_market", "company_name", "provider_market_ticker", "currency", "mapping_confidence", "mapping_source")),
        "stock": _allow_dict(stock, ("symbol", "market", "name")),
        "facts": [_allow_dict(item, ("id", "metric", "value", "display_value", "display_kind", "currency", "source_id", "source_type", "period_end", "timestamp", "provider")) for item in packet.get("facts", []) if isinstance(item, dict)],
        "deterministic_calculations": [_allow_dict(item, ("metric", "value", "raw_value", "display_value", "display_kind", "currency", "meaningful", "meaningfulness_reason", "formula", "inputs", "input_refs")) for item in packet.get("deterministic_calculations", []) if isinstance(item, dict)],
        "market_implied_bridge": {"bridge_lines": [_allow_dict(item, ("type", "display")) for item in bridge.get("bridge_lines", []) if isinstance(item, dict)], "frame_fit_ranking": [_allow_dict(item, ("id", "name", "score", "fit_to_current_market_value", "why_it_fits_or_not", "main_data_gaps", "confidence")) for item in bridge.get("frame_fit_ranking", []) if isinstance(item, dict)]},
        "source_coverage": {
            **_allow_dict(coverage, ("fact_count", "fact_source_id_count", "source_count", "official_source_count", "market_snapshot_status", "financial_fact_status")),
            "provider_statuses": _evidence_provider_statuses(coverage.get("provider_statuses")),
            "source_attempts": _evidence_source_attempts(coverage.get("source_attempts")),
        },
        "degraded_state": _allow_dict(packet.get("degraded_state"), ("degraded", "reasons", "data_gaps")),
        "safety": {"direct_investment_advice": bool(safety.get("direct_investment_advice")), "writes_formal_user_insight": bool(safety.get("writes_formal_user_insight")), "research_aid_only": bool(safety.get("research_aid_only")), "omits_local_path": True, "provider_error_detail_omitted": True},
        "input": _allow_dict(input_data, ("symbol", "market", "created_at")),
    }


def render_valuation_card(packet: dict[str, object]) -> str:
    if not isinstance(packet, dict):
        raise TypeError("packet must be a mapping")
    stock = packet.get("stock") if isinstance(packet.get("stock"), dict) else {}
    degraded = packet.get("degraded_state") if isinstance(packet.get("degraded_state"), dict) else {}
    calculations = {str(item.get("metric")): item for item in packet.get("deterministic_calculations", []) if isinstance(item, dict)}
    lines = [f"Valuation research card: {stock.get('market', '')}.{stock.get('symbol', '')} {stock.get('name', '')}".rstrip(), f"Status: {'degraded' if degraded.get('degraded') else 'ok'}"]
    for reason in degraded.get("reasons", []) if isinstance(degraded.get("reasons"), list) else []:
        lines.append(f"- {reason}")
    lines.append("Valuation snapshot:")
    for label, metric in (("Market cap", "market_cap"), ("Enterprise value", "enterprise_value"), ("FCF margin", "fcf_margin"), ("PE", "pe"), ("P/S", "ps"), ("EV/EBITDA", "ev_ebitda"), ("EV/FCF", "ev_fcf")):
        if metric in calculations:
            lines.append(f"- {label}: {calculations[metric].get('display_value', 'unknown')}")
    lines.append("Relevant frames:")
    for frame in packet.get("selected_frames", []) if isinstance(packet.get("selected_frames"), list) else []:
        if isinstance(frame, dict):
            lines.append(f"- {frame.get('name')} (fit={frame.get('fit_to_current_market_value')})")
    lines.append("Safety: research aid only; no buy/sell recommendation and no formal user insight was written.")
    return "\n".join(lines)


def _validate_target(symbol: str, market: str) -> tuple[str, str]:
    normalized_symbol, normalized_market = str(symbol).strip().upper(), str(market).strip().upper()
    if not _SAFE_TARGET.fullmatch(normalized_symbol) or not _SAFE_TARGET.fullmatch(normalized_market):
        raise ValueError("target must be a market-qualified stock identifier")
    return normalized_symbol, normalized_market


def _extract_facts(context: dict[str, object], snapshot: dict[str, object]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for knowledge in context.get("stock_knowledge", []) if isinstance(context.get("stock_knowledge"), list) else []:
        if not isinstance(knowledge, dict):
            continue
        content = str(knowledge.get("content") or "")
        for metric, patterns in _FACT_PATTERNS.items():
            value = _extract_metric_value(content, patterns)
            if value is not None:
                candidates.append({"metric": metric, "value": value, "source_id": knowledge.get("source_id"), "knowledge_id": knowledge.get("id"), "timestamp": knowledge.get("updated_at") or knowledge.get("created_at"), "input_text": content[:240]})
    for fact in snapshot.get("facts", []) if isinstance(snapshot.get("facts"), list) else []:
        if isinstance(fact, dict) and fact.get("metric") and _number(fact.get("value")) is not None:
            candidates.append({key: fact.get(key) for key in ("metric", "value", "source_id", "source_type", "knowledge_id", "timestamp", "period_end", "provider", "currency")})
    latest: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        latest[str(candidate["metric"])] = candidate
    facts = [latest[metric] for metric in sorted(latest)]
    for index, fact in enumerate(facts, start=1):
        source = str(fact.get("source_id") or fact.get("knowledge_id") or index)
        fact["id"] = f"fact:{fact['metric']}:{source}"
        fact["value"] = float(fact["value"])
    return facts


def _extract_metric_value(content: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(rf"(?:{pattern})\s*(?:=|:|is|was|为|约)?\s*([-+]?\d[\d,]*(?:\.\d+)?%?)", content, re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", "")
            return float(raw[:-1]) / 100 if raw.endswith("%") else float(raw)
    return None


def _decorate_facts(facts: list[dict[str, object]], currency: str | None) -> None:
    for fact in facts:
        metric = str(fact["metric"])
        kind = "currency" if metric in _MONEY_METRICS else "currency_per_share" if metric == "price" else "number"
        fact_currency = str(fact.get("currency") or currency or "").upper() or None
        if kind.startswith("currency") and fact_currency:
            fact["currency"] = fact_currency
        fact["display_kind"] = kind
        fact["display_value"] = _format_value(fact.get("value"), kind, fact_currency)


def _calculate_metrics(values: dict[str, float], refs: dict[str, str], currency: str | None) -> list[dict[str, object]]:
    calculations: list[dict[str, object]] = []
    by_metric: dict[str, dict[str, object]] = {}
    def add(metric: str, value: float, formula: str, inputs: tuple[str, ...], kind: str, negative_reason: str | None = None) -> None:
        input_refs = _flatten_input_refs(inputs, refs, by_metric)
        raw = round(value, 6)
        item: dict[str, object] = {"metric": metric, "value": raw, "formula": formula, "inputs": list(inputs), "input_refs": input_refs, "display_kind": kind, "meaningful": True}
        if currency and kind == "currency":
            item["currency"] = currency
        if negative_reason:
            item.update({"raw_value": raw, "value": None, "meaningful": False, "meaningfulness_reason": negative_reason, "display_value": f"not meaningful ({negative_reason})"})
        else:
            item["display_value"] = _format_value(raw, kind, currency)
        calculations.append(item); by_metric[metric] = item
    fcf = values.get("free_cash_flow")
    if fcf is not None: add("free_cash_flow", fcf, "reported free_cash_flow", ("free_cash_flow",), "currency")
    elif "operating_cash_flow" in values and "capex" in values:
        fcf = values["operating_cash_flow"] - abs(values["capex"]); add("free_cash_flow", fcf, "operating_cash_flow - abs(capex)", ("operating_cash_flow", "capex"), "currency")
    net_debt = values.get("net_debt")
    if net_debt is not None: add("net_debt", net_debt, "reported net_debt", ("net_debt",), "currency")
    elif "debt" in values and "cash" in values:
        net_debt = values["debt"] - values["cash"]; add("net_debt", net_debt, "debt - cash", ("debt", "cash"), "currency")
    market_cap = values.get("market_cap")
    if market_cap is not None: add("market_cap", market_cap, "reported market_cap", ("market_cap",), "currency")
    elif "price" in values and "shares_outstanding" in values:
        market_cap = values["price"] * values["shares_outstanding"]; add("market_cap", market_cap, "price * shares_outstanding", ("price", "shares_outstanding"), "currency")
    ev = values.get("enterprise_value")
    if ev is not None: add("enterprise_value", ev, "reported enterprise_value", ("enterprise_value",), "currency")
    elif market_cap is not None and net_debt is not None:
        ev = market_cap + net_debt; add("enterprise_value", ev, "market_cap + net_debt", ("market_cap", "net_debt"), "currency")
    for metric, numerator, denominator, formula, inputs, kind, negative_reason in (
        ("gross_margin", values.get("gross_profit"), values.get("revenue"), "gross_profit / revenue", ("gross_profit", "revenue"), "percent", None),
        ("operating_margin", values.get("operating_income"), values.get("revenue"), "operating_income / revenue", ("operating_income", "revenue"), "percent", None),
        ("fcf_margin", fcf, values.get("revenue"), "free_cash_flow / revenue", ("free_cash_flow", "revenue"), "percent", None),
        ("fcf_yield", fcf, market_cap, "free_cash_flow / market_cap", ("free_cash_flow", "market_cap"), "percent", "negative FCF"),
        ("pe", market_cap, values.get("net_income"), "market_cap / net_income", ("market_cap", "net_income"), "multiple", "negative earnings"),
        ("ps", market_cap, values.get("revenue"), "market_cap / revenue", ("market_cap", "revenue"), "multiple", None),
        ("ev_ebitda", ev, values.get("ebitda"), "enterprise_value / ebitda", ("enterprise_value", "ebitda"), "multiple", "negative EBITDA"),
        ("ev_fcf", ev, fcf, "enterprise_value / free_cash_flow", ("enterprise_value", "free_cash_flow"), "multiple", "negative FCF"),
    ):
        if numerator is not None and denominator not in (None, 0):
            add(metric, numerator / denominator, formula, inputs, kind, negative_reason if denominator < 0 or (metric == "fcf_yield" and numerator < 0) else None)
    return calculations


def _data_gaps(values: dict[str, float], calculations: list[dict[str, object]], context: dict[str, object], snapshot: dict[str, object]) -> list[str]:
    derived = {str(item["metric"]) for item in calculations}
    gaps = []
    if "price" not in values and "market_cap" not in values: gaps.append("latest market price or market cap is missing")
    if "enterprise_value" not in values and "enterprise_value" not in derived: gaps.append("enterprise value cannot be derived without market cap and net debt")
    for metric, label in (("revenue", "revenue"), ("free_cash_flow", "free cash flow"), ("net_income", "net income")):
        if metric not in values and metric not in derived: gaps.append(f"{label} is missing")
    if not (context.get("sources") or snapshot.get("sources")): gaps.append("source metadata is missing")
    if not _has_confirmed_case(context): gaps.append("no user-confirmed valuation case")
    return gaps


def _score_core_frames(context: dict[str, object], values: dict[str, float], calculations: list[dict[str, object]], gaps: list[str]) -> list[dict[str, object]]:
    text = json.dumps(context, ensure_ascii=False).lower()
    score = {"fcf": .15, "comparable_multiples": .2, "sotp_asset_value": .05, "cyclical": .05, "growth_scenario": .1}
    if {"free_cash_flow", "operating_cash_flow", "capex"} & values.keys(): score["fcf"] += .55
    if {"market_cap", "revenue", "net_income", "ebitda"} & values.keys(): score["comparable_multiples"] += .45
    if any(word in text for word in ("asset", "segment", "holding", "资产", "分部")): score["sotp_asset_value"] += .55
    if any(word in text for word in ("cycle", "cyclical", "semiconductor", "memory", "周期", "半导体")): score["cyclical"] += .65
    if any(word in text for word in ("growth", "tam", "scenario", "ai", "增长", "市场空间")): score["growth_scenario"] += .55
    frames = {item["id"]: item for item in CORE_FRAMES}
    return [{"id": ident, "name": frames[ident]["name"], "score": round(min(value, 1), 3), "reason": "ranked from available facts and local context", "degraded_by": [gap for gap in gaps if ident.split("_")[0] in gap]} for ident, value in sorted(score.items(), key=lambda item: (-item[1], item[0]))]


def _market_implied_bridge(values: dict[str, float], calculations: list[dict[str, object]], scores: list[dict[str, object]], gaps: list[str], currency: str | None) -> dict[str, object]:
    calculated = {str(item["metric"]): item for item in calculations}
    market_cap = values.get("market_cap") or _numeric(calculated.get("market_cap")); ev = values.get("enterprise_value") or _numeric(calculated.get("enterprise_value")); fcf = values.get("free_cash_flow") or _numeric(calculated.get("free_cash_flow")); revenue = values.get("revenue")
    lines: list[dict[str, str]] = []
    if market_cap is not None and revenue not in (None, 0): lines.append({"type": "sales_anchor", "display": f"P/S: {_format_value(market_cap / revenue, 'multiple', currency)} anchors current market value."})
    if ev is not None and revenue not in (None, 0): lines.append({"type": "ev_sales_anchor", "display": f"EV/Sales: {_format_value(ev / revenue, 'multiple', currency)}."})
    if fcf is not None and market_cap not in (None, 0): lines.append({"type": "fcf_yield", "display": "FCF yield is not meaningful with negative FCF." if fcf < 0 else f"FCF yield: {_format_value(fcf / market_cap, 'percent', currency)}."})
    fit = []
    for item in scores:
        confidence = "low" if gaps else "medium"
        fit.append({**item, "fit_to_current_market_value": "fits" if item["score"] >= .6 else "partial_fit" if item["score"] >= .2 else "insufficient_data", "why_it_fits_or_not": "ranked using deterministic fact coverage and context", "main_data_gaps": gaps, "confidence": confidence})
    return {"bridge_lines": lines, "frame_fit_ranking": fit}


def _select_frames(ranking: list[dict[str, object]]) -> list[dict[str, object]]:
    order = {"fits": 0, "partial_fit": 1, "insufficient_data": 2, "does_not_fit": 3}
    ranked = sorted(ranking, key=lambda item: (order.get(str(item.get("fit_to_current_market_value")), 4), -float(item.get("score") or 0)))
    return [item for item in ranked if float(item.get("score") or 0) >= .2][:3] or ranked[:1]


def _source_coverage(context: dict[str, object], facts: list[dict[str, object]], snapshot: dict[str, object]) -> dict[str, object]:
    sources = [item for item in [*(context.get("sources") or []), *(snapshot.get("sources") or [])] if isinstance(item, dict)]
    types = [str(item.get("source_type") or "").lower() for item in sources]
    market = any(item.get("metric") in {"price", "market_cap"} for item in facts)
    financial = any(item.get("metric") in _MONEY_METRICS - {"market_cap", "enterprise_value"} for item in facts)
    return {"fact_count": len(facts), "fact_source_id_count": len({item.get("source_id") for item in facts if item.get("source_id")}), "source_count": len(sources), "official_source_count": sum(any(token in source_type for token in ("official", "sec", "filing", "hkex", "dart", "fss")) for source_type in types), "market_snapshot_status": str(snapshot.get("market_snapshot_status") or ("present" if market else "missing")), "financial_fact_status": str(snapshot.get("financial_fact_status") or ("present" if financial else "missing")), "provider_statuses": {"market_snapshot": {"status": "available" if market else "complete_missing", "explanation": "market fields are available" if market else "market fields are unavailable"}, "financial_facts": {"status": "available" if financial else "complete_missing", "explanation": "financial facts are available" if financial else "financial facts are unavailable"}}, "source_attempts": _safe_attempts(snapshot.get("source_attempts"))}


def _degraded_reasons(gaps: list[str], coverage: dict[str, object], context: dict[str, object]) -> list[str]:
    reasons = list(gaps)
    if not coverage.get("official_source_count"): reasons.append("official financial source coverage is missing")
    stock = context.get("stock") if isinstance(context.get("stock"), dict) else {}
    if not stock.get("name"): reasons.append("stock profile appears minimal and needs research import")
    return sorted(set(reasons))


def _interpretation(selected: list[dict[str, object]], calculations: list[dict[str, object]], gaps: list[str]) -> list[str]:
    items = [f"{item['name']} is a selected research frame." for item in selected]
    if gaps: items.append("Data gaps mean this is research scaffolding rather than a target price.")
    return items


def _watch_items(selected: list[dict[str, object]]) -> list[str]:
    lookup = {item["id"]: item for item in CORE_FRAMES}
    return [f"{lookup[item['id']]['name']} triggers: {', '.join(lookup[item['id']]['triggers'])}." for item in selected if item.get("id") in lookup]


def _write_artifact(packet: dict[str, object], output_dir: Path, symbol: str, market: str, now: datetime | None) -> Path:
    directory = Path(output_dir) / "valuation"; directory.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    timestamped = directory / f"{symbol}_{market}_valuation_{stamp}.json"; latest = directory / f"{symbol}_{market}_valuation_latest.json"
    serialized = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    timestamped.write_text(serialized + "\n", encoding="utf-8"); latest.write_text(serialized + "\n", encoding="utf-8")
    return timestamped


def _timestamp(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _infer_currency(facts: list[dict[str, object]], market: str) -> str | None:
    for fact in facts:
        if fact.get("currency"): return str(fact["currency"]).upper()
    return {"US": "USD", "HK": "HKD", "KR": "KRW"}.get(market)


def _format_value(value: object, kind: str, currency: str | None) -> str:
    number = _number(value)
    if number is None: return "unknown"
    if kind == "percent": return f"{number * 100:.1f}%"
    if kind == "multiple": return f"{number:.1f}x"
    prefix = {"USD": "$", "HKD": "HK$"}.get(str(currency or "").upper(), f"{str(currency).upper()} " if currency else "")
    if kind == "currency_per_share": return f"{prefix}{number:.2f}/share"
    if kind == "currency":
        scale, suffix = (1_000_000_000, "B") if abs(number) >= 1_000_000_000 else (1_000_000, "M") if abs(number) >= 1_000_000 else (1_000, "K") if abs(number) >= 1_000 else (1, "")
        return f"{prefix}{number / scale:.1f}{suffix}"
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _has_confirmed_case(context: dict[str, object]) -> bool:
    for group in ("stock_insights", "stock_knowledge"):
        for item in context.get(group, []) if isinstance(context.get(group), list) else []:
            if isinstance(item, dict) and item.get("confirmed_by_user"): return True
    return False


def _allow_dict(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    return {key: value[key] for key in keys if isinstance(value, dict) and value.get(key) is not None}


def _evidence_provider_statuses(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    return {
        name: {"status": _evidence_status(item.get("status"))}
        for name in _EVIDENCE_PROVIDER_STATUS_NAMES
        if isinstance((item := value.get(name)), dict)
    }


def _evidence_source_attempts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        return []
    attempts: list[dict[str, str]] = []
    for _, item in sorted(value.items(), key=lambda entry: str(entry[0])):
        if not isinstance(item, dict):
            continue
        family = str(item.get("family") or "unknown").lower()
        attempts.append({
            "family": family if family in _EVIDENCE_ATTEMPT_FAMILIES else "unknown",
            "status": _evidence_status(item.get("status")),
        })
    return attempts


def _evidence_status(value: object) -> str:
    status = str(value or "unknown").lower()
    return status if status in _EVIDENCE_STATUS_VALUES else "unknown"


def _safe_attempts(value: object) -> dict[str, object]:
    if not isinstance(value, dict): return {}
    return {str(key): _allow_dict(item, ("family", "status")) for key, item in value.items() if isinstance(item, dict)}


def _flatten_input_refs(
    inputs: tuple[str, ...], refs: dict[str, str], by_metric: dict[str, dict[str, object]],
) -> tuple[str, ...]:
    flattened: list[str] = []
    for input_metric in inputs:
        fact_ref = refs.get(input_metric)
        if fact_ref:
            flattened.append(fact_ref)
            continue
        derived_refs = by_metric.get(input_metric, {}).get("input_refs")
        if isinstance(derived_refs, (list, tuple)):
            flattened.extend(str(ref) for ref in derived_refs)
    return tuple(dict.fromkeys(flattened))


def _numeric(item: dict[str, object] | None) -> float | None:
    return _number(item.get("value") if item else None) or _number(item.get("raw_value") if item else None)


def _number(value: object) -> float | None:
    try: return float(value) if value not in (None, "") else None
    except (TypeError, ValueError): return None
