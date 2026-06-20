from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.serialization import to_jsonable


DEFAULT_PROFILE = {
    "profile_name": "default",
    "max_single_stock_position_pct": 0.06,
    "preferred_starter_position_pct": 0.02,
    "cash_reserve_min_pct": 0.10,
    "max_positions_target": 12,
    "max_positions_hard_cap": 20,
    "daily_monitoring_minutes": 30,
    "weekly_research_hours": 3.0,
    "max_theme_exposure_pct": 0.30,
    "max_market_exposure_json": {},
    "volatility_tolerance": "medium",
    "drawdown_tolerance": "medium",
    "missed_opportunity_vs_drawdown_bias": "drawdown",
    "event_stock_allowed": False,
    "source_insight_ids_json": [],
    "confirmed_by_user": False,
}


def get_active_constraint_profile(profile_name: str = "default") -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM user_constraint_profiles
            WHERE profile_name = %s
              AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (profile_name,),
        ).fetchone()
    return to_jsonable(row) if row else None


def upsert_default_constraint_profile(profile_name: str = "default") -> dict[str, Any]:
    profile = {**DEFAULT_PROFILE, "profile_name": profile_name}
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO user_constraint_profiles (
              profile_name, max_single_stock_position_pct, preferred_starter_position_pct,
              cash_reserve_min_pct, max_positions_target, max_positions_hard_cap,
              daily_monitoring_minutes, weekly_research_hours, max_theme_exposure_pct,
              max_market_exposure_json, volatility_tolerance, drawdown_tolerance,
              missed_opportunity_vs_drawdown_bias, event_stock_allowed,
              source_insight_ids_json, confirmed_by_user
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (profile_name) WHERE status = 'active' DO UPDATE SET
              updated_at = now()
            RETURNING *
            """,
            (
                profile["profile_name"],
                profile["max_single_stock_position_pct"],
                profile["preferred_starter_position_pct"],
                profile["cash_reserve_min_pct"],
                profile["max_positions_target"],
                profile["max_positions_hard_cap"],
                profile["daily_monitoring_minutes"],
                profile["weekly_research_hours"],
                profile["max_theme_exposure_pct"],
                Jsonb(profile["max_market_exposure_json"]),
                profile["volatility_tolerance"],
                profile["drawdown_tolerance"],
                profile["missed_opportunity_vs_drawdown_bias"],
                profile["event_stock_allowed"],
                Jsonb(profile["source_insight_ids_json"]),
                profile["confirmed_by_user"],
            ),
        ).fetchone()
    return to_jsonable(row)


def create_constraint_profile_change(
    field_name: str,
    new_value: Any,
    *,
    profile_id: int | None = None,
    source_channel: str | None = None,
    source_text: str | None = None,
    reason: str | None = None,
    source_candidate_insight_id: int | None = None,
) -> dict[str, Any]:
    profile = get_active_constraint_profile()
    active_profile_id = profile_id or (int(profile["id"]) if profile else None)
    old_value = profile.get(field_name) if profile and field_name in profile else None
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO user_constraint_profile_changes (
              profile_id, field_name, old_value_json, new_value_json, source_channel,
              source_text, reason, source_candidate_insight_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                active_profile_id,
                field_name,
                Jsonb(old_value),
                Jsonb(new_value),
                source_channel,
                source_text,
                reason,
                source_candidate_insight_id,
            ),
        ).fetchone()
    return to_jsonable(row)


def list_constraint_profile_changes(status: str | None = "pending", limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM user_constraint_profile_changes
            WHERE (%s::text IS NULL OR status = %s)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (status, status, limit),
        ).fetchall()
    return to_jsonable(rows)


def confirm_constraint_profile_change(change_id: int) -> dict[str, Any]:
    with transaction() as conn:
        change = conn.execute(
            """
            SELECT *
            FROM user_constraint_profile_changes
            WHERE id = %s
              AND status = 'pending'
            """,
            (change_id,),
        ).fetchone()
        if change is None:
            raise ValueError(f"pending profile change not found: {change_id}")
        if change["profile_id"] is None:
            raise ValueError(f"profile change has no profile_id: {change_id}")

        field_name = str(change["field_name"])
        if field_name not in DEFAULT_PROFILE:
            raise ValueError(f"unsupported profile field: {field_name}")

        conn.execute(
            f"""
            UPDATE user_constraint_profiles SET
              {field_name} = %s,
              confirmed_by_user = true,
              updated_at = now()
            WHERE id = %s
            """,
            (_profile_field_value(field_name, change["new_value_json"]), change["profile_id"]),
        )
        row = conn.execute(
            """
            UPDATE user_constraint_profile_changes SET
              status = 'applied',
              decided_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (change_id,),
        ).fetchone()
    return to_jsonable(row)


