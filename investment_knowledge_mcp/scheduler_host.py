from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import math
from numbers import Real
import re
import signal
import subprocess
from threading import Condition, Event
from time import monotonic
from typing import Callable, Protocol, Sequence


_JOB_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class SubmittedJob(Protocol):
    def done(self) -> bool: ...

    def result(self) -> object: ...


class JobExecutor(Protocol):
    def submit(self, callback: Callable[[], object]) -> SubmittedJob: ...

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None: ...


class HistoryChildProcess(Protocol):
    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


@dataclass(frozen=True)
class HistoryChildState:
    running: bool
    starts: int
    poll_in_flight: bool = False
    last_exit_code: int | None = None
    last_error: str | None = None


class HistoryChildSupervisor:
    """Own at most one externally bounded history-worker subprocess."""

    def __init__(
        self,
        pending_work: Callable[[], bool],
        child_factory: Callable[[], HistoryChildProcess],
    ) -> None:
        if not callable(pending_work):
            raise ValueError("pending_work must be callable")
        if not callable(child_factory):
            raise ValueError("child_factory must be callable")
        self._pending_work = pending_work
        self._child_factory = child_factory
        self._child: HistoryChildProcess | None = None
        self._starts = 0
        self._last_exit_code: int | None = None
        self._last_error: str | None = None
        self._closed = False
        self._poll_in_flight = False
        self._condition = Condition()

    def poll(self) -> HistoryChildState:
        with self._condition:
            if self._closed or self._poll_in_flight:
                return self._health_unlocked()
            self._poll_in_flight = True
        try:
            return self._poll_claimed()
        finally:
            with self._condition:
                self._poll_in_flight = False
                self._condition.notify_all()

    def _poll_claimed(self) -> HistoryChildState:
        with self._condition:
            child = self._child
        if child is not None:
            try:
                exit_code = child.poll()
            except Exception as exc:
                self._set_error(f"poll:{type(exc).__name__}")
                return self.health()
            if exit_code is None:
                return self.health()
            self._record_exit(child, exit_code)

        try:
            pending = bool(self._pending_work())
        except Exception as exc:
            self._set_error(f"probe:{type(exc).__name__}")
            return self.health()
        if not pending:
            return self.health()
        with self._condition:
            if self._closed:
                return self._health_unlocked()
        try:
            child = self._child_factory()
            if child is None:
                raise TypeError("child factory returned no process")
        except Exception as exc:
            self._set_error(f"factory:{type(exc).__name__}")
            return self.health()

        with self._condition:
            if not self._closed:
                self._child = child
                self._starts += 1
                return self._health_unlocked()

        self._stop_unpublished_child(child)
        return self.health()

    def health(self) -> HistoryChildState:
        with self._condition:
            return self._health_unlocked()

    def _health_unlocked(self) -> HistoryChildState:
        return HistoryChildState(
            running=self._child is not None,
            starts=self._starts,
            poll_in_flight=self._poll_in_flight,
            last_exit_code=self._last_exit_code,
            last_error=self._last_error,
        )

    def close(self, *, timeout_seconds: float = 5.0) -> HistoryChildState:
        _require_positive_finite(timeout_seconds, "timeout_seconds")
        timeout = float(timeout_seconds)
        deadline = monotonic() + timeout
        with self._condition:
            self._closed = True
            while self._poll_in_flight:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    self._last_error = "close:poll_in_flight"
                    return self._health_unlocked()
                self._condition.wait(timeout=remaining)
            child = self._child
        if child is None:
            return self.health()

        try:
            exit_code = child.poll()
        except Exception as exc:
            self._set_error(f"close_poll:{type(exc).__name__}")
        else:
            if exit_code is not None:
                self._record_exit(child, exit_code)
                return self.health()

        try:
            child.terminate()
            exit_code = child.wait(timeout=float(timeout_seconds))
        except subprocess.TimeoutExpired:
            return self._kill_and_reap(child, timeout_seconds=float(timeout_seconds))
        except Exception as exc:
            first_error = f"close:{type(exc).__name__}"
            state = self._kill_and_reap(child, timeout_seconds=float(timeout_seconds))
            if not state.running:
                self._set_error(first_error)
                return self.health()
            return state

        self._record_exit(child, exit_code, already_reaped=True)
        return self.health()

    def _kill_and_reap(
        self,
        child: HistoryChildProcess,
        *,
        timeout_seconds: float,
    ) -> HistoryChildState:
        try:
            child.kill()
            exit_code = child.wait(timeout=timeout_seconds)
        except Exception as exc:
            self._set_error(f"close:{type(exc).__name__}")
            return self.health()
        self._record_exit(child, exit_code, already_reaped=True)
        return self.health()

    def _stop_unpublished_child(self, child: HistoryChildProcess) -> None:
        first_error: str | None = None
        try:
            child.terminate()
        except Exception as exc:
            first_error = f"discard:{type(exc).__name__}"
        else:
            try:
                child.wait(timeout=1.0)
                return
            except subprocess.TimeoutExpired:
                pass
            except Exception as exc:
                first_error = f"discard:{type(exc).__name__}"

        try:
            child.kill()
            child.wait(timeout=1.0)
        except Exception as exc:
            self._set_error(f"discard:{type(exc).__name__}")
            return
        if first_error is not None:
            self._set_error(first_error)

    def _record_exit(
        self,
        child: HistoryChildProcess,
        exit_code: int,
        *,
        already_reaped: bool = False,
    ) -> None:
        normalized_code = int(exit_code)
        reap_error: str | None = None
        if not already_reaped:
            try:
                child.wait(timeout=0.0)
            except Exception as exc:
                reap_error = f"reap:{type(exc).__name__}"
        with self._condition:
            if self._child is child:
                self._child = None
            self._last_exit_code = normalized_code
            self._last_error = reap_error or (
                None if normalized_code == 0 else f"exit:{normalized_code}"
            )

    def _set_error(self, error: str) -> None:
        with self._condition:
            self._last_error = error


