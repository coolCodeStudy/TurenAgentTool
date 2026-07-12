from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import threading
from pathlib import Path
import unittest
from unittest import mock
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from investment_knowledge_mcp import daily_market_jobs as jobs
from investment_knowledge_mcp.config import get_config


class FakeCursor:
    def __init__(self, one: dict | None = None, many: list[dict] | None = None, rowcount: int = 0) -> None:
        self.one = one
        self.many = many if many is not None else ([] if one is None else [one])
        self.rowcount = rowcount

    def fetchone(self) -> dict | None:
        return self.one

    def fetchall(self) -> list[dict]:
        return self.many


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple | None]] = []
        self.active_item: dict | None = None
        self.existing_report: dict | None = None
        self.created_job = {
            "id": 41,
            "request_type": "batch",
            "source": "command",
            "status": "queued",
            "force_refresh": False,
        }
        self.created_items: list[dict] = []
        self.job_detail: dict | None = None
        self.listed_jobs: list[dict] = []
        self.claimed_item: dict | None = None
        self.finished_item: dict | None = None
        self.cancelled_job: dict | None = None
        self.stale_count = 0

    def execute(self, query: str, params: tuple | None = None) -> FakeCursor:
        self.queries.append((query, params))
        compact = " ".join(query.split())
        if compact.startswith("SELECT pg_advisory_xact_lock"):
            return FakeCursor({"pg_advisory_xact_lock": None})
        if compact.startswith("SELECT item.id FROM daily_market_brief_job_items"):
            return FakeCursor()
        if compact.startswith("SELECT count(*)::integer AS active_count"):
            return FakeCursor({"active_count": 0})
        if "FOR UPDATE OF job" in compact and "WHERE item.id = %s" in compact:
            job_id = (self.finished_item or {}).get("job_id", 41)
            return FakeCursor({"id": job_id})
        if "WHERE job.id = ANY(%s)" in compact and "ORDER BY job.id FOR UPDATE" in compact:
            return FakeCursor({"id": 41}, [{"id": 41}])
        if compact.startswith("SELECT DISTINCT item.job_id"):
            rows = [{"job_id": 41}] if self.stale_count else []
            return FakeCursor(many=rows)
        if "SELECT item.id, item.job_id, item.market, item.market_date" in compact and "AND item.status IN ('queued', 'running')" in compact:
            if self.active_item and params == (self.active_item["market"], self.active_item["market_date"]):
                return FakeCursor(self.active_item)
            return FakeCursor()
        if "FROM review_reports" in compact:
            return FakeCursor(self.existing_report)
        if "INSERT INTO daily_market_brief_jobs" in compact:
            return FakeCursor(dict(self.created_job))
        if "INSERT INTO daily_market_brief_job_items" in compact:
            item = self.created_items.pop(0)
            return FakeCursor(dict(item))
        if "FOR UPDATE OF job SKIP LOCKED" in compact:
            if self.claimed_item is None:
                return FakeCursor()
            return FakeCursor(
                {
                    "id": self.claimed_item["id"],
                    "job_id": self.claimed_item.get("job_id", 41),
                    "market": self.claimed_item.get("market", "CN"),
                    "market_date": self.claimed_item.get("market_date", date(2026, 7, 1)),
                }
            )
        if "UPDATE daily_market_brief_job_items AS item" in compact and "SET status = 'running'" in compact:
            return FakeCursor(self.claimed_item)
        if "UPDATE daily_market_brief_jobs AS job" in compact and "current_market = %s" in compact:
            return FakeCursor()
        if "UPDATE daily_market_brief_job_items AS item" in compact and "SET status = %s" in compact:
            return FakeCursor(self.finished_item)
        if compact.startswith("WITH aggregates AS") and "cancelled_count" in compact:
            row = self.cancelled_job or self.job_detail
            return FakeCursor(row, [row] if row else [])
        if "UPDATE daily_market_brief_jobs AS job" in compact and "cancel_requested_at" in compact:
            return FakeCursor(self.cancelled_job)
        if "UPDATE daily_market_brief_job_items AS item" in compact and "status = 'cancelled'" in compact:
            return FakeCursor(many=[])
        if "UPDATE daily_market_brief_job_items AS item" in compact and "heartbeat_at < %s" in compact:
            return FakeCursor(many=[{"job_id": 41} for _ in range(self.stale_count)], rowcount=self.stale_count)
        if "FROM daily_market_brief_jobs AS job" in compact and "WHERE job.id = %s" in compact:
            return FakeCursor(self.job_detail)
        if "FROM daily_market_brief_jobs AS job" in compact and "ORDER BY job.created_at DESC" in compact:
            return FakeCursor(many=self.listed_jobs)
        raise AssertionError(f"unexpected SQL: {compact}")


@contextmanager
def fake_transaction(connection: FakeConnection):
    yield connection


class StatefulQueueConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple | None]] = []
        self.jobs = {
            41: {
                "id": 41,
                "status": "running",
                "total_count": 2,
                "completed_count": 0,
                "succeeded_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "cancelled_count": 0,
                "cancel_requested_at": None,
                "current_market": "CN",
                "current_market_date": date(2026, 7, 1),
            }
        }
        self.items = {
            101: {
                "id": 101,
                "job_id": 41,
                "market": "CN",
                "market_date": date(2026, 7, 1),
                "status": "running",
                "attempt_count": 1,
                "worker_name": "worker-a",
                "lease_token": "lease-a",
                "heartbeat_at": datetime(2026, 7, 12, 0, 0, tzinfo=timezone.utc),
                "error_code": None,
                "error_summary": None,
            },
            102: {
                "id": 102,
                "job_id": 41,
                "market": "HK",
                "market_date": date(2026, 7, 1),
                "status": "completed",
                "attempt_count": 1,
                "worker_name": None,
                "lease_token": None,
                "heartbeat_at": None,
                "error_code": None,
                "error_summary": None,
            },
        }

    def execute(self, query: str, params: tuple | None = None) -> FakeCursor:
        self.queries.append((query, params))
        compact = " ".join(query.split())
        if compact.startswith("SELECT pg_advisory_xact_lock"):
            return FakeCursor({"pg_advisory_xact_lock": None})
        if compact.startswith("SELECT item.id FROM daily_market_brief_job_items"):
            running = next((item for item in self.items.values() if item["status"] == "running"), None)
            return FakeCursor({"id": running["id"]} if running else None)
        if "FOR UPDATE OF job" in compact and "WHERE item.id = %s" in compact:
            item = self.items.get(params[0])
            return FakeCursor({"id": item["job_id"]} if item else None)
        if "WHERE job.id = ANY(%s)" in compact and "ORDER BY job.id FOR UPDATE" in compact:
            rows = [
                {"id": job_id}
                for job_id in params[0]
                if job_id in self.jobs
                and ("job.status IN" not in compact or self.jobs[job_id]["status"] in {"queued", "running"})
            ]
            return FakeCursor(rows[0] if len(rows) == 1 else None, rows)
        if compact.startswith("SELECT DISTINCT item.job_id"):
            cutoff = params[0]
            rows = [
                {"job_id": item["job_id"]}
                for item in self.items.values()
                if item["status"] == "running"
                and item["heartbeat_at"] < cutoff
                and not self.jobs[item["job_id"]]["cancel_requested_at"]
            ]
            return FakeCursor(many=rows)
        if "FOR UPDATE OF job SKIP LOCKED" in compact:
            queued = next((item for item in self.items.values() if item["status"] == "queued"), None)
            return FakeCursor(dict(queued) if queued else None)
        if compact.startswith("UPDATE daily_market_brief_job_items AS item SET") and "AND item.lease_token = %s" in compact:
            status, report_id, error_code, error_summary, item_id, worker_name, lease_token, attempt_count = params
            item = self.items[item_id]
            if not (
                item["status"] == "running"
                and item["worker_name"] == worker_name
                and item["lease_token"] == lease_token
                and item["attempt_count"] == attempt_count
            ):
                return FakeCursor()
            item.update(
                status=status,
                report_id=report_id,
                error_code=error_code,
                error_summary=error_summary,
                worker_name=None,
                lease_token=None,
                heartbeat_at=None,
            )
            return FakeCursor(dict(item))
        if compact.startswith("UPDATE daily_market_brief_job_items AS item SET status = 'running'"):
            worker_name, lease_token, item_id = params
            item = self.items[item_id]
            if item["status"] != "queued":
                return FakeCursor()
            item.update(
                status="running",
                attempt_count=item["attempt_count"] + 1,
                worker_name=worker_name,
                lease_token=lease_token,
                heartbeat_at=datetime.now(timezone.utc),
            )
            return FakeCursor(dict(item))
        if compact.startswith("WITH aggregates AS") and "cancelled_count" in compact:
            job_ids = list(params[0])
            updated = [self._recompute_job(job_id) for job_id in job_ids]
            return FakeCursor(updated[0] if len(updated) == 1 else None, updated)
        if compact.startswith("UPDATE daily_market_brief_jobs AS job SET") and "cancel_requested_at" in compact:
            job = self.jobs.get(params[0])
            if job is None or job["status"] not in {"queued", "running"}:
                return FakeCursor()
            job["cancel_requested_at"] = "requested"
            return FakeCursor(dict(job))
        if compact.startswith("UPDATE daily_market_brief_job_items AS item SET") and "status = 'cancelled'" in compact:
            job_id = params[0]
            cancelled = []
            for item in self.items.values():
                if item["job_id"] == job_id and item["status"] == "queued":
                    item["status"] = "cancelled"
                    item["worker_name"] = None
                    item["lease_token"] = None
                    cancelled.append({"job_id": job_id})
            return FakeCursor(many=cancelled, rowcount=len(cancelled))
        if compact.startswith("UPDATE daily_market_brief_job_items AS item SET status = 'queued'"):
            cutoff = params[0]
            recovered = []
            for item in self.items.values():
                job = self.jobs[item["job_id"]]
                if item["status"] == "running" and item["heartbeat_at"] < cutoff and not job["cancel_requested_at"]:
                    item.update(status="queued", worker_name=None, lease_token=None, heartbeat_at=None)
                    recovered.append({"job_id": item["job_id"]})
            return FakeCursor(many=recovered, rowcount=len(recovered))
        if compact.startswith("UPDATE daily_market_brief_jobs AS job SET") and "current_market = %s" in compact:
            market, market_date, job_id = params
            self.jobs[job_id].update(status="running", current_market=market, current_market_date=market_date)
            return FakeCursor()
        raise AssertionError(f"unexpected SQL: {compact}")

    def _recompute_job(self, job_id: int) -> dict:
        job = self.jobs[job_id]
        items = [item for item in self.items.values() if item["job_id"] == job_id]
        counts = {status: sum(item["status"] == status for item in items) for status in jobs.ITEM_STATUSES}
        job.update(
            total_count=len(items),
            completed_count=sum(counts[status] for status in jobs.TERMINAL_ITEM_STATUSES),
            succeeded_count=counts["completed"],
            skipped_count=counts["skipped"],
            failed_count=counts["failed"],
            cancelled_count=counts["cancelled"],
        )
        running = next((item for item in items if item["status"] == "running"), None)
        if running:
            job.update(status="running", current_market=running["market"], current_market_date=running["market_date"])
        elif counts["queued"]:
            job.update(status="queued", current_market=None, current_market_date=None)
        elif job["cancel_requested_at"]:
            job.update(status="cancelled", current_market=None, current_market_date=None)
        elif counts["failed"] == 0:
            job.update(status="completed", current_market=None, current_market_date=None)
        elif counts["completed"] + counts["skipped"] == 0:
            job.update(status="failed", current_market=None, current_market_date=None)
        else:
            job.update(status="partial", current_market=None, current_market_date=None)
        return dict(job)


class DedupRaceConnection:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple | None]] = []
        self.active_reads = 0

    def execute(self, query: str, params: tuple | None = None) -> FakeCursor:
        self.queries.append((query, params))
        compact = " ".join(query.split())
        if compact.startswith("SELECT pg_advisory_xact_lock"):
            return FakeCursor({"pg_advisory_xact_lock": None})
        if "SELECT item.id, item.job_id, item.market, item.market_date" in compact:
            self.active_reads += 1
            if self.active_reads == 1:
                return FakeCursor()
            return FakeCursor({"id": 901, "job_id": 9, "market": "CN", "market_date": date(2026, 7, 1)})
        if "FROM review_reports" in compact:
            return FakeCursor()
        if "INSERT INTO daily_market_brief_jobs" in compact:
            return FakeCursor({"id": 41, "status": "queued"})
        if "INSERT INTO daily_market_brief_job_items" in compact:
            if "ON CONFLICT (market, market_date)" not in compact:
                raise AssertionError("active partial-index conflict is not handled")
            return FakeCursor()
        if compact.startswith("DELETE FROM daily_market_brief_jobs"):
            return FakeCursor({"id": 41})
        if "FROM daily_market_brief_jobs AS job" in compact and "WHERE job.id = %s" in compact:
            return FakeCursor({"id": 9, "status": "queued", "total_count": 1, "items": []})
        raise AssertionError(f"unexpected SQL: {compact}")


