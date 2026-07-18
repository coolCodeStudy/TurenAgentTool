from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.serialization import to_jsonable


JOB_STATUSES = {"queued", "running", "completed", "partial", "failed", "cancelled"}
ITEM_STATUSES = {"queued", "running", "completed", "skipped", "failed", "cancelled"}
TERMINAL_ITEM_STATUSES = {"completed", "skipped", "failed", "cancelled"}
REQUEST_TYPES = {"single", "batch"}
SOURCES = {"web", "command", "scheduler_recovery", "agent"}
MAX_HISTORY_ITEMS = 120
MAX_DEDUP_RETRIES = 3
DEFAULT_MAX_ACTIVE_WEB_JOBS = 3
HISTORY_STALE_AFTER_SECONDS = 900
WEB_HISTORY_JOB_CAPACITY_MESSAGE = "当前历史简报任务较多，请等待已有任务完成后再试。"
PUBLIC_ERROR_SUMMARIES = {
    "generation_failed": "历史市场简报生成失败，请稍后重试。",
    "provider_timeout": "历史数据源响应超时，请稍后重试。",
    "provider_unavailable": "历史数据源暂时不可用，请稍后重试。",
    "historical_data_unavailable": "未找到该市场日期的可用历史数据。",
}


class WebHistoryJobCapacityError(ValueError):
    pass


def has_pending_history_items() -> bool:
    """Return whether the active durable history queue has claimable work."""

    with transaction(connect_timeout_seconds=5) as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM daily_market_brief_job_items AS item
              JOIN daily_market_brief_jobs AS job ON job.id = item.job_id
              WHERE job.status IN ('queued', 'running')
                AND job.cancel_requested_at IS NULL
                AND (
                  item.status = 'queued'
                  OR (
                    item.status = 'running'
                    AND item.heartbeat_at < now() - (%s * interval '1 second')
                  )
                )
            ) AS pending
            """,
            (HISTORY_STALE_AFTER_SECONDS,),
        ).fetchone()
    return bool(row and row.get("pending"))


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

    if source == "web":
        market, market_date = pairs[0]
        return create_web_history_job(market, market_date)

    with transaction() as conn:
        return _create_history_job_in_transaction(
            conn,
            pairs=pairs,
            request_type=request_type,
            source=source,
            force_refresh=bool(force_refresh),
        )


def create_web_history_job(
    market: str,
    market_date: date,
    *,
    max_active_jobs: int = DEFAULT_MAX_ACTIVE_WEB_JOBS,
) -> dict[str, Any]:
    normalized_markets = _normalize_markets([market])
    normalized_dates = _normalize_dates([market_date])
    active_limit = int(max_active_jobs)
    if active_limit < 1:
        raise ValueError("max_active_jobs must be positive")
    pair = (normalized_markets[0], normalized_dates[0])

    with transaction() as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("daily-market-brief:web-admission",),
        ).fetchone()
        _lock_market_date_keys(conn, [pair])
        active = _find_active_item(conn, *pair)
        if active is not None:
            active_job = _get_history_job(conn, int(active["job_id"]))
            if (
                active_job is not None
                and active_job.get("source") == "web"
                and active_job.get("request_type") == "single"
            ):
                active_job["deduplicated_items"] = _deduplicated_items([to_jsonable(active)])
                return active_job
            raise WebHistoryJobCapacityError(WEB_HISTORY_JOB_CAPACITY_MESSAGE)

        active_count = conn.execute(
            """
            SELECT count(*)::integer AS active_count
            FROM daily_market_brief_jobs
            WHERE source = 'web'
              AND status IN ('queued', 'running')
            """
        ).fetchone()
        if int((active_count or {}).get("active_count") or 0) >= active_limit:
            raise WebHistoryJobCapacityError(WEB_HISTORY_JOB_CAPACITY_MESSAGE)
        return _create_history_job_in_transaction(
            conn,
            pairs=[pair],
            request_type="single",
            source="web",
            force_refresh=False,
            market_date_keys_locked=True,
        )


def _create_history_job_in_transaction(
    conn: Any,
    *,
    pairs: list[tuple[str, date]],
    request_type: str,
    source: str,
    force_refresh: bool,
    market_date_keys_locked: bool = False,
) -> dict[str, Any]:
    if not market_date_keys_locked:
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


def get_public_web_history_job(job_id: int) -> dict[str, Any] | None:
    with transaction() as conn:
        return _get_public_web_history_job(conn, job_id)


def list_history_jobs(limit: int = 10) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 100))
    with transaction() as conn:
        rows = conn.execute(
            _history_job_select_sql(where="", order_by="ORDER BY job.created_at DESC", limit=True),
            (bounded_limit,),
        ).fetchall()
    return to_jsonable(rows)


def list_public_web_history_jobs(limit: int = 10) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 50))
    with transaction() as conn:
        rows = conn.execute(
            _history_job_select_sql(
                where="WHERE job.source = 'web' AND job.request_type = 'single'",
                order_by="ORDER BY job.created_at DESC",
                limit=True,
            ),
            (bounded_limit,),
        ).fetchall()
    return to_jsonable(rows)


def claim_next_history_item(worker_name: str) -> dict[str, Any] | None:
    cleaned_worker_name = (worker_name or "history-worker").strip() or "history-worker"
    lease_token = uuid4().hex
    with transaction() as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("daily-market-brief:global-history-claim",),
        ).fetchone()
        running = conn.execute(
            """
            SELECT item.id
            FROM daily_market_brief_job_items AS item
            WHERE item.status = 'running'
            LIMIT 1
            """
        ).fetchone()
        if running is not None:
            return None
        candidate = conn.execute(
            """
            SELECT item.id, item.job_id, item.market, item.market_date, job.force_refresh
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
    claimed = to_jsonable(row) if row else None
    if claimed is not None:
        claimed["force_refresh"] = bool(candidate.get("force_refresh"))
    return claimed


