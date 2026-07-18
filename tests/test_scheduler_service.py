from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from investment_knowledge_mcp.scheduler_host import (
    HistoryChildState,
    HistoryChildSupervisor,
    JobState,
)
from investment_knowledge_mcp.scheduler_service import (
    SchedulerService,
    check_health_snapshot,
    history_worker_command,
)


class _Host:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.shutdown_requested = False
        self.state = (
            JobState(
                job_id="ipo-reminder",
                running=False,
                active_runs=0,
                timed_out_runs=0,
                next_due_at=60.0,
                last_success_at=12.0,
            ),
        )

    def tick(self):
        self.events.append("host.tick")
        return self.state

    def request_shutdown(self):
        self.events.append("host.request_shutdown")
        self.shutdown_requested = True

    def close(self, *, wait: bool):
        self.events.append(f"host.close:{wait}")


class _HistorySupervisor:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.state = HistoryChildState(running=True, starts=1)

    def poll(self):
        self.events.append("history.poll")
        return self.state

    def close(self, *, timeout_seconds: float):
        self.events.append(f"history.close:{timeout_seconds}")
        self.state = replace(self.state, running=False, last_exit_code=0)
        return self.state


class _Child:
    def __init__(self) -> None:
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.returncode is None:
            raise AssertionError("test child is still running")
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

class SchedulerServiceTests(unittest.TestCase):
    def test_history_child_argv_is_exact_and_contains_no_environment_values(self) -> None:
        command = history_worker_command(Path("/srv/app"))

        self.assertEqual(
            (
                sys.executable,
                "/srv/app/scripts/daily_market_brief_history_worker.py",
                "--drain-until-idle",
            ),
            command,
        )
        rendered = " ".join(command).lower()
        for sensitive in ("token", "secret", "password", "webhook", "api_key", "="):
            self.assertNotIn(sensitive, rendered)

    def test_tick_writes_atomic_secret_free_job_and_child_health(self) -> None:
        events: list[str] = []
        host = _Host(events)
        history = _HistorySupervisor(events)
        with TemporaryDirectory() as tmp:
            health_path = Path(tmp) / "scheduler-health.json"
            service = SchedulerService(
                host=host,
                history_supervisor=history,
                health_path=health_path,
                wall_clock=lambda: 1000.0,
            )

            snapshot = service.tick()

            self.assertEqual(["host.tick", "history.poll"], events)
            self.assertEqual("ipo-reminder", snapshot["jobs"][0]["job_id"])
            self.assertTrue(snapshot["history_child"]["running"])
            self.assertEqual(1000.0, snapshot["updated_at_epoch"])
            self.assertEqual(snapshot, json.loads(health_path.read_text(encoding="utf-8")))
            self.assertFalse(any(health_path.parent.glob(f".{health_path.name}.*")))
            payload = health_path.read_text(encoding="utf-8").lower()
            for sensitive in ("token", "secret", "password", "webhook", "authorization"):
                self.assertNotIn(sensitive, payload)

    def test_health_check_rejects_stale_and_unreadable_snapshots(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "health.json"
            healthy = {
                "updated_at_epoch": 100.0,
                "jobs": [
                    {
                        "job_id": "ipo-reminder",
                        "running": False,
                        "active_runs": 0,
                        "timed_out_runs": 0,
                    }
                ],
                "history_child": {
                    "running": False,
                    "starts": 0,
                    "poll_in_flight": False,
                    "cleanup_pending": False,
                    "last_exit_code": None,
                    "last_error": None,
                },
            }
            path.write_text(json.dumps(healthy), encoding="utf-8")

            self.assertTrue(check_health_snapshot(path, now=110.0, max_age_seconds=20.0))
            self.assertFalse(check_health_snapshot(path, now=121.0, max_age_seconds=20.0))
            path.write_text("not-json", encoding="utf-8")
            self.assertFalse(check_health_snapshot(path, now=110.0, max_age_seconds=20.0))

    def test_health_check_rejects_malformed_or_material_supervisor_failure(self) -> None:
        healthy = {
            "updated_at_epoch": 100.0,
            "jobs": [
                {
                    "job_id": "daily-market-brief-cn",
                    "running": False,
                    "active_runs": 0,
                    "timed_out_runs": 0,
                    "last_error": "exception:ProviderUnavailable",
                }
            ],
            "history_child": {
                "running": False,
                "starts": 1,
                "poll_in_flight": False,
                "cleanup_pending": False,
                "last_exit_code": 0,
                "last_error": None,
            },
        }
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "health.json"
            for mutation, expected in (
                ({}, True),
                ({"jobs": []}, False),
                ({"jobs": None}, False),
                ({"history_child": None}, False),
                ({"jobs": [{"job_id": "job", "running": True, "active_runs": 1, "timed_out_runs": 1}]}, False),
                ({"history_child": {**healthy["history_child"], "cleanup_pending": True}}, False),
                ({"history_child": {**healthy["history_child"], "running": True, "starts": 0}}, False),
                ({"history_child": {**healthy["history_child"], "last_exit_code": 2, "last_error": "exit:2"}}, False),
                ({"history_child": {**healthy["history_child"], "last_error": "probe:OperationalError"}}, False),
            ):
                with self.subTest(mutation=mutation):
                    payload = {**healthy, **mutation}
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    self.assertEqual(
                        expected,
                        check_health_snapshot(path, now=110.0, max_age_seconds=20.0),
                    )

    def test_history_crash_stays_unhealthy_through_restarts_until_clean_exit(self) -> None:
        events: list[str] = []
        first = _Child()
        second = _Child()
        third = _Child()
        children = [first, second, third]
        pending = iter((True, True, True, False))
        supervisor = HistoryChildSupervisor(
            lambda: next(pending),
            lambda: children.pop(0),
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "health.json"
            service = SchedulerService(
                host=_Host(events),
                history_supervisor=supervisor,
                health_path=path,
                wall_clock=lambda: 100.0,
            )

            service.tick()
            self.assertTrue(check_health_snapshot(path, now=100.0))

            first.returncode = 7
            crashed_once = service.tick()
            self.assertTrue(crashed_once["history_child"]["running"])
            self.assertEqual(7, crashed_once["history_child"]["last_exit_code"])
            self.assertFalse(check_health_snapshot(path, now=100.0))

            second.returncode = 9
            crashed_twice = service.tick()
            self.assertEqual(9, crashed_twice["history_child"]["last_exit_code"])
            self.assertFalse(check_health_snapshot(path, now=100.0))

            third.returncode = 0
            recovered = service.tick()
            self.assertFalse(recovered["history_child"]["running"])
            self.assertEqual(0, recovered["history_child"]["last_exit_code"])
            self.assertIsNone(recovered["history_child"]["last_error"])
            self.assertTrue(check_health_snapshot(path, now=100.0))

    def test_shutdown_stops_submissions_before_executor_then_reaps_child(self) -> None:
        events: list[str] = []
        service = SchedulerService(
            host=_Host(events),
            history_supervisor=_HistorySupervisor(events),
            health_path=Path("unused.json"),
            wall_clock=lambda: 1000.0,
        )

        service.close(history_timeout_seconds=2.5)

        self.assertEqual(
            ["host.request_shutdown", "host.close:False", "history.close:2.5"],
            events,
        )


if __name__ == "__main__":
    unittest.main()