def reject_constraint_profile_change(change_id: int) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            UPDATE user_constraint_profile_changes SET
              status = 'rejected',
              decided_at = now()
            WHERE id = %s
              AND status = 'pending'
            RETURNING *
            """,
            (change_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"pending profile change not found: {change_id}")
    return to_jsonable(row)


def add_stock_observation(
    stock_id: int,
    observation_type: str,
    value: dict[str, Any],
    *,
    observed_at: str,
    period_start: str | None = None,
    period_end: str | None = None,
    source_id: int | None = None,
    confidence: float = 0.5,
    stale_after: str | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO stock_observations (
              stock_id, observation_type, observed_at, period_start, period_end,
              value_json, source_id, confidence, stale_after
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                stock_id,
                observation_type,
                observed_at,
                period_start,
                period_end,
                Jsonb(value),
                source_id,
                confidence,
                stale_after,
            ),
        ).fetchone()
    return to_jsonable(row)


def list_latest_observations(stock_id: int, types: list[str] | None = None) -> list[dict[str, Any]]:
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (observation_type) *
            FROM stock_observations
            WHERE stock_id = %s
              AND (%s::text[] IS NULL OR observation_type = ANY(%s))
            ORDER BY observation_type, observed_at DESC, id DESC
            """,
            (stock_id, types, types),
        ).fetchall()
    return to_jsonable(rows)


def add_inference_item(
    target_type: str,
    target_id: int | None,
    inference_type: str,
    content: str,
    *,
    supporting_source_ids: list[int] | None = None,
    supporting_knowledge_item_ids: list[int] | None = None,
    confidence: float = 0.5,
    stale_after: str | None = None,
    status: str = "candidate",
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO inference_items (
              target_type, target_id, inference_type, content,
              supporting_source_ids_json, supporting_knowledge_item_ids_json,
              confidence, stale_after, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                target_type,
                target_id,
                inference_type,
                content,
                Jsonb(supporting_source_ids or []),
                Jsonb(supporting_knowledge_item_ids or []),
                confidence,
                stale_after,
                status,
            ),
        ).fetchone()
    return to_jsonable(row)


def latest_account_snapshot(source: str = "futu") -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM account_snapshots
            WHERE source = %s
            ORDER BY snapshot_date DESC, fetched_at DESC, id DESC
            LIMIT 1
            """,
            (source,),
        ).fetchone()
    return to_jsonable(row) if row else None


def list_decisions_for_review_period(start: str, end: str) -> list[dict[str, Any]]:
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM stock_decisions
            WHERE created_at::date BETWEEN %s AND %s
            ORDER BY created_at DESC
            """,
            (start, end),
        ).fetchall()
    return to_jsonable(rows)


