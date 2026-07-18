from __future__ import annotations

from concurrent.futures import Future
import subprocess
from threading import Event, Thread
import unittest

from investment_knowledge_mcp.scheduler_host import (
    HistoryChildSupervisor,
    JobDefinition,
    SchedulerHost,
)


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


class FailingSubmitExecutor(RecordingExecutor):
    def submit(self, callback):
        raise RuntimeError("sensitive executor detail")


class FakeChild:
    def __init__(
        self,
        *,
        returncode: int | None = None,
        wait_times_out: bool = False,
        terminate_error: Exception | None = None,
        kill_error: Exception | None = None,
        final_wait_times_out: bool = False,
    ) -> None:
        self.returncode = returncode
        self.wait_times_out = wait_times_out
        self.terminate_error = terminate_error
        self.kill_error = kill_error
        self.final_wait_times_out = final_wait_times_out
        self.poll_calls = 0
        self.wait_calls: list[float | None] = []
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self) -> int | None:
        self.poll_calls += 1
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if self.wait_times_out and self.kill_calls == 0:
            raise subprocess.TimeoutExpired("history-child", timeout)
        if self.final_wait_times_out and self.kill_calls > 0:
            raise subprocess.TimeoutExpired("history-child", timeout)
        if self.returncode is None:
            self.returncode = -9 if self.kill_calls else -15
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self.terminate_error is not None:
            raise self.terminate_error

    def kill(self) -> None:
        self.kill_calls += 1
        if self.kill_error is not None:
            raise self.kill_error
        self.returncode = -9


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
        self.assertEqual(states["slow"].timed_out_runs, 1)
        self.assertEqual(len(executor.submissions), 2)
        self.assertIsNone(states["other"].last_failure_at)

    def test_submission_failure_does_not_report_job_as_started(self) -> None:
        host = SchedulerHost(
            (JobDefinition("daily", 5, lambda: None, 2),),
            clock=lambda: 0.0,
            executor=FailingSubmitExecutor(),
        )

        state = host.tick(0.0)[0]

        self.assertIsNone(state.last_started_at)
        self.assertEqual(state.last_finished_at, 0.0)
        self.assertEqual(state.last_failure_at, 0.0)
        self.assertEqual(state.last_error, "executor:RuntimeError")
        self.assertEqual(state.next_due_at, 5.0)
        self.assertNotIn("sensitive", repr(state))

    def test_timed_out_non_overlap_run_must_finish_before_next_start(self) -> None:
        executor = RecordingExecutor(immediate=False)
        host = SchedulerHost(
            (JobDefinition("slow", 1, lambda: None, 2),),
            clock=lambda: 0.0,
            executor=executor,
        )

        host.tick(0.0)
        timed_out = host.tick(2.0)[0]
        self.assertTrue(timed_out.running)
        self.assertEqual(timed_out.active_runs, 1)
        self.assertEqual(timed_out.timed_out_runs, 1)
        self.assertEqual(len(executor.submissions), 1)

        executor.run_submission(0)
        resumed = host.tick(3.0)[0]

        self.assertEqual(len(executor.submissions), 2)
        self.assertTrue(resumed.running)
        self.assertEqual(resumed.active_runs, 1)
        self.assertEqual(resumed.timed_out_runs, 0)

    def test_overlapping_success_does_not_hide_active_timed_out_run(self) -> None:
        executor = RecordingExecutor(immediate=False)
        host = SchedulerHost(
            (JobDefinition("overlap", 1, lambda: None, 2, allow_overlap=True),),
            clock=lambda: 0.0,
            executor=executor,
        )

        host.tick(0.0)
        timed_out = host.tick(2.0)[0]
        self.assertEqual(timed_out.active_runs, 2)
        self.assertEqual(timed_out.timed_out_runs, 1)

        executor.run_submission(1)
        state = host.tick(2.5)[0]

        self.assertEqual(state.last_success_at, 2.5)
        self.assertEqual(state.last_error, "timeout")
        self.assertEqual(state.active_runs, 1)
        self.assertEqual(state.timed_out_runs, 1)

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