def finalize_history_item_report(
    item_id: int,
    *,
    worker_name: str,
    lease_token: str,
    attempt_count: int,
    context: dict[str, Any],
    markdown: str,
) -> dict[str, Any]:
    """Serialize cancellation, report persistence, and item completion."""
    cleaned_worker_name, cleaned_lease_token, normalized_attempt = _normalize_lease(
        worker_name, lease_token, attempt_count
    )
    with transaction() as conn:
        locked = _lock_active_history_item(
            conn,
            item_id,
            worker_name=cleaned_worker_name,
            lease_token=cleaned_lease_token,
            attempt_count=normalized_attempt,
        )
        if locked is None:
            raise ValueError(f"daily market brief history item lease is no longer active: {item_id}")
        context_market = str((context.get("market") or {}).get("code") or "").strip().upper()
        context_date = str(context.get("market_date") or "")
        if context_market != locked["market"] or context_date != locked["market_date"].isoformat():
            raise ValueError("daily market brief report context does not match the claimed history item")
        if locked["cancel_requested"]:
            row = _terminalize_history_item(
                conn,
                item_id,
                status="cancelled",
                worker_name=cleaned_worker_name,
                lease_token=cleaned_lease_token,
                attempt_count=normalized_attempt,
            )
        else:
            market = str(context["market"]["code"])
            market_date = str(context["market_date"])
            saved = repository.upsert_daily_market_brief_report_in_transaction(
                conn,
                market=market,
                market_date=market_date,
                summary=markdown,
                context=context,
                source_status=context.get("source_status") or {},
                story={
                    "narrative": context.get("narrative") or "",
                    "no_session": bool(context.get("no_session")),
                    "provider_mode": context.get("provider_mode"),
                    "generation_kind": context.get("generation_kind"),
                    "generated_at": context.get("generated_at") or {},
                },
            )
            row = _terminalize_history_item(
                conn,
                item_id,
                status="completed",
                report_id=int(saved["id"]),
                worker_name=cleaned_worker_name,
                lease_token=cleaned_lease_token,
                attempt_count=normalized_attempt,
            )
        _recompute_history_jobs(conn, [int(row["job_id"])])
    return to_jsonable(row)


