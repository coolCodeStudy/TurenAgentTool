from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.serialization import to_jsonable


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_market(market: str) -> str:
    return market.strip().upper()


def upsert_stock_profile(
    symbol: str,
    market: str,
    name: str | None = None,
    core_business: str | None = None,
    equity_structure: str | None = None,
    stock_character: str | None = None,
    notable_history: str | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO stocks (
              symbol, market, name, core_business, equity_structure,
              stock_character, notable_history
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, market) DO UPDATE SET
              name = COALESCE(EXCLUDED.name, stocks.name),
              core_business = COALESCE(EXCLUDED.core_business, stocks.core_business),
              equity_structure = COALESCE(EXCLUDED.equity_structure, stocks.equity_structure),
              stock_character = COALESCE(EXCLUDED.stock_character, stocks.stock_character),
              notable_history = COALESCE(EXCLUDED.notable_history, stocks.notable_history),
              updated_at = now()
            RETURNING *
            """,
            (
                _normalize_symbol(symbol),
                _normalize_market(market),
                name,
                core_business,
                equity_structure,
                stock_character,
                notable_history,
            ),
        ).fetchone()
    return to_jsonable(row)


def upsert_sector_tree(
    path: list[str],
    description: str | None = None,
    recent_status: str | None = None,
) -> dict[str, Any]:
    if not path:
        raise ValueError("path must contain at least one sector name")

    cleaned_path = [item.strip() for item in path if item and item.strip()]
    if not cleaned_path:
        raise ValueError("path must contain at least one non-empty sector name")

    with transaction() as conn:
        parent_id: int | None = None
        nodes: list[dict[str, Any]] = []

        for index, name in enumerate(cleaned_path):
            is_leaf = index == len(cleaned_path) - 1
            row = _get_sector(conn, name, parent_id)
            if row is None:
                row = conn.execute(
                    """
                    INSERT INTO sectors (name, parent_id, description, recent_status)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        name,
                        parent_id,
                        description if is_leaf else None,
                        recent_status if is_leaf else None,
                    ),
                ).fetchone()
            elif is_leaf and (description is not None or recent_status is not None):
                row = conn.execute(
                    """
                    UPDATE sectors SET
                      description = COALESCE(%s, description),
                      recent_status = COALESCE(%s, recent_status),
                      updated_at = now()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (description, recent_status, row["id"]),
                ).fetchone()

            nodes.append(row)
            parent_id = row["id"]

    return to_jsonable({"leaf": nodes[-1], "path": nodes})


def _get_sector(conn: Connection, name: str, parent_id: int | None) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT *
        FROM sectors
        WHERE name = %s
          AND parent_id IS NOT DISTINCT FROM %s
        """,
        (name, parent_id),
    ).fetchone()


def _get_sector_by_path_in_conn(
    conn: Connection,
    path: list[str],
) -> dict[str, Any] | None:
    cleaned_path = [item.strip() for item in path if item and item.strip()]
    if not cleaned_path:
        raise ValueError("sector path must contain at least one non-empty sector name")

    parent_id: int | None = None
    row: dict[str, Any] | None = None
    for name in cleaned_path:
        row = _get_sector(conn, name, parent_id)
        if row is None:
            return None
        parent_id = row["id"]
    return row


