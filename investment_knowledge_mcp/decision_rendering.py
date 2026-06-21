from __future__ import annotations

from typing import Any


RECOMMENDATION_LABELS = {
    "avoid": "avoid",
    "watch": "watch",
    "wait": "wait",
    "starter": "starter",
    "normal_position": "normal position",
    "high_conviction_candidate": "high-conviction candidate",
    "review_existing_holding": "review existing holding",
    "trim": "trim",
    "reduce": "reduce",
}


def render_decision_ticket(ticket: dict[str, Any]) -> str:
    normalized = _normalize_ticket(ticket)
    stock = normalized["stock"]
    position = normalized.get("suggested_position") or {}
    lines = [
        f"{stock.get('symbol')} {stock.get('market')} Decision Ticket",
        f"Recommendation: {RECOMMENDATION_LABELS.get(normalized.get('recommendation'), normalized.get('recommendation'))}",
        f"Composite score: {_fmt_score(normalized.get('composite_score'))}",
        f"Confidence: {normalized.get('confidence')} | Freshness: {normalized.get('freshness_status')}",
        "",
        "Suggested position:",
        f"- Initial range: {_fmt_range(position.get('initial_min_pct'), position.get('initial_max_pct'))}",
        f"- Max cap: {_fmt_pct(position.get('max_position_pct'))}",
        f"- Position class: {position.get('position_class') or 'n/a'}",
        "",
        "Sub-scores:",
    ]
    for key, component in (normalized.get("score_components") or {}).items():
        lines.append(f"- {key}: {_fmt_score(component.get('score'))}")
    lines.extend(["", "Why:"])
    lines.extend(_bullets(normalized.get("reasons") or []))
    lines.extend(["", "Veto conditions:"])
    lines.extend(_bullets(normalized.get("veto_conditions") or []))
    lines.extend(["", "Entry conditions:"])
    lines.extend(_bullets(normalized.get("entry_conditions") or []))
    lines.extend(["", "Add conditions:"])
    lines.extend(_bullets(normalized.get("add_conditions") or []))
    lines.extend(["", "Reduce/exit review conditions:"])
    lines.extend(_bullets(normalized.get("reduce_conditions") or []))
    review = normalized.get("next_review_trigger") or {}
    lines.extend(["", "Next review:", f"- {review.get('trigger') or 'Review when new material information appears.'}"])
    evidence = normalized.get("evidence_summary") or {}
    lines.extend(
        [
            "",
            "Evidence:",
            f"- Sources: {evidence.get('source_count', 0)}",
            f"- Facts: {int(evidence.get('stock_fact_count') or 0) + int(evidence.get('sector_fact_count') or 0)}",
            f"- Pending candidate insights: {evidence.get('pending_candidate_count', 0)}",
            f"- Unresolved questions: {len(normalized.get('unresolved_questions') or [])}",
        ]
    )
    return "\n".join(lines)


def render_decision_detail(ticket: dict[str, Any]) -> str:
    normalized = _normalize_ticket(ticket)
    lines = [render_decision_ticket(normalized), "", "Score component evidence:"]
    for key, component in (normalized.get("score_components") or {}).items():
        lines.append(f"- {key}: {_fmt_score(component.get('score'))}")
        for reason in component.get("reasons") or []:
            lines.append(f"  - {reason}")
    lines.extend(["", "Gates:"])
    gates = normalized.get("gates") or []
    if gates:
        for gate in gates:
            lines.append(f"- {gate.get('code')}: {gate.get('effect')}={gate.get('value')} ({gate.get('reason')})")
    else:
        lines.append("- No deterministic gate fired.")
    lines.extend(["", "Stale or missing components:"])
    stale = normalized.get("stale_components") or []
    if stale:
        for item in stale:
            lines.append(f"- {item.get('component')}: {item.get('status')} - {item.get('reason')}")
    else:
        lines.append("- None.")
    diagnostics = ((normalized.get("context_pack") or {}).get("external_refresh_result") or {}).get("diagnostics") or []
    if diagnostics:
        lines.extend(["", "Provider diagnostics:"])
        for item in diagnostics[:20]:
            lines.append(
                f"- {item.get('provider')} {item.get('provider_symbol') or ''}: "
                f"{'ok' if item.get('ok') else 'failed'} - {item.get('message')}"
            )
    links = normalized.get("evidence_links") or []
    if links:
        lines.extend(["", "Evidence links:"])
        for link in links[:40]:
            lines.append(
                f"- {link.get('section')} / {link.get('component') or '-'}: "
                f"{link.get('evidence_type')}:{link.get('evidence_id') or link.get('evidence_ref') or '-'}"
            )
    return "\n".join(lines)


