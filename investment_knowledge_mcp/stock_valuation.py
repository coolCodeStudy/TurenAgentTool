from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


CORE_FRAMES: tuple[dict[str, Any], ...] = (
    {
        "id": "fcf",
        "name": "Free Cash Flow",
        "core_question": "How much durable free cash flow can the company generate, and what is that cash flow worth?",
        "triggers": ("FCF turns positive", "FCF margin improves", "Capex peak passes", "Buyback capacity is re-priced"),
        "failure_conditions": (
            "FCF is inflated by one-time working-capital release",
            "Growth requires much higher reinvestment than expected",
            "Cash conversion weakens",
        ),
    },
    {
        "id": "comparable_multiples",
        "name": "Comparable Multiples",
        "core_question": "What valuation multiple does the market assign to comparable companies?",
        "triggers": (
            "The company moves into a higher-quality peer group",
            "The market switches from current-year to forward-year multiples",
            "Sector leader multiples expand",
        ),
        "failure_conditions": (
            "Peer group is wrong",
            "Multiple expansion is not supported by growth, margin, or durability",
            "Sector multiple compresses",
        ),
    },
    {
        "id": "sotp_asset_value",
        "name": "SOTP / Asset Value",
        "core_question": "Are the company's parts, assets, or hidden holdings worth more than the consolidated market value?",
        "triggers": ("Spin-off or separate listing", "Asset sale", "Better segment disclosure", "NAV discount narrows"),
        "failure_conditions": (
            "Assets cannot be monetized",
            "Segment disclosure stays poor",
            "Holding-company discount remains justified",
        ),
    },
    {
        "id": "cyclical",
        "name": "Cyclical",
        "core_question": "Are current earnings near a cycle top or bottom?",
        "triggers": ("Cycle inflection is confirmed", "Pricing rises or stops falling", "Inventory clears"),
        "failure_conditions": (
            "Peak earnings are mistaken for durable earnings",
            "Supply response arrives faster than expected",
            "Inventory cycle reverses",
        ),
    },
    {
        "id": "growth_scenario",
        "name": "Growth / Scenario",
        "core_question": "If the company captures a large opportunity or reaches a milestone, what could the future business be worth?",
        "triggers": (
            "TAM is revised higher",
            "Penetration speed exceeds expectations",
            "Unit economics improve",
            "Major customer order validates the scenario",
        ),
        "failure_conditions": (
            "TAM narrative is exaggerated",
            "Unit economics do not improve",
            "Milestone is delayed or fails",
            "Capital needs dilute upside",
        ),
    },
)


FACT_PATTERNS: dict[str, tuple[str, ...]] = {
    "revenue": (r"\brevenue\b", r"收入", r"营收"),
    "gross_profit": (r"\bgross\s+profit\b", r"毛利"),
    "operating_income": (r"\boperating\s+income\b", r"经营利润", r"营业利润"),
    "net_income": (r"\bnet\s+income\b", r"净利润"),
    "operating_cash_flow": (r"\boperating\s+cash\s+flow\b", r"\bocf\b", r"经营现金流"),
    "capex": (r"\bcapex\b", r"\bcapital\s+expenditure\b", r"资本开支"),
    "free_cash_flow": (r"\bfree\s+cash\s+flow\b", r"\bfcf\b", r"自由现金流"),
    "cash": (r"\bcash\b", r"现金"),
    "debt": (r"\bdebt\b", r"债务", r"有息负债"),
    "net_debt": (r"\bnet\s+debt\b", r"净债务"),
    "shares_outstanding": (r"\bshares\s+outstanding\b", r"总股本", r"股本"),
    "price": (r"\bprice\b", r"股价", r"价格"),
    "market_cap": (r"\bmarket\s+cap\b", r"市值"),
    "enterprise_value": (r"\benterprise\s+value\b", r"\bev\b", r"企业价值"),
    "ebitda": (r"\bebitda\b",),
    "book_value": (r"\bbook\s+value\b", r"账面价值", r"净资产"),
    "revenue_growth": (r"\brevenue\s+growth\b", r"收入增速", r"营收增速"),
    "gross_margin": (r"\bgross\s+margin\b", r"毛利率"),
    "operating_margin": (r"\boperating\s+margin\b", r"经营利润率", r"营业利润率"),
    "tam": (r"\btam\b", r"总地址市场", r"市场空间"),
}