def link_stock_to_sector(
    stock_id: int,
    sector_id: int,
    relation_type: str = "related",
    confidence: float = 0.5,
    source_id: int | None = None,
    confirmed_by_user: bool = False,
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO stock_sector_relations (
              stock_id, sector_id, relation_type, confidence, source_id, confirmed_by_user
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_id, sector_id, relation_type) DO UPDATE SET
              confidence = EXCLUDED.confidence,
              source_id = COALESCE(EXCLUDED.source_id, stock_sector_relations.source_id),
              confirmed_by_user = EXCLUDED.confirmed_by_user
            RETURNING *
            """,
            (stock_id, sector_id, relation_type, confidence, source_id, confirmed_by_user),
        ).fetchone()
    return to_jsonable(row)


def add_source(
    source_type: str,
    title: str | None = None,
    url: str | None = None,
    publisher: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = _upsert_source(
            conn=conn,
            source_type=source_type,
            title=title,
            url=url,
            publisher=publisher,
            published_at=published_at,
        )
    return to_jsonable(row)


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _upsert_source(
    conn: Connection,
    source_type: str,
    title: str | None = None,
    url: str | None = None,
    publisher: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    source_type = source_type.strip()
    title = _clean_optional_text(title)
    url = _clean_optional_text(url)
    publisher = _clean_optional_text(publisher)

    existing = _find_source(
        conn=conn,
        source_type=source_type,
        title=title,
        url=url,
        publisher=publisher,
    )
    if existing is not None:
        return conn.execute(
            """
            UPDATE sources SET
              title = COALESCE(sources.title, %s),
              publisher = COALESCE(sources.publisher, %s),
              published_at = COALESCE(sources.published_at, %s)
            WHERE id = %s
            RETURNING *
            """,
            (title, publisher, published_at, existing["id"]),
        ).fetchone()

    return conn.execute(
        """
        INSERT INTO sources (source_type, title, url, publisher, published_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (source_type, title, url, publisher, published_at),
    ).fetchone()


def _find_source(
    conn: Connection,
    source_type: str,
    title: str | None,
    url: str | None,
    publisher: str | None,
) -> dict[str, Any] | None:
    if url:
        return conn.execute(
            """
            SELECT *
            FROM sources
            WHERE url = %s
            ORDER BY id
            LIMIT 1
            """,
            (url,),
        ).fetchone()

    if title:
        return conn.execute(
            """
            SELECT *
            FROM sources
            WHERE source_type = %s
              AND title = %s
              AND publisher IS NOT DISTINCT FROM %s
            ORDER BY id
            LIMIT 1
            """,
            (source_type, title, publisher),
        ).fetchone()

    return None


def add_knowledge_item(
    target_type: str,
    target_id: int | None,
    knowledge_type: str,
    content: str,
    source_id: int | None = None,
    confidence: float = 0.5,
    confirmed_by_user: bool = False,
    stale_after: str | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = _add_knowledge_item_in_conn(
            conn=conn,
            target_type=target_type,
            target_id=target_id,
            knowledge_type=knowledge_type,
            content=content,
            source_id=source_id,
            confidence=confidence,
            confirmed_by_user=confirmed_by_user,
            stale_after=stale_after,
        )
    return to_jsonable(row)


def add_user_insight(
    target_type: str,
    target_id: int | None,
    insight: str,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = _add_user_insight_in_conn(
            conn=conn,
            target_type=target_type,
            target_id=target_id,
            insight=insight,
            normalized_summary=normalized_summary,
            tags=tags,
        )
    return to_jsonable(row)


def record_user_insight(
    target_type: str,
    insight: str,
    target_id: int | None = None,
    symbol: str | None = None,
    market: str | None = None,
    sector_path: list[str] | None = None,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    target_type = target_type.strip().lower()

    with transaction() as conn:
        resolved_target_id = _resolve_insight_target_in_conn(
            conn=conn,
            target_type=target_type,
            target_id=target_id,
            symbol=symbol,
            market=market,
            sector_path=sector_path,
        )
        row = _add_user_insight_in_conn(
            conn=conn,
            target_type=target_type,
            target_id=resolved_target_id,
            insight=insight,
            normalized_summary=normalized_summary,
            tags=tags,
        )

    return to_jsonable(row)


def propose_candidate_insight(
    target_type: str,
    insight: str,
    target_id: int | None = None,
    symbol: str | None = None,
    market: str | None = None,
    sector_path: list[str] | None = None,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    target_type = target_type.strip().lower()

    with transaction() as conn:
        resolved_target_id = _resolve_insight_target_in_conn(
            conn=conn,
            target_type=target_type,
            target_id=target_id,
            symbol=symbol,
            market=market,
            sector_path=sector_path,
        )
        row = _upsert_candidate_insight_in_conn(
            conn=conn,
            target_type=target_type,
            target_id=resolved_target_id,
            insight=insight,
            normalized_summary=normalized_summary,
            tags=tags,
            reason=reason,
        )

    return to_jsonable(row)


def list_candidate_insights(
    status: str | None = "pending",
    target_type: str | None = None,
) -> list[dict[str, Any]]:
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM candidate_insights
            WHERE (%s::text IS NULL OR status = %s)
              AND (%s::text IS NULL OR target_type = %s)
            ORDER BY created_at DESC
            """,
            (status, status, target_type, target_type),
        ).fetchall()
    return to_jsonable(rows)


def confirm_candidate_insight(candidate_id: int) -> dict[str, Any]:
    with transaction() as conn:
        candidate = _get_candidate_insight_in_conn(conn, candidate_id)
        if candidate is None:
            raise ValueError(f"candidate insight not found: {candidate_id}")

        insight = _add_user_insight_in_conn(
            conn=conn,
            target_type=candidate["target_type"],
            target_id=candidate["target_id"],
            insight=candidate["insight"],
            normalized_summary=candidate.get("normalized_summary"),
            tags=candidate.get("tags") or [],
        )
        updated_candidate = conn.execute(
            """
            UPDATE candidate_insights SET
              status = 'confirmed',
              confirmed_insight_id = %s,
              updated_at = now(),
              decided_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (insight["id"], candidate_id),
        ).fetchone()

    return to_jsonable({"candidate": updated_candidate, "user_insight": insight})


def reject_candidate_insight(candidate_id: int) -> dict[str, Any]:
    with transaction() as conn:
        candidate = _get_candidate_insight_in_conn(conn, candidate_id)
        if candidate is None:
            raise ValueError(f"candidate insight not found: {candidate_id}")
        row = conn.execute(
            """
            UPDATE candidate_insights SET
              status = 'rejected',
              updated_at = now(),
              decided_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (candidate_id,),
        ).fetchone()
    return to_jsonable(row)


def record_command_event(
    command: str,
    ok: bool,
    message: str,
    source: str | None = None,
    sender: str | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO command_events (source, sender, command, ok, message)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (source, sender, command, ok, message),
        ).fetchone()
    return to_jsonable(row)


def create_coding_task(
    title: str,
    description: str | None = None,
    priority: str = "normal",
    labels: list[str] | None = None,
    source: str | None = None,
    sender: str | None = None,
) -> dict[str, Any]:
    cleaned_title = title.strip()
    if not cleaned_title:
        raise ValueError("title is required")

    cleaned_description = (description or cleaned_title).strip()
    cleaned_priority = priority.strip().lower()
    if cleaned_priority not in {"low", "normal", "high"}:
        cleaned_priority = "normal"

    cleaned_labels = [item.strip() for item in labels or [] if item and item.strip()]

    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO coding_tasks (
              title, description, priority, labels, source, sender
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                cleaned_title,
                cleaned_description,
                cleaned_priority,
                Jsonb(cleaned_labels),
                source,
                sender,
            ),
        ).fetchone()
    return to_jsonable(row)


def list_coding_tasks(status: str | None = "pending", limit: int = 10) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 50))
    with transaction() as conn:
        if status is None or status == "all":
            rows = conn.execute(
                """
                SELECT *
                FROM coding_tasks
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM coding_tasks
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (status, limit),
            ).fetchall()
    return to_jsonable(rows)


def get_coding_task(task_id: int) -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM coding_tasks
            WHERE id = %s
            """,
            (task_id,),
        ).fetchone()
    return to_jsonable(row) if row else None


def claim_next_coding_task(worker_name: str = "codex-worker") -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            """
            WITH next_task AS (
              SELECT id
              FROM coding_tasks
              WHERE status IN ('pending', 'accepted')
              ORDER BY
                CASE priority
                  WHEN 'high' THEN 0
                  WHEN 'normal' THEN 1
                  ELSE 2
                END,
                created_at ASC
              LIMIT 1
              FOR UPDATE SKIP LOCKED
            )
            UPDATE coding_tasks AS task SET
              status = 'running',
              worker_started_at = COALESCE(worker_started_at, now()),
              updated_at = now(),
              worker_log = concat_ws(E'\n', NULLIF(worker_log, ''), %s::text)
            FROM next_task
            WHERE task.id = next_task.id
            RETURNING task.*
            """,
            (f"{worker_name}: claimed task",),
        ).fetchone()
    return to_jsonable(row) if row else None


def update_coding_task(
    task_id: int,
    status: str,
    result: str | None = None,
    branch_name: str | None = None,
    commit_sha: str | None = None,
    worker_log: str | None = None,
    linked_issue_url: str | None = None,
) -> dict[str, Any]:
    if status not in {"pending", "accepted", "running", "needs_user", "done", "rejected", "cancelled"}:
        raise ValueError(f"invalid coding task status: {status}")

    with transaction() as conn:
        row = conn.execute(
            """
            UPDATE coding_tasks SET
              status = %s,
              result = COALESCE(%s, result),
              branch_name = COALESCE(%s, branch_name),
              commit_sha = COALESCE(%s, commit_sha),
              linked_issue_url = COALESCE(%s, linked_issue_url),
              worker_log = concat_ws(E'\n', NULLIF(worker_log, ''), NULLIF(%s::text, '')),
              worker_finished_at = CASE
                WHEN %s IN ('done', 'needs_user', 'rejected', 'cancelled') THEN now()
                ELSE worker_finished_at
              END,
              updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (
                status,
                result,
                branch_name,
                commit_sha,
                linked_issue_url,
                worker_log,
                status,
                task_id,
            ),
        ).fetchone()

    if row is None:
        raise ValueError(f"coding task not found: {task_id}")
    return to_jsonable(row)


def upsert_account_snapshot(
    snapshot_date: str,
    account_info: dict[str, Any] | None,
    positions: list[dict[str, Any]] | None,
    fx_rates: dict[str, Any] | None,
    fetched_at: str,
    metadata: dict[str, Any] | None = None,
    source: str = "futu",
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO account_snapshots (
              snapshot_date, source, account_info, positions, fx_rates, metadata, fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_date, source) DO UPDATE SET
              account_info = EXCLUDED.account_info,
              positions = EXCLUDED.positions,
              fx_rates = EXCLUDED.fx_rates,
              metadata = EXCLUDED.metadata,
              fetched_at = EXCLUDED.fetched_at,
              updated_at = now()
            RETURNING *
            """,
            (
                snapshot_date,
                source,
                Jsonb(account_info or {}),
                Jsonb(positions or []),
                Jsonb(fx_rates or {}),
                Jsonb(metadata or {}),
                fetched_at,
            ),
        ).fetchone()
    return to_jsonable(row)


def list_account_snapshots(
    start: str,
    end: str,
    source: str = "futu",
) -> list[dict[str, Any]]:
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM account_snapshots
            WHERE source = %s
              AND snapshot_date BETWEEN %s AND %s
            ORDER BY snapshot_date ASC
            """,
            (source, start, end),
        ).fetchall()
    return to_jsonable(rows)


def upsert_trade_records(
    deals: list[dict[str, Any]],
    source: str = "futu",
) -> dict[str, Any]:
    inserted_or_updated = 0
    with transaction() as conn:
        for deal in deals:
            normalized = _normalize_trade_record(deal)
            conn.execute(
                """
                INSERT INTO trade_records (
                  source, record_key, deal_id, order_id, code, stock_name, trd_side,
                  qty, price, amount, currency, create_time, trade_date, raw, synced_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (source, record_key) DO UPDATE SET
                  deal_id = EXCLUDED.deal_id,
                  order_id = EXCLUDED.order_id,
                  code = EXCLUDED.code,
                  stock_name = EXCLUDED.stock_name,
                  trd_side = EXCLUDED.trd_side,
                  qty = EXCLUDED.qty,
                  price = EXCLUDED.price,
                  amount = EXCLUDED.amount,
                  currency = EXCLUDED.currency,
                  create_time = EXCLUDED.create_time,
                  trade_date = EXCLUDED.trade_date,
                  raw = EXCLUDED.raw,
                  synced_at = now(),
                  updated_at = now()
                """,
                (
                    source,
                    normalized["record_key"],
                    normalized["deal_id"],
                    normalized["order_id"],
                    normalized["code"],
                    normalized["stock_name"],
                    normalized["trd_side"],
                    normalized["qty"],
                    normalized["price"],
                    normalized["amount"],
                    normalized["currency"],
                    normalized["create_time"],
                    normalized["trade_date"],
                    Jsonb(normalized["raw"]),
                ),
            )
            inserted_or_updated += 1

    return {"synced_count": inserted_or_updated}


def count_trade_records(
    start: str,
    end: str,
    source: str = "futu",
) -> int:
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT count(*) AS count
            FROM trade_records
            WHERE source = %s
              AND trade_date BETWEEN %s AND %s
            """,
            (source, start, end),
        ).fetchone()
    return int(row["count"] if row else 0)


def _normalize_trade_record(deal: dict[str, Any]) -> dict[str, Any]:
    create_time = _clean_optional_text(str(deal.get("create_time") or "")) if deal.get("create_time") is not None else None
    deal_id = _clean_optional_text(str(deal.get("deal_id") or "")) if deal.get("deal_id") is not None else None
    order_id = _clean_optional_text(str(deal.get("order_id") or "")) if deal.get("order_id") is not None else None
    code = _clean_optional_text(str(deal.get("code") or "")) if deal.get("code") is not None else None
    record_key = deal_id or "|".join(
        [
            str(order_id or ""),
            str(code or ""),
            str(deal.get("trd_side") or ""),
            str(deal.get("qty") or ""),
            str(deal.get("price") or ""),
            str(create_time or ""),
        ]
    )
    return {
        "record_key": record_key,
        "deal_id": deal_id,
        "order_id": order_id,
        "code": code,
        "stock_name": _clean_optional_text(str(deal.get("stock_name") or "")) if deal.get("stock_name") is not None else None,
        "trd_side": _clean_optional_text(str(deal.get("trd_side") or "")) if deal.get("trd_side") is not None else None,
        "qty": _optional_number(deal.get("qty")),
        "price": _optional_number(deal.get("price")),
        "amount": _optional_number(deal.get("amount")),
        "currency": _clean_optional_text(str(deal.get("currency") or "")) if deal.get("currency") is not None else None,
        "create_time": create_time,
        "trade_date": _date_from_text(create_time),
        "raw": deal.get("raw") if isinstance(deal.get("raw"), dict) else deal,
    }


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_from_text(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if len(text) < 10:
        return None
    return text[:10].replace("/", "-")


def retry_coding_task(task_id: int, worker_log: str | None = None) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            UPDATE coding_tasks SET
              status = 'pending',
              worker_started_at = NULL,
              worker_finished_at = NULL,
              result = NULL,
              worker_log = concat_ws(E'\n', NULLIF(worker_log, ''), NULLIF(%s::text, '')),
              updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (worker_log, task_id),
        ).fetchone()

    if row is None:
        raise ValueError(f"coding task not found: {task_id}")
    return to_jsonable(row)


def upsert_worker_status(
    name: str,
    status: str,
    last_error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("worker name is required")

    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO worker_status (name, status, last_seen_at, last_error, metadata, updated_at)
            VALUES (%s, %s, now(), %s, %s, now())
            ON CONFLICT (name) DO UPDATE SET
              status = EXCLUDED.status,
              last_seen_at = now(),
              last_error = EXCLUDED.last_error,
              metadata = EXCLUDED.metadata,
              updated_at = now()
            RETURNING *
            """,
            (cleaned_name, status, last_error, Jsonb(metadata or {})),
        ).fetchone()
    return to_jsonable(row)


def list_worker_status() -> list[dict[str, Any]]:
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM worker_status
            ORDER BY last_seen_at DESC
            """
        ).fetchall()
    return to_jsonable(rows)


def _resolve_insight_target_in_conn(
    conn: Connection,
    target_type: str,
    target_id: int | None = None,
    symbol: str | None = None,
    market: str | None = None,
    sector_path: list[str] | None = None,
) -> int | None:
    if target_type == "stock":
        if target_id is not None:
            return target_id
        if not symbol or not market:
            raise ValueError("symbol and market are required when target_type is stock")
        stock = _get_stock_in_conn(conn, symbol=symbol, market=market)
        if stock is None:
            raise ValueError(f"stock not found: {symbol} {market}")
        return stock["id"]

    if target_type == "sector":
        if target_id is not None:
            return target_id
        if not sector_path:
            raise ValueError("sector_path is required when target_type is sector")
        sector = _get_sector_by_path_in_conn(conn, sector_path)
        if sector is None:
            raise ValueError(f"sector path not found: {' > '.join(sector_path)}")
        return sector["id"]

    if target_type in {"portfolio", "strategy"}:
        return None

    if target_id is None:
        raise ValueError(
            "target_id is required for custom target types; known target types are "
            "stock, sector, portfolio, and strategy"
        )
    return target_id


def import_stock_research_draft(
    draft: dict[str, Any],
    confirmed_by_user: bool = False,
) -> dict[str, Any]:
    stock_input = draft.get("stock") or {}
    symbol = stock_input.get("symbol")
    market = stock_input.get("market")
    if not symbol or not market:
        raise ValueError("draft.stock.symbol and draft.stock.market are required")

    source_id_by_key: dict[str, int] = {}

    with transaction() as conn:
        stock = _upsert_stock_profile_in_conn(
            conn=conn,
            symbol=symbol,
            market=market,
            name=stock_input.get("name"),
            core_business=stock_input.get("core_business"),
            equity_structure=stock_input.get("equity_structure"),
            stock_character=stock_input.get("stock_character"),
            notable_history=stock_input.get("notable_history"),
        )

        sources: list[dict[str, Any]] = []
        for index, source_input in enumerate(draft.get("sources") or []):
            source = _upsert_source(
                conn=conn,
                source_type=source_input.get("source_type", "model"),
                title=source_input.get("title"),
                url=source_input.get("url"),
                publisher=source_input.get("publisher"),
                published_at=source_input.get("published_at"),
            )
            key = source_input.get("key") or str(index)
            source_id_by_key[key] = source["id"]
            sources.append(source)

        sectors: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        for sector_input in draft.get("sectors") or []:
            sector_tree = _upsert_sector_tree_in_conn(
                conn=conn,
                path=sector_input.get("path") or [],
                description=sector_input.get("description"),
                recent_status=sector_input.get("recent_status"),
            )
            relation = _link_stock_to_sector_in_conn(
                conn=conn,
                stock_id=stock["id"],
                sector_id=sector_tree["leaf"]["id"],
                relation_type=sector_input.get("relation_type", "related"),
                confidence=sector_input.get("confidence", 0.5),
                source_id=_resolve_source_id(sector_input, source_id_by_key),
                confirmed_by_user=confirmed_by_user,
            )
            sectors.append(sector_tree)
            relations.append(relation)

        knowledge_items: list[dict[str, Any]] = []
        for item_input in draft.get("knowledge_items") or []:
            knowledge_items.append(
                _add_knowledge_item_in_conn(
                    conn=conn,
                    target_type="stock",
                    target_id=stock["id"],
                    knowledge_type=item_input["knowledge_type"],
                    content=item_input["content"],
                    source_id=_resolve_source_id(item_input, source_id_by_key),
                    confidence=item_input.get("confidence", 0.5),
                    confirmed_by_user=confirmed_by_user,
                    stale_after=item_input.get("stale_after"),
                )
            )

        user_insights: list[dict[str, Any]] = []
        for insight_input in draft.get("user_insights") or []:
            user_insights.append(
                _add_user_insight_in_conn(
                    conn=conn,
                    target_type="stock",
                    target_id=stock["id"],
                    insight=insight_input["insight"],
                    normalized_summary=insight_input.get("normalized_summary"),
                    tags=insight_input.get("tags") or [],
                )
            )

    search_result = search_stock(symbol=symbol, market=market)
    return to_jsonable(
        {
            "stock": stock,
            "sources": sources,
            "sectors": sectors,
            "relations": relations,
            "knowledge_items": knowledge_items,
            "user_insights": user_insights,
            "search_result": search_result,
        }
    )


def _resolve_source_id(item: dict[str, Any], source_id_by_key: dict[str, int]) -> int | None:
    if item.get("source_id") is not None:
        return item["source_id"]
    source_key = item.get("source_key")
    if source_key is None:
        return None
    return source_id_by_key.get(source_key)


def _upsert_stock_profile_in_conn(
    conn: Connection,
    symbol: str,
    market: str,
    name: str | None = None,
    core_business: str | None = None,
    equity_structure: str | None = None,
    stock_character: str | None = None,
    notable_history: str | None = None,
) -> dict[str, Any]:
    return conn.execute(
        """
        INSERT INTO stocks (
          symbol, market, name, core_business, equity_structure,
          stock_character, notable_history
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, market) DO UPDATE SET
          name = COALESCE(EXCLUDED.name, stocks.name),
          core_business = COALESCE(EXCLUDED.core_business, stocks.core_business),
          equity_structure = COALESCE(EXCLUDED.equity_structure, stocks.equity_structure),
          stock_character = COALESCE(EXCLUDED.stock_character, stocks.stock_character),
          notable_history = COALESCE(EXCLUDED.notable_history, stocks.notable_history),
          updated_at = now()
        RETURNING *
        """,
        (
            _normalize_symbol(symbol),
            _normalize_market(market),
            name,
            core_business,
            equity_structure,
            stock_character,
            notable_history,
        ),
    ).fetchone()


def _get_stock_in_conn(conn: Connection, symbol: str, market: str) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT *
        FROM stocks
        WHERE symbol = %s AND market = %s
        """,
        (_normalize_symbol(symbol), _normalize_market(market)),
    ).fetchone()


def _upsert_sector_tree_in_conn(
    conn: Connection,
    path: list[str],
    description: str | None = None,
    recent_status: str | None = None,
) -> dict[str, Any]:
    cleaned_path = [item.strip() for item in path if item and item.strip()]
    if not cleaned_path:
        raise ValueError("sector path must contain at least one non-empty sector name")

    parent_id: int | None = None
    nodes: list[dict[str, Any]] = []

    for index, name in enumerate(cleaned_path):
        is_leaf = index == len(cleaned_path) - 1
        row = _get_sector(conn, name, parent_id)
        if row is None:
            row = conn.execute(
                """
                INSERT INTO sectors (name, parent_id, description, recent_status)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (
                    name,
                    parent_id,
                    description if is_leaf else None,
                    recent_status if is_leaf else None,
                ),
            ).fetchone()
        elif is_leaf and (description is not None or recent_status is not None):
            row = conn.execute(
                """
                UPDATE sectors SET
                  description = COALESCE(%s, description),
                  recent_status = COALESCE(%s, recent_status),
                  updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (description, recent_status, row["id"]),
            ).fetchone()

        nodes.append(row)
        parent_id = row["id"]

    return {"leaf": nodes[-1], "path": nodes}


def _link_stock_to_sector_in_conn(
    conn: Connection,
    stock_id: int,
    sector_id: int,
    relation_type: str = "related",
    confidence: float = 0.5,
    source_id: int | None = None,
    confirmed_by_user: bool = False,
) -> dict[str, Any]:
    return conn.execute(
        """
        INSERT INTO stock_sector_relations (
          stock_id, sector_id, relation_type, confidence, source_id, confirmed_by_user
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (stock_id, sector_id, relation_type) DO UPDATE SET
          confidence = EXCLUDED.confidence,
          source_id = COALESCE(EXCLUDED.source_id, stock_sector_relations.source_id),
          confirmed_by_user = EXCLUDED.confirmed_by_user
        RETURNING *
        """,
        (stock_id, sector_id, relation_type, confidence, source_id, confirmed_by_user),
    ).fetchone()


def _add_knowledge_item_in_conn(
    conn: Connection,
    target_type: str,
    target_id: int | None,
    knowledge_type: str,
    content: str,
    source_id: int | None = None,
    confidence: float = 0.5,
    confirmed_by_user: bool = False,
    stale_after: str | None = None,
) -> dict[str, Any]:
    target_type = target_type.strip()
    knowledge_type = knowledge_type.strip()
    content = content.strip()

    existing = conn.execute(
        """
        SELECT *
        FROM knowledge_items
        WHERE target_type = %s
          AND target_id IS NOT DISTINCT FROM %s
          AND knowledge_type = %s
          AND content = %s
        ORDER BY id
        LIMIT 1
        """,
        (target_type, target_id, knowledge_type, content),
    ).fetchone()
    if existing is not None:
        return conn.execute(
            """
            UPDATE knowledge_items SET
              source_id = COALESCE(knowledge_items.source_id, %s),
              confidence = GREATEST(knowledge_items.confidence, %s),
              confirmed_by_user = knowledge_items.confirmed_by_user OR %s,
              stale_after = COALESCE(knowledge_items.stale_after, %s),
              updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (source_id, confidence, confirmed_by_user, stale_after, existing["id"]),
        ).fetchone()

    return conn.execute(
        """
        INSERT INTO knowledge_items (
          target_type, target_id, knowledge_type, content, source_id,
          confidence, confirmed_by_user, stale_after
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            target_type,
            target_id,
            knowledge_type,
            content,
            source_id,
            confidence,
            confirmed_by_user,
            stale_after,
        ),
    ).fetchone()


def _add_user_insight_in_conn(
    conn: Connection,
    target_type: str,
    target_id: int | None,
    insight: str,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    target_type = target_type.strip()
    insight = insight.strip()
    normalized_summary = _clean_optional_text(normalized_summary)
    tags = tags or []

    existing = conn.execute(
        """
        SELECT *
        FROM user_insights
        WHERE target_type = %s
          AND target_id IS NOT DISTINCT FROM %s
          AND insight = %s
        ORDER BY id
        LIMIT 1
        """,
        (target_type, target_id, insight),
    ).fetchone()
    if existing is not None:
        return conn.execute(
            """
            UPDATE user_insights SET
              normalized_summary = COALESCE(user_insights.normalized_summary, %s),
              tags = CASE
                WHEN user_insights.tags = '[]'::jsonb THEN %s
                ELSE user_insights.tags
              END
            WHERE id = %s
            RETURNING *
            """,
            (normalized_summary, Jsonb(tags), existing["id"]),
        ).fetchone()

    return conn.execute(
        """
        INSERT INTO user_insights (
          target_type, target_id, insight, normalized_summary, tags
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (target_type, target_id, insight, normalized_summary, Jsonb(tags or [])),
    ).fetchone()


def _upsert_candidate_insight_in_conn(
    conn: Connection,
    target_type: str,
    target_id: int | None,
    insight: str,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    target_type = target_type.strip()
    insight = insight.strip()
    normalized_summary = _clean_optional_text(normalized_summary)
    reason = _clean_optional_text(reason)
    tags = tags or []

    existing = conn.execute(
        """
        SELECT *
        FROM candidate_insights
        WHERE target_type = %s
          AND target_id IS NOT DISTINCT FROM %s
          AND status = 'pending'
          AND regexp_replace(lower(insight), '[[:space:][:punct:]]+', '', 'g') = %s
        ORDER BY id
        LIMIT 1
        """,
        (target_type, target_id, _normalize_candidate_insight_key(insight)),
    ).fetchone()
    if existing is None and target_type in {"portfolio", "strategy"}:
        existing = conn.execute(
            """
            SELECT *
            FROM candidate_insights
            WHERE target_type IN ('portfolio', 'strategy')
              AND target_id IS NULL
              AND status = 'pending'
              AND regexp_replace(lower(insight), '[[:space:][:punct:]]+', '', 'g') = %s
            ORDER BY id
            LIMIT 1
            """,
            (_normalize_candidate_insight_key(insight),),
        ).fetchone()
    if existing is not None:
        return conn.execute(
            """
            UPDATE candidate_insights SET
              target_type = %s,
              normalized_summary = COALESCE(candidate_insights.normalized_summary, %s),
              tags = CASE
                WHEN candidate_insights.tags = '[]'::jsonb THEN %s
                ELSE candidate_insights.tags
              END,
              reason = COALESCE(candidate_insights.reason, %s),
              repeat_count = candidate_insights.repeat_count + 1,
              updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (target_type, normalized_summary, Jsonb(tags), reason, existing["id"]),
        ).fetchone()

    exact_existing = conn.execute(
        """
        SELECT *
        FROM candidate_insights
        WHERE target_type = %s
          AND target_id IS NOT DISTINCT FROM %s
          AND insight = %s
          AND status = 'pending'
        ORDER BY id
        LIMIT 1
        """,
        (target_type, target_id, insight),
    ).fetchone()
    if exact_existing is not None:
        return conn.execute(
            """
            UPDATE candidate_insights SET
              normalized_summary = COALESCE(candidate_insights.normalized_summary, %s),
              tags = CASE
                WHEN candidate_insights.tags = '[]'::jsonb THEN %s
                ELSE candidate_insights.tags
              END,
              reason = COALESCE(candidate_insights.reason, %s),
              repeat_count = candidate_insights.repeat_count + 1,
              updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (normalized_summary, Jsonb(tags), reason, exact_existing["id"]),
        ).fetchone()

    return conn.execute(
        """
        INSERT INTO candidate_insights (
          target_type, target_id, insight, normalized_summary, tags, reason
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (target_type, target_id, insight, normalized_summary, Jsonb(tags), reason),
    ).fetchone()


def _normalize_candidate_insight_key(insight: str) -> str:
    return re.sub(r"[\s\W_]+", "", insight.strip().lower())


def _get_candidate_insight_in_conn(
    conn: Connection,
    candidate_id: int,
) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT *
        FROM candidate_insights
        WHERE id = %s
        """,
        (candidate_id,),
    ).fetchone()


def search_stock(symbol: str, market: str) -> dict[str, Any]:
    with transaction() as conn:
        stock = _get_stock_in_conn(conn, symbol=symbol, market=market)

        if stock is None:
            return {"stock": None, "sectors": [], "knowledge_items": [], "user_insights": []}

        sectors = conn.execute(
            """
            SELECT
              ssr.id AS relation_id,
              ssr.relation_type,
              ssr.confidence,
              ssr.source_id,
              ssr.confirmed_by_user,
              s.id,
              s.name,
              s.parent_id,
              s.description,
              s.recent_status
            FROM stock_sector_relations ssr
            JOIN sectors s ON s.id = ssr.sector_id
            WHERE ssr.stock_id = %s
            ORDER BY ssr.relation_type, s.name
            """,
            (stock["id"],),
        ).fetchall()

        knowledge_items = conn.execute(
            """
            SELECT *
            FROM knowledge_items
            WHERE target_type = 'stock' AND target_id = %s
            ORDER BY created_at DESC
            """,
            (stock["id"],),
        ).fetchall()

        user_insights = conn.execute(
            """
            SELECT *
            FROM user_insights
            WHERE target_type = 'stock' AND target_id = %s
            ORDER BY created_at DESC
            """,
            (stock["id"],),
        ).fetchall()

    return to_jsonable(
        {
            "stock": stock,
            "sectors": sectors,
            "knowledge_items": knowledge_items,
            "user_insights": user_insights,
        }
    )


def search_stock_summary(
    symbol: str,
    market: str,
    include_knowledge_items: bool = False,
    include_sources: bool = False,
    include_audit: bool = False,
    verbose: bool = False,
    full: bool = False,
) -> dict[str, Any]:
    """Return a Level 1 decision view while preserving optional evidence expansion."""
    include_knowledge_items = include_knowledge_items or verbose or full
    include_sources = include_sources or verbose or full
    include_audit = include_audit or verbose or full

    with transaction() as conn:
        stock = _get_stock_in_conn(conn, symbol=symbol, market=market)
        if stock is None:
            return {
                "stock": None,
                "level_1_summary": None,
                "counts": {
                    "sectors": 0,
                    "knowledge_items": 0,
                    "user_insights": 0,
                    "sources": 0,
                    "research_jobs": 0,
                },
            }

        sectors = conn.execute(
            """
            SELECT
              ssr.id AS relation_id,
              ssr.relation_type,
              ssr.confidence,
              ssr.source_id,
              ssr.confirmed_by_user,
              s.id,
              s.name,
              s.parent_id,
              s.description,
              s.recent_status
            FROM stock_sector_relations ssr
            JOIN sectors s ON s.id = ssr.sector_id
            WHERE ssr.stock_id = %s
            ORDER BY ssr.relation_type, s.name
            """,
            (stock["id"],),
        ).fetchall()

        knowledge_items = conn.execute(
            """
            SELECT *
            FROM knowledge_items
            WHERE target_type = 'stock' AND target_id = %s
            ORDER BY confirmed_by_user DESC, confidence DESC, created_at DESC
            """,
            (stock["id"],),
        ).fetchall()

        user_insights = conn.execute(
            """
            SELECT *
            FROM user_insights
            WHERE target_type = 'stock' AND target_id = %s
            ORDER BY created_at DESC
            """,
            (stock["id"],),
        ).fetchall()

        sources = _get_stock_sources_in_conn(conn, stock_id=stock["id"])
        latest_job = _get_latest_research_job_for_stock_in_conn(
            conn,
            symbol=stock["symbol"],
            market=stock["market"],
        )
        job_count_row = conn.execute(
            """
            SELECT count(*) AS count
            FROM research_jobs
            WHERE upper(symbol) = upper(%s)
              AND upper(market) = upper(%s)
            """,
            (stock["symbol"], stock["market"]),
        ).fetchone()

    level_1_summary = _build_level_1_stock_summary(
        stock=stock,
        knowledge_items=knowledge_items,
        sources=sources,
        latest_job=latest_job,
    )
    result: dict[str, Any] = {
        "stock": stock,
        "level_1_summary": level_1_summary,
        "counts": {
            "sectors": len(sectors),
            "knowledge_items": len(knowledge_items),
            "user_insights": len(user_insights),
            "sources": len(sources),
            "research_jobs": int(job_count_row["count"] if job_count_row else 0),
        },
    }
    if include_knowledge_items:
        result["knowledge_items"] = knowledge_items
        result["sectors"] = sectors
        result["user_insights"] = user_insights
    if include_sources:
        result["sources"] = sources
    if include_audit:
        result["latest_research_job"] = latest_job
    if full:
        result["search_result"] = {
            "stock": stock,
            "sectors": sectors,
            "knowledge_items": knowledge_items,
            "user_insights": user_insights,
        }
    return to_jsonable(result)


def _get_stock_sources_in_conn(conn: Connection, stock_id: int) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT DISTINCT s.*
        FROM sources s
        WHERE s.id IN (
          SELECT source_id
          FROM knowledge_items
          WHERE target_type = 'stock'
            AND target_id = %s
            AND source_id IS NOT NULL
          UNION
          SELECT source_id
          FROM stock_sector_relations
          WHERE stock_id = %s
            AND source_id IS NOT NULL
        )
        ORDER BY s.published_at DESC NULLS LAST, s.created_at DESC
        """,
        (stock_id, stock_id),
    ).fetchall()


def _get_latest_research_job_for_stock_in_conn(
    conn: Connection,
    symbol: str,
    market: str,
) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT *
        FROM research_jobs
        WHERE upper(symbol) = upper(%s)
          AND upper(market) = upper(%s)
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (symbol, market),
    ).fetchone()


def _build_level_1_stock_summary(
    *,
    stock: dict[str, Any],
    knowledge_items: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    latest_job: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "one_line_thesis": _one_line_thesis(stock=stock, knowledge_items=knowledge_items),
        "key_drivers": _pick_knowledge_lines(
            knowledge_items,
            {"business", "sector_logic", "announcement", "equity_structure", "history"},
            limit=3,
        ),
        "core_risks": _pick_knowledge_lines(knowledge_items, {"risk"}, limit=3),
        "watch_items": _pick_knowledge_lines(knowledge_items, {"watch_item"}, limit=3),
        "data_freshness": _summarize_data_freshness(knowledge_items),
        "source_status": _summarize_source_status(knowledge_items=knowledge_items, sources=sources),
        "audit_status": _summarize_audit_status(latest_job),
    }


def _one_line_thesis(stock: dict[str, Any], knowledge_items: list[dict[str, Any]]) -> str:
    core_business = _clean_summary_text(stock.get("core_business"))
    stock_character = _clean_summary_text(stock.get("stock_character"))
    if core_business and stock_character:
        return f"{core_business}；{stock_character}"
    if core_business:
        return core_business
    if stock_character:
        return stock_character
    for item in knowledge_items:
        if item.get("knowledge_type") in {"business", "sector_logic"}:
            return _clean_summary_text(item.get("content")) or "暂无一句话 thesis。"
    return "暂无一句话 thesis。"


def _pick_knowledge_lines(
    knowledge_items: list[dict[str, Any]],
    knowledge_types: set[str],
    limit: int,
) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for item in knowledge_items:
        if str(item.get("knowledge_type") or "") not in knowledge_types:
            continue
        content = _clean_summary_text(item.get("content"))
        if not content or content in seen:
            continue
        seen.add(content)
        lines.append(content)
        if len(lines) >= limit:
            break
    return lines


def _clean_summary_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:240]