@dataclass(frozen=True)
class JobDefinition:
    job_id: str
    interval_seconds: float
    run_once: Callable[[], object] = field(repr=False)
    timeout_seconds: float
    allow_overlap: bool = False

    def __post_init__(self) -> None:
        normalized_id = str(self.job_id or "").strip()
        if not _JOB_ID_PATTERN.fullmatch(normalized_id):
            raise ValueError("job_id must be a lowercase safe identifier")
        object.__setattr__(self, "job_id", normalized_id)
        _require_positive_finite(self.interval_seconds, "interval_seconds")
        _require_positive_finite(self.timeout_seconds, "timeout_seconds")
        if not callable(self.run_once):
            raise ValueError("run_once must be callable")
        if not isinstance(self.allow_overlap, bool):
            raise ValueError("allow_overlap must be a boolean")


@dataclass(frozen=True)
class JobState:
    """Observable state; ``timed_out_runs`` are still-live thread callbacks."""

    job_id: str
    running: bool
    active_runs: int
    timed_out_runs: int
    next_due_at: float
    last_started_at: float | None = None
    last_finished_at: float | None = None
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error: str | None = None


@dataclass
class _ActiveRun:
    future: SubmittedJob
    started_at: float
    timeout_reported: bool = False


@dataclass
class _JobRuntime:
    definition: JobDefinition
    next_due_at: float
    active_runs: list[_ActiveRun] = field(default_factory=list)
    last_started_at: float | None = None
    last_finished_at: float | None = None
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error: str | None = None


