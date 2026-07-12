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
        if compact.startswith("UPDATE daily_market_brief_job_items AS item SET") and "lease_token = %s" in compact:
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
        if compact.startswith("UPDATE daily_market_brief_job_items AS item SET") and "status = 'queued'" in compact:
            cutoff = params[0]
            recovered = []
            for item in self.items.values():
                job = self.jobs[item["job_id"]]
                if item["status"] == "running" and item["heartbeat_at"] < cutoff and not job["cancel_requested_at"]:
                    item.update(status="queued", worker_name=None, lease_token=None, heartbeat_at=None)
                    recovered.append({"job_id": item["job_id"]})
            return FakeCursor(many=recovered, rowcount=len(recovered))
        if "FOR UPDATE SKIP LOCKED" in compact:
            worker_name, lease_token = params
            queued = next((item for item in self.items.values() if item["status"] == "queued"), None)
            if queued is None:
                return FakeCursor()
            queued.update(
                status="running",
                attempt_count=queued["attempt_count"] + 1,
                worker_name=worker_name,
                lease_token=lease_token,
                heartbeat_at=datetime.now(timezone.utc),
            )
            job = self.jobs[queued["job_id"]]
            job.update(status="running", current_market=queued["market"], current_market_date=queued["market_date"])
            return FakeCursor(dict(queued))
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
        self.connection.claimed_item = {
            "id": 101,
            "status": "running",
            "worker_name": "history-worker",
            "lease_token": "generated",
            "attempt_count": 1,
        }

        claimed = jobs.claim_next_history_item("history-worker")

        self.assertEqual(101, claimed["id"])
        self.assertEqual(1, len(self.connection.queries))
        query, params = self.connection.queries[0]
        self.assertIn("FOR UPDATE SKIP LOCKED", query)
        self.assertIn("status = 'queued'", query)
        self.assertEqual("history-worker", params[0])
        self.assertTrue(params[1])
        self.assertIn("lease_token = %s", query)

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
        query, params = self.connection.queries[0]
        self.assertNotIn("daily_market_brief_jobs", query)
        self.assertNotIn("/srv/private.py", str(params))
        self.assertNotIn("password=secret", str(params))
        self.assertEqual(2, len(self.connection.queries))

    def test_cancel_requests_stop_for_queued_items_and_preserves_running_item_for_cooperative_cancel(self) -> None:
        self.connection.cancelled_job = {"id": 41, "status": "running", "cancel_requested_at": "2026-07-12T00:00:00+00:00"}

        cancelled = jobs.request_history_job_cancel(41)

        self.assertEqual(41, cancelled["id"])
        query, params = self.connection.queries[0]
        self.assertIn("cancel_requested_at = COALESCE(job.cancel_requested_at, now())", query)
        self.assertEqual((41,), params)
        self.assertEqual(3, len(self.connection.queries))

    def test_requeues_stale_running_items_using_heartbeat_cutoff(self) -> None:
        self.connection.stale_count = 3
        cutoff = datetime(2026, 7, 12, 0, 0, tzinfo=timezone.utc)

        recovered = jobs.requeue_stale_history_items(cutoff)

        self.assertEqual(3, recovered)
        query, params = self.connection.queries[0]
        self.assertIn("status = 'running'", query)
        self.assertIn("heartbeat_at < %s", query)
        self.assertEqual((cutoff,), params)


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
        self.assertEqual(2, len(connection.queries))
        self.assertNotIn("daily_market_brief_jobs", connection.queries[0][0])
        self.assertIn("daily_market_brief_jobs", connection.queries[1][0])

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
        self.assertEqual(3, len(connection.queries))

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


if __name__ == "__main__":
    unittest.main()
