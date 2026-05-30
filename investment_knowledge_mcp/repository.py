from __future__ import annotations

import re
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