def valuation_method_library() -> list[dict[str, Any]]:
    return [
        {
            "id": frame["id"],
            "name": frame["name"],
            "core_question": frame["core_question"],
            "triggers": list(frame["triggers"]),
            "failure_conditions": list(frame["failure_conditions"]),
        }
        for frame in CORE_FRAMES
    ]


def render_valuation_methods() -> str:
    lines = ["估值方法库（P0 internal core frames; 默认只展示最相关的 1-3 个）："]
    for index, frame in enumerate(valuation_method_library(), start=1):
        lines.append(f"{index}. {frame['name']} - {frame['core_question']}")
    lines.append("")
    lines.append("P0 specialist frames such as dividend, residual income, and event-driven valuation stay hidden unless clearly triggered.")
    return "\n".join(lines)


def build_valuation_artifact(
    context: dict[str, Any],
    *,
    symbol: str,
    market: str,
    output_dir: Path,
    command: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any], Path]:
    created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0).isoformat()
    stock = context.get("stock") or {}
    facts = _extract_facts(context)
    fact_values = {fact["metric"]: fact["value"] for fact in facts if fact.get("value") is not None}
    calculations = _calculate_metrics(fact_values)
    gaps = _data_gaps(fact_values, calculations, context)
    scores = _score_frames(context=context, fact_values=fact_values, calculations=calculations, gaps=gaps)
    selected_frames = _select_frames(scores)
    coverage = _source_coverage(context=context, facts=facts)
    degraded_reasons = _degraded_reasons(gaps=gaps, coverage=coverage, context=context)
    packet = {
        "feature": "stock_valuation_research",
        "version": 1,
        "created_at": created_at,
        "input": {"symbol": symbol.strip().upper(), "market": market.strip().upper(), "command": command},
        "stock": {
            "id": stock.get("id"),
            "symbol": stock.get("symbol") or symbol.strip().upper(),
            "market": stock.get("market") or market.strip().upper(),
            "name": stock.get("name"),
            "core_business": stock.get("core_business"),
            "stock_character": stock.get("stock_character"),
        },
        "facts": facts,
        "assumptions": _assumptions(context),
        "deterministic_calculations": calculations,
        "internal_frame_scores": scores,
        "selected_frames": selected_frames,
        "interpretation": _interpretation(selected_frames, calculations, gaps),
        "watch_items": _watch_items(selected_frames),
        "source_coverage": coverage,
        "degraded_state": {
            "degraded": bool(degraded_reasons),
            "reasons": degraded_reasons,
            "data_gaps": gaps,
        },
        "safety": {
            "direct_investment_advice": False,
            "writes_formal_user_insight": False,
            "requires_user_confirmation_for_valuation_case": True,
        },
    }
    artifact_path = _write_artifact(packet, output_dir=output_dir)
    packet["artifact_path"] = str(artifact_path)
    return packet, artifact_path


def load_latest_valuation_artifact(*, symbol: str, market: str, output_dir: Path) -> tuple[dict[str, Any], Path] | None:
    artifact_dir = output_dir / "valuation"
    pattern = f"{symbol.strip().upper()}_{market.strip().upper()}_valuation_*.json"
    matches = sorted(artifact_dir.glob(pattern), reverse=True)
    if not matches:
        return None
    path = matches[0]
    return json.loads(path.read_text(encoding="utf-8")), path


