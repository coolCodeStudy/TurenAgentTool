from __future__ import annotations

from typing import Any

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.decision_context import build_decision_context_pack
from investment_knowledge_mcp.decision_external_data import refresh_external_decision_observations
from investment_knowledge_mcp.decision_repository import (
    add_decision_evidence_links,
    add_inference_item,
    create_constraint_profile_change,
    confirm_constraint_profile_change,
    get_active_constraint_profile,
    get_stock_decision,
    list_constraint_profile_changes,
    list_stock_decisions,
    reject_constraint_profile_change,
    save_stock_decision,
    set_candidate_source_metadata,
    upsert_default_constraint_profile,
)
from investment_knowledge_mcp.decision_scoring import build_deterministic_ticket
from investment_knowledge_mcp.decision_synthesis import generate_decision_synthesis, merge_synthesis


def decide_stock(symbol: str, market: str, mode: str = "focused", save: bool = True) -> dict[str, Any]:
    context_pack = build_decision_context_pack(symbol=symbol, market=market, mode=mode)
    refresh_result = _refresh_context_inputs(context_pack=context_pack, mode=mode)
    if refresh_result.get("refreshed"):
        context_pack = build_decision_context_pack(symbol=symbol, market=market, mode=mode)
    context_pack["external_refresh_result"] = refresh_result
    ticket = build_deterministic_ticket(context_pack)
    synthesis = generate_decision_synthesis(context_pack, ticket)
    ticket = merge_synthesis(ticket, synthesis)

    if not save:
        return ticket

    saved = save_stock_decision(ticket)
    decision_id = int(saved["id"])
    evidence_links = _evidence_links_from_context(context_pack)
    links = add_decision_evidence_links(decision_id, evidence_links)
    _persist_inferences(ticket, decision_id)
    candidates = _persist_candidate_proposals(ticket, decision_id, symbol=symbol, market=market)

    result = {**ticket, "id": decision_id, "saved_decision": saved, "evidence_links": links}
    if candidates:
        result["candidate_insight_rows"] = candidates
    return result


def get_decision_detail(decision_id: int) -> dict[str, Any] | None:
    return get_stock_decision(decision_id)


def get_latest_decision_detail(symbol: str, market: str) -> dict[str, Any] | None:
    decisions = list_stock_decisions(symbol=symbol, market=market, limit=1)
    if not decisions:
        return None
    return get_stock_decision(int(decisions[0]["id"]))


def list_decision_history(symbol: str, market: str, limit: int = 20) -> list[dict[str, Any]]:
    return list_stock_decisions(symbol=symbol, market=market, limit=limit)


def refresh_decision_data(symbol: str, market: str, mode: str = "focused") -> dict[str, Any]:
    context_pack = build_decision_context_pack(symbol=symbol, market=market, mode=mode)
    refresh_result = _refresh_context_inputs(context_pack=context_pack, mode=mode)
    if refresh_result.get("refreshed"):
        context_pack = build_decision_context_pack(symbol=symbol, market=market, mode=mode)
    return {
        "symbol": context_pack["stock"]["symbol"],
        "market": context_pack["stock"]["market"],
        "mode": mode,
        "input_context_hash": context_pack.get("input_context_hash"),
        "freshness_report": context_pack.get("freshness_report"),
        "open_questions": context_pack.get("open_questions") or [],
        "external_refresh_result": refresh_result,
    }


def get_decision_profile() -> dict[str, Any]:
    profile = get_active_constraint_profile() or upsert_default_constraint_profile()
    return {"profile": profile, "pending_changes": list_constraint_profile_changes(status="pending", limit=20)}


def propose_decision_profile_change(
    field_name: str,
    value: Any,
    *,
    reason: str | None = None,
    source_text: str | None = None,
    source_channel: str = "command",
) -> dict[str, Any]:
    profile = get_active_constraint_profile() or upsert_default_constraint_profile()
    return create_constraint_profile_change(
        field_name=field_name,
        new_value=value,
        profile_id=int(profile["id"]),
        source_channel=source_channel,
        source_text=source_text,
        reason=reason,
    )


def confirm_decision_profile_change(change_id: int) -> dict[str, Any]:
    return confirm_constraint_profile_change(change_id)


def reject_decision_profile_change(change_id: int) -> dict[str, Any]:
    return reject_constraint_profile_change(change_id)


def _evidence_links_from_context(context_pack: dict[str, Any]) -> list[dict[str, Any]]:
    links = []
    for item in context_pack.get("evidence_index") or []:
        links.append(
            {
                "section": "evidence_summary",
                "component": item.get("component"),
                "evidence_type": item.get("evidence_type"),
                "evidence_id": item.get("evidence_id") if isinstance(item.get("evidence_id"), int) else None,
                "evidence_ref": item.get("summary"),
            }
        )
    return links[:100]


def _persist_inferences(ticket: dict[str, Any], decision_id: int) -> None:
    stock = ticket.get("stock") or {}
    for item in ticket.get("model_inferences") or []:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        add_inference_item(
            target_type="stock",
            target_id=stock.get("id"),
            inference_type=str(item.get("type") or "decision_synthesis"),
            content=content,
            confidence=float(item.get("confidence") or 0.5),
            status="candidate",
        )


def _persist_candidate_proposals(
    ticket: dict[str, Any],
    decision_id: int,
    *,
    symbol: str,
    market: str,
) -> list[dict[str, Any]]:
    rows = []
    for item in ticket.get("candidate_insight_proposals") or []:
        target_type = str(item.get("target_type") or "strategy").strip().lower()
        if target_type not in {"stock", "portfolio", "strategy"}:
            target_type = "strategy"
        insight = str(item.get("insight") or "").strip()
        if not insight:
            continue
        row = repository.propose_candidate_insight(
            target_type=target_type,
            symbol=symbol if target_type == "stock" else None,
            market=market if target_type == "stock" else None,
            insight=insight,
            normalized_summary=item.get("normalized_summary"),
            tags=["decision-system"],
            reason=item.get("reason") or f"Proposed by stock decision #{decision_id}.",
        )
        row = set_candidate_source_metadata(
            int(row["id"]),
            source_workflow="decision",
            source_object_type="stock_decision",
            source_object_id=decision_id,
            source_metadata={"symbol": symbol, "market": market},
        )
        rows.append(row)
    return rows


def _refresh_context_inputs(context_pack: dict[str, Any], mode: str) -> dict[str, Any]:
    try:
        return refresh_external_decision_observations(stock=context_pack["stock"], mode=mode)
    except Exception as exc:
        return {
            "mode": mode,
            "refreshed": [],
            "diagnostics": [
                {
                    "provider": "external_adapter_ladder",
                    "ok": False,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            ],
        }
