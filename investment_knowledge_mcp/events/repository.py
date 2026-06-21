from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.events.models import EventPacket, EventScanResult, EventSource
from investment_knowledge_mcp.serialization import to_jsonable


def upsert_event_source(source: EventSource) -> dict[str, Any]:
    record = source.to_record()
    with transaction() as conn:
        existing = None
        if record.get("accession_number"):
            existing = conn.execute(
                """
                SELECT *
                FROM event_sources
                WHERE source_type = %s
                  AND accession_number = %s
                LIMIT 1
                """,
                (record["source_type"], record["accession_number"]),
            ).fetchone()
        if existing is None and record.get("canonical_url") and record.get("raw_hash"):
            existing = conn.execute(
                """
                SELECT *
                FROM event_sources
                WHERE canonical_url = %s
                  AND raw_hash = %s
                LIMIT 1
                """,
                (record["canonical_url"], record["raw_hash"]),
            ).fetchone()
        if existing is not None:
            row = conn.execute(
                """
                UPDATE event_sources SET
                  publisher = COALESCE(%s, publisher),
                  url = COALESCE(%s, url),
                  canonical_url = COALESCE(%s, canonical_url),
                  title = COALESCE(%s, title),
                  published_at = COALESCE(%s, published_at),
                  market = COALESCE(%s, market),
                  symbol = COALESCE(%s, symbol),
                  cik = COALESCE(%s, cik),
                  form_type = COALESCE(%s, form_type),
                  raw_hash = COALESCE(%s, raw_hash),
                  excerpt = COALESCE(%s, excerpt),
                  parsed_facts = CASE WHEN %s::jsonb = '{}'::jsonb THEN parsed_facts ELSE %s::jsonb END,
                  fetch_status = COALESCE(%s, fetch_status),
                  fetched_at = now(),
                  updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (
                    record.get("publisher"),
                    record.get("url"),
                    record.get("canonical_url"),
                    record.get("title"),
                    record.get("published_at"),
                    record.get("market"),
                    record.get("symbol"),
                    record.get("cik"),
                    record.get("form_type"),
                    record.get("raw_hash"),
                    record.get("excerpt"),
                    Jsonb(record.get("parsed_facts") or {}),
                    Jsonb(record.get("parsed_facts") or {}),
                    record.get("fetch_status"),
                    existing["id"],
                ),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO event_sources (
                  source_type, publisher, url, canonical_url, title, published_at,
                  market, symbol, accession_number, cik, form_type, raw_hash,
                  excerpt, parsed_facts, fetch_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    record["source_type"],
                    record.get("publisher"),
                    record["url"],
                    record.get("canonical_url"),
                    record.get("title"),
                    record.get("published_at"),
                    record.get("market"),
                    record.get("symbol"),
                    record.get("accession_number"),
                    record.get("cik"),
                    record.get("form_type"),
                    record.get("raw_hash"),
                    record.get("excerpt"),
                    Jsonb(record.get("parsed_facts") or {}),
                    record.get("fetch_status") or "ok",
                ),
            ).fetchone()
    return to_jsonable(row)


def upsert_portfolio_event(packet: EventPacket, source_ids: list[int] | None = None) -> dict[str, Any]:
    record = packet.to_record(source_ids=source_ids)
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO portfolio_events (
              market, symbol, event_type, event_title, event_date, next_trading_date,
              priority, confidence, status, source_ids, source_facts, derived_facts,
              media_labels, uncertainties, portfolio_relevance, dedupe_key,
              scan_status, needs_research
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dedupe_key) DO UPDATE SET
              event_title = EXCLUDED.event_title,
              next_trading_date = COALESCE(EXCLUDED.next_trading_date, portfolio_events.next_trading_date),
              priority = EXCLUDED.priority,
              confidence = EXCLUDED.confidence,
              status = EXCLUDED.status,
              source_ids = (
                SELECT COALESCE(jsonb_agg(DISTINCT item), '[]'::jsonb)
                FROM jsonb_array_elements(portfolio_events.source_ids || EXCLUDED.source_ids) AS item
              ),
              source_facts = EXCLUDED.source_facts,
              derived_facts = EXCLUDED.derived_facts,
              media_labels = EXCLUDED.media_labels,
              uncertainties = EXCLUDED.uncertainties,
              portfolio_relevance = EXCLUDED.portfolio_relevance,
              scan_status = EXCLUDED.scan_status,
              needs_research = EXCLUDED.needs_research,
              updated_at = now()
            RETURNING *
            """,
            (
                record["market"],
                record["symbol"],
                record["event_type"],
                record["event_title"],
                record.get("event_date"),
                record.get("next_trading_date"),
                record["priority"],
                record["confidence"],
                record["status"],
                Jsonb(record["source_ids"]),
                Jsonb(record["source_facts"]),
                Jsonb(record["derived_facts"]),
                Jsonb(record["media_labels"]),
                Jsonb(record["uncertainties"]),
                Jsonb(record["portfolio_relevance"]),
                record["dedupe_key"],
                record["scan_status"],
                record["needs_research"],
            ),
        ).fetchone()
    return to_jsonable(row)


