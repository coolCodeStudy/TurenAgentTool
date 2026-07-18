from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import math
from numbers import Real
import re
import signal
from threading import Event
from time import monotonic
from typing import Callable, Protocol, Sequence


_JOB_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class SubmittedJob(Protocol):
    def done(self) -> bool: ...

    def result(self) -> object: ...


class JobExecutor(Protocol):
    def submit(self, callback: Callable[[], object]) -> SubmittedJob: ...

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None: ...


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
    job_id: str
    running: bool
    active_runs: int
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

        runtime.last_started_at = now
        runtime.next_due_at = now + float(runtime.definition.interval_seconds)
        try:
            future = self._executor.submit(runtime.definition.run_once)
        except BaseException as exc:
            runtime.last_finished_at = now
            runtime.last_failure_at = now
            runtime.last_error = f"executor:{type(exc).__name__}"
            return
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