def render_valuation_card(packet: dict[str, Any], *, include_artifact_path: bool = True) -> str:
    stock = packet.get("stock") or {}
    title = f"估值研究卡：{stock.get('market')}.{stock.get('symbol')}"
    if stock.get("name"):
        title += f" {stock['name']}"
    lines = [title, ""]
    degraded = packet.get("degraded_state") or {}
    lines.append(f"状态：{'degraded' if degraded.get('degraded') else 'ok'}")
    if degraded.get("reasons"):
        lines.extend(f"- {reason}" for reason in degraded["reasons"])
    lines.append("")

    lines.append("Relevant frames:")
    for frame in packet.get("selected_frames") or []:
        lines.append(f"- {frame['name']} (score {frame['score']:.2f}): {frame['reason']}")
    lines.append("")

    lines.append("Facts:")
    facts = packet.get("facts") or []
    if facts:
        for fact in facts[:8]:
            source = f" source_id={fact['source_id']}" if fact.get("source_id") is not None else " source_id=missing"
            lines.append(f"- {fact['metric']}: {fact['value']}{source}")
    else:
        lines.append("- No reusable financial or market facts were found in the local stock context.")
    lines.append("")

    lines.append("Assumptions:")
    assumptions = packet.get("assumptions") or {}
    for item in assumptions.get("items") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("Deterministic calculations:")
    calculations = packet.get("deterministic_calculations") or []
    if calculations:
        for calculation in calculations:
            lines.append(f"- {calculation['metric']}: {calculation['value']} ({calculation['formula']})")
    else:
        lines.append("- No deterministic valuation ratios could be calculated from available inputs.")
    lines.append("")

    lines.append("Interpretation:")
    for item in packet.get("interpretation") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("Watch items:")
    for item in packet.get("watch_items") or []:
        lines.append(f"- {item}")
    lines.append("")

    coverage = packet.get("source_coverage") or {}
    lines.append(
        "Source coverage: "
        f"facts={coverage.get('fact_count', 0)}, "
        f"sources={coverage.get('source_count', 0)}, "
        f"official_or_regulator_sources={coverage.get('official_source_count', 0)}, "
        f"market_snapshot={coverage.get('market_snapshot_status', 'missing')}, "
        f"user_confirmed_case={coverage.get('user_confirmed_valuation_case', False)}"
    )
    lines.append("Safety: frame research only; no buy/sell recommendation and no formal user insight was written.")
    if include_artifact_path and packet.get("artifact_path"):
        lines.append(f"Artifact: {packet['artifact_path']}")
    return "\n".join(lines)


