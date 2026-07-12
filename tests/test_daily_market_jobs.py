from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest import mock

from investment_knowledge_mcp import daily_market_jobs as jobs


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
        if "FOR UPDATE SKIP LOCKED" in compact:
            return FakeCursor(self.claimed_item)
        if "UPDATE daily_market_brief_job_items AS item" in compact and "SET status = %s" in compact:
            return FakeCursor(self.finished_item)
        if "UPDATE daily_market_brief_jobs AS job" in compact and "cancel_requested_at" in compact:
            return FakeCursor(self.cancelled_job)
        if "UPDATE daily_market_brief_job_items" in compact and "heartbeat_at < %s" in compact:
            return FakeCursor(rowcount=self.stale_count)
        if "FROM daily_market_brief_jobs AS job" in compact and "WHERE job.id = %s" in compact:
            return FakeCursor(self.job_detail)
        if "FROM daily_market_brief_jobs AS job" in compact and "ORDER BY job.created_at DESC" in compact:
            return FakeCursor(many=self.listed_jobs)
        raise AssertionError(f"unexpected SQL: {compact}")


@contextmanager
def fake_transaction(connection: FakeConnection):
    yield connection


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

    def test_claims_exactly_one_item_with_skip_locked_in_one_transaction(self) -> None:
        self.connection.claimed_item = {"id": 101, "status": "running", "worker_name": "history-worker"}

        claimed = jobs.claim_next_history_item("history-worker")

        self.assertEqual(101, claimed["id"])
        self.assertEqual(1, len(self.connection.queries))
        query, params = self.connection.queries[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", query)
        self.assertIn("status = 'queued'", query)
        self.assertEqual(("history-worker",), params)

    def test_finish_item_updates_aggregate_and_sanitizes_error(self) -> None:
        self.connection.finished_item = {"id": 101, "status": "failed", "error_summary": "数据源暂时不可用"}

        finished = jobs.finish_history_item(
            101,
            status="failed",
            error_summary="Traceback: /srv/private.py password=secret\nprovider timeout",
        )

        self.assertEqual("数据源暂时不可用", finished["error_summary"])
        query, params = self.connection.queries[0]
        self.assertIn("daily_market_brief_jobs", query)
        self.assertNotIn("/srv/private.py", str(params))
        self.assertNotIn("password=secret", str(params))

    def test_cancel_requests_stop_for_queued_items_and_preserves_running_item_for_cooperative_cancel(self) -> None:
        self.connection.cancelled_job = {"id": 41, "status": "running", "cancel_requested_at": "2026-07-12T00:00:00+00:00"}

        cancelled = jobs.request_history_job_cancel(41)

        self.assertEqual(41, cancelled["id"])
        query, params = self.connection.queries[0]
        self.assertIn("cancel_requested_at = COALESCE(job.cancel_requested_at, now())", query)
        self.assertIn("'cancelled'", query)
        self.assertEqual((41,), params)

    def test_requeues_stale_running_items_using_heartbeat_cutoff(self) -> None:
        self.connection.stale_count = 3
        cutoff = datetime(2026, 7, 12, 0, 0, tzinfo=timezone.utc)

        recovered = jobs.requeue_stale_history_items(cutoff)

        self.assertEqual(3, recovered)
        query, params = self.connection.queries[0]
        self.assertIn("status = 'running'", query)
        self.assertIn("heartbeat_at < %s", query)
        self.assertEqual((cutoff,), params)


if __name__ == "__main__":
    unittest.main()
