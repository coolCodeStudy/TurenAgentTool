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
    provider_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0).isoformat()
    stock = context.get("stock") or {}
    facts = _extract_facts(context, provider_snapshot=provider_snapshot)
    currency = _infer_currency(facts=facts, market=market)
    _attach_fact_display_values(facts, currency=currency)
    fact_values = {fact["metric"]: fact["value"] for fact in facts if fact.get("value") is not None}
    calculations = _calculate_metrics(fact_values, currency=currency)
    gaps = _data_gaps(fact_values, calculations, context, provider_snapshot=provider_snapshot)
    scores = _score_frames(context=context, fact_values=fact_values, calculations=calculations, gaps=gaps)
    bridge = _market_implied_bridge(
        context=context,
        fact_values=fact_values,
        calculations=calculations,
        frame_scores=scores,
        gaps=gaps,
        currency=currency,
    )
    selected_frames = _select_frames(bridge["frame_fit_ranking"])
    coverage = _source_coverage(context=context, facts=facts, provider_snapshot=provider_snapshot)
    degraded_reasons = _degraded_reasons(gaps=gaps, coverage=coverage, context=context, provider_snapshot=provider_snapshot)
    target_resolution = _target_resolution(symbol=symbol, market=market, command=command, provider_snapshot=provider_snapshot)
    packet = {
        "feature": "stock_valuation_research",
        "version": 1,
        "created_at": created_at,
        "input": {"symbol": symbol.strip().upper(), "market": market.strip().upper(), "command": command},
        "target_resolution": target_resolution,
        "stock": {
            "id": stock.get("id"),
            "symbol": stock.get("symbol") or symbol.strip().upper(),
            "market": stock.get("market") or market.strip().upper(),
            "name": stock.get("name"),
            "core_business": stock.get("core_business"),
            "stock_character": stock.get("stock_character"),
        },
        "facts": facts,
        "assumptions": _assumptions(context, provider_snapshot=provider_snapshot),
        "deterministic_calculations": calculations,
        "internal_frame_scores": scores,
        "selected_frames": selected_frames,
        "market_implied_bridge": bridge,
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


def build_valuation_artifact_evidence(packet: dict[str, Any], *, artifact_kind: str = "latest") -> dict[str, Any]:
    stock = packet.get("stock") if isinstance(packet.get("stock"), dict) else {}
    input_fields = packet.get("input") if isinstance(packet.get("input"), dict) else {}
    return {
        "feature": "stock_valuation_research",
        "evidence_type": "valuation_artifact_readback",
        "artifact": {
            "kind": artifact_kind,
            "symbol": str(input_fields.get("symbol") or stock.get("symbol") or "").upper(),
            "market": str(input_fields.get("market") or stock.get("market") or "").upper(),
            "created_at": packet.get("created_at"),
            "version": packet.get("version"),
        },
        "target_resolution": _evidence_target_resolution(packet.get("target_resolution") if isinstance(packet.get("target_resolution"), dict) else {}),
        "facts": [_evidence_fact(item) for item in packet.get("facts") or [] if isinstance(item, dict)],
        "deterministic_calculations": [
            _evidence_calculation(item) for item in packet.get("deterministic_calculations") or [] if isinstance(item, dict)
        ],
        "source_coverage": _evidence_source_coverage(packet.get("source_coverage") if isinstance(packet.get("source_coverage"), dict) else {}),
        "market_implied_bridge": _evidence_bridge(packet.get("market_implied_bridge") if isinstance(packet.get("market_implied_bridge"), dict) else {}),
        "safety": {
            "direct_investment_advice": bool((packet.get("safety") or {}).get("direct_investment_advice")),
            "writes_formal_user_insight": bool((packet.get("safety") or {}).get("writes_formal_user_insight")),
            "omits_local_artifact_path": True,
            "provider_error_detail_omitted": True,
        },
    }


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

    target_resolution = packet.get("target_resolution") or {}
    if target_resolution:
        lines.append("Target resolution:")
        lines.append(
            "- Input: "
            f"{target_resolution.get('input_target')} -> resolved: "
            f"{target_resolution.get('normalized_target')} {target_resolution.get('company_name')} -> "
            f"market snapshot ticker: {target_resolution.get('provider_market_ticker')}"
        )
        lines.append("")

    calculations = packet.get("deterministic_calculations") or []
    calc_by_metric = {item.get("metric"): item for item in calculations}
    facts_by_metric = {item.get("metric"): item for item in packet.get("facts") or []}
    snapshot_rows = (
        ("Market cap", calc_by_metric.get("market_cap") or facts_by_metric.get("market_cap")),
        ("Enterprise value", calc_by_metric.get("enterprise_value") or facts_by_metric.get("enterprise_value")),
        ("Revenue", facts_by_metric.get("revenue")),
        ("Free cash flow", calc_by_metric.get("free_cash_flow") or facts_by_metric.get("free_cash_flow")),
        ("FCF margin", calc_by_metric.get("fcf_margin")),
        ("P/S", calc_by_metric.get("ps")),
        ("PE", calc_by_metric.get("pe")),
        ("EV/FCF", calc_by_metric.get("ev_fcf")),
    )
    if any(item for _, item in snapshot_rows):
        lines.append("Valuation snapshot:")
        for label, item in snapshot_rows:
            if item:
                lines.append(f"- {label}: {_item_display(item)}")
        lines.append("")

    coverage = packet.get("source_coverage") or {}
    provider_statuses = coverage.get("provider_statuses") or {}
    if provider_statuses:
        lines.append("Data status:")
        for label, key in (
            ("Official financials", "financial_facts"),
            ("Official/company financials", "official_financials"),
            ("Fallback fundamentals", "fallback_fundamentals"),
            ("Market snapshot", "market_snapshot"),
            ("Provider mapping", "provider_mapping"),
        ):
            status = provider_statuses.get(key) or {}
            if status:
                status_label = str(status.get("status") or "").replace("_", " ")
                lines.append(f"- {label}: {status_label}. {status.get('explanation')}")
        source_attempts = coverage.get("source_attempts") or {}
        for key, attempt in source_attempts.items():
            family = attempt.get("family")
            status_value = attempt.get("status")
            if family and status_value:
                lines.append(f"- Source attempt {key}: {family} ({str(status_value).replace('_', ' ')})")
        lines.append("")

    lines.append("Relevant frames:")
    for frame in packet.get("selected_frames") or []:
        fit = frame.get("fit_to_current_market_value")
        fit_copy = f", fit={fit}" if fit else ""
        lines.append(f"- {frame['name']} (score {frame['score']:.2f}{fit_copy}): {frame['reason']}")
    lines.append("")

    bridge = packet.get("market_implied_bridge") or {}
    bridge_lines = bridge.get("bridge_lines") or []
    if bridge_lines:
        lines.append("Market-implied bridge:")
        for item in bridge_lines:
            lines.append(f"- {item.get('display')}")
        lines.append("")

    lines.append("Facts:")
    facts = packet.get("facts") or []
    if facts:
        for fact in facts[:8]:
            source = f" source_id={fact['source_id']}" if fact.get("source_id") is not None else " source_id=missing"
            lines.append(f"- {fact['metric']}: {_item_display(fact)}{source}")
    else:
        lines.append("- No reusable financial or market facts were found in the local stock context.")
    lines.append("")

    lines.append("Assumptions:")
    assumptions = packet.get("assumptions") or {}
    for item in assumptions.get("items") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("Deterministic calculations:")
    if calculations:
        for calculation in calculations:
            lines.append(f"- {calculation['metric']}: {_item_display(calculation)} ({calculation['formula']})")
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


def _evidence_fact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "metric",
            "value",
            "display_value",
            "display_kind",
            "currency",
            "source_id",
            "source_type",
            "timestamp",
            "period_end",
            "provider",
        )
        if item.get(key) is not None
    }


