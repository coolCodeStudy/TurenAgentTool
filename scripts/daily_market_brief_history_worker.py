from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import signal
import sys
from threading import Event, Thread, current_thread, main_thread
from time import monotonic
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.daily_market_brief import (
    build_daily_market_brief,
    get_daily_market_brief_report,
    resolve_latest_completed_session_date,
    validate_daily_market_brief_context_for_save,
)
from investment_knowledge_mcp.daily_market_history import (
    HistoricalActivityCancelled,
    load_historical_market_activity,
)
from investment_knowledge_mcp.daily_market_jobs import (
    HISTORY_STALE_AFTER_SECONDS,
    PUBLIC_ERROR_SUMMARIES,
    claim_next_history_item,
    finalize_history_item_report,
    finish_history_item,
    heartbeat_history_item,
    requeue_stale_history_items,
)


LOGGER = logging.getLogger("daily_market_brief_history_worker")
HEARTBEAT_INTERVAL_SECONDS = 10.0
STALE_AFTER_SECONDS = float(HISTORY_STALE_AFTER_SECONDS)
RECOVERY_INTERVAL_SECONDS = 60.0
DRAIN_ERROR_EXIT_CODE = 1


class ItemDeadlineExceeded(BaseException):
    pass


def run_worker_once(
    *,
    worker_name: str,
    item_timeout_seconds: float = 600.0,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    item = claim_next_history_item(worker_name)
    if item is None:
        return None

    timeout_seconds = max(0.001, float(item_timeout_seconds))
    deadline = _monotonic() + timeout_seconds
    try:
        with _item_deadline(timeout_seconds):
            return _process_claimed_item(item, deadline=deadline, now=now)
    except ItemDeadlineExceeded:
        LOGGER.warning("history item deadline exceeded: item_id=%s", item["id"])
        try:
            _finish(
                item,
                status="failed",
                error_code="provider_timeout",
                error_summary=PUBLIC_ERROR_SUMMARIES["provider_timeout"],
            )
        except ValueError:
            LOGGER.warning("timed out history item lease is no longer active: item_id=%s", item["id"])
        return {"item_id": int(item["id"]), "status": "failed", "error_code": "provider_timeout"}


def _process_claimed_item(
    item: dict[str, Any],
    *,
    deadline: float,
    now: datetime | None,
) -> dict[str, Any]:

    lease = _lease_kwargs(item)
    item_id = int(item["id"])
    initial_state = heartbeat_history_item(item_id, **lease)
    if initial_state is None:
        return {"item_id": item_id, "status": "lease_lost"}
    if initial_state.get("cancel_requested"):
        return _finish(item, status="cancelled")

    effective_now = now or datetime.now(timezone.utc)
    target_date = _item_market_date(item)
    latest_completed = resolve_latest_completed_session_date(item["market"], now=effective_now)
    if target_date >= latest_completed:
        return _finish(
            item,
            status="failed",
            error_code="historical_data_unavailable",
            error_summary=PUBLIC_ERROR_SUMMARIES["historical_data_unavailable"],
        )

    existing = get_daily_market_brief_report(item["market"], item["market_date"])
    if existing is not None and not bool(item.get("force_refresh")):
        skip_state = heartbeat_history_item(item_id, **lease)
        if skip_state is None:
            return {"item_id": item_id, "status": "lease_lost"}
        if skip_state.get("cancel_requested"):
            return _finish(item, status="cancelled")
        report_id = int(existing["id"])
        _finish(item, status="skipped", report_id=report_id)
        return {"item_id": item_id, "status": "skipped", "report_id": report_id}

    cancel_seen = Event()
    lease_lost = Event()
    try:
        with _heartbeat_loop(item_id, lease, cancel_seen, lease_lost):
            result = build_daily_market_brief(
                market=item["market"],
                market_date=target_date,
                save=False,
                now=now,
                historical_activity_provider=lambda market, market_date: load_historical_market_activity(
                    market,
                    market_date,
                    timeout_seconds=_remaining_seconds(deadline),
                    cancel_event=cancel_seen,
                ),
            )
        if lease_lost.is_set():
            LOGGER.warning("history item lease lost before finalization: item_id=%s", item_id)
            return {"item_id": item_id, "status": "lease_lost"}
        validate_daily_market_brief_context_for_save(
            result.context, existing_report=existing
        )
        finalized = finalize_history_item_report(
            item_id,
            context=result.context,
            markdown=result.markdown,
            **lease,
        )
        if finalized["status"] == "cancelled":
            return {"item_id": item_id, "status": "cancelled"}
        report_id = int(finalized["report_id"])
        return {
            "item_id": item_id,
            "status": "completed",
            "report_id": report_id,
            "partial": _is_partial_result(result.context),
        }
    except HistoricalActivityCancelled:
        if lease_lost.is_set():
            return {"item_id": item_id, "status": "lease_lost"}
        return _finish(item, status="cancelled")
    except Exception as exc:
        error_code, error_summary = _public_history_job_error(exc)
        LOGGER.warning(
            "history item failed: item_id=%s error_code=%s exception_type=%s",
            item_id,
            error_code,
            type(exc).__name__,
        )
        try:
            _finish(
                item,
                status="failed",
                error_code=error_code,
                error_summary=error_summary,
            )
        except ValueError:
            LOGGER.warning("history item failure could not finalize stale lease: item_id=%s", item_id)
        return {"item_id": item_id, "status": "failed", "error_code": error_code}


def run_worker_forever(*, poll_seconds: float = 5.0, stop_event: Event | None = None) -> None:
    stop = stop_event or Event()
    worker_name = _default_worker_name()
    delay = max(0.0, float(poll_seconds))
    next_recovery = 0.0
    LOGGER.info("daily market brief history worker started: worker=%s", worker_name)
    while not stop.is_set():
        now_tick = _monotonic()
        if now_tick >= next_recovery:
            try:
                recovered = requeue_stale_history_items(
                    _utcnow() - timedelta(seconds=STALE_AFTER_SECONDS)
                )
                if recovered:
                    LOGGER.info("requeued stale history items: count=%s", recovered)
            except Exception as exc:
                LOGGER.warning("history stale recovery failed: exception_type=%s", type(exc).__name__)
            next_recovery = now_tick + RECOVERY_INTERVAL_SECONDS
        try:
            outcome = run_worker_once(worker_name=worker_name)
        except Exception as exc:
            LOGGER.warning("history worker iteration failed: exception_type=%s", type(exc).__name__)
            outcome = None
        if outcome is None:
            stop.wait(delay)
        else:
            LOGGER.info(
                "history item checkpointed: item_id=%s status=%s report_id=%s",
                outcome.get("item_id"),
                outcome.get("status"),
                outcome.get("report_id"),
            )


def drain_worker_until_idle() -> int:
    """Process the current queue with one worker identity, then return its item count."""

    worker_name = _default_worker_name()
    recovered = requeue_stale_history_items(
        _utcnow() - timedelta(seconds=STALE_AFTER_SECONDS)
    )
    if recovered:
        LOGGER.info("requeued stale history items: count=%s", recovered)

    processed = 0
    while True:
        outcome = run_worker_once(worker_name=worker_name)
        if outcome is None:
            return processed
        processed += 1
        LOGGER.info(
            "history item checkpointed: item_id=%s status=%s report_id=%s",
            outcome.get("item_id"),
            outcome.get("status"),
            outcome.get("report_id"),
        )


@contextmanager
def _heartbeat_loop(
    item_id: int,
    lease: dict[str, Any],
    cancel_seen: Event,
    lease_lost: Event,
) -> Iterator[None]:
    stop = Event()

    def beat() -> None:
        while not stop.wait(max(0.001, HEARTBEAT_INTERVAL_SECONDS)):
            try:
                state = heartbeat_history_item(item_id, **lease)
            except Exception as exc:
                LOGGER.warning(
                    "history item heartbeat failed: item_id=%s exception_type=%s",
                    item_id,
                    type(exc).__name__,
                )
                continue
            if state is None:
                lease_lost.set()
                cancel_seen.set()
                return
            if state.get("cancel_requested"):
                cancel_seen.set()

    thread = Thread(target=beat, name=f"daily-market-history-heartbeat-{item_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=max(0.1, HEARTBEAT_INTERVAL_SECONDS + 0.1))


def _finish(
    item: dict[str, Any],
    *,
    status: str,
    report_id: int | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    finished = finish_history_item(
        int(item["id"]),
        status=status,
        report_id=report_id,
        error_code=error_code,
        error_summary=error_summary,
        **_lease_kwargs(item),
    )
    actual_status = str(finished.get("status") or status)
    outcome = {"item_id": int(item["id"]), "status": actual_status}
    actual_report_id = finished.get("report_id")
    if actual_report_id is not None:
        outcome["report_id"] = int(actual_report_id)
    return outcome


def _lease_kwargs(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "worker_name": str(item["worker_name"]),
        "lease_token": str(item["lease_token"]),
        "attempt_count": int(item["attempt_count"]),
    }


def _item_market_date(item: dict[str, Any]) -> date:
    value = item["market_date"]
    return value if type(value) is date else date.fromisoformat(str(value))


def _public_history_job_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, TimeoutError):
        code = "provider_timeout"
    elif isinstance(exc, (ConnectionError, ImportError, ModuleNotFoundError)):
        code = "provider_unavailable"
    elif isinstance(exc, ValueError) and any(
        marker in str(exc) for marker in ("暂不可用", "未找到", "无可用", "not available")
    ):
        code = "historical_data_unavailable"
    else:
        code = "generation_failed"
    return code, PUBLIC_ERROR_SUMMARIES[code]


def _is_partial_result(context: dict[str, Any]) -> bool:
    if context.get("no_session"):
        return False
    statuses = context.get("source_status") or {}
    return any(
        isinstance(value, dict)
        and value.get("status") in {
            "partial",
            "timed_out",
            "provider_unavailable",
            "historical_not_supported",
            "not_available",
            "missing",
        }
        for key, value in statuses.items()
        if key != "session"
    )


def _default_worker_name() -> str:
    return os.environ.get("DAILY_MARKET_BRIEF_HISTORY_WORKER_NAME") or f"history-worker-{os.getpid()}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _monotonic() -> float:
    return monotonic()


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - _monotonic()
    if remaining <= 0:
        raise ItemDeadlineExceeded()
    return remaining


@contextmanager
def _item_deadline(timeout_seconds: float) -> Iterator[None]:
    if current_thread() is not main_thread():
        raise RuntimeError("history item deadlines require the worker main thread")

    def expire(signum: int, frame: Any) -> None:
        raise ItemDeadlineExceeded()

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, expire)
    started = _monotonic()
    previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            elapsed = _monotonic() - started
            signal.setitimer(
                signal.ITIMER_REAL,
                max(0.000001, previous_timer[0] - elapsed),
                previous_timer[1],
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process queued historical daily market brief jobs.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--drain-until-idle", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.drain_until_idle:
        try:
            drain_worker_until_idle()
        except Exception as exc:
            LOGGER.error("history drain failed: exception_type=%s", type(exc).__name__)
            return DRAIN_ERROR_EXIT_CODE
        return 0
    run_worker_forever(poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
