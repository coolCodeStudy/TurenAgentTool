from __future__ import annotations

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
        row = conn.execute(
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
    return to_jsonable(row)


def add_user_insight(
    target_type: str,
    target_id: int | None,
    insight: str,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO user_insights (
              target_type, target_id, insight, normalized_summary, tags
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (target_type, target_id, insight, normalized_summary, Jsonb(tags or [])),
        ).fetchone()
    return to_jsonable(row)


def search_stock(symbol: str, market: str) -> dict[str, Any]:
    with transaction() as conn:
        stock = conn.execute(
            """
            SELECT *
            FROM stocks
            WHERE symbol = %s AND market = %s
            """,
            (_normalize_symbol(symbol), _normalize_market(market)),
        ).fetchone()

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