class ConflictBecomesTerminalConnection(DedupRaceConnection):
    def __init__(self) -> None:
        super().__init__()
        self.item_insert_attempts = 0

    def execute(self, query: str, params: tuple | None = None) -> FakeCursor:
        compact = " ".join(query.split())
        if compact.startswith("SELECT pg_advisory_xact_lock"):
            self.queries.append((query, params))
            return FakeCursor({"pg_advisory_xact_lock": None})
        if "SELECT item.id, item.job_id, item.market, item.market_date" in compact:
            self.queries.append((query, params))
            self.active_reads += 1
            return FakeCursor()
        if "INSERT INTO daily_market_brief_job_items" in compact:
            self.queries.append((query, params))
            self.item_insert_attempts += 1
            if self.item_insert_attempts == 1:
                return FakeCursor()
            return FakeCursor(
                {
                    "id": 902,
                    "job_id": 41,
                    "market": "CN",
                    "market_date": date(2026, 7, 1),
                    "status": "queued",
                }
            )
        if "SELECT item.id, item.job_id, item.market, item.market_date, item.status" in compact:
            self.queries.append((query, params))
            return FakeCursor()
        if compact.startswith("WITH aggregates AS"):
            self.queries.append((query, params))
            return FakeCursor({"id": 41, "status": "queued", "total_count": 1}, [{"id": 41, "status": "queued", "total_count": 1}])
        if "FROM daily_market_brief_jobs AS job" in compact and "WHERE job.id = %s" in compact:
            self.queries.append((query, params))
            return FakeCursor({"id": 41, "status": "queued", "total_count": 1, "items": []})
        return super().execute(query, params)


class PersistentConflictConnection(ConflictBecomesTerminalConnection):
    def execute(self, query: str, params: tuple | None = None) -> FakeCursor:
        compact = " ".join(query.split())
        if "FROM daily_market_brief_jobs AS job" in compact and "WHERE job.id = %s" in compact:
            self.queries.append((query, params))
            return FakeCursor({"id": 9, "status": "queued", "total_count": 1, "items": []})
        if "INSERT INTO daily_market_brief_job_items" in compact:
            self.queries.append((query, params))
            self.item_insert_attempts += 1
            if "DO UPDATE" in compact:
                return FakeCursor(
                    {
                        "id": 901,
                        "job_id": 9,
                        "market": "CN",
                        "market_date": date(2026, 7, 1),
                        "status": "queued",
                    }
                )
            return FakeCursor()
        return super().execute(query, params)


class BarrierConnection:
    def __init__(self, connection: psycopg.Connection, recompute_barrier: threading.Barrier) -> None:
        self.connection = connection
        self.recompute_barrier = recompute_barrier
        self.parent_locked = False

    def execute(self, query: str, params: tuple | None = None):
        compact = " ".join(query.split())
        if compact.startswith("WITH aggregates AS") and not self.parent_locked:
            self.recompute_barrier.wait(timeout=5)
        result = self.connection.execute(query, params)
        if "FOR UPDATE OF job" in compact and "daily_market_brief_jobs AS job" in compact:
            self.parent_locked = True
        return result


class ConflictTerminalPostgresConnection:
    def __init__(self, connection: psycopg.Connection, terminalizer: psycopg.Connection, conflicting_item_id: int) -> None:
        self.connection = connection
        self.terminalizer = terminalizer
        self.conflicting_item_id = conflicting_item_id
        self.active_read_missed = False
        self.conflict_terminalized = False

    def execute(self, query: str, params: tuple | None = None):
        compact = " ".join(query.split())
        if "SELECT item.id, item.job_id, item.market, item.market_date" in compact and not self.active_read_missed:
            self.active_read_missed = True
            return FakeCursor()
        result = self.connection.execute(query, params)
        if "INSERT INTO daily_market_brief_job_items" in compact and not self.conflict_terminalized:
            self.terminalizer.execute(
                "UPDATE daily_market_brief_job_items SET status = 'completed', finished_at = now() WHERE id = %s",
                (self.conflicting_item_id,),
            )
            self.conflict_terminalized = True
        return result


class DailyMarketJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = FakeConnection()
        self.transaction_patch = mock.patch.object(
            jobs, "transaction", side_effect=lambda: fake_transaction(self.connection)
        )
        self.transaction_patch.start()

    def tearDown(self) -> None:
        self.transaction_patch.stop()

    def test_schema_defines_job_and_item_queue_contract(self) -> None:
        schema = (Path(__file__).resolve().parents[1] / "db" / "schema.sql").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS daily_market_brief_jobs", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_market_brief_job_items", schema)
        self.assertIn("ON DELETE CASCADE", schema)
        self.assertIn("UNIQUE (job_id, market, market_date)", schema)
        self.assertIn("cancel_requested_at", schema)
        self.assertIn("heartbeat_at", schema)
        self.assertIn("CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled'))", schema)
        self.assertIn("CHECK (status IN ('queued', 'running', 'completed', 'skipped', 'failed', 'cancelled'))", schema)
        self.assertIn("idx_daily_market_brief_job_items_active", schema)

    def test_create_normalizes_and_deduplicates_market_dates_with_aggregate_progress(self) -> None:
        self.connection.created_items = [
            {"id": 101, "job_id": 41, "market": "CN", "market_date": date(2026, 7, 1), "status": "queued"},
            {"id": 102, "job_id": 41, "market": "US", "market_date": date(2026, 7, 1), "status": "queued"},
        ]
        self.connection.job_detail = {
            "id": 41,
            "total_count": 2,
            "completed_count": 0,
            "succeeded_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "items": self.connection.created_items,
        }

        created = jobs.create_history_job(
            [" cn ", "US", "CN"],
            [date(2026, 7, 1), date(2026, 7, 1)],
            request_type="batch",
            source="command",
        )

        self.assertEqual(41, created["id"])
        item_inserts = [params for query, params in self.connection.queries if "INSERT INTO daily_market_brief_job_items" in query]
        self.assertEqual(2, len(item_inserts))
        self.assertEqual({("CN", date(2026, 7, 1)), ("US", date(2026, 7, 1))}, {(params[1], params[2]) for params in item_inserts})
        self.assertEqual(2, created["total_count"])

    def test_batch_rejects_more_than_120_market_dates(self) -> None:
        dates = [date(2026, 1, 1) + timedelta(days=index) for index in range(41)]

        with self.assertRaisesRegex(ValueError, "最多 120"):
            jobs.create_history_job(["CN", "HK", "US"], dates, request_type="batch", source="command")

        self.assertEqual([], self.connection.queries)

    def test_create_omits_already_active_market_date_and_returns_dedup_metadata(self) -> None:
        self.connection.active_item = {"id": 17, "job_id": 9, "market": "CN", "market_date": date(2026, 7, 1)}
        self.connection.created_items = [
            {"id": 102, "job_id": 41, "market": "HK", "market_date": date(2026, 7, 1), "status": "queued"}
        ]
        self.connection.job_detail = {"id": 41, "total_count": 1, "items": []}

        created = jobs.create_history_job(
            ["CN", "HK"], [date(2026, 7, 1)], request_type="batch", source="command"
        )

        self.assertEqual(1, created["total_count"])
        self.assertEqual([{"job_id": 9, "market": "CN", "market_date": "2026-07-01"}], created["deduplicated_items"])

    def test_existing_report_becomes_skipped_item_unless_force_refresh(self) -> None:
        self.connection.existing_report = {"id": 77}
        self.connection.created_items = [
            {"id": 101, "job_id": 41, "market": "CN", "market_date": date(2026, 7, 1), "status": "skipped", "report_id": 77, "skip_reason": "existing_report"}
        ]
        self.connection.job_detail = {"id": 41, "total_count": 1, "skipped_count": 1, "items": []}

        created = jobs.create_history_job(["CN"], [date(2026, 7, 1)], request_type="single", source="web")

        self.assertEqual(1, created["skipped_count"])
        params = next(params for query, params in self.connection.queries if "INSERT INTO daily_market_brief_job_items" in query)
        self.assertEqual("skipped", params[3])
        self.assertEqual(77, params[4])
        self.assertEqual("existing_report", params[5])

    def test_list_history_jobs_is_newest_first_and_uses_bounded_limit(self) -> None:
        self.connection.listed_jobs = [{"id": 9}, {"id": 8}]

        listed = jobs.list_history_jobs(limit=999)

        self.assertEqual([9, 8], [job["id"] for job in listed])
        query, params = self.connection.queries[-1]
        self.assertIn("ORDER BY job.created_at DESC", query)
        self.assertEqual((100,), params)

    def test_public_web_history_jobs_are_filtered_to_single_web_jobs(self) -> None:
        self.connection.listed_jobs = [{"id": 9}, {"id": 8}]

        listed = jobs.list_public_web_history_jobs(limit=999)

        self.assertEqual([9, 8], [job["id"] for job in listed])
        query, params = self.connection.queries[-1]
        self.assertIn("job.source = 'web'", query)
        self.assertIn("job.request_type = 'single'", query)
        self.assertEqual((50,), params)

    def test_claims_exactly_one_item_with_skip_locked_in_one_transaction(self) -> None:
        self.connection.claimed_item = {
            "id": 101,
            "status": "running",
            "worker_name": "history-worker",
            "lease_token": "generated",
            "attempt_count": 1,
            "job_id": 41,
            "market": "CN",
            "market_date": date(2026, 7, 1),
        }

        claimed = jobs.claim_next_history_item("history-worker")

        self.assertEqual(101, claimed["id"])
        self.assertEqual(5, len(self.connection.queries))
        query, params = self.connection.queries[2]
        self.assertIn("FOR UPDATE OF job SKIP LOCKED", query)
        self.assertIn("status = 'queued'", query)
        claim_query, claim_params = self.connection.queries[3]
        self.assertEqual("history-worker", claim_params[0])
        self.assertTrue(claim_params[1])
        self.assertIn("lease_token = %s", claim_query)

    def test_finish_item_updates_aggregate_and_sanitizes_error(self) -> None:
        self.connection.finished_item = {
            "id": 101,
            "job_id": 41,
            "status": "failed",
            "error_code": "generation_failed",
            "error_summary": jobs.PUBLIC_ERROR_SUMMARIES["generation_failed"],
        }
        self.connection.job_detail = {"id": 41, "status": "failed"}

        finished = jobs.finish_history_item(
            101,
            status="failed",
            worker_name="history-worker",
            lease_token="lease-1",
            attempt_count=1,
            error_summary="Traceback: /srv/private.py password=secret\nprovider timeout",
        )

        self.assertEqual("generation_failed", finished["error_code"])
        self.assertEqual(jobs.PUBLIC_ERROR_SUMMARIES["generation_failed"], finished["error_summary"])
        query, params = self.connection.queries[1]
        self.assertNotIn("daily_market_brief_jobs", query)
        self.assertNotIn("/srv/private.py", str(params))
        self.assertNotIn("password=secret", str(params))
        self.assertEqual(3, len(self.connection.queries))

    def test_cancel_requests_stop_for_queued_items_and_preserves_running_item_for_cooperative_cancel(self) -> None:
        self.connection.cancelled_job = {"id": 41, "status": "running", "cancel_requested_at": "2026-07-12T00:00:00+00:00"}

        cancelled = jobs.request_history_job_cancel(41)

        self.assertEqual(41, cancelled["id"])
        query, params = self.connection.queries[1]
        self.assertIn("cancel_requested_at = COALESCE(job.cancel_requested_at, now())", query)
        self.assertEqual((41,), params)
        self.assertEqual(4, len(self.connection.queries))

    def test_requeues_stale_running_items_using_heartbeat_cutoff(self) -> None:
        self.connection.stale_count = 3
        cutoff = datetime(2026, 7, 12, 0, 0, tzinfo=timezone.utc)

        recovered = jobs.requeue_stale_history_items(cutoff)

        self.assertEqual(3, recovered)
        query, params = next(
            (query, params)
            for query, params in self.connection.queries
            if "UPDATE daily_market_brief_job_items AS item" in query
        )
        self.assertIn("status = 'running'", query)
        self.assertIn("heartbeat_at < %s", query)
        self.assertEqual((cutoff, [41]), params)


