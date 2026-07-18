from __future__ import annotations

from concurrent.futures import Future
import unittest

from investment_knowledge_mcp.scheduler_host import JobDefinition, SchedulerHost


class RecordingExecutor:
    def __init__(self, *, immediate: bool = True) -> None:
        self.immediate = immediate
        self.submissions: list[tuple[object, Future[object]]] = []
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def submit(self, callback):
        future: Future[object] = Future()
        self.submissions.append((callback, future))
        if self.immediate:
            try:
                future.set_result(callback())
            except BaseException as exc:
                future.set_exception(exc)
        return future

    def run_submission(self, index: int) -> None:
        callback, future = self.submissions[index]
        try:
            future.set_result(callback())
        except BaseException as exc:
            future.set_exception(exc)

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        self.shutdown_calls.append((wait, cancel_futures))


class SchedulerHostTests(unittest.TestCase):
    def test_due_jobs_run_independently(self) -> None:
        calls: list[str] = []
        executor = RecordingExecutor()
        host = SchedulerHost(
            (
                JobDefinition("ipo", 60, lambda: calls.append("ipo"), 10),
                JobDefinition("brief", 60, lambda: calls.append("brief"), 10),
            ),
            clock=lambda: 0.0,
            executor=executor,
        )

        states = host.tick(0.0)

        self.assertEqual(calls, ["ipo", "brief"])
        self.assertEqual([state.job_id for state in states], ["ipo", "brief"])
        self.assertTrue(all(state.last_success_at == 0.0 for state in states))

    def test_failed_job_does_not_stop_other_jobs(self) -> None:
        calls: list[str] = []

        def fail() -> None:
            calls.append("failed")
            raise RuntimeError("sensitive provider detail")

        host = SchedulerHost(
            (
                JobDefinition("failed", 60, fail, 10),
                JobDefinition("healthy", 60, lambda: calls.append("healthy"), 10),
            ),
            clock=lambda: 0.0,
            executor=RecordingExecutor(),
        )

        states = {state.job_id: state for state in host.tick(0.0)}

        self.assertEqual(calls, ["failed", "healthy"])
        self.assertEqual(states["failed"].last_error, "exception:RuntimeError")
        self.assertEqual(states["failed"].last_failure_at, 0.0)
        self.assertEqual(states["healthy"].last_success_at, 0.0)
        self.assertNotIn("sensitive", repr(states["failed"]))

    def test_running_job_is_not_started_twice(self) -> None:
        executor = RecordingExecutor(immediate=False)
        host = SchedulerHost(
            (JobDefinition("history", 1, lambda: None, 30),),
            clock=lambda: 0.0,
            executor=executor,
        )

        first = host.tick(0.0)[0]
        overdue = host.tick(2.0)[0]

        self.assertEqual(len(executor.submissions), 1)
        self.assertTrue(first.running)
        self.assertTrue(overdue.running)
        self.assertEqual(overdue.active_runs, 1)

        executor.run_submission(0)
        completed = host.tick(3.0)[0]
        self.assertEqual(completed.last_success_at, 3.0)
        self.assertEqual(len(executor.submissions), 2)

    def test_health_reports_each_job_last_success_and_failure(self) -> None:
        should_fail = [True, False]

        def callback() -> None:
            if should_fail.pop(0):
                raise ValueError("do not expose")

        host = SchedulerHost(
            (JobDefinition("daily", 5, callback, 2),),
            clock=lambda: 0.0,
            executor=RecordingExecutor(),
        )

        failed = host.tick(0.0)[0]
        healthy = host.tick(5.0)[0]
        health = host.health()[0]

        self.assertEqual(failed.last_failure_at, 0.0)
        self.assertEqual(healthy.last_success_at, 5.0)
        self.assertEqual(health.last_failure_at, 0.0)
        self.assertEqual(health.last_success_at, 5.0)
        self.assertIsNone(health.last_error)

    def test_timeout_is_isolated_and_does_not_release_non_overlap_guard(self) -> None:
        executor = RecordingExecutor(immediate=False)
        host = SchedulerHost(
            (
                JobDefinition("slow", 1, lambda: None, 2),
                JobDefinition("other", 10, lambda: None, 20),
            ),
            clock=lambda: 0.0,
            executor=executor,
        )

        host.tick(0.0)
        states = {state.job_id: state for state in host.tick(2.0)}

        self.assertEqual(states["slow"].last_error, "timeout")
        self.assertTrue(states["slow"].running)
        self.assertEqual(len(executor.submissions), 2)
        self.assertIsNone(states["other"].last_failure_at)

    def test_signal_handler_only_requests_shutdown(self) -> None:
        executor = RecordingExecutor(immediate=False)
        host = SchedulerHost((), clock=lambda: 0.0, executor=executor)

        host.request_shutdown(15, None)

        self.assertTrue(host.shutdown_requested)
        self.assertEqual(executor.shutdown_calls, [])
        self.assertEqual(host.tick(0.0), ())
        host.close(wait=False)
        self.assertEqual(executor.shutdown_calls, [(False, True)])

    def test_job_definitions_require_safe_unique_identifiers_and_positive_limits(self) -> None:
        with self.assertRaises(ValueError):
            JobDefinition("", 1, lambda: None, 1)
        with self.assertRaises(ValueError):
            JobDefinition("bad id", 1, lambda: None, 1)
        with self.assertRaises(ValueError):
            JobDefinition("job", 0, lambda: None, 1)
        with self.assertRaises(ValueError):
            JobDefinition("job", 1, lambda: None, float("inf"))
        with self.assertRaises(ValueError):
            SchedulerHost(
                (
                    JobDefinition("same", 1, lambda: None, 1),
                    JobDefinition("same", 2, lambda: None, 1),
                ),
                clock=lambda: 0.0,
                executor=RecordingExecutor(),
            )


if __name__ == "__main__":
    unittest.main()