def _evidence_calculation(item: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        key: item.get(key)
        for key in (
            "metric",
            "value",
            "raw_value",
            "display_value",
            "display_kind",
            "currency",
            "meaningful",
            "meaningfulness_reason",
            "formula",
            "inputs",
        )
        if item.get(key) is not None
    }
    if "meaningful" not in evidence:
        evidence["meaningful"] = True
    return evidence


def _evidence_source_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_count": coverage.get("fact_count", 0),
        "fact_source_id_count": coverage.get("fact_source_id_count", 0),
        "source_count": coverage.get("source_count", 0),
        "official_source_count": coverage.get("official_source_count", 0),
        "market_snapshot_status": coverage.get("market_snapshot_status", "missing"),
        "financial_fact_status": coverage.get("financial_fact_status", "missing"),
        "peer_data_status": coverage.get("peer_data_status", "missing"),
        "user_confirmed_valuation_case": bool(coverage.get("user_confirmed_valuation_case")),
        "provider_statuses": coverage.get("provider_statuses") or {},
        "source_attempts": coverage.get("source_attempts") or {},
    }


def _evidence_target_resolution(target_resolution: dict[str, Any]) -> dict[str, Any]:
    return {
        key: target_resolution.get(key)
        for key in (
            "input_target",
            "normalized_target",
            "normalized_symbol",
            "normalized_market",
            "company_name",
            "provider_market_ticker",
            "provider",
            "currency",
            "mapping_confidence",
            "mapping_source",
        )
        if target_resolution.get(key) is not None
    }


