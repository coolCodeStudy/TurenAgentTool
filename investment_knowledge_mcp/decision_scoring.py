from __future__ import annotations

from typing import Any


WEIGHTS = {
    "portfolio_fit": 20,
    "fundamental_quality": 18,
    "valuation_setup": 16,
    "sector_regime": 14,
    "market_regime": 10,
    "technical_setup": 9,
    "chip_event_structure": 8,
    "evidence_quality_freshness": 5,
}

RECOMMENDATION_ORDER = [
    "avoid",
    "watch",
    "wait",
    "starter",
    "normal_position",
    "high_conviction_candidate",
]


def pre_score_decision(context_pack: dict[str, Any]) -> dict[str, Any]:
    components = {
        "portfolio_fit": _portfolio_score(context_pack),
        "fundamental_quality": _fundamental_score(context_pack),
        "valuation_setup": _observation_score(context_pack.get("valuation_pack")),
        "sector_regime": _sector_score(context_pack),
        "market_regime": _observation_score(context_pack.get("market_pack")),
        "technical_setup": _observation_score(context_pack.get("technical_pack")),
        "chip_event_structure": _chip_event_score(context_pack),
        "evidence_quality_freshness": _evidence_score(context_pack),
    }
    composite = 0.0
    for key, weight in WEIGHTS.items():
        composite += components[key]["score"] * weight / 100.0
    return {
        "weights": WEIGHTS,
        "components": components,
        "composite_score": round(composite, 2),
    }