def save_stock_decision(ticket: dict[str, Any]) -> dict[str, Any]:
    stock = ticket["stock"]
    position = ticket.get("suggested_position") or {}
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO stock_decisions (
              stock_id, symbol, market, requested_at, decision_type, mode,
              recommendation, composite_score, confidence, freshness_status,
              suggested_initial_position_min_pct, suggested_initial_position_max_pct,
              suggested_max_position_pct, position_class, score_components_json,
              gates_json, reasons_json, veto_conditions_json, entry_conditions_json,
              add_conditions_json, reduce_conditions_json, next_review_trigger_json,
              evidence_summary_json, stale_components_json, unresolved_questions_json,
              stock_card_json, context_pack_json, input_context_hash, model_name
            )
            VALUES (
              %s, %s, %s, COALESCE(%s::timestamptz, now()), %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING *
            """,
            (
                stock["id"],
                stock["symbol"],
                stock["market"],
                ticket.get("requested_at"),
                ticket.get("decision_type", "single_stock"),
                ticket.get("mode", "focused"),
                ticket["recommendation"],
                ticket["composite_score"],
                ticket["confidence"],
                ticket["freshness_status"],
                position.get("initial_min_pct"),
                position.get("initial_max_pct"),
                position.get("max_position_pct"),
                position.get("position_class"),
                Jsonb(ticket.get("score_components") or {}),
                Jsonb(ticket.get("gates") or []),
                Jsonb(ticket.get("reasons") or []),
                Jsonb(ticket.get("veto_conditions") or []),
                Jsonb(ticket.get("entry_conditions") or []),
                Jsonb(ticket.get("add_conditions") or []),
                Jsonb(ticket.get("reduce_conditions") or []),
                Jsonb(ticket.get("next_review_trigger") or {}),
                Jsonb(ticket.get("evidence_summary") or {}),
                Jsonb(ticket.get("stale_components") or []),
                Jsonb(ticket.get("unresolved_questions") or []),
                Jsonb(ticket.get("stock_card") or {}),
                Jsonb(ticket.get("context_pack") or {}),
                ticket.get("input_context_hash"),
                ticket.get("model_name"),
            ),
        ).fetchone()
    return to_jsonable(row)


def add_decision_evidence_links(decision_id: int, links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not links:
        return []
    with transaction() as conn:
        rows = []
        for link in links:
            rows.append(
                conn.execute(
                    """
                    INSERT INTO stock_decision_evidence_links (
                      decision_id, section, component, evidence_type, evidence_id, evidence_ref
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        decision_id,
                        link.get("section"),
                        link.get("component"),
                        link.get("evidence_type"),
                        link.get("evidence_id"),
                        link.get("evidence_ref"),
                    ),
                ).fetchone()
            )
    return to_jsonable(rows)


def get_stock_decision(decision_id: int) -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM stock_decisions
            WHERE id = %s
            """,
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        links = conn.execute(
            """
            SELECT *
            FROM stock_decision_evidence_links
            WHERE decision_id = %s
            ORDER BY id ASC
            """,
            (decision_id,),
        ).fetchall()
    result = to_jsonable(row)
    result["evidence_links"] = to_jsonable(links)
    return result


def list_stock_decisions(symbol: str, market: str, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM stock_decisions
            WHERE upper(symbol) = upper(%s)
              AND upper(market) = upper(%s)
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (symbol, market, limit),
        ).fetchall()
    return to_jsonable(rows)


def set_candidate_source_metadata(
    candidate_id: int,
    *,
    source_workflow: str | None = None,
    source_object_type: str | None = None,
    source_object_id: int | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            UPDATE candidate_insights SET
              source_workflow = COALESCE(%s, source_workflow),
              source_object_type = COALESCE(%s, source_object_type),
              source_object_id = COALESCE(%s, source_object_id),
              source_metadata = COALESCE(%s, source_metadata),
              updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (
                source_workflow,
                source_object_type,
                source_object_id,
                Jsonb(source_metadata or {}),
                candidate_id,
            ),
        ).fetchone()
    if row is None:
        raise ValueError(f"candidate insight not found: {candidate_id}")
    return to_jsonable(row)


def _profile_field_value(field_name: str, value: Any) -> Any:
    if field_name in {"max_market_exposure_json", "source_insight_ids_json"}:
        return Jsonb(value)
    return value
