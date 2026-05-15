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


def add_source(
    source_type: str,
    title: str | None = None,
    url: str | None = None,
    publisher: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    with transaction() as conn:
        row = _insert_source(
            conn=conn,
            source_type=source_type,
            title=title,
            url=url,
            publisher=publisher,
            published_at=published_at,
        )
    return to_jsonable(row)


def _insert_source(
    conn: Connection,
    source_type: str,
    title: str | None = None,
    url: str | None = None,
    publisher: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    return conn.execute(
        """
        INSERT INTO sources (source_type, title, url, publisher, published_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *
        """,
        (source_type, title, url, publisher, published_at),
    ).fetchone()


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
            source = _insert_source(
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
