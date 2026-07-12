from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.serialization import to_jsonable


JOB_STATUSES = {"queued", "running", "completed", "partial", "failed", "cancelled"}
ITEM_STATUSES = {"queued", "running", "completed", "skipped", "failed", "cancelled"}
TERMINAL_ITEM_STATUSES = {"completed", "skipped", "failed", "cancelled"}
REQUEST_TYPES = {"single", "batch"}
SOURCES = {"web", "command", "scheduler_recovery", "agent"}
MAX_HISTORY_ITEMS = 120
MAX_DEDUP_RETRIES = 3
PUBLIC_ERROR_SUMMARIES = {
    "generation_failed": "历史市场简报生成失败，请稍后重试。",
    "provider_timeout": "历史数据源响应超时，请稍后重试。",
    "provider_unavailable": "历史数据源暂时不可用，请稍后重试。",
    "historical_data_unavailable": "未找到该市场日期的可用历史数据。",
}


def create_history_job(
    markets: list[str],
    dates: list[date],
    *,
    request_type: str,
    source: str,
    force_refresh: bool = False,
    max_items: int = MAX_HISTORY_ITEMS,
) -> dict[str, Any]:
    normalized_markets = _normalize_markets(markets)
    normalized_dates = _normalize_dates(dates)
    request_type = _normalize_choice(request_type, REQUEST_TYPES, "request_type")
    source = _normalize_choice(source, SOURCES, "source")
    pairs = [(market, market_date) for market in normalized_markets for market_date in normalized_dates]
    if request_type == "single" and len(pairs) != 1:
        raise ValueError("single request_type requires exactly one market/date pair")
    if source == "web" and force_refresh:
        raise ValueError("web source cannot request force_refresh")
    item_limit = min(max(1, int(max_items)), MAX_HISTORY_ITEMS)
    if len(pairs) > item_limit:
        raise ValueError(f"一次最多 {item_limit} 个市场/日期项目")

    with transaction() as conn:
        _lock_market_date_keys(conn, pairs)
        active_items: list[dict[str, Any]] = []
        pending_pairs: list[tuple[str, date]] = []
        for market, market_date in pairs:
            active = _find_active_item(conn, market, market_date)
            if active is None:
                pending_pairs.append((market, market_date))
            else:
                active_items.append(to_jsonable(active))

        if not pending_pairs:
            return _deduplicated_job(conn, active_items)

        item_specs: list[tuple[str, date, str, int | None, str | None]] = []
        for market, market_date in pending_pairs:
            report = None if force_refresh else _find_existing_report(conn, market, market_date)
            if report is None:
                item_specs.append((market, market_date, "queued", None, None))
            else:
                item_specs.append((market, market_date, "skipped", int(report["id"]), "existing_report"))

        job = conn.execute(
            """
            INSERT INTO daily_market_brief_jobs (request_type, source, status, force_refresh)
            VALUES (%s, %s, 'queued', %s)
            RETURNING *
            """,
            (request_type, source, bool(force_refresh)),
        ).fetchone()
        if job is None:
            raise RuntimeError("unable to create daily market brief history job")

        inserted_count = 0
        for market, market_date, status, report_id, skip_reason in item_specs:
            for _ in range(MAX_DEDUP_RETRIES):
                inserted = _insert_history_item(
                    conn,
                    job_id=int(job["id"]),
                    market=market,
                    market_date=market_date,
                    status=status,
                    report_id=report_id,
                    skip_reason=skip_reason,
                )
                if inserted is not None:
                    inserted_count += 1
                    break
                raced_active = _find_active_item(conn, market, market_date)
                if raced_active is not None:
                    active_items.append(to_jsonable(raced_active))
                    break
            else:
                resolved = _resolve_history_item_conflict(
                    conn,
                    job_id=int(job["id"]),
                    market=market,
                    market_date=market_date,
                    status=status,
                    report_id=report_id,
                    skip_reason=skip_reason,
                )
                if int(resolved["job_id"]) == int(job["id"]):
                    inserted_count += 1
                else:
                    active_items.append(to_jsonable(resolved))

        if inserted_count == 0:
            conn.execute(
                """
                DELETE FROM daily_market_brief_jobs
                WHERE id = %s
                RETURNING id
                """,
                (job["id"],),
            ).fetchone()
            return _deduplicated_job(conn, active_items)

        _recompute_history_jobs(conn, [int(job["id"])])
        created = _get_history_job(conn, int(job["id"])) or to_jsonable(job)
        created["deduplicated_items"] = _deduplicated_items(active_items)
        return created