def persist_event_packet(packet: EventPacket) -> dict[str, Any]:
    source_ids: list[int] = []
    if packet.source is not None:
        source = upsert_event_source(packet.source)
        source_ids.append(int(source["id"]))
    return upsert_portfolio_event(packet, source_ids=source_ids)


def record_event_scan_run(result: EventScanResult) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO event_scan_runs (
              scope, market, symbol, status, started_at, finished_at,
              symbols_total, symbols_scanned, events_found, errors, metadata
            )
            VALUES (%s, %s, %s, %s, COALESCE(%s, now()), COALESCE(%s, now()), %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                result.scope,
                result.market,
                result.symbol,
                result.status,
                result.started_at,
                result.finished_at,
                result.symbols_total,
                result.symbols_scanned,
                len(result.events),
                Jsonb([error.to_record() for error in result.errors]),
                Jsonb({}),
            ),
        ).fetchone()
    return to_jsonable(row)


def list_portfolio_events(
    *,
    market: str | None = None,
    symbol: str | None = None,
    include_muted: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    filters = ["event.status IN ('upcoming', 'active', 'recent')"]
    params: list[Any] = []
    if market:
        filters.append("upper(event.market) = upper(%s)")
        params.append(market)
    if symbol:
        filters.append("upper(event.symbol) = upper(%s)")
        params.append(symbol)
    muted_filter = ""
    if not include_muted:
        muted_filter = """
          AND COALESCE(pref.preference, 'default') <> 'muted'
        """
    params.append(limit)
    sql = f"""
        SELECT event.*
        FROM portfolio_events AS event
        LEFT JOIN event_alert_preferences AS pref
          ON pref.event_id = event.id
         AND pref.channel = 'all'
        WHERE {' AND '.join(filters)}
        {muted_filter}
        ORDER BY
          CASE event.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
          event.event_date DESC NULLS LAST,
          event.detected_at DESC,
          event.id DESC
        LIMIT %s
    """
    with transaction() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return to_jsonable(rows)


def mute_latest_event_for_symbol(symbol: str, market: str = "US", reason: str | None = None) -> dict[str, Any] | None:
    events = list_portfolio_events(market=market, symbol=symbol, include_muted=True, limit=1)
    if not events:
        return None
    event_id = int(events[0]["id"])
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO event_alert_preferences (event_id, channel, preference, reason)
            VALUES (%s, 'all', 'muted', %s)
            ON CONFLICT (event_id, channel) DO UPDATE SET
              preference = 'muted',
              reason = COALESCE(EXCLUDED.reason, event_alert_preferences.reason),
              updated_at = now()
            RETURNING *
            """,
            (event_id, reason),
        ).fetchone()
    return to_jsonable({"event": events[0], "preference": row})


def update_scan_checkpoint(
    *,
    market: str,
    symbol: str,
    last_filing_date: str | None,
    last_accession_numbers: list[str],
    provider: str = "sec",
) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO event_scan_checkpoints (
              market, symbol, provider, last_scanned_at, last_filing_date, last_accession_numbers
            )
            VALUES (%s, %s, %s, now(), %s, %s)
            ON CONFLICT (market, symbol, provider) DO UPDATE SET
              last_scanned_at = now(),
              last_filing_date = COALESCE(EXCLUDED.last_filing_date, event_scan_checkpoints.last_filing_date),
              last_accession_numbers = EXCLUDED.last_accession_numbers,
              updated_at = now()
            RETURNING *
            """,
            (market.upper(), symbol.upper(), provider, last_filing_date, Jsonb(last_accession_numbers)),
        ).fetchone()
    return to_jsonable(row)


def get_scan_checkpoint(*, market: str, symbol: str, provider: str = "sec") -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM event_scan_checkpoints
            WHERE upper(market) = upper(%s)
              AND upper(symbol) = upper(%s)
              AND provider = %s
            """,
            (market, symbol, provider),
        ).fetchone()
    return to_jsonable(row) if row else None
