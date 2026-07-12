from __future__ import annotations

from datetime import date, datetime
from typing import Any

from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.serialization import to_jsonable


JOB_STATUSES = {"queued", "running", "completed", "partial", "failed", "cancelled"}
ITEM_STATUSES = {"queued", "running", "completed", "skipped", "failed", "cancelled"}
TERMINAL_ITEM_STATUSES = {"completed", "skipped", "failed", "cancelled"}
REQUEST_TYPES = {"single", "batch"}
SOURCES = {"web", "command", "scheduler_recovery", "agent"}
MAX_HISTORY_ITEMS = 120


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
    item_limit = min(max(1, int(max_items)), MAX_HISTORY_ITEMS)
    if len(pairs) > item_limit:
        raise ValueError(f"一次最多 {item_limit} 个市场/日期项目")

    with transaction() as conn:
        active_items: list[dict[str, Any]] = []
        pending_pairs: list[tuple[str, date]] = []
        for market, market_date in pairs:
            active = conn.execute(
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
            if active is None:
                pending_pairs.append((market, market_date))
            else:
                active_items.append(to_jsonable(active))

        if not pending_pairs:
            if active_items:
                existing = _get_history_job(conn, int(active_items[0]["job_id"]))
                if existing is not None:
                    existing["deduplicated_items"] = _deduplicated_items(active_items)
                    return existing
            return {"status": "deduplicated", "total_count": 0, "items": [], "deduplicated_items": []}

        item_specs: list[tuple[str, date, str, int | None, str | None]] = []
        for market, market_date in pending_pairs:
            report = None if force_refresh else _find_existing_report(conn, market, market_date)
            if report is None:
                item_specs.append((market, market_date, "queued", None, None))
            else:
                item_specs.append((market, market_date, "skipped", int(report["id"]), "existing_report"))

        initial_status = "completed" if all(spec[2] == "skipped" for spec in item_specs) else "queued"
        job = conn.execute(
            """
            INSERT INTO daily_market_brief_jobs (request_type, source, status, force_refresh, total_count, completed_count, skipped_count, summary, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s = 'completed' THEN now() ELSE NULL END)
            RETURNING *
            """,
            (
                request_type,
                source,
                initial_status,
                bool(force_refresh),
                len(item_specs),
                sum(spec[2] == "skipped" for spec in item_specs),
                sum(spec[2] == "skipped" for spec in item_specs),
                "existing reports skipped" if initial_status == "completed" else None,
                initial_status,
            ),
        ).fetchone()
        if job is None:
            raise RuntimeError("unable to create daily market brief history job")

        for market, market_date, status, report_id, skip_reason in item_specs:
            conn.execute(
                """
                INSERT INTO daily_market_brief_job_items (job_id, market, market_date, status, report_id, skip_reason, finished_at)
                VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s = 'skipped' THEN now() ELSE NULL END)
                RETURNING *
                """,
                (job["id"], market, market_date, status, report_id, skip_reason, status),
            ).fetchone()

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
    with transaction() as conn:
        row = conn.execute(
            """
            WITH next_item AS (
              SELECT item.id, item.job_id, item.market, item.market_date
              FROM daily_market_brief_job_items AS item
              JOIN daily_market_brief_jobs AS job ON job.id = item.job_id
              WHERE item.status = 'queued'
                AND job.status IN ('queued', 'running')
                AND job.cancel_requested_at IS NULL
              ORDER BY item.created_at ASC, item.id ASC
              LIMIT 1
              FOR UPDATE SKIP LOCKED
            ), claimed AS (
              UPDATE daily_market_brief_job_items AS item SET
                status = 'running',
                attempt_count = item.attempt_count + 1,
                worker_name = %s,
                claimed_at = now(),
                heartbeat_at = now(),
                updated_at = now()
              FROM next_item
              WHERE item.id = next_item.id
              RETURNING item.*
            )
            UPDATE daily_market_brief_jobs AS job SET
              status = 'running',
              current_market = claimed.market,
              current_market_date = claimed.market_date,
              worker_heartbeat_at = now(),
              updated_at = now()
            FROM claimed
            WHERE job.id = claimed.job_id
            RETURNING claimed.*
            """,
            (cleaned_worker_name,),
        ).fetchone()
    return to_jsonable(row) if row else None


def finish_history_item(
    item_id: int,
    *,
    status: str,
    report_id: int | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    if status not in TERMINAL_ITEM_STATUSES:
        raise ValueError("history item status must be completed, skipped, failed, or cancelled")
    safe_error = _sanitize_error_summary(error_summary)
    with transaction() as conn:
        row = conn.execute(
            """
            WITH finished AS (
              UPDATE daily_market_brief_job_items AS item SET
                status = %s,
                report_id = COALESCE(%s, item.report_id),
                error_summary = %s,
                heartbeat_at = now(),
                finished_at = now(),
                updated_at = now()
              WHERE item.id = %s
                AND item.status IN ('queued', 'running')
              RETURNING item.*
            ), counts AS (
              SELECT
                finished.job_id,
                count(item.id)::integer AS total_count,
                count(item.id) FILTER (WHERE item.status IN ('completed', 'skipped', 'failed', 'cancelled'))::integer AS completed_count,
                count(item.id) FILTER (WHERE item.status = 'completed')::integer AS succeeded_count,
                count(item.id) FILTER (WHERE item.status = 'skipped')::integer AS skipped_count,
                count(item.id) FILTER (WHERE item.status = 'failed')::integer AS failed_count,
                count(item.id) FILTER (WHERE item.status = 'running')::integer AS running_count,
                count(item.id) FILTER (WHERE item.status = 'queued')::integer AS queued_count
              FROM finished
              JOIN daily_market_brief_job_items AS item ON item.job_id = finished.job_id
              GROUP BY finished.job_id
            ), updated_job AS (
              UPDATE daily_market_brief_jobs AS job SET
                total_count = counts.total_count,
                completed_count = counts.completed_count,
                succeeded_count = counts.succeeded_count,
                skipped_count = counts.skipped_count,
                failed_count = counts.failed_count,
                status = CASE
                  WHEN counts.running_count > 0 OR counts.queued_count > 0 THEN 'running'
                  WHEN job.cancel_requested_at IS NOT NULL THEN 'cancelled'
                  WHEN counts.failed_count = 0 THEN 'completed'
                  WHEN counts.succeeded_count + counts.skipped_count = 0 THEN 'failed'
                  ELSE 'partial'
                END,
                current_market = NULL,
                current_market_date = NULL,
                worker_heartbeat_at = now(),
                completed_at = CASE WHEN counts.running_count = 0 AND counts.queued_count = 0 THEN now() ELSE NULL END,
                updated_at = now()
              FROM counts
              WHERE job.id = counts.job_id
              RETURNING job.id
            )
            SELECT finished.*
            FROM finished
            JOIN updated_job ON updated_job.id = finished.job_id
            """,
            (status, report_id, safe_error, item_id),
        ).fetchone()
    if row is None:
        raise ValueError(f"daily market brief history item not found or not active: {item_id}")
    return to_jsonable(row)


def request_history_job_cancel(job_id: int) -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            """
            WITH requested AS (
              UPDATE daily_market_brief_jobs AS job SET
                cancel_requested_at = COALESCE(job.cancel_requested_at, now()),
                updated_at = now()
              WHERE job.id = %s
                AND job.status IN ('queued', 'running')
              RETURNING job.id
            ), cancelled_items AS (
              UPDATE daily_market_brief_job_items AS item SET
                status = 'cancelled',
                finished_at = now(),
                updated_at = now()
              FROM requested
              WHERE item.job_id = requested.id
                AND item.status = 'queued'
              RETURNING item.job_id
            )
            UPDATE daily_market_brief_jobs AS job SET
              status = CASE
                WHEN EXISTS (
                  SELECT 1 FROM daily_market_brief_job_items AS item
                  WHERE item.job_id = job.id AND item.status = 'running'
                ) THEN job.status
                ELSE 'cancelled'
              END,
              completed_count = (
                SELECT count(*)::integer FROM daily_market_brief_job_items AS item
                WHERE item.job_id = job.id AND item.status IN ('completed', 'skipped', 'failed', 'cancelled')
              ),
              completed_at = CASE WHEN NOT EXISTS (
                SELECT 1 FROM daily_market_brief_job_items AS item
                WHERE item.job_id = job.id AND item.status = 'running'
              ) THEN now() ELSE NULL END,
              updated_at = now()
            FROM requested
            WHERE job.id = requested.id
            RETURNING job.*
            """,
            (job_id,),
        ).fetchone()
    return to_jsonable(row) if row else None


def requeue_stale_history_items(stale_before: datetime) -> int:
    with transaction() as conn:
        result = conn.execute(
            """
            UPDATE daily_market_brief_job_items
            SET
              status = 'queued',
              worker_name = NULL,
              claimed_at = NULL,
              heartbeat_at = NULL,
              updated_at = now()
            WHERE status = 'running'
              AND heartbeat_at < %s
              AND EXISTS (
                SELECT 1 FROM daily_market_brief_jobs AS job
                WHERE job.id = daily_market_brief_job_items.job_id
                  AND job.cancel_requested_at IS NULL
              )
            """,
            (stale_before,),
        )
    return int(result.rowcount)


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
    normalized = sorted(set(dates))
    if not normalized or any(not isinstance(value, date) for value in normalized):
        raise ValueError("dates must contain one or more date values")
    return normalized


def _normalize_choice(value: str, allowed: set[str], label: str) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned not in allowed:
        raise ValueError(f"{label} must be one of {', '.join(sorted(allowed))}")
    return cleaned


def _deduplicated_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "job_id": item["job_id"],
            "market": item["market"],
            "market_date": item["market_date"],
        }
        for item in items
    ]


def _sanitize_error_summary(error_summary: str | None) -> str | None:
    if not error_summary:
        return None
    cleaned = " ".join(str(error_summary).split())
    unsafe_markers = ("traceback", "password", "token", "secret", "api_key", "/", "\\\\")
    if any(marker in cleaned.lower() for marker in unsafe_markers):
        return "历史市场简报生成失败，请稍后重试。"
    return cleaned[:240]