def get_history_job(job_id: int) -> dict[str, Any] | None:
    with transaction() as conn:
        return _get_history_job(conn, job_id)


def list_history_jobs(limit: int = 10) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 100))
    with transaction() as conn:
        rows = conn.execute(
            _history_job_select_sql(where="", order_by="ORDER BY job.created_at DESC", limit=True),
            (bounded_limit,),
        ).fetchall()
    return to_jsonable(rows)


def claim_next_history_item(worker_name: str) -> dict[str, Any] | None:
    cleaned_worker_name = (worker_name or "history-worker").strip() or "history-worker"
    lease_token = uuid4().hex
    with transaction() as conn:
        candidate = conn.execute(
            """
            SELECT item.id, item.job_id, item.market, item.market_date
            FROM daily_market_brief_job_items AS item
            JOIN daily_market_brief_jobs AS job ON job.id = item.job_id
            WHERE item.status = 'queued'
              AND job.status IN ('queued', 'running')
              AND job.cancel_requested_at IS NULL
            ORDER BY item.created_at ASC, item.id ASC
            LIMIT 1
            FOR UPDATE OF job SKIP LOCKED
            """
        ).fetchone()
        if candidate is None:
            return None
        row = conn.execute(
            """
            UPDATE daily_market_brief_job_items AS item SET
              status = 'running',
              attempt_count = item.attempt_count + 1,
              worker_name = %s,
              lease_token = %s,
              claimed_at = now(),
              heartbeat_at = now(),
              updated_at = now()
            WHERE item.id = %s
              AND item.status = 'queued'
            RETURNING item.*
            """,
            (cleaned_worker_name, lease_token, candidate["id"]),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            UPDATE daily_market_brief_jobs AS job SET
              status = 'running',
              current_market = %s,
              current_market_date = %s,
              worker_heartbeat_at = now(),
              updated_at = now()
            WHERE job.id = %s
            """,
            (row["market"], row["market_date"], row["job_id"]),
        )
    return to_jsonable(row) if row else None


def finish_history_item(
    item_id: int,
    *,
    status: str,
    worker_name: str,
    lease_token: str,
    attempt_count: int,
    report_id: int | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    if status not in TERMINAL_ITEM_STATUSES:
        raise ValueError("history item status must be completed, skipped, failed, or cancelled")
    cleaned_worker_name = (worker_name or "").strip()
    cleaned_lease_token = (lease_token or "").strip()
    if not cleaned_worker_name or not cleaned_lease_token or int(attempt_count) < 1:
        raise ValueError("worker_name, lease_token, and positive attempt_count are required")
    public_error_code, public_error_summary = _resolve_public_error(status, error_code, error_summary)
    with transaction() as conn:
        locked_job = _lock_history_job_for_item(conn, item_id)
        if locked_job is None:
            raise ValueError(f"daily market brief history item not found: {item_id}")
        row = conn.execute(
            """
            UPDATE daily_market_brief_job_items AS item SET
              status = %s,
              report_id = COALESCE(%s, item.report_id),
              error_code = %s,
              error_summary = %s,
              worker_name = NULL,
              lease_token = NULL,
              heartbeat_at = NULL,
              finished_at = now(),
              updated_at = now()
            WHERE item.id = %s
              AND item.status = 'running'
              AND item.worker_name = %s
              AND item.lease_token = %s
              AND item.attempt_count = %s
            RETURNING item.*
            """,
            (
                status,
                report_id,
                public_error_code,
                public_error_summary,
                item_id,
                cleaned_worker_name,
                cleaned_lease_token,
                int(attempt_count),
            ),
        ).fetchone()
        if row is None:
            raise ValueError(f"daily market brief history item lease is no longer active: {item_id}")
        _recompute_history_jobs(conn, [int(row["job_id"])])
    return to_jsonable(row)


def request_history_job_cancel(job_id: int) -> dict[str, Any] | None:
    with transaction() as conn:
        locked = _lock_history_jobs(conn, [job_id], active_only=True)
        if not locked:
            return None
        requested = conn.execute(
            """
            UPDATE daily_market_brief_jobs AS job SET
              cancel_requested_at = COALESCE(job.cancel_requested_at, now()),
              updated_at = now()
            WHERE job.id = %s
              AND job.status IN ('queued', 'running')
            RETURNING job.*
            """,
            (job_id,),
        ).fetchone()
        if requested is None:
            return None
        conn.execute(
            """
            UPDATE daily_market_brief_job_items AS item SET
              status = 'cancelled',
              worker_name = NULL,
              lease_token = NULL,
              heartbeat_at = NULL,
              finished_at = now(),
              updated_at = now()
            WHERE item.job_id = %s
              AND item.status = 'queued'
            RETURNING item.job_id
            """,
            (job_id,),
        ).fetchall()
        refreshed = _recompute_history_jobs(conn, [job_id])
    return refreshed[0] if refreshed else to_jsonable(requested)


def requeue_stale_history_items(stale_before: datetime) -> int:
    with transaction() as conn:
        candidates = conn.execute(
            """
            SELECT DISTINCT item.job_id
            FROM daily_market_brief_job_items AS item
            JOIN daily_market_brief_jobs AS job ON job.id = item.job_id
            WHERE item.status = 'running'
              AND item.heartbeat_at < %s
              AND job.cancel_requested_at IS NULL
            ORDER BY item.job_id
            """,
            (stale_before,),
        ).fetchall()
        candidate_job_ids = sorted({int(row["job_id"]) for row in candidates})
        if not candidate_job_ids:
            return 0
        locked_jobs = _lock_history_jobs(conn, candidate_job_ids)
        locked_job_ids = [int(row["id"]) for row in locked_jobs]
        if not locked_job_ids:
            return 0
        rows = conn.execute(
            """
            UPDATE daily_market_brief_job_items AS item SET
              status = 'queued',
              worker_name = NULL,
              lease_token = NULL,
              claimed_at = NULL,
              heartbeat_at = NULL,
              updated_at = now()
            WHERE item.status = 'running'
              AND item.heartbeat_at < %s
              AND item.job_id = ANY(%s)
              AND EXISTS (
                SELECT 1 FROM daily_market_brief_jobs AS job
                WHERE job.id = item.job_id
                  AND job.cancel_requested_at IS NULL
              )
            RETURNING item.job_id
            """,
            (stale_before, locked_job_ids),
        ).fetchall()
        job_ids = sorted({int(row["job_id"]) for row in rows})
        if job_ids:
            _recompute_history_jobs(conn, job_ids)
    return len(rows)


def _lock_market_date_keys(conn: Any, pairs: list[tuple[str, date]]) -> None:
    for market, market_date in sorted(pairs):
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"daily-market-brief:{market}:{market_date.isoformat()}",),
        ).fetchone()


def _lock_history_job_for_item(conn: Any, item_id: int) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT job.id
        FROM daily_market_brief_jobs AS job
        JOIN daily_market_brief_job_items AS item ON item.job_id = job.id
        WHERE item.id = %s
        FOR UPDATE OF job
        """,
        (item_id,),
    ).fetchone()