def heartbeat_history_item(
    item_id: int,
    *,
    worker_name: str,
    lease_token: str,
    attempt_count: int,
) -> dict[str, Any] | None:
    """Renew an active lease and report whether its parent requested cancellation."""
    cleaned_worker_name = (worker_name or "").strip()
    cleaned_lease_token = (lease_token or "").strip()
    if not cleaned_worker_name or not cleaned_lease_token or int(attempt_count) < 1:
        raise ValueError("worker_name, lease_token, and positive attempt_count are required")
    with transaction() as conn:
        job = conn.execute(
            """
            SELECT
              job.id,
              (job.cancel_requested_at IS NOT NULL) AS cancel_requested
            FROM daily_market_brief_jobs AS job
            JOIN daily_market_brief_job_items AS item ON item.job_id = job.id
            WHERE item.id = %s
              AND item.status = 'running'
              AND item.worker_name = %s
              AND item.lease_token = %s
              AND item.attempt_count = %s
            FOR UPDATE OF job
            """,
            (item_id, cleaned_worker_name, cleaned_lease_token, int(attempt_count)),
        ).fetchone()
        if job is None:
            return None
        row = conn.execute(
            """
            UPDATE daily_market_brief_job_items AS item SET
              heartbeat_at = now(),
              updated_at = now()
            WHERE item.id = %s
              AND item.status = 'running'
              AND item.worker_name = %s
              AND item.lease_token = %s
              AND item.attempt_count = %s
            RETURNING item.id, item.job_id, item.heartbeat_at
            """,
            (item_id, cleaned_worker_name, cleaned_lease_token, int(attempt_count)),
        ).fetchone()
        if row is not None:
            conn.execute(
                """
                UPDATE daily_market_brief_jobs
                SET worker_heartbeat_at = %s, updated_at = now()
                WHERE id = %s
                """,
                (row["heartbeat_at"], row["job_id"]),
            )
    if row is None:
        return None
    result = to_jsonable(row)
    result["cancel_requested"] = bool(job["cancel_requested"])
    return result


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
    cleaned_worker_name, cleaned_lease_token, normalized_attempt = _normalize_lease(
        worker_name, lease_token, attempt_count
    )
    public_error_code, public_error_summary = _resolve_public_error(status, error_code, error_summary)
    with transaction() as conn:
        locked_job = _lock_history_job_for_item(conn, item_id)
        if locked_job is None:
            raise ValueError(f"daily market brief history item not found: {item_id}")
        if locked_job.get("cancel_requested") and status != "cancelled":
            status = "cancelled"
            report_id = None
            public_error_code = None
            public_error_summary = None
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
                normalized_attempt,
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
        SELECT job.id, (job.cancel_requested_at IS NOT NULL) AS cancel_requested
        FROM daily_market_brief_jobs AS job
        JOIN daily_market_brief_job_items AS item ON item.job_id = job.id
        WHERE item.id = %s
        FOR UPDATE OF job
        """,
        (item_id,),
    ).fetchone()


def _lock_active_history_item(
    conn: Any,
    item_id: int,
    *,
    worker_name: str,
    lease_token: str,
    attempt_count: int,
) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT
          job.id AS job_id,
          item.market,
          item.market_date,
          (job.cancel_requested_at IS NOT NULL) AS cancel_requested
        FROM daily_market_brief_jobs AS job
        JOIN daily_market_brief_job_items AS item ON item.job_id = job.id
        WHERE item.id = %s
          AND item.status = 'running'
          AND item.worker_name = %s
          AND item.lease_token = %s
          AND item.attempt_count = %s
        FOR UPDATE OF job
        """,
        (item_id, worker_name, lease_token, attempt_count),
    ).fetchone()


def _terminalize_history_item(
    conn: Any,
    item_id: int,
    *,
    status: str,
    worker_name: str,
    lease_token: str,
    attempt_count: int,
    report_id: int | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        UPDATE daily_market_brief_job_items AS item SET
          status = %s,
          report_id = %s,
          error_code = NULL,
          error_summary = NULL,
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
        (status, report_id, item_id, worker_name, lease_token, attempt_count),
    ).fetchone()
    if row is None:
        raise ValueError(f"daily market brief history item lease is no longer active: {item_id}")
    return row


def _normalize_lease(worker_name: str, lease_token: str, attempt_count: int) -> tuple[str, str, int]:
    cleaned_worker_name = (worker_name or "").strip()
    cleaned_lease_token = (lease_token or "").strip()
    normalized_attempt = int(attempt_count)
    if not cleaned_worker_name or not cleaned_lease_token or normalized_attempt < 1:
        raise ValueError("worker_name, lease_token, and positive attempt_count are required")
    return cleaned_worker_name, cleaned_lease_token, normalized_attempt


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


def _get_public_web_history_job(conn: Any, job_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        _history_job_select_sql(
            where="WHERE job.id = %s AND job.source = 'web' AND job.request_type = 'single'",
            order_by="",
            limit=False,
        ),
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