def _evidence_bridge(bridge: dict[str, Any]) -> dict[str, Any]:
    return {
        "bridge_lines": [
            {"type": item.get("type"), "display": item.get("display")}
            for item in bridge.get("bridge_lines") or []
            if isinstance(item, dict)
        ],
        "frame_fit_ranking": [
            _evidence_frame_fit(item)
            for item in bridge.get("frame_fit_ranking") or []
            if isinstance(item, dict)
        ],
    }


def _evidence_frame_fit(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "id",
            "name",
            "score",
            "fit_to_current_market_value",
            "why_it_fits_or_not",
            "implied_assumptions",
            "assumptions_that_must_become_true",
            "main_data_gaps",
            "confidence",
        )
        if item.get(key) is not None
    }


def _extract_facts(context: dict[str, Any], *, provider_snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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
    for provider_fact in (provider_snapshot or {}).get("facts") or []:
        if provider_fact.get("value") is None:
            continue
        facts.append(
            {
                "metric": provider_fact.get("metric"),
                "value": provider_fact.get("value"),
                "source_id": provider_fact.get("source_id"),
                "source_type": provider_fact.get("source_type"),
                "knowledge_id": provider_fact.get("knowledge_id"),
                "confidence": provider_fact.get("confidence"),
                "confirmed_by_user": bool(provider_fact.get("confirmed_by_user")),
                "timestamp": provider_fact.get("timestamp"),
                "period_end": provider_fact.get("period_end"),
                "input_text": str(provider_fact.get("input_text") or "")[:240],
                "provider": provider_fact.get("provider"),
                "currency": provider_fact.get("currency"),
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


def _calculate_metrics(values: dict[str, float], *, currency: str | None = None) -> list[dict[str, Any]]:
    calculations: list[dict[str, Any]] = []

    fcf = values.get("free_cash_flow")
    if fcf is None and values.get("operating_cash_flow") is not None and values.get("capex") is not None:
        fcf = values["operating_cash_flow"] - abs(values["capex"])
        calculations.append(_calc("free_cash_flow", fcf, "operating_cash_flow - abs(capex)", ["operating_cash_flow", "capex"], kind="currency", currency=currency))

    net_debt = values.get("net_debt")
    if net_debt is None and values.get("debt") is not None and values.get("cash") is not None:
        net_debt = values["debt"] - values["cash"]
        calculations.append(_calc("net_debt", net_debt, "debt - cash", ["debt", "cash"], kind="currency", currency=currency))

    market_cap = values.get("market_cap")
    if market_cap is None and values.get("price") is not None and values.get("shares_outstanding") is not None:
        market_cap = values["price"] * values["shares_outstanding"]
        calculations.append(_calc("market_cap", market_cap, "price * shares_outstanding", ["price", "shares_outstanding"], kind="currency", currency=currency))

    ev = values.get("enterprise_value")
    if ev is None and market_cap is not None and net_debt is not None:
        ev = market_cap + net_debt
        calculations.append(_calc("enterprise_value", ev, "market_cap + net_debt", ["market_cap", "net_debt"], kind="currency", currency=currency))

    ratio_specs = (
        ("fcf_margin", fcf, values.get("revenue"), "free_cash_flow / revenue", ["free_cash_flow", "revenue"], "percent", None),
        ("fcf_yield", fcf, market_cap, "free_cash_flow / market_cap", ["free_cash_flow", "market_cap"], "percent", "negative FCF"),
        ("pe", market_cap, values.get("net_income"), "market_cap / net_income", ["market_cap", "net_income"], "multiple", "negative earnings"),
        ("ps", market_cap, values.get("revenue"), "market_cap / revenue", ["market_cap", "revenue"], "multiple", None),
        ("ev_ebitda", ev, values.get("ebitda"), "enterprise_value / ebitda", ["enterprise_value", "ebitda"], "multiple", "negative EBITDA"),
        ("ev_fcf", ev, fcf, "enterprise_value / free_cash_flow", ["enterprise_value", "free_cash_flow"], "multiple", "negative FCF"),
    )
    for metric, numerator, denominator, formula, inputs, kind, negative_reason in ratio_specs:
        if numerator is not None and denominator not in (None, 0):
            invalid_negative = negative_reason if denominator < 0 or (metric == "fcf_yield" and numerator < 0) else None
            calculations.append(
                _calc(
                    metric,
                    numerator / denominator,
                    formula,
                    inputs,
                    kind=kind,
                    negative_reason=invalid_negative,
                )
            )

    return calculations


def _calc(
    metric: str,
    value: float,
    formula: str,
    inputs: list[str],
    *,
    kind: str,
    currency: str | None = None,
    negative_reason: str | None = None,
) -> dict[str, Any]:
    raw_value = round(value, 6)
    item: dict[str, Any] = {
        "metric": metric,
        "value": raw_value,
        "formula": formula,
        "inputs": inputs,
        "display_kind": kind,
        "meaningful": True,
    }
    if currency:
        item["currency"] = currency
    if negative_reason:
        item["raw_value"] = raw_value
        item["value"] = None
        item["meaningful"] = False
        item["meaningfulness_reason"] = negative_reason
        item["display_value"] = f"not meaningful ({negative_reason})"
    else:
        item["display_value"] = _format_value(raw_value, kind=kind, currency=currency)
    return item


def _data_gaps(
    values: dict[str, float],
    calculations: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    provider_snapshot: dict[str, Any] | None = None,
) -> list[str]:
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
    if not (context.get("sources") or (provider_snapshot or {}).get("sources") or []):
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
    fit_order = {"fits": 0, "partial_fit": 1, "insufficient_data": 2, "does_not_fit": 3}
    ranked = sorted(scores, key=lambda item: (fit_order.get(str(item.get("fit_to_current_market_value")), 4), -float(item.get("score") or 0)))
    selected = [score for score in ranked if score["score"] >= 0.2][:3]
    return selected or ranked[:1]


def _gap_affects_frame(gap: str, frame_id: str) -> bool:
    if frame_id == "fcf" and "free cash flow" in gap:
        return True
    if frame_id == "comparable_multiples" and any(token in gap for token in ("price", "market cap", "net income", "revenue")):
        return True
    if frame_id == "growth_scenario" and "revenue" in gap:
        return True
    return False


def _source_coverage(
    context: dict[str, Any],
    facts: list[dict[str, Any]],
    *,
    provider_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = [*(context.get("sources") or []), *((provider_snapshot or {}).get("sources") or [])]
    source_types = [str(source.get("source_type") or "").lower() for source in sources]
    official_count = sum(
        1
        for source_type in source_types
        if any(token in source_type for token in ("official", "filing", "sec", "hkex", "exchange", "annual_report"))
    )
    if provider_snapshot and provider_snapshot.get("financial_fact_status"):
        financial_fact_status = str(provider_snapshot.get("financial_fact_status"))
    elif any(fact.get("metric") in {"revenue", "net_income", "operating_cash_flow", "capex", "free_cash_flow", "cash", "debt", "ebitda"} for fact in facts):
        financial_fact_status = "present"
    else:
        financial_fact_status = "missing"
    return {
        "fact_count": len(facts),
        "fact_source_id_count": len({fact.get("source_id") for fact in facts if fact.get("source_id") is not None}),
        "source_count": len(sources),
        "official_source_count": official_count,
        "market_snapshot_status": "present" if any(fact["metric"] in {"price", "market_cap"} for fact in facts) else "missing",
        "peer_data_status": "missing",
        "financial_fact_status": financial_fact_status,
        "user_confirmed_valuation_case": _has_user_confirmed_valuation_case(context),
        "provider_errors": list((provider_snapshot or {}).get("errors") or []),
        "provider_statuses": _provider_statuses(facts=facts, provider_snapshot=provider_snapshot),
        "source_attempts": (provider_snapshot or {}).get("source_attempts") or {},
        "target_resolution": (provider_snapshot or {}).get("target_resolution") or {},
    }


def _degraded_reasons(
    *,
    gaps: list[str],
    coverage: dict[str, Any],
    context: dict[str, Any],
    provider_snapshot: dict[str, Any] | None = None,
) -> list[str]:
    reasons = list(gaps)
    reasons.extend(_provider_gap_reasons(coverage=coverage, provider_snapshot=provider_snapshot))
    if coverage.get("official_source_count", 0) == 0:
        reasons.append("official financial source coverage is missing")
    if _stock_context_needs_research(context):
        reasons.append("stock profile appears minimal and needs research import")
    return sorted(dict.fromkeys(reasons))


def _provider_gap_reasons(*, coverage: dict[str, Any], provider_snapshot: dict[str, Any] | None = None) -> list[str]:
    if not ((provider_snapshot or {}).get("errors") or []):
        return []
    provider_statuses = coverage.get("provider_statuses") or {}
    reasons: list[str] = []
    for key, label in (("financial_facts", "official financial provider"), ("market_snapshot", "market snapshot provider")):
        status = provider_statuses.get(key) or {}
        status_value = status.get("status")
        if status_value == "partial_provider_gap":
            reasons.append(f"provider data gap: {label} is partially unavailable; usable fields are shown when available")
        elif status_value == "complete_missing":
            reasons.append(f"provider data gap: {label} is unavailable")
        elif status_value == "stale_or_unknown_freshness":
            reasons.append(f"provider data gap: {label} freshness is stale or unknown")
    return reasons or ["provider data gap: provider snapshot is unavailable or incomplete"]


def _assumptions(context: dict[str, Any], *, provider_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    confirmed = _has_user_confirmed_valuation_case(context)
    items = []
    if confirmed:
        items.append("A user-confirmed valuation case exists in local stock insights or knowledge.")
    else:
        items.append("No user-confirmed valuation case exists; frame ranking is a system candidate only.")
    if provider_snapshot is not None:
        if (provider_snapshot.get("target_resolution") or {}).get("normalized_market") in {"KR", "HK"}:
            items.append("P0.3 uses mapped non-US market snapshots and labels vendor fallback fundamentals separately from official/company financial facts.")
        else:
            items.append("P0.1 uses provider snapshots when available and labels provider gaps instead of inventing missing facts.")
    else:
        items.append("P0 uses existing local stock context and deterministic calculations when no provider snapshot is available.")
    items.append("Peer sets, analyst estimates, and target-price precision are intentionally omitted unless sourced.")
    return {"user_confirmed_valuation_case": confirmed, "items": items}


def _interpretation(selected_frames: list[dict[str, Any]], calculations: list[dict[str, Any]], gaps: list[str]) -> list[str]:
    items: list[str] = []
    calc_by_metric = {item["metric"]: item for item in calculations}
    for frame in selected_frames:
        if frame["id"] == "fcf" and "fcf_yield" in calc_by_metric:
            items.append(f"FCF frame can inspect current FCF yield of {_item_display(calc_by_metric['fcf_yield'])}.")
        elif frame["id"] == "comparable_multiples":
            available = [metric for metric in ("pe", "ps", "ev_ebitda") if metric in calc_by_metric and calc_by_metric[metric].get("meaningful") is not False]
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


def _attach_fact_display_values(facts: list[dict[str, Any]], *, currency: str | None) -> None:
    for fact in facts:
        metric = str(fact.get("metric") or "")
        fact_currency = fact.get("currency") or currency
        if metric in {"revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capex", "free_cash_flow", "cash", "debt", "net_debt", "market_cap", "enterprise_value", "ebitda", "book_value"}:
            kind = "currency"
        elif metric in {"gross_margin", "operating_margin", "fcf_margin", "fcf_yield", "revenue_growth"}:
            kind = "percent"
        elif metric == "price":
            kind = "currency_per_share"
        else:
            kind = "number"
        fact["display_kind"] = kind
        if fact_currency and kind in {"currency", "currency_per_share"}:
            fact["currency"] = fact_currency
        fact["display_value"] = _format_value(fact.get("value"), kind=kind, currency=fact_currency)


def _item_display(item: dict[str, Any]) -> str:
    return str(item.get("display_value") or item.get("value") or "unknown")


def _infer_currency(*, facts: list[dict[str, Any]], market: str) -> str | None:
    for fact in facts:
        currency = fact.get("currency")
        if currency:
            return str(currency).upper()
    if market.strip().upper() == "US":
        return "USD"
    if market.strip().upper() == "HK":
        return "HKD"
    if market.strip().upper() == "KR":
        return "KRW"
    return None


def _format_value(value: Any, *, kind: str, currency: str | None = None) -> str:
    if value in (None, ""):
        return "unknown"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if kind == "percent":
        return f"{number * 100:.1f}%"
    if kind == "multiple":
        return f"{number:.1f}x"
    if kind == "currency_per_share":
        prefix = _currency_prefix(currency)
        if not prefix:
            return "unknown currency"
        return f"{prefix}{number:.2f}/share"
    if kind == "currency":
        prefix = _currency_prefix(currency)
        if not prefix:
            return "unknown currency"
        sign = "-" if number < 0 else ""
        scaled, suffix = _scale_abs_number(abs(number))
        return f"{sign}{prefix}{scaled:.1f}{suffix}"
    if kind == "number":
        scaled, suffix = _scale_abs_number(abs(number))
        sign = "-" if number < 0 else ""
        if suffix:
            return f"{sign}{scaled:.1f}{suffix}"
        return f"{number:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _currency_prefix(currency: str | None) -> str | None:
    if not currency:
        return None
    normalized = currency.upper()
    if normalized == "USD":
        return "$"
    if normalized == "HKD":
        return "HK$"
    if normalized == "CNY":
        return "RMB "
    return f"{normalized} "


def _scale_abs_number(number: float) -> tuple[float, str]:
    if number >= 1_000_000_000:
        return number / 1_000_000_000, "B"
    if number >= 1_000_000:
        return number / 1_000_000, "M"
    if number >= 1_000:
        return number / 1_000, "K"
    return number, ""


def _provider_statuses(*, facts: list[dict[str, Any]], provider_snapshot: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    errors = [str(error) for error in (provider_snapshot or {}).get("errors") or []]
    has_financial = any(str(fact.get("source_type") or "").lower() in {"sec_companyfacts", "official_filing"} for fact in facts)
    has_official_non_us = any(str(fact.get("source_type") or "").lower() in {"hkexnews", "dart_fss", "company_ir", "company_report"} for fact in facts)
    has_fallback = any(str(fact.get("source_type") or "").lower() == "yahoo_fallback_fundamentals" for fact in facts)
    has_market = any(fact.get("metric") in {"price", "market_cap", "shares_outstanding"} for fact in facts)
    yahoo_errors = [error for error in errors if "yahoo" in error.lower()]
    sec_errors = [error for error in errors if "sec" in error.lower()]
    statuses = {
        "financial_facts": _provider_status(
            has_data=has_financial,
            errors=sec_errors,
            present_copy="official financial facts are available",
            missing_copy="official financial facts are unavailable",
        ),
        "market_snapshot": _provider_status(
            has_data=has_market,
            errors=yahoo_errors,
            present_copy="market-cap and price fields are available",
            missing_copy="market snapshot fields are unavailable",
        ),
    }
    source_attempts = (provider_snapshot or {}).get("source_attempts") or {}
    if source_attempts:
        official_family = ((source_attempts.get("official_financials") or {}).get("family") or "official/company financial sources")
        statuses["provider_mapping"] = {
            "status": "available" if (provider_snapshot or {}).get("target_resolution") else "complete_missing",
            "explanation": "provider ticker/entity mapping is available." if (provider_snapshot or {}).get("target_resolution") else "provider ticker/entity mapping is unavailable.",
        }
        statuses["official_financials"] = _provider_status(
            has_data=has_official_non_us,
            errors=[error for error in errors if any(token in error.lower() for token in ("hkex", "dart", "fss", "company ir", "official"))],
            present_copy=f"{official_family} facts are available",
            missing_copy=f"{official_family} structured facts are unavailable in this P0.3 slice",
        )
        if has_fallback:
            statuses["fallback_fundamentals"] = {
                "status": "fallback_used",
                "explanation": "Yahoo/yfinance vendor-labeled fallback operating anchors are used; they are not official/regulator facts.",
            }
        else:
            statuses["fallback_fundamentals"] = {
                "status": "complete_missing",
                "explanation": "vendor-labeled fallback fundamentals are unavailable.",
            }
    if any(fact.get("timestamp") in (None, "") for fact in facts if fact.get("metric") in {"price", "market_cap"}):
        statuses["market_snapshot"] = {
            "status": "stale_or_unknown_freshness",
            "explanation": "market snapshot data exists, but timestamp or freshness is stale or unknown.",
        }
    return statuses


def _target_resolution(
    *,
    symbol: str,
    market: str,
    command: str,
    provider_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    resolution = dict((provider_snapshot or {}).get("target_resolution") or {})
    if not resolution:
        return {}
    resolution["input_target"] = command
    return resolution


def _provider_status(*, has_data: bool, errors: list[str], present_copy: str, missing_copy: str) -> dict[str, str]:
    if has_data and errors:
        return {
            "status": "partial_provider_gap",
            "explanation": f"{present_copy}, but another provider call or field failed; usable fields are shown and raw diagnostics stay out of the card.",
        }
    if has_data:
        return {"status": "available", "explanation": f"{present_copy}."}
    if errors:
        return {"status": "complete_missing", "explanation": f"{missing_copy}; raw diagnostics stay out of the card."}
    return {"status": "complete_missing", "explanation": f"{missing_copy}."}


def _market_implied_bridge(
    *,
    context: dict[str, Any],
    fact_values: dict[str, float],
    calculations: list[dict[str, Any]],
    frame_scores: list[dict[str, Any]],
    gaps: list[str],
    currency: str | None,
) -> dict[str, Any]:
    calc_by_metric = {item["metric"]: item for item in calculations}
    market_cap = fact_values.get("market_cap") or _calc_numeric(calc_by_metric.get("market_cap"))
    ev = fact_values.get("enterprise_value") or _calc_numeric(calc_by_metric.get("enterprise_value"))
    revenue = fact_values.get("revenue")
    fcf = fact_values.get("free_cash_flow") or _calc_numeric(calc_by_metric.get("free_cash_flow"))
    net_income = fact_values.get("net_income")
    bridge_lines: list[dict[str, str]] = []

    if market_cap is not None and revenue not in (None, 0):
        ps = market_cap / revenue
        bridge_lines.append(
            {
                "type": "sales_anchor",
                "display": f"P/S: {_format_value(ps, kind='multiple')} on {_format_value(revenue, kind='currency', currency=currency)} revenue explains the current {_format_value(market_cap, kind='currency', currency=currency)} market cap as a sales-multiple bridge.",
            }
        )
    elif market_cap is not None:
        bridge_lines.append({"type": "sales_anchor_missing", "display": "P/S bridge is unavailable because revenue is missing."})

    if ev is not None and revenue not in (None, 0):
        bridge_lines.append(
            {
                "type": "ev_sales_anchor",
                "display": f"EV/Sales: {_format_value(ev / revenue, kind='multiple')} using {_format_value(ev, kind='currency', currency=currency)} enterprise value.",
            }
        )

    if fcf is not None and market_cap not in (None, 0):
        if fcf > 0:
            bridge_lines.append(
                {
                    "type": "fcf_yield",
                    "display": f"FCF yield: {_format_value(fcf / market_cap, kind='percent')} from current FCF of {_format_value(fcf, kind='currency', currency=currency)}.",
                }
            )
        else:
            bridge_lines.append({"type": "ev_fcf_not_meaningful", "display": "EV/FCF is not meaningful because current FCF is negative; the bridge must rely on future FCF recovery rather than current FCF multiple."})
            if revenue not in (None, 0):
                required = []
                for yield_assumption in (0.03, 0.05, 0.07):
                    required_fcf = market_cap * yield_assumption
                    required_margin = required_fcf / revenue
                    required.append(f"{int(yield_assumption * 100)}% market-cap yield needs {_format_value(required_margin, kind='percent')} future FCF margin")
                bridge_lines.append({"type": "required_fcf_margin", "display": "; ".join(required) + " (illustrative bridge math, not a target price)."})

    if net_income is not None and net_income <= 0:
        bridge_lines.append({"type": "cycle_normalized_earnings", "display": "PE is not meaningful because current earnings are negative; a cycle-normalized earnings or margin-recovery placeholder is needed before earnings can explain current market value."})

    frame_fit_ranking = _frame_fit_ranking(
        frame_scores=frame_scores,
        fact_values=fact_values,
        calc_by_metric=calc_by_metric,
        bridge_lines=bridge_lines,
        gaps=gaps,
        context_text=_context_text(context),
    )
    return {"bridge_lines": bridge_lines, "frame_fit_ranking": frame_fit_ranking}


def _calc_numeric(item: dict[str, Any] | None) -> float | None:
    if not item:
        return None
    value = item.get("value")
    if value is None:
        value = item.get("raw_value")
    if value in (None, ""):
        return None
    return float(value)


def _frame_fit_ranking(
    *,
    frame_scores: list[dict[str, Any]],
    fact_values: dict[str, float],
    calc_by_metric: dict[str, dict[str, Any]],
    bridge_lines: list[dict[str, str]],
    gaps: list[str],
    context_text: str,
) -> list[dict[str, Any]]:
    ranking: list[dict[str, Any]] = []
    has_sales_bridge = any(item.get("type") == "sales_anchor" for item in bridge_lines)
    has_negative_fcf = (fact_values.get("free_cash_flow") or _calc_numeric(calc_by_metric.get("free_cash_flow")) or 0) < 0
    has_negative_earnings = (fact_values.get("net_income") or 0) < 0
    for frame in frame_scores:
        fit = "insufficient_data"
        why = "Available facts do not yet bridge this frame to current market value."
        assumptions = []
        must_become_true = []
        main_gaps = list(frame.get("degraded_by") or [])
        if frame["id"] == "comparable_multiples":
            if has_sales_bridge:
                fit = "fits" if not has_negative_earnings else "partial_fit"
                why = "Current market value can be expressed through a deterministic sales multiple, while earnings-based multiples need normalization if earnings are negative."
                assumptions.append("Market accepts revenue or sales multiple as the near-term anchor.")
                must_become_true.append("Revenue durability and future margin conversion must support the visible sales multiple.")
            else:
                main_gaps.append("revenue or market cap is missing")
        elif frame["id"] == "fcf":
            if has_negative_fcf:
                fit = "does_not_fit"
                why = "Current negative FCF cannot explain market value through ordinary EV/FCF or FCF yield."
                assumptions.append("Future FCF margin recovery is required before this frame can support current value.")
                must_become_true.append("FCF must turn positive and reach the required illustrative margin bridge.")
            elif "fcf_yield" in calc_by_metric:
                fit = "fits"
                why = "Positive FCF yield directly bridges current market value to cash generation."
                assumptions.append("Current FCF is durable rather than one-time working-capital release.")
                must_become_true.append("Cash conversion remains durable.")
        elif frame["id"] == "cyclical":
            if has_negative_earnings and any(token in context_text for token in ("cycle", "cyclical", "semiconductor", "memory", "capacity", "inventory", "周期", "半导体")):
                fit = "partial_fit"
                why = "Current earnings do not explain market value, but the stock context supports a cycle-normalized earnings bridge."
                assumptions.append("Market is looking through depressed current earnings toward mid-cycle recovery.")
                must_become_true.append("Cycle-normalized margins or earnings must recover enough to support the current value.")
            elif has_negative_earnings:
                fit = "insufficient_data"
                main_gaps.append("cycle-normalized earnings input is missing")
        elif frame["id"] == "growth_scenario":
            if has_negative_earnings or has_negative_fcf:
                fit = "partial_fit"
                why = "Current profit or FCF cannot support market value, so an expectation-based growth/scenario bridge is needed."
                assumptions.append("Market assigns value to future revenue growth, margin maturity, TAM, or milestone probability.")
                must_become_true.append("Growth and margin milestones must become observable enough to justify the current value.")
            elif has_sales_bridge:
                fit = "partial_fit"
                why = "Sales anchor exists, but scenario assumptions need TAM, growth, and mature margin evidence."
                assumptions.append("Future scale or optionality exceeds current financial statement evidence.")
                must_become_true.append("Forward growth or milestone evidence must validate the scenario.")
        elif frame["id"] == "sotp_asset_value":
            fit = "insufficient_data"
            why = "SOTP cannot explain current market value without segment, asset, holding, or NAV inputs."
            main_gaps.append("segment or asset value data is missing")
        ranking.append(
            {
                **frame,
                "fit_to_current_market_value": fit,
                "why_it_fits_or_not": why,
                "implied_assumptions": assumptions or ["No deterministic market-implied assumption available from current inputs."],
                "assumptions_that_must_become_true": must_become_true or ["Additional source-backed inputs must validate this frame."],
                "main_data_gaps": sorted(dict.fromkeys(main_gaps or gaps)),
                "confidence": "medium" if fit in {"fits", "partial_fit"} and not main_gaps else "low",
            }
        )
    fit_order = {"fits": 0, "partial_fit": 1, "insufficient_data": 2, "does_not_fit": 3}
    return sorted(ranking, key=lambda item: (fit_order.get(item["fit_to_current_market_value"], 4), -float(item.get("score") or 0)))


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