def _lock_history_jobs(conn: Any, job_ids: list[int], *, active_only: bool = False) -> list[dict[str, Any]]:
    ordered_ids = sorted(set(job_ids))
    if not ordered_ids:
        return []
    active_clause = "AND job.status IN ('queued', 'running')" if active_only else ""
    return conn.execute(
        f"""
        SELECT job.id
        FROM daily_market_brief_jobs AS job
        WHERE job.id = ANY(%s)
          {active_clause}
        ORDER BY job.id
        FOR UPDATE
        """,
        (ordered_ids,),
    ).fetchall()


def _recompute_history_jobs(conn: Any, job_ids: list[int]) -> list[dict[str, Any]]:
    if not job_ids:
        return []
    rows = conn.execute(
        """
        WITH aggregates AS (
          SELECT
            item.job_id,
            count(*)::integer AS total_count,
            count(*) FILTER (WHERE item.status IN ('completed', 'skipped', 'failed', 'cancelled'))::integer AS completed_count,
            count(*) FILTER (WHERE item.status = 'completed')::integer AS succeeded_count,
            count(*) FILTER (WHERE item.status = 'skipped')::integer AS skipped_count,
            count(*) FILTER (WHERE item.status = 'failed')::integer AS failed_count,
            count(*) FILTER (WHERE item.status = 'cancelled')::integer AS cancelled_count,
            count(*) FILTER (WHERE item.status = 'running')::integer AS running_count,
            count(*) FILTER (WHERE item.status = 'queued')::integer AS queued_count,
            (array_agg(item.market ORDER BY item.claimed_at DESC NULLS LAST, item.id DESC)
              FILTER (WHERE item.status = 'running'))[1] AS current_market,
            (array_agg(item.market_date ORDER BY item.claimed_at DESC NULLS LAST, item.id DESC)
              FILTER (WHERE item.status = 'running'))[1] AS current_market_date,
            max(item.heartbeat_at) FILTER (WHERE item.status = 'running') AS worker_heartbeat_at
          FROM daily_market_brief_job_items AS item
          WHERE item.job_id = ANY(%s)
          GROUP BY item.job_id
        )
        UPDATE daily_market_brief_jobs AS job SET
          total_count = aggregates.total_count,
          completed_count = aggregates.completed_count,
          succeeded_count = aggregates.succeeded_count,
          skipped_count = aggregates.skipped_count,
          failed_count = aggregates.failed_count,
          cancelled_count = aggregates.cancelled_count,
          status = CASE
            WHEN aggregates.running_count > 0 THEN 'running'
            WHEN job.cancel_requested_at IS NOT NULL THEN 'cancelled'
            WHEN aggregates.queued_count > 0 THEN 'queued'
            WHEN aggregates.failed_count = 0 THEN 'completed'
            WHEN aggregates.succeeded_count + aggregates.skipped_count = 0 THEN 'failed'
            ELSE 'partial'
          END,
          current_market = aggregates.current_market,
          current_market_date = aggregates.current_market_date,
          worker_heartbeat_at = aggregates.worker_heartbeat_at,
          completed_at = CASE
            WHEN aggregates.running_count = 0 AND aggregates.queued_count = 0 THEN COALESCE(job.completed_at, now())
            ELSE NULL
          END,
          updated_at = now()
        FROM aggregates
        WHERE job.id = aggregates.job_id
        RETURNING job.*
        """,
        (job_ids,),
    ).fetchall()
    return to_jsonable(rows)


