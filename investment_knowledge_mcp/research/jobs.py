from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.serialization import to_jsonable


TERMINAL_STATUSES = {"drafted", "needs_review", "imported", "failed", "cancelled"}
ACTIVE_STATUSES = {"queued", "running"}


def create_research_job(
    symbol: str,
    market: str,
    name: str | None = None,
    priority: str = "normal",
    source_policy: str = "broad_search",
    provider: str = "codex",
    auto_import: bool = True,
    import_needs_review: bool = False,
    refresh: bool = False,
    source: str | None = None,
    sender: str | None = None,
) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    market = _normalize_market(market)
    priority = _normalize_choice(priority, {"low", "normal", "high"}, "normal")
    source_policy = _normalize_choice(source_policy, {"official_first", "broad_search", "user_sources"}, "broad_search")
    provider = _normalize_choice(provider, {"codex", "openai", "none"}, "codex")

    with transaction() as conn:
        existing = conn.execute(
            """
            SELECT *
            FROM research_jobs
            WHERE symbol = %s
              AND market = %s
              AND status IN ('queued', 'running')
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (symbol, market),
        ).fetchone()
        if existing is not None:
            return to_jsonable(existing)

        row = conn.execute(
            """
            INSERT INTO research_jobs (
              symbol, market, name, priority, source_policy, provider,
              auto_import, import_needs_review, refresh, source, sender
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                symbol,
                market,
                name,
                priority,
                source_policy,
                provider,
                auto_import,
                import_needs_review,
                refresh,
                source,
                sender,
            ),
        ).fetchone()
    return to_jsonable(row)


def list_research_jobs(status: str | None = "queued", limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with transaction() as conn:
        if status is None or status == "all":
            rows = conn.execute(
                """
                SELECT *
                FROM research_jobs
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM research_jobs
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (status, limit),
            ).fetchall()
    return to_jsonable(rows)


def claim_next_research_job(worker_name: str = "research-agent-worker") -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            """
            WITH next_job AS (
              SELECT id
              FROM research_jobs
              WHERE status = 'queued'
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
            UPDATE research_jobs AS job SET
              status = 'running',
              worker_name = %s,
              worker_started_at = COALESCE(worker_started_at, now()),
              updated_at = now(),
              worker_log = concat_ws(E'\n', NULLIF(worker_log, ''), %s::text)
            FROM next_job
            WHERE job.id = next_job.id
            RETURNING job.*
            """,
            (worker_name, f"{worker_name}: claimed research job"),
        ).fetchone()
    return to_jsonable(row) if row else None


def update_research_job(
    job_id: int,
    status: str,
    result_summary: str | None = None,
    error: str | None = None,
    artifact_dir: str | None = None,
    artifacts: dict[str, Any] | None = None,
    source_discovery: dict[str, Any] | None = None,
    worker_log: str | None = None,
) -> dict[str, Any]:
    status = _normalize_choice(status, {"queued", "running", *TERMINAL_STATUSES}, "failed")
    with transaction() as conn:
        row = conn.execute(
            """
            UPDATE research_jobs SET
              status = %s,
              result_summary = COALESCE(%s, result_summary),
              error = %s,
              artifact_dir = COALESCE(%s, artifact_dir),
              artifacts = CASE WHEN %s::jsonb IS NULL THEN artifacts ELSE %s::jsonb END,
              source_discovery = CASE WHEN %s::jsonb IS NULL THEN source_discovery ELSE %s::jsonb END,
              worker_log = concat_ws(E'\n', NULLIF(worker_log, ''), NULLIF(%s, '')),
              worker_finished_at = CASE
                WHEN %s IN ('drafted', 'needs_review', 'imported', 'failed', 'cancelled') THEN now()
                ELSE worker_finished_at
              END,
              updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (
                status,
                result_summary,
                error,
                artifact_dir,
                Jsonb(artifacts) if artifacts is not None else None,
                Jsonb(artifacts) if artifacts is not None else None,
                Jsonb(source_discovery) if source_discovery is not None else None,
                Jsonb(source_discovery) if source_discovery is not None else None,
                worker_log,
                status,
                job_id,
            ),
        ).fetchone()
        if row is None:
            raise ValueError(f"research job not found: {job_id}")
    return to_jsonable(row)


def requeue_research_jobs(status: str = "failed", limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with transaction() as conn:
        rows = conn.execute(
            """
            WITH target_jobs AS (
              SELECT id
              FROM research_jobs
              WHERE status = %s
              ORDER BY updated_at DESC
              LIMIT %s
            )
            UPDATE research_jobs AS job SET
              status = 'queued',
              error = NULL,
              worker_name = NULL,
              worker_started_at = NULL,
              worker_finished_at = NULL,
              updated_at = now(),
              worker_log = concat_ws(E'\n', NULLIF(worker_log, ''), 'requeued by command')
            FROM target_jobs
            WHERE job.id = target_jobs.id
            RETURNING job.*
            """,
            (status, limit),
        ).fetchall()
    return to_jsonable(rows)


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_market(market: str) -> str:
    return market.strip().upper()


def _normalize_choice(value: str, allowed: set[str], default: str) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in allowed else default