class DailyMarketJobsReviewRegressionTests(unittest.TestCase):
    def test_schema_enforces_lease_and_aggregate_invariants(self) -> None:
        schema = (Path(__file__).resolve().parents[1] / "db" / "schema.sql").read_text(encoding="utf-8")

        self.assertIn("cancelled_count INTEGER NOT NULL DEFAULT 0", schema)
        self.assertIn("lease_token TEXT", schema)
        self.assertIn("error_code TEXT", schema)
        self.assertIn("CHECK (completed_count <= total_count)", schema)
        self.assertIn(
            "CHECK (completed_count = succeeded_count + skipped_count + failed_count + cancelled_count)",
            schema,
        )

    def test_public_job_detail_does_not_expose_worker_lease_token(self) -> None:
        detail_sql = jobs._history_job_select_sql(where="WHERE job.id = %s", order_by="", limit=False)

        self.assertNotIn("'lease_token'", detail_sql)

    def test_last_running_item_finishes_then_parent_terminalizes_in_second_statement(self) -> None:
        connection = StatefulQueueConnection()
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            finished = jobs.finish_history_item(
                101,
                status="completed",
                report_id=77,
                worker_name="worker-a",
                lease_token="lease-a",
                attempt_count=1,
            )

        self.assertEqual("completed", finished["status"])
        self.assertEqual("completed", connection.jobs[41]["status"])
        self.assertEqual(2, connection.jobs[41]["completed_count"])
        self.assertEqual(2, connection.jobs[41]["succeeded_count"])
        self.assertEqual(3, len(connection.queries))
        self.assertIn("FOR UPDATE OF job", connection.queries[0][0])
        self.assertNotIn("daily_market_brief_jobs", connection.queries[1][0])
        self.assertIn("daily_market_brief_jobs", connection.queries[2][0])

    def test_finish_locks_parent_before_item_mutation(self) -> None:
        connection = StatefulQueueConnection()
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            jobs.finish_history_item(
                101,
                status="completed",
                worker_name="worker-a",
                lease_token="lease-a",
                attempt_count=1,
            )

        self.assertIn("FOR UPDATE OF job", connection.queries[0][0])
        self.assertIn("UPDATE daily_market_brief_job_items", connection.queries[1][0])

    def test_cancellation_updates_queued_items_then_recomputes_all_counts(self) -> None:
        connection = StatefulQueueConnection()
        connection.items[101].update(status="running")
        connection.items[103] = {
            "id": 103,
            "job_id": 41,
            "market": "US",
            "market_date": date(2026, 7, 1),
            "status": "queued",
            "attempt_count": 0,
            "worker_name": None,
            "lease_token": None,
            "heartbeat_at": None,
            "error_code": None,
            "error_summary": None,
        }
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            cancelled = jobs.request_history_job_cancel(41)

        self.assertEqual("running", cancelled["status"])
        self.assertEqual("cancelled", connection.items[103]["status"])
        self.assertEqual(3, cancelled["total_count"])
        self.assertEqual(2, cancelled["completed_count"])
        self.assertEqual(1, cancelled["succeeded_count"])
        self.assertEqual(1, cancelled["cancelled_count"])
        self.assertEqual(4, len(connection.queries))

    def test_cancellation_terminalizes_job_when_no_item_remains_running(self) -> None:
        connection = StatefulQueueConnection()
        connection.items[101].update(
            status="queued",
            worker_name=None,
            lease_token=None,
            heartbeat_at=None,
        )
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            cancelled = jobs.request_history_job_cancel(41)

        self.assertEqual("cancelled", cancelled["status"])
        self.assertEqual(2, cancelled["completed_count"])
        self.assertEqual(1, cancelled["succeeded_count"])
        self.assertEqual(1, cancelled["cancelled_count"])

    def test_cancellation_locks_parent_before_job_or_item_mutation(self) -> None:
        connection = StatefulQueueConnection()
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            jobs.request_history_job_cancel(41)

        self.assertIn("FOR UPDATE", connection.queries[0][0])
        self.assertIn("daily_market_brief_jobs", connection.queries[0][0])
        self.assertIn("cancel_requested_at", connection.queries[1][0])

    def test_active_partial_unique_race_returns_existing_job_metadata(self) -> None:
        connection = DedupRaceConnection()
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            created = jobs.create_history_job(
                ["CN"],
                [date(2026, 7, 1)],
                request_type="single",
                source="command",
            )

        self.assertEqual(9, created["id"])
        self.assertEqual(
            [{"job_id": 9, "market": "CN", "market_date": "2026-07-01"}],
            created["deduplicated_items"],
        )
        insert_sql = next(query for query, _ in connection.queries if "INSERT INTO daily_market_brief_job_items" in query)
        self.assertIn("ON CONFLICT (market, market_date)", insert_sql)
        self.assertIn("WHERE status IN ('queued', 'running')", insert_sql)

    def test_conflict_that_becomes_terminal_is_retried_and_inserted(self) -> None:
        connection = ConflictBecomesTerminalConnection()
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            created = jobs.create_history_job(
                ["CN"],
                [date(2026, 7, 1)],
                request_type="single",
                source="command",
            )

        self.assertEqual(41, created["id"])
        self.assertEqual(2, connection.item_insert_attempts)
        self.assertEqual([], created["deduplicated_items"])

    def test_persistent_conflict_exhaustion_returns_real_job_metadata(self) -> None:
        connection = PersistentConflictConnection()
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            created = jobs.create_history_job(
                ["CN"],
                [date(2026, 7, 1)],
                request_type="single",
                source="command",
            )

        self.assertEqual(9, created["id"])
        self.assertEqual(jobs.MAX_DEDUP_RETRIES + 1, connection.item_insert_attempts)
        self.assertEqual(
            [{"job_id": 9, "market": "CN", "market_date": "2026-07-01"}],
            created["deduplicated_items"],
        )

    def test_stale_requeue_invalidates_lease_and_expired_worker_cannot_finish_after_reclaim(self) -> None:
        connection = StatefulQueueConnection()
        cutoff = datetime(2026, 7, 12, 1, 0, tzinfo=timezone.utc)
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            self.assertEqual(1, jobs.requeue_stale_history_items(cutoff))
            self.assertEqual("queued", connection.jobs[41]["status"])
            self.assertIsNone(connection.jobs[41]["current_market"])
            self.assertIsNone(connection.jobs[41]["current_market_date"])
            reclaimed = jobs.claim_next_history_item("worker-b")
            with self.assertRaisesRegex(ValueError, "lease"):
                jobs.finish_history_item(
                    101,
                    status="completed",
                    worker_name="worker-a",
                    lease_token="lease-a",
                    attempt_count=1,
                )
            finished = jobs.finish_history_item(
                101,
                status="completed",
                worker_name="worker-b",
                lease_token=reclaimed["lease_token"],
                attempt_count=reclaimed["attempt_count"],
            )

        self.assertNotEqual("lease-a", reclaimed["lease_token"])
        self.assertEqual(2, reclaimed["attempt_count"])
        self.assertEqual("completed", finished["status"])

    def test_stale_requeue_locks_sorted_parents_before_item_mutation(self) -> None:
        connection = StatefulQueueConnection()
        cutoff = datetime(2026, 7, 12, 1, 0, tzinfo=timezone.utc)
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            jobs.requeue_stale_history_items(cutoff)

        item_update_index = next(
            index
            for index, (query, _) in enumerate(connection.queries)
            if "UPDATE daily_market_brief_job_items" in query
        )
        parent_lock_index = next(
            index
            for index, (query, _) in enumerate(connection.queries)
            if "FOR UPDATE" in query and "daily_market_brief_jobs" in query
        )
        self.assertLess(parent_lock_index, item_update_index)
        self.assertIn("ORDER BY job.id", connection.queries[parent_lock_index][0])

    def test_claim_locks_parent_with_skip_locked_before_item_mutation(self) -> None:
        connection = StatefulQueueConnection()
        connection.items[101].update(status="queued", worker_name=None, lease_token=None, heartbeat_at=None)
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            claimed = jobs.claim_next_history_item("worker-b")

        self.assertEqual(101, claimed["id"])
        self.assertIn("FOR UPDATE OF job SKIP LOCKED", connection.queries[2][0])
        self.assertIn("UPDATE daily_market_brief_job_items", connection.queries[3][0])
        self.assertIn("UPDATE daily_market_brief_jobs", connection.queries[4][0])

    def test_web_source_cannot_force_refresh(self) -> None:
        with self.assertRaisesRegex(ValueError, "web.*force_refresh"):
            jobs.create_history_job(
                ["CN"],
                [date(2026, 7, 1)],
                request_type="single",
                source="web",
                force_refresh=True,
            )

    def test_single_request_requires_exactly_one_normalized_pair(self) -> None:
        with self.assertRaisesRegex(ValueError, "single.*exactly one"):
            jobs.create_history_job(
                ["CN", "HK"],
                [date(2026, 7, 1)],
                request_type="single",
                source="command",
            )

    def test_raw_internal_error_is_replaced_by_approved_code_and_summary(self) -> None:
        connection = StatefulQueueConnection()
        raw_error = "SELECT secret FROM accounts; internal host db.local:5432"
        with mock.patch.object(jobs, "transaction", side_effect=lambda: fake_transaction(connection)):
            finished = jobs.finish_history_item(
                101,
                status="failed",
                worker_name="worker-a",
                lease_token="lease-a",
                attempt_count=1,
                error_summary=raw_error,
            )

        self.assertEqual("generation_failed", finished["error_code"])
        self.assertEqual(jobs.PUBLIC_ERROR_SUMMARIES["generation_failed"], finished["error_summary"])
        self.assertNotIn(raw_error, str(connection.queries))

    def test_invalid_date_values_are_rejected_before_sorting_and_datetime_is_not_a_date(self) -> None:
        for invalid_dates in (
            [date(2026, 7, 1), "2026-07-02"],
            [datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)],
        ):
            with self.subTest(invalid_dates=invalid_dates):
                with self.assertRaisesRegex(ValueError, "date values"):
                    jobs.create_history_job(
                        ["CN"],
                        invalid_dates,
                        request_type="single",
                        source="command",
                    )