def _summarize_data_freshness(knowledge_items: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stale_after_values = [item.get("stale_after") for item in knowledge_items if item.get("stale_after") is not None]
    stale_count = 0
    parsed_values: list[datetime] = []
    for value in stale_after_values:
        parsed = _coerce_datetime(value)
        if parsed is None:
            continue
        parsed_values.append(parsed)
        if parsed <= now:
            stale_count += 1
    earliest = min(parsed_values).isoformat() if parsed_values else None
    if not knowledge_items:
        summary = "no_knowledge_items"
    elif not parsed_values:
        summary = "no_stale_after_set"
    elif stale_count:
        summary = f"{stale_count} stale knowledge items"
    else:
        summary = "fresh_until_next_stale_after"
    return {
        "summary": summary,
        "knowledge_items": len(knowledge_items),
        "stale_after_count": len(parsed_values),
        "stale_count": stale_count,
        "earliest_stale_after": earliest,
    }


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _summarize_source_status(
    *,
    knowledge_items: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    with_source = [item for item in knowledge_items if item.get("source_id") is not None]
    source_with_url = [source for source in sources if source.get("url")]
    return {
        "summary": "has_sources" if sources else "no_sources",
        "source_count": len(sources),
        "source_with_url_count": len(source_with_url),
        "knowledge_items_with_source_count": len(with_source),
        "knowledge_items_missing_source_count": max(0, len(knowledge_items) - len(with_source)),
    }


def _summarize_audit_status(latest_job: dict[str, Any] | None) -> dict[str, Any]:
    if latest_job is None:
        return {"summary": "no_research_job", "latest_job_id": None, "audit_status": None, "warnings_count": 0}
    artifacts = latest_job.get("artifacts") if isinstance(latest_job.get("artifacts"), dict) else {}
    warnings = artifacts.get("warnings") if isinstance(artifacts.get("warnings"), list) else []
    audit_status = artifacts.get("audit_status")
    return {
        "summary": audit_status or latest_job.get("status") or "unknown",
        "latest_job_id": latest_job.get("id"),
        "job_status": latest_job.get("status"),
        "audit_status": audit_status,
        "warnings_count": len(warnings),
    }


def resolve_stock_reference(query: str) -> list[dict[str, Any]]:
    cleaned = query.strip()
    if not cleaned:
        return []

    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM stocks
            WHERE upper(symbol) = upper(%s)
               OR lower(coalesce(name, '')) = lower(%s)
               OR name ILIKE %s
            ORDER BY
              CASE
                WHEN upper(symbol) = upper(%s) THEN 0
                WHEN lower(coalesce(name, '')) = lower(%s) THEN 1
                ELSE 2
              END,
              market,
              symbol
            LIMIT 5
            """,
            (cleaned, cleaned, f"%{cleaned}%", cleaned, cleaned),
        ).fetchall()
    return to_jsonable(rows)


def get_stock_context(symbol: str, market: str) -> dict[str, Any]:
    with transaction() as conn:
        stock = _get_stock_in_conn(conn, symbol=symbol, market=market)
        if stock is None:
            return {
                "stock": None,
                "sectors": [],
                "stock_knowledge": [],
                "stock_insights": [],
                "stock_candidate_insights": [],
                "sector_knowledge": [],
                "sector_insights": [],
                "sector_candidate_insights": [],
                "global_insights": [],
                "global_candidate_insights": [],
                "sources": [],
            }

        sectors = _get_stock_sector_context_in_conn(conn, stock_id=stock["id"])
        sector_ids = [sector["sector_id"] for sector in sectors]
        expanded_sector_ids = _expand_sector_ids_with_ancestors(conn, sector_ids)

        stock_knowledge = _get_knowledge_for_target_in_conn(
            conn=conn,
            target_type="stock",
            target_ids=[stock["id"]],
        )
        stock_insights = _get_user_insights_for_target_in_conn(
            conn=conn,
            target_type="stock",
            target_ids=[stock["id"]],
        )
        stock_candidate_insights = _get_candidate_insights_for_target_in_conn(
            conn=conn,
            target_type="stock",
            target_ids=[stock["id"]],
        )
        sector_knowledge = _get_knowledge_for_target_in_conn(
            conn=conn,
            target_type="sector",
            target_ids=expanded_sector_ids,
        )
        sector_insights = _get_user_insights_for_target_in_conn(
            conn=conn,
            target_type="sector",
            target_ids=expanded_sector_ids,
        )
        sector_candidate_insights = _get_candidate_insights_for_target_in_conn(
            conn=conn,
            target_type="sector",
            target_ids=expanded_sector_ids,
        )
        global_insights = _get_global_user_insights_in_conn(conn)
        global_candidate_insights = _get_global_candidate_insights_in_conn(conn)
        sources = _get_sources_for_context_in_conn(
            conn=conn,
            source_ids=[
                item["source_id"]
                for item in [*stock_knowledge, *sector_knowledge, *sectors]
                if item.get("source_id") is not None
            ],
        )

    return to_jsonable(
        {
            "stock": stock,
            "sectors": sectors,
            "stock_knowledge": stock_knowledge,
            "stock_insights": stock_insights,
            "stock_candidate_insights": stock_candidate_insights,
            "sector_knowledge": sector_knowledge,
            "sector_insights": sector_insights,
            "sector_candidate_insights": sector_candidate_insights,
            "global_insights": global_insights,
            "global_candidate_insights": global_candidate_insights,
            "sources": sources,
        }
    )


def get_sector_context(
    path: list[str] | None = None,
    sector_id: int | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        sector = _resolve_sector_in_conn(conn, path=path, sector_id=sector_id)
        if sector is None:
            return {
                "sector": None,
                "descendant_sectors": [],
                "linked_stocks": [],
                "sector_knowledge": [],
                "sector_insights": [],
                "sector_candidate_insights": [],
                "global_insights": [],
                "global_candidate_insights": [],
                "sources": [],
            }

        descendant_sectors = _get_descendant_sector_context_in_conn(conn, sector_id=sector["sector_id"])
        descendant_sector_ids = [item["sector_id"] for item in descendant_sectors]
        linked_stocks = _get_stocks_linked_to_sectors_in_conn(conn, sector_ids=descendant_sector_ids)
        sector_knowledge = _get_knowledge_for_target_in_conn(
            conn=conn,
            target_type="sector",
            target_ids=descendant_sector_ids,
        )
        sector_insights = _get_user_insights_for_target_in_conn(
            conn=conn,
            target_type="sector",
            target_ids=descendant_sector_ids,
        )
        sector_candidate_insights = _get_candidate_insights_for_target_in_conn(
            conn=conn,
            target_type="sector",
            target_ids=descendant_sector_ids,
        )
        global_insights = _get_global_user_insights_in_conn(conn)
        global_candidate_insights = _get_global_candidate_insights_in_conn(conn)
        sources = _get_sources_for_context_in_conn(
            conn=conn,
            source_ids=[
                item["source_id"]
                for item in [*sector_knowledge, *linked_stocks]
                if item.get("source_id") is not None
            ],
        )

    return to_jsonable(
        {
            "sector": sector,
            "descendant_sectors": descendant_sectors,
            "linked_stocks": linked_stocks,
            "sector_knowledge": sector_knowledge,
            "sector_insights": sector_insights,
            "sector_candidate_insights": sector_candidate_insights,
            "global_insights": global_insights,
            "global_candidate_insights": global_candidate_insights,
            "sources": sources,
        }
    )


def get_global_user_memory() -> dict[str, Any]:
    with transaction() as conn:
        global_insights = _get_global_user_insights_in_conn(conn)
        global_candidate_insights = _get_global_candidate_insights_in_conn(conn)
    return to_jsonable(
        {
            "global_insights": global_insights,
            "global_candidate_insights": global_candidate_insights,
        }
    )


def _resolve_sector_in_conn(
    conn: Connection,
    path: list[str] | None,
    sector_id: int | None,
) -> dict[str, Any] | None:
    if sector_id is not None:
        return _get_sector_context_by_id_in_conn(conn, sector_id=sector_id)
    if path:
        sector = _get_sector_by_path_in_conn(conn, path)
        if sector is None:
            return None
        return _get_sector_context_by_id_in_conn(conn, sector_id=sector["id"])
    raise ValueError("path or sector_id is required")


def _get_stock_sector_context_in_conn(
    conn: Connection,
    stock_id: int,
) -> list[dict[str, Any]]:
    return conn.execute(
        """
        WITH RECURSIVE sector_paths AS (
          SELECT
            id,
            name,
            parent_id,
            name::text AS path,
            description,
            recent_status
          FROM sectors
          WHERE parent_id IS NULL
          UNION ALL
          SELECT
            s.id,
            s.name,
            s.parent_id,
            sp.path || ' > ' || s.name,
            s.description,
            s.recent_status
          FROM sectors s
          JOIN sector_paths sp ON s.parent_id = sp.id
        )
        SELECT
          ssr.id AS relation_id,
          ssr.stock_id,
          ssr.sector_id,
          ssr.relation_type,
          ssr.confidence,
          ssr.source_id,
          ssr.confirmed_by_user,
          sp.name,
          sp.parent_id,
          sp.path,
          sp.description,
          sp.recent_status
        FROM stock_sector_relations ssr
        JOIN sector_paths sp ON sp.id = ssr.sector_id
        WHERE ssr.stock_id = %s
        ORDER BY ssr.relation_type, ssr.confidence DESC, sp.path
        """,
        (stock_id,),
    ).fetchall()


def _get_sector_context_by_id_in_conn(
    conn: Connection,
    sector_id: int,
) -> dict[str, Any] | None:
    return conn.execute(
        """
        WITH RECURSIVE sector_paths AS (
          SELECT
            id,
            name,
            parent_id,
            name::text AS path,
            description,
            recent_status,
            created_at,
            updated_at
          FROM sectors
          WHERE parent_id IS NULL
          UNION ALL
          SELECT
            s.id,
            s.name,
            s.parent_id,
            sp.path || ' > ' || s.name,
            s.description,
            s.recent_status,
            s.created_at,
            s.updated_at
          FROM sectors s
          JOIN sector_paths sp ON s.parent_id = sp.id
        )
        SELECT
          id AS sector_id,
          name,
          parent_id,
          path,
          description,
          recent_status,
          created_at,
          updated_at
        FROM sector_paths
        WHERE id = %s
        """,
        (sector_id,),
    ).fetchone()


def _get_descendant_sector_context_in_conn(
    conn: Connection,
    sector_id: int,
) -> list[dict[str, Any]]:
    return conn.execute(
        """
        WITH RECURSIVE descendants AS (
          SELECT id
          FROM sectors
          WHERE id = %s
          UNION ALL
          SELECT s.id
          FROM sectors s
          JOIN descendants d ON s.parent_id = d.id
        ),
        sector_paths AS (
          SELECT
            id,
            name,
            parent_id,
            name::text AS path,
            description,
            recent_status
          FROM sectors
          WHERE parent_id IS NULL
          UNION ALL
          SELECT
            s.id,
            s.name,
            s.parent_id,
            sp.path || ' > ' || s.name,
            s.description,
            s.recent_status
          FROM sectors s
          JOIN sector_paths sp ON s.parent_id = sp.id
        )
        SELECT
          sp.id AS sector_id,
          sp.name,
          sp.parent_id,
          sp.path,
          sp.description,
          sp.recent_status
        FROM sector_paths sp
        JOIN descendants d ON d.id = sp.id
        ORDER BY sp.path
        """,
        (sector_id,),
    ).fetchall()


def _expand_sector_ids_with_ancestors(
    conn: Connection,
    sector_ids: list[int],
) -> list[int]:
    if not sector_ids:
        return []
    rows = conn.execute(
        """
        WITH RECURSIVE ancestors AS (
          SELECT id, parent_id
          FROM sectors
          WHERE id = ANY(%s)
          UNION
          SELECT s.id, s.parent_id
          FROM sectors s
          JOIN ancestors a ON a.parent_id = s.id
        )
        SELECT DISTINCT id
        FROM ancestors
        """,
        (sector_ids,),
    ).fetchall()
    return [row["id"] for row in rows]


def _get_knowledge_for_target_in_conn(
    conn: Connection,
    target_type: str,
    target_ids: list[int],
) -> list[dict[str, Any]]:
    if not target_ids:
        return []
    return conn.execute(
        """
        SELECT
          k.*,
          s.title AS source_title,
          s.url AS source_url,
          s.publisher AS source_publisher,
          s.published_at AS source_published_at
        FROM knowledge_items k
        LEFT JOIN sources s ON s.id = k.source_id
        WHERE k.target_type = %s
          AND k.target_id = ANY(%s)
        ORDER BY k.confirmed_by_user DESC, k.confidence DESC, k.created_at DESC
        """,
        (target_type, target_ids),
    ).fetchall()


def _get_user_insights_for_target_in_conn(
    conn: Connection,
    target_type: str,
    target_ids: list[int],
) -> list[dict[str, Any]]:
    if not target_ids:
        return []
    return conn.execute(
        """
        SELECT *
        FROM user_insights
        WHERE target_type = %s
          AND target_id = ANY(%s)
        ORDER BY created_at DESC
        """,
        (target_type, target_ids),
    ).fetchall()


def _get_candidate_insights_for_target_in_conn(
    conn: Connection,
    target_type: str,
    target_ids: list[int],
) -> list[dict[str, Any]]:
    if not target_ids:
        return []
    return conn.execute(
        """
        SELECT *
        FROM candidate_insights
        WHERE target_type = %s
          AND target_id = ANY(%s)
          AND status = 'pending'
        ORDER BY created_at DESC
        """,
        (target_type, target_ids),
    ).fetchall()


def _get_global_user_insights_in_conn(conn: Connection) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT *
        FROM user_insights
        WHERE target_type IN ('portfolio', 'strategy')
        ORDER BY created_at DESC
        """
    ).fetchall()


def _get_global_candidate_insights_in_conn(conn: Connection) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT *
        FROM candidate_insights
        WHERE target_type IN ('portfolio', 'strategy')
          AND status = 'pending'
        ORDER BY created_at DESC
        """
    ).fetchall()


def _get_stocks_linked_to_sectors_in_conn(
    conn: Connection,
    sector_ids: list[int],
) -> list[dict[str, Any]]:
    if not sector_ids:
        return []
    return conn.execute(
        """
        WITH RECURSIVE sector_paths AS (
          SELECT
            id,
            name,
            parent_id,
            name::text AS path
          FROM sectors
          WHERE parent_id IS NULL
          UNION ALL
          SELECT
            s.id,
            s.name,
            s.parent_id,
            sp.path || ' > ' || s.name
          FROM sectors s
          JOIN sector_paths sp ON s.parent_id = sp.id
        )
        SELECT
          st.id AS stock_id,
          st.symbol,
          st.market,
          st.name AS stock_name,
          ssr.id AS relation_id,
          ssr.sector_id,
          ssr.relation_type,
          ssr.confidence,
          ssr.source_id,
          ssr.confirmed_by_user,
          sp.path AS sector_path
        FROM stock_sector_relations ssr
        JOIN stocks st ON st.id = ssr.stock_id
        JOIN sector_paths sp ON sp.id = ssr.sector_id
        WHERE ssr.sector_id = ANY(%s)
        ORDER BY ssr.confidence DESC, st.market, st.symbol
        """,
        (sector_ids,),
    ).fetchall()


def _get_sources_for_context_in_conn(
    conn: Connection,
    source_ids: list[int],
) -> list[dict[str, Any]]:
    unique_source_ids = sorted({source_id for source_id in source_ids if source_id is not None})
    if not unique_source_ids:
        return []
    return conn.execute(
        """
        SELECT *
        FROM sources
        WHERE id = ANY(%s)
        ORDER BY id
        """,
        (unique_source_ids,),
    ).fetchall()