def render_decision_history(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return "No saved decision tickets found."
    lines = ["Decision history:"]
    for item in decisions:
        lines.append(
            f"- #{item.get('id')} {item.get('symbol')} {item.get('market')} "
            f"{item.get('recommendation')} score={_fmt_score(item.get('composite_score'))} "
            f"confidence={item.get('confidence')} freshness={item.get('freshness_status')} "
            f"created={item.get('created_at')}"
        )
    return "\n".join(lines)


def render_decision_profile(profile: dict[str, Any] | None, pending_changes: list[dict[str, Any]] | None = None) -> str:
    if not profile:
        return "No active decision profile found."
    lines = [
        f"Decision profile: {profile.get('profile_name')} #{profile.get('id')}",
        f"Confirmed by user: {profile.get('confirmed_by_user')}",
        f"- Max single stock: {_fmt_pct(profile.get('max_single_stock_position_pct'))}",
        f"- Preferred starter: {_fmt_pct(profile.get('preferred_starter_position_pct'))}",
        f"- Cash reserve min: {_fmt_pct(profile.get('cash_reserve_min_pct'))}",
        f"- Max theme exposure: {_fmt_pct(profile.get('max_theme_exposure_pct'))}",
        f"- Position target / hard cap: {profile.get('max_positions_target')} / {profile.get('max_positions_hard_cap')}",
        f"- Monitoring time: {profile.get('daily_monitoring_minutes')} min/day, {profile.get('weekly_research_hours')} h/week",
        f"- Volatility / drawdown tolerance: {profile.get('volatility_tolerance')} / {profile.get('drawdown_tolerance')}",
        f"- Event stock allowed: {profile.get('event_stock_allowed')}",
    ]
    if pending_changes:
        lines.extend(["", "Pending profile changes:"])
        for change in pending_changes:
            lines.append(f"- #{change.get('id')} {change.get('field_name')} -> {change.get('new_value_json')}")
    return "\n".join(lines)


def _normalize_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    if "score_components" in ticket:
        return ticket
    stock = {"id": ticket.get("stock_id"), "symbol": ticket.get("symbol"), "market": ticket.get("market")}
    return {
        "id": ticket.get("id"),
        "stock": stock,
        "recommendation": ticket.get("recommendation"),
        "composite_score": ticket.get("composite_score"),
        "confidence": ticket.get("confidence"),
        "freshness_status": ticket.get("freshness_status"),
        "suggested_position": {
            "initial_min_pct": ticket.get("suggested_initial_position_min_pct"),
            "initial_max_pct": ticket.get("suggested_initial_position_max_pct"),
            "max_position_pct": ticket.get("suggested_max_position_pct"),
            "position_class": ticket.get("position_class"),
        },
        "score_components": ticket.get("score_components_json") or {},
        "gates": ticket.get("gates_json") or [],
        "reasons": ticket.get("reasons_json") or [],
        "veto_conditions": ticket.get("veto_conditions_json") or [],
        "entry_conditions": ticket.get("entry_conditions_json") or [],
        "add_conditions": ticket.get("add_conditions_json") or [],
        "reduce_conditions": ticket.get("reduce_conditions_json") or [],
        "next_review_trigger": ticket.get("next_review_trigger_json") or {},
        "evidence_summary": ticket.get("evidence_summary_json") or {},
        "stale_components": ticket.get("stale_components_json") or [],
        "unresolved_questions": ticket.get("unresolved_questions_json") or [],
        "context_pack": ticket.get("context_pack_json") or {},
        "evidence_links": ticket.get("evidence_links") or [],
    }


def _bullets(items: list[Any]) -> list[str]:
    if not items:
        return ["- None."]
    return [f"- {item}" for item in items[:8]]


def _fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.1f}/100"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_range(min_value: Any, max_value: Any) -> str:
    if min_value is None or max_value is None:
        return "n/a"
    return f"{_fmt_pct(min_value)}-{_fmt_pct(max_value)}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"
