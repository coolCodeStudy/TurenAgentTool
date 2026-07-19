from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Protocol

from investment_knowledge_mcp.daily_market_jobs import has_pending_history_items
from investment_knowledge_mcp.scheduler_host import (
    HistoryChildState,
    HistoryChildSupervisor,
    JobState,
)
from investment_knowledge_mcp.scheduler_jobs import default_scheduler_host


DEFAULT_HEALTH_PATH = Path("/tmp/scheduler-host-health.json")
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_MAX_HEALTH_AGE_SECONDS = 30.0
DEFAULT_HISTORY_CLOSE_TIMEOUT_SECONDS = 10.0


class SchedulerHostLike(Protocol):
    shutdown_requested: bool

    def tick(self) -> tuple[JobState, ...]: ...

    def request_shutdown(self, _signum: int | None = None, _frame: object = None) -> None: ...

    def close(self, *, wait: bool = False) -> None: ...


class HistorySupervisorLike(Protocol):
    def poll(self) -> HistoryChildState: ...

    def close(self, *, timeout_seconds: float) -> HistoryChildState: ...


def history_worker_command(project_root: Path) -> tuple[str, ...]:
    return (
        sys.executable,
        str(project_root / "scripts" / "daily_market_brief_history_worker.py"),
        "--drain-until-idle",
    )


def _start_history_child(project_root: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(history_worker_command(project_root), cwd=project_root)


class SchedulerService:
    """Production loop joining scheduler jobs with an isolated history child.

    In-process job shutdown is observation-only because Python threads cannot be
    forcefully terminated. Shutdown therefore stops submissions, closes the
    executor without waiting, and only then terminates and reaps the killable
    history subprocess.
    """

    def __init__(
        self,
        *,
        host: SchedulerHostLike,
        history_supervisor: HistorySupervisorLike,
        health_path: Path = DEFAULT_HEALTH_PATH,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.host = host
        self.history_supervisor = history_supervisor
        self.health_path = Path(health_path)
        self.wall_clock = wall_clock
        self._closed = False

    def tick(self) -> dict[str, Any]:
        jobs = self.host.tick()
        child = self.history_supervisor.poll()
        snapshot = _health_snapshot(jobs, child, updated_at_epoch=self.wall_clock())
        _write_health_snapshot(self.health_path, snapshot)
        return snapshot

    def request_shutdown(self, signum: int | None = None, frame: object = None) -> None:
        self.host.request_shutdown(signum, frame)

    def run_forever(self, *, poll_interval_seconds: float = DEFAULT_POLL_SECONDS) -> None:
        if not math.isfinite(poll_interval_seconds) or poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive and finite")
        signal.signal(signal.SIGINT, self.request_shutdown)
        signal.signal(signal.SIGTERM, self.request_shutdown)
        try:
            while not self.host.shutdown_requested:
                self.tick()
                time.sleep(poll_interval_seconds)
        finally:
            self.close()

    def close(
        self,
        *,
        history_timeout_seconds: float = DEFAULT_HISTORY_CLOSE_TIMEOUT_SECONDS,
    ) -> None:
        if self._closed:
            return
        self.host.request_shutdown()
        self.host.close(wait=False)
        self.history_supervisor.close(timeout_seconds=history_timeout_seconds)
        self._closed = True


def build_default_service(
    *,
    project_root: Path | None = None,
    health_path: Path = DEFAULT_HEALTH_PATH,
) -> SchedulerService:
    root = project_root or Path(__file__).resolve().parents[1]
    supervisor = HistoryChildSupervisor(
        has_pending_history_items,
        lambda: _start_history_child(root),
    )
    return SchedulerService(
        host=default_scheduler_host(),
        history_supervisor=supervisor,
        health_path=health_path,
    )


def check_health_snapshot(
    path: Path = DEFAULT_HEALTH_PATH,
    *,
    now: float | None = None,
    max_age_seconds: float = DEFAULT_MAX_HEALTH_AGE_SECONDS,
) -> bool:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not _healthy_supervision_state(payload):
            return False
        updated_at = float(payload["updated_at_epoch"])
        current = time.time() if now is None else float(now)
        age = current - updated_at
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
    return math.isfinite(age) and 0 <= age <= max_age_seconds


def _healthy_supervision_state(payload: dict[str, Any]) -> bool:
    jobs = payload.get("jobs")
    child = payload.get("history_child")
    if not isinstance(jobs, list) or not jobs or not isinstance(child, dict):
        return False
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("job_id"), str) or not job["job_id"]:
            return False
        running = job.get("running")
        active_runs = job.get("active_runs")
        timed_out_runs = job.get("timed_out_runs")
        if (
            not isinstance(running, bool)
            or isinstance(active_runs, bool)
            or not isinstance(active_runs, int)
            or active_runs < 0
            or isinstance(timed_out_runs, bool)
            or not isinstance(timed_out_runs, int)
            or timed_out_runs < 0
            or timed_out_runs > active_runs
            or running != (active_runs > 0)
        ):
            return False
        if timed_out_runs:
            return False

    required_booleans = ("running", "poll_in_flight", "cleanup_pending")
    if any(not isinstance(child.get(name), bool) for name in required_booleans):
        return False
    starts = child.get("starts")
    if isinstance(starts, bool) or not isinstance(starts, int) or starts < 0:
        return False
    if child["cleanup_pending"] or (child["running"] and starts == 0):
        return False
    exit_code = child.get("last_exit_code")
    last_error = child.get("last_error")
    if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
        return False
    if exit_code not in (None, 0):
        return False
    if last_error is not None and not isinstance(last_error, str):
        return False
    if isinstance(last_error, str) and last_error.startswith(
        ("probe:", "factory:", "poll:", "reap:", "cleanup:", "close_poll:")
    ):
        return False
    return True


def _health_snapshot(
    jobs: tuple[JobState, ...],
    child: HistoryChildState,
    *,
    updated_at_epoch: float,
) -> dict[str, Any]:
    return {
        "updated_at_epoch": float(updated_at_epoch),
        "jobs": [asdict(job) for job in jobs],
        "history_child": asdict(child),
    }


def _write_health_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the consolidated scheduler host.")
    parser.add_argument("--check-health", action="store_true")
    parser.add_argument("--health-path", type=Path, default=DEFAULT_HEALTH_PATH)
    parser.add_argument("--max-health-age-seconds", type=float, default=DEFAULT_MAX_HEALTH_AGE_SECONDS)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    args = parser.parse_args(argv)
    if args.check_health:
        return 0 if check_health_snapshot(
            args.health_path,
            max_age_seconds=args.max_health_age_seconds,
        ) else 1
    build_default_service(health_path=args.health_path).run_forever(
        poll_interval_seconds=args.poll_seconds
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