def apply_decision_gates(context_pack: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    gates = []
    freshness = context_pack.get("freshness_report") or {}
    constraints = context_pack.get("user_constraints") or {}
    portfolio = context_pack.get("portfolio_exposure") or {}
    technical = context_pack.get("technical_pack") or {}
    valuation = context_pack.get("valuation_pack") or {}
    chip = context_pack.get("chip_event_pack") or {}

    if constraints.get("unconfirmed_defaults"):
        gates.append(_gate("unconfirmed_profile", "confidence_cap", "medium", "Using unconfirmed conservative decision defaults."))

    if portfolio.get("status") != "ok":
        gates.append(_gate("missing_portfolio", "recommendation_cap", "watch", "No current portfolio snapshot is available."))

    if technical.get("status") in {"missing", "stale"}:
        gates.append(_gate("stale_technical", "recommendation_cap", "watch", "Technical setup is missing or stale."))

    if valuation.get("status") in {"missing", "stale"}:
        gates.append(_gate("stale_valuation", "confidence_cap", "medium", "Valuation setup is missing or stale."))

    if chip.get("status") in {"missing", "stale"} and not constraints.get("event_stock_allowed"):
        gates.append(_gate("unreviewed_event_risk", "recommendation_cap", "starter", "Chip/event structure is not confirmed."))

    if freshness.get("overall_status") == "missing_critical":
        gates.append(_gate("missing_critical_data", "confidence_cap", "low", "At least one critical decision input is missing."))

    position_count = int(portfolio.get("position_count") or 0)
    hard_cap = int(constraints.get("max_positions_hard_cap") or 0)
    target_holding = portfolio.get("target_holding")
    if hard_cap and position_count >= hard_cap and not target_holding:
        gates.append(_gate("position_count_cap", "recommendation_cap", "wait", "Portfolio already reaches the hard position-count cap."))

    max_recommendation = _max_recommendation_from_score(float(score.get("composite_score") or 0.0))
    confidence = _confidence_from_score(float(score.get("composite_score") or 0.0), freshness.get("overall_status"))
    for gate in gates:
        if gate["effect"] == "recommendation_cap":
            max_recommendation = _min_recommendation(max_recommendation, gate["value"])
        elif gate["effect"] == "confidence_cap":
            confidence = _min_confidence(confidence, gate["value"])

    return {
        "gates": gates,
        "max_recommendation": max_recommendation,
        "confidence": confidence,
        "freshness_status": freshness.get("overall_status") or "unknown",
    }


def derive_position_range(context_pack: dict[str, Any], score: dict[str, Any], gates: dict[str, Any]) -> dict[str, Any]:
    constraints = context_pack.get("user_constraints") or {}
    portfolio = context_pack.get("portfolio_exposure") or {}
    target_holding = portfolio.get("target_holding")
    recommendation = gates.get("max_recommendation") or "watch"
    max_single = float(constraints.get("max_single_stock_position_pct") or 0.06)
    starter = min(float(constraints.get("preferred_starter_position_pct") or 0.02), max_single)
    confidence = gates.get("confidence") or "low"

    if recommendation in {"avoid", "watch", "wait"}:
        initial_min = None
        initial_max = None
        position_class = "watch"
    elif recommendation == "starter":
        initial_min = round(max(starter * 0.5, 0.005), 4)
        initial_max = round(starter, 4)
        position_class = "starter"
    elif recommendation == "normal_position":
        initial_min = round(starter, 4)
        initial_max = round(min(max_single * 0.6, starter * 2), 4)
        position_class = "normal"
    else:
        initial_min = round(starter, 4)
        initial_max = round(min(max_single * 0.75, starter * 2.5), 4)
        position_class = "high_conviction_candidate"

    if confidence == "low" and initial_max is not None:
        initial_max = min(initial_max, starter)
        position_class = "starter"

    if target_holding:
        current_weight = target_holding.get("currency_weight")
        if current_weight is not None and current_weight >= max_single:
            initial_min = None
            initial_max = None
            recommendation = "review_existing_holding"
            position_class = "review"

    return {
        "recommendation": recommendation,
        "initial_min_pct": initial_min,
        "initial_max_pct": initial_max,
        "max_position_pct": round(max_single, 4),
        "position_class": position_class,
    }


def build_deterministic_ticket(context_pack: dict[str, Any]) -> dict[str, Any]:
    score = pre_score_decision(context_pack)
    gates = apply_decision_gates(context_pack, score)
    position = derive_position_range(context_pack, score, gates)
    components = score["components"]
    reasons = _top_reasons(context_pack, components)
    stale_components = [
        item for item in (context_pack.get("freshness_report") or {}).get("components", []) if item.get("status") != "ok"
    ]
    return {
        "decision_type": "single_stock",
        "mode": context_pack.get("mode") or "focused",
        "stock": context_pack["stock"],
        "recommendation": position["recommendation"],
        "composite_score": score["composite_score"],
        "confidence": gates["confidence"],
        "freshness_status": gates["freshness_status"],
        "suggested_position": position,
        "score_components": components,
        "gates": gates["gates"],
        "reasons": reasons,
        "veto_conditions": _veto_conditions(gates),
        "entry_conditions": _entry_conditions(context_pack, gates),
        "add_conditions": _add_conditions(context_pack, gates),
        "reduce_conditions": _reduce_conditions(context_pack),
        "next_review_trigger": _next_review_trigger(stale_components),
        "evidence_summary": _evidence_summary(context_pack),
        "stale_components": stale_components,
        "unresolved_questions": context_pack.get("open_questions") or [],
        "stock_card": context_pack.get("stock_card") or {},
        "context_pack": context_pack,
        "input_context_hash": context_pack.get("input_context_hash"),
        "model_name": "deterministic-v1",
    }


def _portfolio_score(context_pack: dict[str, Any]) -> dict[str, Any]:
    portfolio = context_pack.get("portfolio_exposure") or {}
    constraints = context_pack.get("user_constraints") or {}
    score = 60
    reasons = []
    if portfolio.get("status") != "ok":
        score -= 25
        reasons.append("Portfolio snapshot is missing.")
    if constraints.get("unconfirmed_defaults"):
        score -= 10
        reasons.append("Decision profile uses unconfirmed defaults.")
    if portfolio.get("target_holding"):
        score += 10
        reasons.append("Stock is already in the portfolio, so sizing can use current exposure.")
    if int(portfolio.get("position_count") or 0) > int(constraints.get("max_positions_target") or 12):
        score -= 10
        reasons.append("Portfolio position count is above target.")
    return _component(score, reasons or ["Portfolio fit is provisional."])


def _fundamental_score(context_pack: dict[str, Any]) -> dict[str, Any]:
    card = context_pack.get("stock_card") or {}
    drivers = card.get("key_drivers") or []
    risks = card.get("core_risks") or []
    score = 50 + min(len(drivers), 3) * 10
    if not risks:
        score -= 10
    if "暂无" in str(card.get("one_line_thesis") or ""):
        score -= 15
    return _component(score, [card.get("one_line_thesis") or "No thesis available."])


def _observation_score(pack: dict[str, Any] | None) -> dict[str, Any]:
    pack = pack or {}
    status = pack.get("status")
    if status == "ok":
        confidence = float(pack.get("confidence") or 0.5)
        return _component(60 + min(confidence, 1.0) * 25, [f"{pack.get('observation_type')} is fresh."])
    if status == "stale":
        return _component(40, [f"{pack.get('observation_type')} is stale."])
    return _component(35, [f"{pack.get('observation_type') or 'observation'} is missing."])


def _sector_score(context_pack: dict[str, Any]) -> dict[str, Any]:
    sector_pack = context_pack.get("sector_pack") or {}
    linked = sector_pack.get("linked_sectors") or []
    base = _observation_score(sector_pack)
    score = base["score"] + min(len(linked), 3) * 5
    reasons = base["reasons"]
    if linked:
        reasons.append("Stock has linked sector context.")
    return _component(score, reasons)


def _chip_event_score(context_pack: dict[str, Any]) -> dict[str, Any]:
    pack = context_pack.get("chip_event_pack") or {}
    constraints = context_pack.get("user_constraints") or {}
    base = _observation_score(pack)
    if not constraints.get("event_stock_allowed") and pack.get("status") != "ok":
        return _component(min(base["score"], 35), [*base["reasons"], "Event-heavy risk is not explicitly allowed."])
    return base


def _evidence_score(context_pack: dict[str, Any]) -> dict[str, Any]:
    counts = context_pack.get("graph_counts") or {}
    source_count = int(counts.get("sources") or 0)
    fact_count = int(counts.get("stock_knowledge") or 0) + int(counts.get("sector_knowledge") or 0)
    score = 35 + min(source_count, 5) * 6 + min(fact_count, 10) * 3
    if (context_pack.get("freshness_report") or {}).get("overall_status") == "missing_critical":
        score -= 15
    return _component(score, [f"{source_count} sources and {fact_count} graph facts are linked."])


def _component(score: float, reasons: list[str]) -> dict[str, Any]:
    return {"score": round(max(0.0, min(100.0, score)), 2), "reasons": reasons[:5]}


def _gate(code: str, effect: str, value: str, reason: str) -> dict[str, str]:
    return {"code": code, "effect": effect, "value": value, "reason": reason}


def _max_recommendation_from_score(score: float) -> str:
    if score >= 82:
        return "high_conviction_candidate"
    if score >= 70:
        return "normal_position"
    if score >= 58:
        return "starter"
    if score >= 45:
        return "wait"
    return "watch"


def _confidence_from_score(score: float, freshness: str | None) -> str:
    if freshness == "missing_critical" or score < 45:
        return "low"
    if freshness == "degraded" or score < 72:
        return "medium"
    return "high"


def _min_recommendation(left: str, right: str) -> str:
    return left if RECOMMENDATION_ORDER.index(left) <= RECOMMENDATION_ORDER.index(right) else right


def _min_confidence(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order[left] <= order[right] else right


def _top_reasons(context_pack: dict[str, Any], components: dict[str, Any]) -> list[str]:
    reasons = []
    card = context_pack.get("stock_card") or {}
    thesis = card.get("one_line_thesis")
    if thesis:
        reasons.append(f"Evidence card thesis: {thesis}")
    for key, component in sorted(components.items(), key=lambda item: item[1].get("score", 0), reverse=True):
        for reason in component.get("reasons") or []:
            reasons.append(f"{key}: {reason}")
            break
        if len(reasons) >= 5:
            break
    return reasons[:5]


def _veto_conditions(gates: dict[str, Any]) -> list[str]:
    vetoes = [gate["reason"] for gate in gates.get("gates") or [] if gate.get("effect") == "recommendation_cap"]
    return vetoes or ["No hard veto surfaced by deterministic gates."]


def _entry_conditions(context_pack: dict[str, Any], gates: dict[str, Any]) -> list[str]:
    conditions = []
    if gates.get("confidence") == "low":
        conditions.append("Resolve critical missing or stale inputs before considering a position.")
    if any(gate.get("code") == "stale_technical" for gate in gates.get("gates") or []):
        conditions.append("Refresh technical setup before entry.")
    if not conditions:
        conditions.append("Entry can be considered only within the suggested position range and max cap.")
    return conditions


def _add_conditions(context_pack: dict[str, Any], gates: dict[str, Any]) -> list[str]:
    return [
        "Add only after fresh portfolio, valuation, and technical packs support the same direction.",
        "Do not add beyond the max position cap or user-confirmed concentration limits.",
    ]


def _reduce_conditions(context_pack: dict[str, Any]) -> list[str]:
    card = context_pack.get("stock_card") or {}
    risks = card.get("core_risks") or []
    return risks[:3] or ["Review reduction if the thesis weakens or stale critical inputs cannot be refreshed."]


def _next_review_trigger(stale_components: list[dict[str, Any]]) -> dict[str, Any]:
    if stale_components:
        return {
            "type": "data_refresh",
            "trigger": "Refresh stale or missing components before relying on this ticket.",
            "components": [item.get("component") for item in stale_components[:5]],
        }
    return {"type": "event", "trigger": "Review when new filings, major price movement, or sector regime change appears."}


def _evidence_summary(context_pack: dict[str, Any]) -> dict[str, Any]:
    counts = context_pack.get("graph_counts") or {}
    return {
        "source_count": counts.get("sources", 0),
        "stock_fact_count": counts.get("stock_knowledge", 0),
        "sector_fact_count": counts.get("sector_knowledge", 0),
        "pending_candidate_count": (
            int(counts.get("stock_candidate_insights") or 0)
            + int(counts.get("sector_candidate_insights") or 0)
            + int(counts.get("global_candidate_insights") or 0)
        ),
        "evidence_index_count": len(context_pack.get("evidence_index") or []),
    }