class HistoryChildSupervisorTests(unittest.TestCase):
    def test_concurrent_polls_cannot_start_two_children(self) -> None:
        probe_entered = Event()
        release_probe = Event()
        children: list[FakeChild] = []

        def pending() -> bool:
            probe_entered.set()
            release_probe.wait(timeout=1.0)
            return True

        def factory() -> FakeChild:
            child = FakeChild()
            children.append(child)
            return child

        supervisor = HistoryChildSupervisor(pending, factory)
        first = Thread(target=supervisor.poll)
        first.start()
        self.assertTrue(probe_entered.wait(timeout=1.0))

        concurrent_state = supervisor.poll()
        release_probe.set()
        first.join(timeout=1.0)

        self.assertFalse(first.is_alive())
        self.assertTrue(concurrent_state.poll_in_flight)
        self.assertEqual(1, len(children))
        self.assertEqual(1, supervisor.health().starts)

    def test_close_prevents_child_start_after_in_flight_probe(self) -> None:
        probe_entered = Event()
        release_probe = Event()
        factory_calls = 0

        def pending() -> bool:
            probe_entered.set()
            release_probe.wait(timeout=1.0)
            return True

        def factory() -> FakeChild:
            nonlocal factory_calls
            factory_calls += 1
            return FakeChild()

        supervisor = HistoryChildSupervisor(pending, factory)
        polling = Thread(target=supervisor.poll)
        polling.start()
        self.assertTrue(probe_entered.wait(timeout=1.0))

        close_state = supervisor.close(timeout_seconds=0.01)
        release_probe.set()
        polling.join(timeout=1.0)

        self.assertFalse(close_state.running)
        self.assertTrue(close_state.poll_in_flight)
        self.assertEqual("close:poll_in_flight", close_state.last_error)
        self.assertFalse(polling.is_alive())
        self.assertEqual(0, factory_calls)
        self.assertFalse(supervisor.health().running)

    def test_close_discards_child_returned_by_in_flight_factory(self) -> None:
        factory_entered = Event()
        release_factory = Event()
        child = FakeChild()

        def factory() -> FakeChild:
            factory_entered.set()
            release_factory.wait(timeout=1.0)
            return child

        supervisor = HistoryChildSupervisor(lambda: True, factory)
        polling = Thread(target=supervisor.poll)
        polling.start()
        self.assertTrue(factory_entered.wait(timeout=1.0))

        close_state = supervisor.close(timeout_seconds=0.01)
        release_factory.set()
        polling.join(timeout=2.0)

        self.assertFalse(close_state.running)
        self.assertTrue(close_state.poll_in_flight)
        self.assertFalse(polling.is_alive())
        self.assertEqual(1, child.terminate_calls)
        self.assertEqual([1.0], child.wait_calls)
        self.assertFalse(supervisor.health().running)
        self.assertEqual(0, supervisor.health().starts)

    def test_close_kills_unpublished_child_when_terminate_raises(self) -> None:
        factory_entered = Event()
        release_factory = Event()
        secret = "provider credential detail"
        child = FakeChild(terminate_error=RuntimeError(secret))

        def factory() -> FakeChild:
            factory_entered.set()
            release_factory.wait(timeout=1.0)
            return child

        supervisor = HistoryChildSupervisor(lambda: True, factory)
        polling = Thread(target=supervisor.poll)
        polling.start()
        self.assertTrue(factory_entered.wait(timeout=1.0))

        supervisor.close(timeout_seconds=0.01)
        release_factory.set()
        polling.join(timeout=2.0)

        self.assertFalse(polling.is_alive())
        self.assertEqual(1, child.terminate_calls)
        self.assertEqual(1, child.kill_calls)
        self.assertEqual([1.0], child.wait_calls)
        state = supervisor.health()
        self.assertFalse(state.running)
        self.assertEqual(0, state.starts)
        self.assertEqual("discard:RuntimeError", state.last_error)
        self.assertNotIn(secret, repr(state))

    def test_unpublished_child_remains_owned_when_fallback_kill_fails(self) -> None:
        factory_entered = Event()
        release_factory = Event()
        child = FakeChild(
            terminate_error=RuntimeError("private terminate detail"),
            kill_error=OSError("private kill detail"),
        )

        def factory() -> FakeChild:
            factory_entered.set()
            release_factory.wait(timeout=1.0)
            return child

        supervisor = HistoryChildSupervisor(lambda: True, factory)
        polling = Thread(target=supervisor.poll)
        polling.start()
        self.assertTrue(factory_entered.wait(timeout=1.0))
        supervisor.close(timeout_seconds=0.01)
        release_factory.set()
        polling.join(timeout=2.0)

        state = supervisor.health()
        self.assertTrue(state.running)
        self.assertTrue(state.cleanup_pending)
        self.assertEqual("discard:RuntimeError|cleanup:OSError", state.last_error)
        self.assertNotIn("private", repr(state))

        child.terminate_error = None
        child.kill_error = None
        recovered = supervisor.close(timeout_seconds=0.1)
        self.assertFalse(recovered.running)
        self.assertFalse(recovered.cleanup_pending)

    def test_unpublished_child_remains_owned_when_final_wait_times_out(self) -> None:
        factory_entered = Event()
        release_factory = Event()
        child = FakeChild(wait_times_out=True, final_wait_times_out=True)

        def factory() -> FakeChild:
            factory_entered.set()
            release_factory.wait(timeout=1.0)
            return child

        supervisor = HistoryChildSupervisor(lambda: True, factory)
        polling = Thread(target=supervisor.poll)
        polling.start()
        self.assertTrue(factory_entered.wait(timeout=1.0))
        supervisor.close(timeout_seconds=0.01)
        release_factory.set()
        polling.join(timeout=2.0)

        state = supervisor.health()
        self.assertTrue(state.running)
        self.assertTrue(state.cleanup_pending)
        self.assertEqual("cleanup:TimeoutExpired", state.last_error)

        child.final_wait_times_out = False
        recovered = supervisor.close(timeout_seconds=0.1)
        self.assertFalse(recovered.running)
        self.assertFalse(recovered.cleanup_pending)

    def test_pending_work_starts_exactly_one_child_while_it_is_live(self) -> None:
        child = FakeChild()
        factory_calls = 0

        def factory() -> FakeChild:
            nonlocal factory_calls
            factory_calls += 1
            return child

        supervisor = HistoryChildSupervisor(lambda: True, factory)

        first = supervisor.poll()
        second = supervisor.poll()

        self.assertTrue(first.running)
        self.assertTrue(second.running)
        self.assertEqual(1, first.starts)
        self.assertEqual(1, factory_calls)

    def test_no_child_is_created_without_pending_work(self) -> None:
        factory_calls = 0

        def factory() -> FakeChild:
            nonlocal factory_calls
            factory_calls += 1
            return FakeChild()

        state = HistoryChildSupervisor(lambda: False, factory).poll()

        self.assertFalse(state.running)
        self.assertEqual(0, state.starts)
        self.assertEqual(0, factory_calls)

    def test_clean_and_nonzero_exits_are_recorded_without_raising(self) -> None:
        for exit_code in (0, 7):
            with self.subTest(exit_code=exit_code):
                child = FakeChild()
                pending = iter((True, False))
                supervisor = HistoryChildSupervisor(lambda: next(pending), lambda: child)
                supervisor.poll()
                child.returncode = exit_code

                state = supervisor.poll()

                self.assertFalse(state.running)
                self.assertEqual(exit_code, state.last_exit_code)
                self.assertEqual(None if exit_code == 0 else "exit:7", state.last_error)
                self.assertEqual([0.0], child.wait_calls)

    def test_crashed_child_can_be_replaced_when_work_remains(self) -> None:
        first = FakeChild()
        children = [first, FakeChild()]
        supervisor = HistoryChildSupervisor(lambda: True, lambda: children.pop(0))
        supervisor.poll()
        first.returncode = 9

        state = supervisor.poll()

        self.assertTrue(state.running)
        self.assertEqual(2, state.starts)
        self.assertEqual(9, state.last_exit_code)
        self.assertEqual("exit:9", state.last_error)

    def test_factory_and_probe_failures_are_sanitized(self) -> None:
        secret = "password=sensitive"

        def factory() -> FakeChild:
            raise RuntimeError(secret)

        factory_state = HistoryChildSupervisor(lambda: True, factory).poll()
        probe_state = HistoryChildSupervisor(
            lambda: (_ for _ in ()).throw(ValueError(secret)), lambda: FakeChild()
        ).poll()

        self.assertEqual("factory:RuntimeError", factory_state.last_error)
        self.assertEqual("probe:ValueError", probe_state.last_error)
        self.assertNotIn(secret, repr(factory_state))
        self.assertNotIn(secret, repr(probe_state))

    def test_close_terminates_then_kills_and_reaps_a_live_child(self) -> None:
        child = FakeChild(wait_times_out=True)
        supervisor = HistoryChildSupervisor(lambda: True, lambda: child)
        supervisor.poll()

        state = supervisor.close(timeout_seconds=0.1)

        self.assertFalse(state.running)
        self.assertEqual(1, child.terminate_calls)
        self.assertEqual(1, child.kill_calls)
        self.assertEqual([0.1, 0.1], child.wait_calls)
        self.assertEqual(-9, state.last_exit_code)

    def test_close_still_kills_and_reaps_when_terminate_raises(self) -> None:
        secret = "credential detail"
        child = FakeChild(terminate_error=RuntimeError(secret))
        supervisor = HistoryChildSupervisor(lambda: True, lambda: child)
        supervisor.poll()

        state = supervisor.close(timeout_seconds=0.1)

        self.assertFalse(state.running)
        self.assertEqual(1, child.terminate_calls)
        self.assertEqual(1, child.kill_calls)
        self.assertEqual([0.1], child.wait_calls)
        self.assertEqual(-9, state.last_exit_code)
        self.assertEqual("close:RuntimeError", state.last_error)
        self.assertNotIn(secret, repr(state))


if __name__ == "__main__":
    unittest.main()