def _get_history_job(conn: Any, job_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        _history_job_select_sql(where="WHERE job.id = %s", order_by="", limit=False),
        (job_id,),
    ).fetchone()
    return to_jsonable(row) if row else None


def _history_job_select_sql(*, where: str, order_by: str, limit: bool) -> str:
    limit_clause = "LIMIT %s" if limit else ""
    return f"""
        SELECT
          job.*,
          COALESCE(items.items, '[]'::jsonb) AS items
        FROM daily_market_brief_jobs AS job
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(
            jsonb_build_object(
              'id', item.id,
              'market', item.market,
              'market_date', item.market_date,
              'status', item.status,
              'attempt_count', item.attempt_count,
              'report_id', item.report_id,
              'skip_reason', item.skip_reason,
              'error_code', item.error_code,
              'error_summary', item.error_summary,
              'worker_name', item.worker_name,
              'claimed_at', item.claimed_at,
              'heartbeat_at', item.heartbeat_at,
              'finished_at', item.finished_at
            ) ORDER BY item.created_at ASC, item.id ASC
          ) AS items
          FROM daily_market_brief_job_items AS item
          WHERE item.job_id = job.id
        ) AS items ON true
        {where}
        {order_by}
        {limit_clause}
        """


def _find_active_item(conn: Any, market: str, market_date: date) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT item.id, item.job_id, item.market, item.market_date
        FROM daily_market_brief_job_items AS item
        JOIN daily_market_brief_jobs AS job ON job.id = item.job_id
        WHERE item.market = %s
          AND item.market_date = %s
          AND item.status IN ('queued', 'running')
          AND job.status IN ('queued', 'running')
        LIMIT 1
        """,
        (market, market_date),
    ).fetchone()


def _insert_history_item(
    conn: Any,
    *,
    job_id: int,
    market: str,
    market_date: date,
    status: str,
    report_id: int | None,
    skip_reason: str | None,
) -> dict[str, Any] | None:
    return conn.execute(
        """
        INSERT INTO daily_market_brief_job_items (
          job_id, market, market_date, status, report_id, skip_reason, finished_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s = 'skipped' THEN now() ELSE NULL END)
        ON CONFLICT (market, market_date)
          WHERE status IN ('queued', 'running')
          DO NOTHING
        RETURNING *
        """,
        (job_id, market, market_date, status, report_id, skip_reason, status),
    ).fetchone()


def _resolve_history_item_conflict(
    conn: Any,
    *,
    job_id: int,
    market: str,
    market_date: date,
    status: str,
    report_id: int | None,
    skip_reason: str | None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO daily_market_brief_job_items (
          job_id, market, market_date, status, report_id, skip_reason, finished_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s = 'skipped' THEN now() ELSE NULL END)
        ON CONFLICT (market, market_date)
          WHERE status IN ('queued', 'running')
          DO UPDATE SET updated_at = daily_market_brief_job_items.updated_at
        RETURNING *
        """,
        (job_id, market, market_date, status, report_id, skip_reason, status),
    ).fetchone()
    if row is None:
        raise AssertionError("conflict resolution did not return an item")
    return row


