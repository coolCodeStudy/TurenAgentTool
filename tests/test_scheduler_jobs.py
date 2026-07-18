from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from investment_knowledge_mcp.config import AppConfig
from investment_knowledge_mcp import scheduler_jobs


class InlineExecutor:
    def __init__(self) -> None:
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def submit(self, callback):
        future: Future[object] = Future()
        try:
            future.set_result(callback())
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        self.shutdown_calls.append((wait, cancel_futures))


class SchedulerJobTests(unittest.TestCase):
    def _config(self, **overrides) -> AppConfig:
        values = {
            "dingtalk_ipo_reminders_enabled": True,
            "dingtalk_send_webhook": "configured",
            "dingtalk_ipo_reminder_interval_seconds": 300,
            "account_snapshot_scheduler_enabled": True,
            "account_snapshot_time": "00:05",
            "account_snapshot_interval_seconds": 300,
        }
        values.update(overrides)
        return AppConfig(**values)

    def test_default_host_registers_non_overlapping_bounded_jobs(self) -> None:
        host = scheduler_jobs.default_scheduler_host(
            config=self._config(
                dingtalk_ipo_reminder_interval_seconds=1,
                account_snapshot_interval_seconds=100_000,
            ),
            clock=lambda: 0.0,
            now=lambda: datetime(2026, 7, 20, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            executor=InlineExecutor(),
        )

        definitions = scheduler_jobs.default_scheduler_jobs(
            config=self._config(
                dingtalk_ipo_reminder_interval_seconds=1,
                account_snapshot_interval_seconds=100_000,
            ),
            now=lambda: datetime(2026, 7, 20, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertEqual(
            [definition.job_id for definition in definitions],
            [
                "ipo-reminder",
                "account-snapshot",
                "daily-market-brief-cn",
                "daily-market-brief-hk",
                "daily-market-brief-us",
            ],
        )
        self.assertEqual(definitions[0].interval_seconds, 60)
        self.assertEqual(definitions[1].interval_seconds, 3600)
        self.assertTrue(all(definition.timeout_seconds > 0 for definition in definitions))
        self.assertTrue(all(definition.timeout_seconds <= 900 for definition in definitions))
        self.assertTrue(all(not definition.allow_overlap for definition in definitions))
        self.assertEqual([state.job_id for state in host.health()], [item.job_id for item in definitions])

    def test_disabled_legacy_schedulers_are_not_registered(self) -> None:
        definitions = scheduler_jobs.default_scheduler_jobs(
            config=self._config(
                dingtalk_ipo_reminders_enabled=False,
                dingtalk_send_webhook=None,
                account_snapshot_scheduler_enabled=False,
            ),
            now=lambda: datetime(2026, 7, 20, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        self.assertEqual(
            [definition.job_id for definition in definitions],
            ["daily-market-brief-cn", "daily-market-brief-hk", "daily-market-brief-us"],
        )

    def test_account_snapshot_runs_once_after_due_time(self) -> None:
        wall_time = [datetime(2026, 7, 20, 0, 4, tzinfo=ZoneInfo("Asia/Shanghai"))]
        with mock.patch.object(scheduler_jobs, "run_account_snapshot_once", return_value={"id": 1}) as run:
            host = scheduler_jobs.default_scheduler_host(
                config=self._config(dingtalk_ipo_reminders_enabled=False),
                clock=lambda: 0.0,
                now=lambda: wall_time[0],
                executor=InlineExecutor(),
            )

            host.tick(0.0)
            wall_time[0] = datetime(2026, 7, 20, 0, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
            host.tick(300.0)
            wall_time[0] = datetime(2026, 7, 20, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            host.tick(600.0)

        run.assert_called_once_with(snapshot_date=wall_time[0].date(), logger=mock.ANY)

    def test_failed_account_snapshot_is_retried_on_next_interval(self) -> None:
        wall_time = datetime(2026, 7, 20, 0, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
        with mock.patch.object(
            scheduler_jobs,
            "run_account_snapshot_once",
            side_effect=(RuntimeError("private"), {"id": 1}),
        ) as run:
            host = scheduler_jobs.default_scheduler_host(
                config=self._config(dingtalk_ipo_reminders_enabled=False),
                clock=lambda: 0.0,
                now=lambda: wall_time,
                executor=InlineExecutor(),
            )

            failed = {state.job_id: state for state in host.tick(0.0)}
            recovered = {state.job_id: state for state in host.tick(300.0)}

        self.assertEqual(run.call_count, 2)
        self.assertEqual(failed["account-snapshot"].last_error, "exception:RuntimeError")
        self.assertEqual(recovered["account-snapshot"].last_success_at, 300.0)

    def test_daily_market_jobs_are_due_and_fail_independently(self) -> None:
        calls: list[str] = []

        def run(market: str, **_kwargs):
            calls.append(market)
            if market == "CN":
                raise RuntimeError("private")
            return object()

        with (
            mock.patch.object(scheduler_jobs, "should_run_daily_market_brief", return_value=True),
            mock.patch.object(
                scheduler_jobs,
                "resolve_latest_completed_session_date",
                return_value=datetime(2026, 7, 20).date(),
            ),
            mock.patch.object(scheduler_jobs, "run_daily_market_brief_once", side_effect=run),
        ):
            host = scheduler_jobs.default_scheduler_host(
                config=self._config(
                    dingtalk_ipo_reminders_enabled=False,
                    account_snapshot_scheduler_enabled=False,
                ),
                clock=lambda: 0.0,
                now=lambda: datetime(2026, 7, 20, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                executor=InlineExecutor(),
            )

            states = {state.job_id: state for state in host.tick(0.0)}

        self.assertEqual(calls, ["CN", "HK", "US"])
        self.assertEqual(states["daily-market-brief-cn"].last_error, "exception:RuntimeError")
        self.assertEqual(states["daily-market-brief-hk"].last_success_at, 0.0)
        self.assertEqual(states["daily-market-brief-us"].last_success_at, 0.0)

    def test_daily_market_success_is_not_repeated_for_same_session(self) -> None:
        wall_time = datetime(2026, 7, 20, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with (
            mock.patch.object(scheduler_jobs, "should_run_daily_market_brief", return_value=True),
            mock.patch.object(
                scheduler_jobs,
                "resolve_latest_completed_session_date",
                return_value=wall_time.date(),
            ),
            mock.patch.object(scheduler_jobs, "run_daily_market_brief_once", return_value=object()) as run,
        ):
            host = scheduler_jobs.default_scheduler_host(
                config=self._config(
                    dingtalk_ipo_reminders_enabled=False,
                    account_snapshot_scheduler_enabled=False,
                ),
                clock=lambda: 0.0,
                now=lambda: wall_time,
                executor=InlineExecutor(),
            )

            host.tick(0.0)
            host.tick(300.0)

        self.assertEqual(run.call_count, 3)

    def test_invalid_wall_clock_is_rejected_without_running_jobs(self) -> None:
        with mock.patch.object(scheduler_jobs, "run_account_snapshot_once") as run:
            host = scheduler_jobs.default_scheduler_host(
                config=self._config(dingtalk_ipo_reminders_enabled=False),
                clock=lambda: 0.0,
                now=lambda: datetime(2026, 7, 20, 0, 5),
                executor=InlineExecutor(),
            )

            states = {state.job_id: state for state in host.tick(0.0)}

        run.assert_not_called()
        self.assertEqual(states["account-snapshot"].last_error, "exception:ValueError")


if __name__ == "__main__":
    unittest.main()