class SchedulerHost:
    """Monotonic, independently supervised execution for periodic one-shot jobs.

    ``tick`` is deliberately deterministic: callers may supply a monotonic
    timestamp and an executor. Worker exceptions are reduced to their type so
    health output cannot expose provider or credential detail.

    Thread timeouts are observation-only: Python cannot safely terminate a
    running callback. In-process job adapters must therefore be bounded or
    cooperatively cancellable. Work that requires enforced termination belongs
    behind a subprocess boundary, not this thread executor.
    """

    def __init__(
        self,
        jobs: Sequence[JobDefinition],
        *,
        clock: Callable[[], float] = monotonic,
        executor: JobExecutor | None = None,
    ) -> None:
        definitions = tuple(jobs)
        identifiers = [definition.job_id for definition in definitions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("job_id values must be unique")
        if not callable(clock):
            raise ValueError("clock must be callable")
        initial_now = _require_finite_time(clock())
        self._clock = clock
        self._executor: JobExecutor = executor or ThreadPoolExecutor(
            max_workers=max(1, len(definitions)),
            thread_name_prefix="scheduler-job",
        )
        self._jobs = [
            _JobRuntime(definition=definition, next_due_at=initial_now)
            for definition in definitions
        ]
        self._shutdown = Event()
        self._closed = False
        self._last_tick_at: float | None = None

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown.is_set()

    def tick(self, now: float | None = None) -> tuple[JobState, ...]:
        current = _require_finite_time(self._clock() if now is None else now)
        if self._last_tick_at is not None and current < self._last_tick_at:
            raise ValueError("tick time must be monotonic")
        self._last_tick_at = current

        for runtime in self._jobs:
            self._reap(runtime, current)

        if not self.shutdown_requested:
            for runtime in self._jobs:
                self._start_if_due(runtime, current)

            # Inline and deterministic executors may finish during submit.
            for runtime in self._jobs:
                self._reap(runtime, current)

        return self.health()

    def health(self) -> tuple[JobState, ...]:
        return tuple(
            JobState(
                job_id=runtime.definition.job_id,
                running=bool(runtime.active_runs),
                active_runs=len(runtime.active_runs),
                timed_out_runs=sum(active.timeout_reported for active in runtime.active_runs),
                next_due_at=runtime.next_due_at,
                last_started_at=runtime.last_started_at,
                last_finished_at=runtime.last_finished_at,
                last_success_at=runtime.last_success_at,
                last_failure_at=runtime.last_failure_at,
                last_error=runtime.last_error,
            )
            for runtime in self._jobs
        )

    def request_shutdown(self, _signum: int | None = None, _frame: object = None) -> None:
        """Signal-handler-safe boundary: set a flag and perform no blocking work."""

        self._shutdown.set()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self.request_shutdown)
        signal.signal(signal.SIGTERM, self.request_shutdown)

    def run_forever(self, *, poll_interval_seconds: float = 1.0) -> None:
        _require_positive_finite(poll_interval_seconds, "poll_interval_seconds")
        self.install_signal_handlers()
        try:
            while not self.shutdown_requested:
                self.tick()
                self._shutdown.wait(float(poll_interval_seconds))
        finally:
            self.close(wait=False)

    def close(self, *, wait: bool = False) -> None:
        """Stop new submissions and close the executor.

        ``wait=False`` does not wait for or terminate callbacks that are already
        running, so it is not a bounded-shutdown guarantee. Pending callbacks
        are only cancellation requests delegated to the executor.
        """

        if self._closed:
            return
        self.request_shutdown()
        self._executor.shutdown(wait=wait, cancel_futures=True)
        self._closed = True

    def _start_if_due(self, runtime: _JobRuntime, now: float) -> None:
        if now < runtime.next_due_at:
            return
        if runtime.active_runs and not runtime.definition.allow_overlap:
            return

        runtime.next_due_at = now + float(runtime.definition.interval_seconds)
        try:
            future = self._executor.submit(runtime.definition.run_once)
        except BaseException as exc:
            runtime.last_finished_at = now
            runtime.last_failure_at = now
            runtime.last_error = f"executor:{type(exc).__name__}"
            return
        runtime.last_started_at = now
        runtime.active_runs.append(_ActiveRun(future=future, started_at=now))

    def _reap(self, runtime: _JobRuntime, now: float) -> None:
        remaining: list[_ActiveRun] = []
        for active in runtime.active_runs:
            if active.future.done():
                runtime.last_finished_at = now
                if active.timeout_reported:
                    continue
                try:
                    active.future.result()
                except BaseException as exc:
                    runtime.last_failure_at = now
                    runtime.last_error = f"exception:{type(exc).__name__}"
                else:
                    runtime.last_success_at = now
                    runtime.last_error = None
                continue

            elapsed = now - active.started_at
            if elapsed >= float(runtime.definition.timeout_seconds) and not active.timeout_reported:
                active.timeout_reported = True
                runtime.last_failure_at = now
                runtime.last_error = "timeout"
            remaining.append(active)
        runtime.active_runs = remaining
        if any(active.timeout_reported for active in remaining):
            runtime.last_error = "timeout"


def _require_positive_finite(value: object, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ValueError(f"{name} must be a finite positive real number")


def _require_finite_time(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise ValueError("time must be a finite real number")
    return float(value)