class DailyMarketJobsPostgresConcurrencyTests(unittest.TestCase):
    schema_name: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema_name = f"daily_market_jobs_test_{uuid4().hex}"
        try:
            cls.admin = cls._connect()
        except psycopg.OperationalError as exc:
            raise unittest.SkipTest(f"PostgreSQL test database unavailable: {exc}") from exc
        cls.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema_name)))
        cls.admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema_name)))
        cls.admin.execute(
            """
            CREATE TABLE daily_market_brief_jobs (
              id BIGSERIAL PRIMARY KEY,
              request_type TEXT NOT NULL DEFAULT 'batch',
              source TEXT NOT NULL DEFAULT 'command',
              status TEXT NOT NULL DEFAULT 'queued',
              force_refresh BOOLEAN NOT NULL DEFAULT false,
              total_count INTEGER NOT NULL DEFAULT 0,
              completed_count INTEGER NOT NULL DEFAULT 0,
              succeeded_count INTEGER NOT NULL DEFAULT 0,
              skipped_count INTEGER NOT NULL DEFAULT 0,
              failed_count INTEGER NOT NULL DEFAULT 0,
              cancelled_count INTEGER NOT NULL DEFAULT 0,
              current_market TEXT,
              current_market_date DATE,
              summary TEXT,
              cancel_requested_at TIMESTAMPTZ,
              worker_heartbeat_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              completed_at TIMESTAMPTZ
            );
            CREATE TABLE daily_market_brief_job_items (
              id BIGSERIAL PRIMARY KEY,
              job_id BIGINT NOT NULL REFERENCES daily_market_brief_jobs(id) ON DELETE CASCADE,
              market TEXT NOT NULL,
              market_date DATE NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              attempt_count INTEGER NOT NULL DEFAULT 0,
              report_id BIGINT,
              skip_reason TEXT,
              error_code TEXT,
              error_summary TEXT,
              worker_name TEXT,
              lease_token TEXT,
              claimed_at TIMESTAMPTZ,
              heartbeat_at TIMESTAMPTZ,
              finished_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE UNIQUE INDEX daily_market_brief_job_items_active_unique
              ON daily_market_brief_job_items(market, market_date)
              WHERE status IN ('queued', 'running');
            CREATE TABLE review_reports (
              id BIGSERIAL PRIMARY KEY,
              report_type TEXT NOT NULL,
              report_date DATE NOT NULL,
              portfolio_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
              summary TEXT,
              period_start DATE,
              period_end DATE,
              source_status JSONB NOT NULL DEFAULT '{}'::jsonb,
              story JSONB NOT NULL DEFAULT '{}'::jsonb,
              generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              refreshed_at TIMESTAMPTZ,
              report_key TEXT
            );
            """
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if not hasattr(cls, "admin"):
            return
        cls.admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema_name)))
        cls.admin.close()

    def setUp(self) -> None:
        self.admin.execute(
            "TRUNCATE daily_market_brief_job_items, daily_market_brief_jobs, review_reports RESTART IDENTITY CASCADE"
        )

    @classmethod
    def _connect(cls) -> psycopg.Connection:
        config = get_config()
        kwargs = {"row_factory": dict_row, "autocommit": True, "connect_timeout": 2}
        if config.database_url:
            return psycopg.connect(config.database_url, **kwargs)
        return psycopg.connect(
            host=config.postgres_host,
            port=config.postgres_port,
            dbname=config.postgres_db,
            user=config.postgres_user,
            password=config.postgres_password,
            **kwargs,
        )

    @contextmanager
    def _transaction(self, barrier: threading.Barrier):
        connection = self._connect()
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema_name)))
            with connection.transaction():
                yield BarrierConnection(connection, barrier)
        finally:
            connection.close()

    @contextmanager
    def _conflict_transaction(self, conflicting_item_id: int):
        connection = self._connect()
        terminalizer = self._connect()
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema_name)))
            terminalizer.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema_name)))
            with connection.transaction():
                yield ConflictTerminalPostgresConnection(connection, terminalizer, conflicting_item_id)
        finally:
            terminalizer.close()
            connection.close()

    @contextmanager
    def _plain_transaction(self):
        connection = self._connect()
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema_name)))
            with connection.transaction():
                yield connection
        finally:
            connection.close()

    def test_two_concurrent_finishes_preserve_final_parent_aggregate(self) -> None:
        job_id = self.admin.execute(
            """
            INSERT INTO daily_market_brief_jobs (status, total_count, current_market, current_market_date)
            VALUES ('running', 2, 'CN', DATE '2026-07-01')
            RETURNING id
            """
        ).fetchone()["id"]
        item_rows = self.admin.execute(
            """
            INSERT INTO daily_market_brief_job_items (
              job_id, market, market_date, status, attempt_count, worker_name, lease_token, claimed_at, heartbeat_at
            )
            VALUES
              (%s, 'CN', DATE '2026-07-01', 'running', 1, 'worker-a', 'lease-a', now(), now()),
              (%s, 'HK', DATE '2026-07-01', 'running', 1, 'worker-b', 'lease-b', now(), now())
            RETURNING id, worker_name, lease_token
            """,
            (job_id, job_id),
        ).fetchall()
        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def finish(row: dict) -> None:
            try:
                jobs.finish_history_item(
                    int(row["id"]),
                    status="completed",
                    worker_name=str(row["worker_name"]),
                    lease_token=str(row["lease_token"]),
                    attempt_count=1,
                )
            except BaseException as exc:
                errors.append(exc)

        with mock.patch.object(jobs, "transaction", side_effect=lambda: self._transaction(barrier)):
            threads = [threading.Thread(target=finish, args=(row,)) for row in item_rows]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads), "concurrent finish threads did not terminate")
        self.assertEqual([], errors)
        parent = self.admin.execute(
            "SELECT status, total_count, completed_count, succeeded_count FROM daily_market_brief_jobs WHERE id = %s",
            (job_id,),
        ).fetchone()
        self.assertEqual(
            {"status": "completed", "total_count": 2, "completed_count": 2, "succeeded_count": 2},
            parent,
        )
        statuses = self.admin.execute(
            "SELECT status FROM daily_market_brief_job_items WHERE job_id = %s ORDER BY id",
            (job_id,),
        ).fetchall()
        self.assertEqual(["completed", "completed"], [row["status"] for row in statuses])

    def test_partial_unique_conflict_that_terminalizes_is_retried(self) -> None:
        existing_job_id = self.admin.execute(
            "INSERT INTO daily_market_brief_jobs (status, total_count) VALUES ('queued', 1) RETURNING id"
        ).fetchone()["id"]
        conflicting_item_id = self.admin.execute(
            """
            INSERT INTO daily_market_brief_job_items (job_id, market, market_date, status)
            VALUES (%s, 'CN', DATE '2026-07-01', 'queued')
            RETURNING id
            """,
            (existing_job_id,),
        ).fetchone()["id"]

        with mock.patch.object(
            jobs,
            "transaction",
            side_effect=lambda: self._conflict_transaction(conflicting_item_id),
        ):
            created = jobs.create_history_job(
                ["CN"],
                [date(2026, 7, 1)],
                request_type="single",
                source="command",
            )

        self.assertNotEqual(existing_job_id, created["id"])
        rows = self.admin.execute(
            """
            SELECT job_id, status
            FROM daily_market_brief_job_items
            WHERE market = 'CN' AND market_date = DATE '2026-07-01'
            ORDER BY id
            """
        ).fetchall()
        self.assertEqual(
            [(existing_job_id, "completed"), (created["id"], "queued")],
            [(row["job_id"], row["status"]) for row in rows],
        )

    def test_concurrent_web_admission_never_creates_a_fourth_active_job(self) -> None:
        for market, market_date in (("CN", "2026-07-01"), ("HK", "2026-07-01")):
            job_id = self.admin.execute(
                """
                INSERT INTO daily_market_brief_jobs (request_type, source, status, total_count)
                VALUES ('single', 'web', 'queued', 1)
                RETURNING id
                """
            ).fetchone()["id"]
            self.admin.execute(
                """
                INSERT INTO daily_market_brief_job_items (job_id, market, market_date, status)
                VALUES (%s, %s, %s, 'queued')
                """,
                (job_id, market, market_date),
            )

        start = threading.Barrier(2)
        created: list[dict] = []
        errors: list[BaseException] = []

        def admit(market: str, market_date: date) -> None:
            start.wait(timeout=5)
            try:
                created.append(jobs.create_web_history_job(market, market_date))
            except BaseException as exc:
                errors.append(exc)

        with mock.patch.object(jobs, "transaction", side_effect=self._plain_transaction):
            threads = [
                threading.Thread(target=admit, args=("US", date(2026, 7, 1))),
                threading.Thread(target=admit, args=("CN", date(2026, 7, 2))),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(1, len(created))
        self.assertEqual(1, len(errors))
        self.assertIsInstance(errors[0], jobs.WebHistoryJobCapacityError)
        active_count = self.admin.execute(
            """
            SELECT count(*) AS count
            FROM daily_market_brief_jobs
            WHERE source = 'web' AND status IN ('queued', 'running')
            """
        ).fetchone()["count"]
        self.assertEqual(3, active_count)

    def test_web_admission_counts_all_active_rows_and_deduplicates_before_capacity(self) -> None:
        active_job_ids = []
        for market, market_date in (("CN", "2026-07-01"), ("HK", "2026-07-01"), ("US", "2026-07-01")):
            job_id = self.admin.execute(
                """
                INSERT INTO daily_market_brief_jobs (
                  request_type, source, status, total_count, created_at
                ) VALUES ('single', 'web', 'queued', 1, now() - interval '2 days')
                RETURNING id
                """
            ).fetchone()["id"]
            active_job_ids.append(job_id)
            self.admin.execute(
                """
                INSERT INTO daily_market_brief_job_items (job_id, market, market_date, status)
                VALUES (%s, %s, %s, 'queued')
                """,
                (job_id, market, market_date),
            )
        for offset in range(150):
            self.admin.execute(
                """
                INSERT INTO daily_market_brief_jobs (
                  request_type, source, status, total_count, completed_count, succeeded_count, completed_at
                ) VALUES ('single', 'web', 'completed', 1, 1, 1, now())
                """
            )

        with mock.patch.object(jobs, "transaction", side_effect=self._plain_transaction):
            duplicate = jobs.create_web_history_job("CN", date(2026, 7, 1))
            with self.assertRaises(jobs.WebHistoryJobCapacityError) as raised:
                jobs.create_web_history_job("CN", date(2026, 7, 2))

        self.assertEqual(active_job_ids[0], duplicate["id"])
        self.assertEqual(jobs.WEB_HISTORY_JOB_CAPACITY_MESSAGE, str(raised.exception))

    def test_web_admission_does_not_return_authenticated_batch_on_dedup(self) -> None:
        command_job_id = self.admin.execute(
            """
            INSERT INTO daily_market_brief_jobs (request_type, source, status, total_count)
            VALUES ('batch', 'command', 'queued', 2)
            RETURNING id
            """
        ).fetchone()["id"]
        self.admin.execute(
            """
            INSERT INTO daily_market_brief_job_items (job_id, market, market_date, status)
            VALUES (%s, 'CN', '2026-07-01', 'queued')
            """,
            (command_job_id,),
        )

        with mock.patch.object(jobs, "transaction", side_effect=self._plain_transaction):
            with self.assertRaises(jobs.WebHistoryJobCapacityError):
                jobs.create_web_history_job("CN", date(2026, 7, 1))

    def test_public_web_job_lookup_ignores_authenticated_batch_jobs(self) -> None:
        command_job_id = self.admin.execute(
            """
            INSERT INTO daily_market_brief_jobs (request_type, source, status, total_count)
            VALUES ('batch', 'command', 'queued', 1)
            RETURNING id
            """
        ).fetchone()["id"]
        web_job_id = self.admin.execute(
            """
            INSERT INTO daily_market_brief_jobs (request_type, source, status, total_count)
            VALUES ('single', 'web', 'queued', 1)
            RETURNING id
            """
        ).fetchone()["id"]

        with mock.patch.object(jobs, "transaction", side_effect=self._plain_transaction):
            self.assertIsNone(jobs.get_public_web_history_job(command_job_id))
            visible = jobs.get_public_web_history_job(web_job_id)

        self.assertEqual(web_job_id, visible["id"])

    def test_two_concurrent_claims_across_jobs_leave_only_one_running_item(self) -> None:
        for market in ("CN", "HK"):
            job_id = self.admin.execute(
                """
                INSERT INTO daily_market_brief_jobs (request_type, source, status, total_count)
                VALUES ('single', 'command', 'queued', 1)
                RETURNING id
                """
            ).fetchone()["id"]
            self.admin.execute(
                """
                INSERT INTO daily_market_brief_job_items (job_id, market, market_date, status)
                VALUES (%s, %s, DATE '2026-07-01', 'queued')
                """,
                (job_id, market),
            )

        start = threading.Barrier(2)
        claims: list[dict | None] = []

        def claim(worker_name: str) -> None:
            start.wait(timeout=5)
            claims.append(jobs.claim_next_history_item(worker_name))

        with mock.patch.object(jobs, "transaction", side_effect=self._plain_transaction):
            threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(1, sum(claimed is not None for claimed in claims))
        running = self.admin.execute(
            "SELECT count(*) AS count FROM daily_market_brief_job_items WHERE status = 'running'"
        ).fetchone()["count"]
        self.assertEqual(1, running)

    def test_cancel_and_report_finalization_are_one_serialized_decision(self) -> None:
        context = {
            "market": {"code": "CN"},
            "market_date": "2026-07-01",
            "source_status": {"gainers": {"status": "ok"}},
            "narrative": "history",
            "no_session": False,
            "provider_mode": "live",
            "generation_kind": "historical_reconstruction",
            "generated_at": {},
        }
        for _ in range(10):
            self.admin.execute(
                "TRUNCATE daily_market_brief_job_items, daily_market_brief_jobs, review_reports RESTART IDENTITY CASCADE"
            )
            job_id = self.admin.execute(
                """
                INSERT INTO daily_market_brief_jobs (request_type, source, status, total_count)
                VALUES ('single', 'command', 'running', 1)
                RETURNING id
                """
            ).fetchone()["id"]
            item_id = self.admin.execute(
                """
                INSERT INTO daily_market_brief_job_items (
                  job_id, market, market_date, status, attempt_count, worker_name, lease_token,
                  claimed_at, heartbeat_at
                ) VALUES (%s, 'CN', DATE '2026-07-01', 'running', 1, 'worker-a', 'lease-a', now(), now())
                RETURNING id
                """,
                (job_id,),
            ).fetchone()["id"]
            start = threading.Barrier(2)
            errors: list[BaseException] = []

            def cancel() -> None:
                try:
                    start.wait(timeout=5)
                    jobs.request_history_job_cancel(job_id)
                except BaseException as exc:
                    errors.append(exc)

            def finalize() -> None:
                try:
                    start.wait(timeout=5)
                    jobs.finalize_history_item_report(
                        item_id,
                        worker_name="worker-a",
                        lease_token="lease-a",
                        attempt_count=1,
                        context=context,
                        markdown="# history",
                    )
                except BaseException as exc:
                    errors.append(exc)

            with mock.patch.object(jobs, "transaction", side_effect=self._plain_transaction):
                threads = [threading.Thread(target=cancel), threading.Thread(target=finalize)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=15)

            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual([], errors)
            item = self.admin.execute(
                "SELECT status, report_id FROM daily_market_brief_job_items WHERE id = %s", (item_id,)
            ).fetchone()
            report_count = self.admin.execute(
                "SELECT count(*) AS count FROM review_reports WHERE report_type = 'daily_market_brief'"
            ).fetchone()["count"]
            if item["status"] == "cancelled":
                self.assertIsNone(item["report_id"])
                self.assertEqual(0, report_count)
            else:
                self.assertEqual("completed", item["status"])
                self.assertIsNotNone(item["report_id"])
                self.assertEqual(1, report_count)

    def test_report_finalization_rejects_context_that_does_not_match_claimed_item(self) -> None:
        job_id = self.admin.execute(
            """
            INSERT INTO daily_market_brief_jobs (request_type, source, status, total_count)
            VALUES ('single', 'command', 'running', 1)
            RETURNING id
            """
        ).fetchone()["id"]
        item_id = self.admin.execute(
            """
            INSERT INTO daily_market_brief_job_items (
              job_id, market, market_date, status, attempt_count, worker_name, lease_token,
              claimed_at, heartbeat_at
            ) VALUES (%s, 'CN', DATE '2026-07-01', 'running', 1, 'worker-a', 'lease-a', now(), now())
            RETURNING id
            """,
            (job_id,),
        ).fetchone()["id"]
        context = {
            "market": {"code": "HK"},
            "market_date": "2026-07-02",
            "source_status": {},
            "generation_kind": "historical_reconstruction",
        }

        with mock.patch.object(jobs, "transaction", side_effect=self._plain_transaction):
            with self.assertRaisesRegex(ValueError, "does not match"):
                jobs.finalize_history_item_report(
                    item_id,
                    worker_name="worker-a",
                    lease_token="lease-a",
                    attempt_count=1,
                    context=context,
                    markdown="# wrong",
                )

        item = self.admin.execute(
            "SELECT status, report_id FROM daily_market_brief_job_items WHERE id = %s", (item_id,)
        ).fetchone()
        self.assertEqual({"status": "running", "report_id": None}, item)
        report_count = self.admin.execute("SELECT count(*) AS count FROM review_reports").fetchone()["count"]
        self.assertEqual(0, report_count)


if __name__ == "__main__":
    unittest.main()