def _extract_facts(context: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for item in context.get("stock_knowledge") or []:
        content = str(item.get("content") or "")
        for metric, patterns in FACT_PATTERNS.items():
            value = _extract_metric_value(content, patterns)
            if value is None:
                continue
            facts.append(
                {
                    "metric": metric,
                    "value": value,
                    "source_id": item.get("source_id"),
                    "knowledge_id": item.get("id"),
                    "confidence": item.get("confidence"),
                    "confirmed_by_user": bool(item.get("confirmed_by_user")),
                    "timestamp": item.get("updated_at") or item.get("created_at"),
                    "input_text": content[:240],
                }
            )
    return _dedupe_facts(facts)


def _extract_metric_value(content: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(
            rf"(?:{pattern})\s*(?:=|:|is|was|为|约|大约|达到)?\s*([-+]?\d[\d,]*(?:\.\d+)?%?)",
            content,
            flags=re.IGNORECASE,
        )
        if match:
            raw = match.group(1).replace(",", "")
            if raw.endswith("%"):
                return round(float(raw[:-1]) / 100, 6)
            return float(raw)
    return None


def _dedupe_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for fact in facts:
        latest[fact["metric"]] = fact
    return [latest[key] for key in sorted(latest)]


def _calculate_metrics(values: dict[str, float]) -> list[dict[str, Any]]:
    calculations: list[dict[str, Any]] = []

    fcf = values.get("free_cash_flow")
    if fcf is None and values.get("operating_cash_flow") is not None and values.get("capex") is not None:
        fcf = values["operating_cash_flow"] - abs(values["capex"])
        calculations.append(_calc("free_cash_flow", fcf, "operating_cash_flow - abs(capex)", ["operating_cash_flow", "capex"]))

    net_debt = values.get("net_debt")
    if net_debt is None and values.get("debt") is not None and values.get("cash") is not None:
        net_debt = values["debt"] - values["cash"]
        calculations.append(_calc("net_debt", net_debt, "debt - cash", ["debt", "cash"]))

    market_cap = values.get("market_cap")
    if market_cap is None and values.get("price") is not None and values.get("shares_outstanding") is not None:
        market_cap = values["price"] * values["shares_outstanding"]
        calculations.append(_calc("market_cap", market_cap, "price * shares_outstanding", ["price", "shares_outstanding"]))

    ev = values.get("enterprise_value")
    if ev is None and market_cap is not None and net_debt is not None:
        ev = market_cap + net_debt
        calculations.append(_calc("enterprise_value", ev, "market_cap + net_debt", ["market_cap", "net_debt"]))

    ratio_specs = (
        ("fcf_margin", fcf, values.get("revenue"), "free_cash_flow / revenue", ["free_cash_flow", "revenue"]),
        ("fcf_yield", fcf, market_cap, "free_cash_flow / market_cap", ["free_cash_flow", "market_cap"]),
        ("pe", market_cap, values.get("net_income"), "market_cap / net_income", ["market_cap", "net_income"]),
        ("ps", market_cap, values.get("revenue"), "market_cap / revenue", ["market_cap", "revenue"]),
        ("ev_ebitda", ev, values.get("ebitda"), "enterprise_value / ebitda", ["enterprise_value", "ebitda"]),
        ("ev_fcf", ev, fcf, "enterprise_value / free_cash_flow", ["enterprise_value", "free_cash_flow"]),
    )
    for metric, numerator, denominator, formula, inputs in ratio_specs:
        if numerator is not None and denominator not in (None, 0):
            calculations.append(_calc(metric, numerator / denominator, formula, inputs))

    return calculations


def _calc(metric: str, value: float, formula: str, inputs: list[str]) -> dict[str, Any]:
    return {"metric": metric, "value": round(value, 6), "formula": formula, "inputs": inputs}


def _data_gaps(values: dict[str, float], calculations: list[dict[str, Any]], context: dict[str, Any]) -> list[str]:
    calc_metrics = {item["metric"] for item in calculations}
    gaps: list[str] = []
    if "price" not in values and "market_cap" not in values:
        gaps.append("latest market price or market cap is missing")
    if "enterprise_value" not in values and "enterprise_value" not in calc_metrics:
        gaps.append("enterprise value cannot be derived without market cap and net debt")
    if "revenue" not in values:
        gaps.append("revenue is missing")
    if "free_cash_flow" not in values and "free_cash_flow" not in calc_metrics:
        gaps.append("free cash flow is missing")
    if "net_income" not in values:
        gaps.append("net income is missing")
    if not (context.get("sources") or []):
        gaps.append("source metadata is missing")
    if not _has_user_confirmed_valuation_case(context):
        gaps.append("no user-confirmed valuation case")
    return gaps


def _score_frames(
    *,
    context: dict[str, Any],
    fact_values: dict[str, float],
    calculations: list[dict[str, Any]],
    gaps: list[str],
) -> list[dict[str, Any]]:
    text = _context_text(context)
    calc_metrics = {item["metric"] for item in calculations}
    scores: dict[str, float] = {
        "fcf": 0.15,
        "comparable_multiples": 0.2,
        "sotp_asset_value": 0.05,
        "cyclical": 0.05,
        "growth_scenario": 0.1,
    }
    reasons: dict[str, list[str]] = {frame["id"]: [] for frame in CORE_FRAMES}

    if {"free_cash_flow", "operating_cash_flow", "capex"} & fact_values.keys() or {"free_cash_flow", "fcf_yield", "ev_fcf"} & calc_metrics:
        scores["fcf"] += 0.45
        reasons["fcf"].append("cash-flow inputs or FCF calculations are available")
    if any(word in text for word in ("cash flow", "fcf", "buyback", "capex", "现金流", "回购", "资本开支")):
        scores["fcf"] += 0.2
        reasons["fcf"].append("stock context discusses cash generation or reinvestment")

    if {"market_cap", "net_income", "revenue", "ebitda"} & fact_values.keys() or {"pe", "ps", "ev_ebitda"} & calc_metrics:
        scores["comparable_multiples"] += 0.45
        reasons["comparable_multiples"].append("market or earnings/revenue inputs support multiples")
    if any(word in text for word in ("peer", "multiple", "valuation", "估值", "倍数", "同业")):
        scores["comparable_multiples"] += 0.15
        reasons["comparable_multiples"].append("context references peer or multiple comparison")

    if any(word in text for word in ("segment", "asset", "holding", "nav", "spin-off", "spinoff", "分部", "资产", "控股", "拆分")):
        scores["sotp_asset_value"] += 0.55
        reasons["sotp_asset_value"].append("context references segments, assets, holdings, or unlock events")

    if any(word in text for word in ("cycle", "cyclical", "memory", "semiconductor", "shipping", "energy", "inventory", "capacity", "周期", "半导体", "存储", "库存", "产能")):
        scores["cyclical"] += 0.65
        reasons["cyclical"].append("context suggests cycle-sensitive earnings or supply-demand framing")

    if any(word in text for word in ("growth", "tam", "scenario", "ai", "saas", "biotech", "milestone", "增长", "市场空间", "场景", "里程碑")):
        scores["growth_scenario"] += 0.55
        reasons["growth_scenario"].append("context suggests growth, TAM, scenario, or milestone framing")
    if "tam" in fact_values or "revenue_growth" in fact_values:
        scores["growth_scenario"] += 0.2
        reasons["growth_scenario"].append("growth or TAM input is available")

    if "peer data is missing" not in gaps:
        reasons["comparable_multiples"].append("peer data still needs confirmation before precision")

    by_id = {frame["id"]: frame for frame in CORE_FRAMES}
    return [
        {
            "id": frame_id,
            "name": by_id[frame_id]["name"],
            "score": round(min(score, 1.0), 3),
            "reason": "; ".join(reasons[frame_id]) or "baseline frame kept for ranking",
            "degraded_by": [gap for gap in gaps if _gap_affects_frame(gap, frame_id)],
        }
        for frame_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


def _select_frames(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [score for score in scores if score["score"] >= 0.2][:3]
    return selected or scores[:1]


def _gap_affects_frame(gap: str, frame_id: str) -> bool:
    if frame_id == "fcf" and "free cash flow" in gap:
        return True
    if frame_id == "comparable_multiples" and any(token in gap for token in ("price", "market cap", "net income", "revenue")):
        return True
    if frame_id == "growth_scenario" and "revenue" in gap:
        return True
    return False


def _source_coverage(context: dict[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any]:
    sources = context.get("sources") or []
    source_types = [str(source.get("source_type") or "").lower() for source in sources]
    official_count = sum(
        1
        for source_type in source_types
        if any(token in source_type for token in ("official", "filing", "sec", "hkex", "exchange", "annual_report"))
    )
    return {
        "fact_count": len(facts),
        "fact_source_id_count": len({fact.get("source_id") for fact in facts if fact.get("source_id") is not None}),
        "source_count": len(sources),
        "official_source_count": official_count,
        "market_snapshot_status": "present" if any(fact["metric"] in {"price", "market_cap"} for fact in facts) else "missing",
        "peer_data_status": "missing",
        "financial_fact_status": "present" if facts else "missing",
        "user_confirmed_valuation_case": _has_user_confirmed_valuation_case(context),
    }


def _degraded_reasons(*, gaps: list[str], coverage: dict[str, Any], context: dict[str, Any]) -> list[str]:
    reasons = list(gaps)
    if coverage.get("official_source_count", 0) == 0:
        reasons.append("official financial source coverage is missing")
    if _stock_context_needs_research(context):
        reasons.append("stock profile appears minimal and needs research import")
    return sorted(dict.fromkeys(reasons))


def _assumptions(context: dict[str, Any]) -> dict[str, Any]:
    confirmed = _has_user_confirmed_valuation_case(context)
    items = []
    if confirmed:
        items.append("A user-confirmed valuation case exists in local stock insights or knowledge.")
    else:
        items.append("No user-confirmed valuation case exists; frame ranking is a system candidate only.")
    items.append("P0 uses existing local stock context and deterministic calculations; it does not fetch fresh provider data.")
    items.append("Peer sets, analyst estimates, and target-price precision are intentionally omitted unless sourced.")
    return {"user_confirmed_valuation_case": confirmed, "items": items}


def _interpretation(selected_frames: list[dict[str, Any]], calculations: list[dict[str, Any]], gaps: list[str]) -> list[str]:
    items: list[str] = []
    calc_by_metric = {item["metric"]: item for item in calculations}
    for frame in selected_frames:
        if frame["id"] == "fcf" and "fcf_yield" in calc_by_metric:
            items.append(f"FCF frame can inspect current FCF yield of {calc_by_metric['fcf_yield']['value']}.")
        elif frame["id"] == "comparable_multiples":
            available = [metric for metric in ("pe", "ps", "ev_ebitda") if metric in calc_by_metric]
            if available:
                items.append(f"Comparable frame has deterministic multiples: {', '.join(available)}.")
            else:
                items.append("Comparable frame is relevant but lacks enough market and peer inputs for precision.")
        elif frame["id"] == "cyclical":
            items.append("Cyclical frame should test whether current earnings are peak, trough, or mid-cycle.")
        elif frame["id"] == "growth_scenario":
            items.append("Growth/scenario frame should test TAM, penetration, margin, and milestone probability assumptions.")
        elif frame["id"] == "sotp_asset_value":
            items.append("SOTP frame should map segment, asset, debt, and holding-discount assumptions.")
    if gaps:
        items.append("Because data gaps remain, treat this as valuation research scaffolding rather than a target price.")
    return items


def _watch_items(selected_frames: list[dict[str, Any]]) -> list[str]:
    by_id = {frame["id"]: frame for frame in CORE_FRAMES}
    items: list[str] = []
    for selected in selected_frames:
        frame = by_id[selected["id"]]
        items.append(f"{frame['name']} triggers: {', '.join(frame['triggers'][:2])}.")
        items.append(f"{frame['name']} failure checks: {', '.join(frame['failure_conditions'][:2])}.")
    return items


def _context_text(context: dict[str, Any]) -> str:
    chunks: list[str] = []
    stock = context.get("stock") or {}
    chunks.extend(str(stock.get(field) or "") for field in ("name", "core_business", "stock_character", "notable_history"))
    for key in ("stock_knowledge", "sector_knowledge", "stock_insights", "sector_insights", "global_insights"):
        for item in context.get(key) or []:
            chunks.append(str(item.get("content") or item.get("insight") or item.get("normalized_summary") or ""))
    for sector in context.get("sectors") or []:
        chunks.append(str(sector.get("sector_name") or sector.get("name") or ""))
    return "\n".join(chunks).lower()


def _has_user_confirmed_valuation_case(context: dict[str, Any]) -> bool:
    for key in ("stock_knowledge", "stock_insights"):
        for item in context.get(key) or []:
            text = str(item.get("content") or item.get("insight") or item.get("normalized_summary") or "").lower()
            if ("valuation" in text or "估值" in text) and (
                item.get("confirmed_by_user") is True or key == "stock_insights"
            ):
                return True
    return False


def _stock_context_needs_research(context: dict[str, Any]) -> bool:
    stock = context.get("stock") or {}
    marker_text = " ".join(
        str(stock.get(field) or "")
        for field in ("core_business", "stock_character", "notable_history")
    ).lower()
    minimal_marker = (
        "minimal profile initialized from command workbench" in marker_text
        or "needs research" in marker_text
        or "missing-stock recovery" in marker_text
    )
    return minimal_marker and not (context.get("stock_knowledge") or []) and not (context.get("sources") or [])


def _write_artifact(packet: dict[str, Any], *, output_dir: Path) -> Path:
    artifact_dir = output_dir / "valuation"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    symbol = packet["input"]["symbol"]
    market = packet["input"]["market"]
    timestamp = packet["created_at"].replace(":", "").replace("-", "")
    path = artifact_dir / f"{symbol}_{market}_valuation_{timestamp}.json"
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_path = artifact_dir / f"{symbol}_{market}_valuation_latest.json"
    latest_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
