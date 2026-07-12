from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from contextlib import contextmanager
from threading import Event
import unittest
from unittest import mock

from investment_knowledge_mcp.daily_market_brief import DailyMarketBriefResult
from investment_knowledge_mcp import daily_market_jobs as jobs
from scripts import daily_market_brief_history_worker as worker


def _claimed_item(**overrides):
    item = {
        "id": 52,
        "job_id": 41,
        "market": "CN",
        "market_date": date(2026, 7, 9),
        "attempt_count": 2,
        "worker_name": "fixture-worker",
        "lease_token": "lease-52",
        "force_refresh": False,
    }
    item.update(overrides)
    return item


def _result(*, report_id: int | None = None, source_status: dict | None = None, no_session: bool = False):
    context = {
        "market": {"code": "CN"},
        "market_date": "2026-07-09",
        "source_status": source_status or {"gainers": {"status": "ok"}},
        "no_session": no_session,
        "generation_kind": "historical_reconstruction",
    }
    return DailyMarketBriefResult(
        context=context,
        markdown="# historical",
        saved_report={"id": report_id} if report_id is not None else None,
    )


class DailyMarketHistoryWorkerTests(unittest.TestCase):
    def test_claims_and_saves_one_exact_historical_item(self) -> None:
        item = _claimed_item()
        built = _result()
        with (
            mock.patch.object(worker, "claim_next_history_item", return_value=item),
            mock.patch.object(worker, "heartbeat_history_item", return_value={"cancel_requested": False}),
            mock.patch.object(worker, "get_daily_market_brief_report", return_value=None),
            mock.patch.object(worker, "build_daily_market_brief", return_value=built) as build,
            mock.patch.object(worker, "save_daily_market_brief_report", return_value={"id": 19}) as save,
            mock.patch.object(worker, "finish_history_item", return_value={"status": "completed"}) as finish,
        ):
            outcome = worker.run_worker_once(worker_name="fixture-worker", item_timeout_seconds=600)

        self.assertEqual("completed", outcome["status"])
        self.assertEqual(19, outcome["report_id"])
        build.assert_called_once()
        kwargs = build.call_args.kwargs
        self.assertEqual("CN", kwargs["market"])
        self.assertEqual(date(2026, 7, 9), kwargs["market_date"])
        self.assertFalse(kwargs["save"])
        provider = kwargs["historical_activity_provider"]
        with mock.patch.object(worker, "load_historical_market_activity", return_value="activity") as load:
            self.assertEqual("activity", provider("CN", date(2026, 7, 9)))
        load.assert_called_once_with("CN", date(2026, 7, 9), timeout_seconds=600.0)
        save.assert_called_once_with(context=built.context, markdown=built.markdown)
        self.assertEqual("completed", finish.call_args.kwargs["status"])
        self.assertEqual(19, finish.call_args.kwargs["report_id"])

    def test_skips_report_created_after_enqueue_unless_force_refresh(self) -> None:
        with (
            mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item()),
            mock.patch.object(worker, "heartbeat_history_item", return_value={"cancel_requested": False}),
            mock.patch.object(worker, "get_daily_market_brief_report", return_value={"id": 17}),
            mock.patch.object(worker, "build_daily_market_brief") as build,
            mock.patch.object(worker, "finish_history_item", return_value={"status": "skipped"}) as finish,
        ):
            outcome = worker.run_worker_once(worker_name="fixture-worker")

        self.assertEqual({"item_id": 52, "status": "skipped", "report_id": 17}, outcome)
        build.assert_not_called()
        self.assertEqual("skipped", finish.call_args.kwargs["status"])
        self.assertEqual(17, finish.call_args.kwargs["report_id"])

        with (
            mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item(force_refresh=True)),
            mock.patch.object(worker, "heartbeat_history_item", return_value={"cancel_requested": False}),
            mock.patch.object(worker, "get_daily_market_brief_report", return_value={"id": 17}),
            mock.patch.object(worker, "build_daily_market_brief", return_value=_result()),
            mock.patch.object(worker, "save_daily_market_brief_report", return_value={"id": 20}),
            mock.patch.object(worker, "finish_history_item", return_value={"status": "completed"}),
        ):
            outcome = worker.run_worker_once(worker_name="fixture-worker")
        self.assertEqual(20, outcome["report_id"])

    def test_cancellation_wins_before_existing_report_skip_finalization(self) -> None:
        heartbeats = iter(({"cancel_requested": False}, {"cancel_requested": True}))
        with (
            mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item()),
            mock.patch.object(worker, "heartbeat_history_item", side_effect=lambda *_, **__: next(heartbeats)),
            mock.patch.object(worker, "get_daily_market_brief_report", return_value={"id": 17}),
            mock.patch.object(worker, "finish_history_item", return_value={"status": "cancelled"}) as finish,
        ):
            outcome = worker.run_worker_once(worker_name="fixture-worker")
        self.assertEqual("cancelled", outcome["status"])
        self.assertEqual("cancelled", finish.call_args.kwargs["status"])

    def test_no_session_and_useful_partial_results_are_saved(self) -> None:
        scenarios = (
            (_result(no_session=True), False),
            (_result(source_status={"gainers": {"status": "timed_out", "usable": 1}}), True),
        )
        for built, expected_partial in scenarios:
            with self.subTest(partial=expected_partial):
                with (
                    mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item()),
                    mock.patch.object(worker, "heartbeat_history_item", return_value={"cancel_requested": False}),
                    mock.patch.object(worker, "get_daily_market_brief_report", return_value=None),
                    mock.patch.object(worker, "build_daily_market_brief", return_value=built),
                    mock.patch.object(worker, "save_daily_market_brief_report", return_value={"id": 21}),
                    mock.patch.object(worker, "finish_history_item", return_value={"status": "completed"}),
                ):
                    outcome = worker.run_worker_once(worker_name="fixture-worker")
                self.assertEqual("completed", outcome["status"])
                self.assertEqual(expected_partial, outcome["partial"])

    def test_cancelled_before_build_never_calls_provider_or_saves(self) -> None:
        with (
            mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item()),
            mock.patch.object(worker, "heartbeat_history_item", return_value={"cancel_requested": True}),
            mock.patch.object(worker, "build_daily_market_brief") as build,
            mock.patch.object(worker, "save_daily_market_brief_report") as save,
            mock.patch.object(worker, "finish_history_item", return_value={"status": "cancelled"}) as finish,
        ):
            outcome = worker.run_worker_once(worker_name="fixture-worker")
        self.assertEqual("cancelled", outcome["status"])
        build.assert_not_called()
        save.assert_not_called()
        self.assertEqual("cancelled", finish.call_args.kwargs["status"])

    def test_lost_lease_before_build_stops_without_side_effects(self) -> None:
        with (
            mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item()),
            mock.patch.object(worker, "heartbeat_history_item", return_value=None),
            mock.patch.object(worker, "build_daily_market_brief") as build,
            mock.patch.object(worker, "save_daily_market_brief_report") as save,
            mock.patch.object(worker, "finish_history_item") as finish,
        ):
            outcome = worker.run_worker_once(worker_name="fixture-worker")
        self.assertEqual("lease_lost", outcome["status"])
        build.assert_not_called()
        save.assert_not_called()
        finish.assert_not_called()

    def test_cancelled_before_finalization_does_not_save(self) -> None:
        heartbeats = iter(({"cancel_requested": False}, {"cancel_requested": True}))
        with (
            mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item()),
            mock.patch.object(worker, "heartbeat_history_item", side_effect=lambda *_, **__: next(heartbeats)),
            mock.patch.object(worker, "get_daily_market_brief_report", return_value=None),
            mock.patch.object(worker, "build_daily_market_brief", return_value=_result()),
            mock.patch.object(worker, "save_daily_market_brief_report") as save,
            mock.patch.object(worker, "finish_history_item", return_value={"status": "cancelled"}) as finish,
        ):
            outcome = worker.run_worker_once(worker_name="fixture-worker")
        self.assertEqual("cancelled", outcome["status"])
        save.assert_not_called()
        self.assertEqual("cancelled", finish.call_args.kwargs["status"])

    def test_failure_persists_only_public_error_code_and_copy(self) -> None:
        raw = RuntimeError("SSL password=super-secret host=internal-db")
        with (
            mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item()),
            mock.patch.object(worker, "heartbeat_history_item", return_value={"cancel_requested": False}),
            mock.patch.object(worker, "get_daily_market_brief_report", return_value=None),
            mock.patch.object(worker, "build_daily_market_brief", side_effect=raw),
            mock.patch.object(worker, "finish_history_item", return_value={"status": "failed"}) as finish,
        ):
            outcome = worker.run_worker_once(worker_name="fixture-worker")
        self.assertEqual("failed", outcome["status"])
        self.assertEqual("generation_failed", outcome["error_code"])
        persisted = finish.call_args.kwargs
        self.assertEqual("generation_failed", persisted["error_code"])
        self.assertNotIn("secret", persisted["error_summary"])
        self.assertNotIn("SSL", persisted["error_summary"])

    def test_long_build_heartbeats_while_provider_is_running(self) -> None:
        build_started = Event()
        allow_finish = Event()

        def build(**kwargs):
            build_started.set()
            self.assertTrue(allow_finish.wait(1))
            return _result()

        heartbeat_calls = 0

        def heartbeat(*args, **kwargs):
            nonlocal heartbeat_calls
            heartbeat_calls += 1
            if build_started.is_set() and heartbeat_calls >= 2:
                allow_finish.set()
            return {"cancel_requested": False}

        with (
            mock.patch.object(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.01),
            mock.patch.object(worker, "claim_next_history_item", return_value=_claimed_item()),
            mock.patch.object(worker, "heartbeat_history_item", side_effect=heartbeat),
            mock.patch.object(worker, "get_daily_market_brief_report", return_value=None),
            mock.patch.object(worker, "build_daily_market_brief", side_effect=build),
            mock.patch.object(worker, "save_daily_market_brief_report", return_value={"id": 22}),
            mock.patch.object(worker, "finish_history_item", return_value={"status": "completed"}),
        ):
            worker.run_worker_once(worker_name="fixture-worker")
        self.assertGreaterEqual(heartbeat_calls, 2)

    def test_forever_recovers_stale_items_and_processes_until_stopped(self) -> None:
        stop = Event()
        outcomes = iter(({"item_id": 1, "status": "completed"}, None))

        def once(**kwargs):
            outcome = next(outcomes)
            if outcome is None:
                stop.set()
            return outcome

        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        with (
            mock.patch.object(worker, "requeue_stale_history_items", return_value=1) as requeue,
            mock.patch.object(worker, "run_worker_once", side_effect=once) as run_once,
            mock.patch.object(worker, "_utcnow", return_value=now),
        ):
            worker.run_worker_forever(poll_seconds=0, stop_event=stop)
        requeue.assert_called_once_with(now - timedelta(seconds=worker.STALE_AFTER_SECONDS))
        self.assertEqual(2, run_once.call_count)

    def test_returns_none_when_queue_is_empty(self) -> None:
        with mock.patch.object(worker, "claim_next_history_item", return_value=None):
            self.assertIsNone(worker.run_worker_once(worker_name="fixture-worker"))

    def test_repository_heartbeat_locks_parent_before_updating_item(self) -> None:
        class Cursor:
            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class Connection:
            def __init__(self):
                self.queries = []

            def execute(self, query, params=None):
                compact = " ".join(query.split())
                self.queries.append(compact)
                if "FOR UPDATE OF job" in compact:
                    return Cursor({"id": 41, "cancel_requested": True})
                if compact.startswith("UPDATE daily_market_brief_job_items"):
                    return Cursor({"id": 52, "job_id": 41, "heartbeat_at": "now"})
                if compact.startswith("UPDATE daily_market_brief_jobs"):
                    return Cursor()
                raise AssertionError(compact)

        connection = Connection()

        @contextmanager
        def transaction():
            yield connection

        with mock.patch.object(jobs, "transaction", transaction):
            state = jobs.heartbeat_history_item(
                52,
                worker_name="fixture-worker",
                lease_token="lease-52",
                attempt_count=2,
            )
        self.assertTrue(state["cancel_requested"])
        self.assertIn("FOR UPDATE OF job", connection.queries[0])
        self.assertTrue(connection.queries[1].startswith("UPDATE daily_market_brief_job_items"))


if __name__ == "__main__":
    unittest.main()
