from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
import os
from threading import Event, Thread
from typing import Any, Iterator

from investment_knowledge_mcp.daily_market_brief import (
    build_daily_market_brief,
    get_daily_market_brief_report,
    save_daily_market_brief_report,
)
from investment_knowledge_mcp.daily_market_history import load_historical_market_activity
from investment_knowledge_mcp.daily_market_jobs import (
    PUBLIC_ERROR_SUMMARIES,
    claim_next_history_item,
    finish_history_item,
    heartbeat_history_item,
    requeue_stale_history_items,
)


LOGGER = logging.getLogger("daily_market_brief_history_worker")
HEARTBEAT_INTERVAL_SECONDS = 10.0
STALE_AFTER_SECONDS = 900.0


def run_worker_once(
    *,
    worker_name: str,
    item_timeout_seconds: float = 600.0,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    item = claim_next_history_item(worker_name)
    if item is None:
        return None

    lease = _lease_kwargs(item)
    item_id = int(item["id"])
    initial_state = heartbeat_history_item(item_id, **lease)
    if initial_state is None:
        return {"item_id": item_id, "status": "lease_lost"}
    if initial_state.get("cancel_requested"):
        return _finish(item, status="cancelled")

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

    timeout_seconds = max(0.001, float(item_timeout_seconds))
    cancel_seen = Event()
    lease_lost = Event()
    try:
        with _heartbeat_loop(item_id, lease, cancel_seen, lease_lost):
            result = build_daily_market_brief(
                market=item["market"],
                market_date=item["market_date"],
                save=False,
                now=now,
                historical_activity_provider=lambda market, market_date: load_historical_market_activity(
                    market,
                    market_date,
                    timeout_seconds=timeout_seconds,
                ),
            )
        if lease_lost.is_set():
            LOGGER.warning("history item lease lost before finalization: item_id=%s", item_id)
            return {"item_id": item_id, "status": "lease_lost"}
        final_state = heartbeat_history_item(item_id, **lease)
        if final_state is None:
            return {"item_id": item_id, "status": "lease_lost"}
        if cancel_seen.is_set() or final_state.get("cancel_requested"):
            return _finish(item, status="cancelled")

        saved = save_daily_market_brief_report(context=result.context, markdown=result.markdown)
        report_id = int(saved["id"])
        _finish(item, status="completed", report_id=report_id)
        return {
            "item_id": item_id,
            "status": "completed",
            "report_id": report_id,
            "partial": _is_partial_result(result.context),
        }
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
    stale_before = _utcnow() - timedelta(seconds=STALE_AFTER_SECONDS)
    recovered = requeue_stale_history_items(stale_before)
    if recovered:
        LOGGER.info("requeued stale history items: count=%s", recovered)

    delay = max(0.0, float(poll_seconds))
    LOGGER.info("daily market brief history worker started: worker=%s", worker_name)
    while not stop.is_set():
        outcome = run_worker_once(worker_name=worker_name)
        if outcome is None:
            stop.wait(delay)
        else:
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
    finish_history_item(
        int(item["id"]),
        status=status,
        report_id=report_id,
        error_code=error_code,
        error_summary=error_summary,
        **_lease_kwargs(item),
    )
    outcome = {"item_id": int(item["id"]), "status": status}
    if report_id is not None:
        outcome["report_id"] = report_id
    return outcome


def _lease_kwargs(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "worker_name": str(item["worker_name"]),
        "lease_token": str(item["lease_token"]),
        "attempt_count": int(item["attempt_count"]),
    }


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued historical daily market brief jobs.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_worker_forever(poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    main()