def _find_existing_report(conn: Any, market: str, market_date: date) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT id
        FROM review_reports
        WHERE report_type = 'daily_market_brief'
          AND report_date = %s
          AND portfolio_snapshot->'market'->>'code' = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (market_date, market),
    ).fetchone()


def _normalize_markets(markets: list[str]) -> list[str]:
    normalized = sorted({str(market).strip().upper() for market in markets if str(market).strip()})
    invalid = [market for market in normalized if market not in {"CN", "HK", "US"}]
    if invalid or not normalized:
        raise ValueError("markets must contain one or more of CN, HK, US")
    return normalized


def _normalize_dates(dates: list[date]) -> list[date]:
    if not dates or any(type(value) is not date for value in dates):
        raise ValueError("dates must contain one or more date values")
    return sorted(set(dates))


def _normalize_choice(value: str, allowed: set[str], label: str) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned not in allowed:
        raise ValueError(f"{label} must be one of {', '.join(sorted(allowed))}")
    return cleaned


def _deduplicated_job(conn: Any, active_items: list[dict[str, Any]]) -> dict[str, Any]:
    if not active_items:
        return {"status": "deduplicated", "total_count": 0, "items": [], "deduplicated_items": []}
    existing = _get_history_job(conn, int(active_items[0]["job_id"]))
    if existing is None:
        raise RuntimeError("active daily market brief job disappeared during deduplication")
    existing["deduplicated_items"] = _deduplicated_items(active_items)
    return existing


def _deduplicated_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "job_id": item["job_id"],
            "market": item["market"],
            "market_date": item["market_date"],
        }
        for item in items
    ]


def _resolve_public_error(
    status: str,
    error_code: str | None,
    error_summary: str | None,
) -> tuple[str | None, str | None]:
    if status != "failed":
        return None, None
    cleaned_code = (error_code or "").strip().lower()
    if cleaned_code and cleaned_code not in PUBLIC_ERROR_SUMMARIES:
        raise ValueError("unsupported public history error code")
    if not cleaned_code and error_summary in PUBLIC_ERROR_SUMMARIES.values():
        cleaned_code = next(code for code, summary in PUBLIC_ERROR_SUMMARIES.items() if summary == error_summary)
    if not cleaned_code:
        cleaned_code = "generation_failed"
    return cleaned_code, PUBLIC_ERROR_SUMMARIES[cleaned_code]
