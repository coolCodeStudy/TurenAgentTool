from __future__ import annotations

import argparse
from datetime import date, datetime, time
import logging
import os
from threading import Event
from typing import Any
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.config import AppConfig, get_config
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.futu_provider import get_futu_positions, get_futu_trade_history


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_FX_TO_USD = {
    "USD": 1.0,
    "HKD": 1.0 / 7.8,
}
_SNAPSHOT_LOOP_STARTED = False
_SNAPSHOT_LOOP_INTERVAL_SECONDS: int | None = None
_SNAPSHOT_LOOP_TIME: str | None = None


def run_account_snapshot_scheduler_forever(config: AppConfig | None = None, logger: logging.Logger | None = None) -> None:
    global _SNAPSHOT_LOOP_STARTED, _SNAPSHOT_LOOP_INTERVAL_SECONDS, _SNAPSHOT_LOOP_TIME

    config = config or get_config()
    logger = logger or logging.getLogger("investment_knowledge_mcp.account_snapshots")

    if not config.account_snapshot_scheduler_enabled:
        logger.info("Account snapshot scheduler disabled by ACCOUNT_SNAPSHOT_SCHEDULER_ENABLED=false")
        _wait_forever()
        return

    scheduled_time = _parse_time(config.account_snapshot_time)
    interval = max(60, config.account_snapshot_interval_seconds)
    _SNAPSHOT_LOOP_STARTED = True
    _SNAPSHOT_LOOP_INTERVAL_SECONDS = interval
    _SNAPSHOT_LOOP_TIME = scheduled_time.strftime("%H:%M")
    logger.info("Account snapshot scheduler started: time=%s interval_seconds=%s", _SNAPSHOT_LOOP_TIME, interval)
    _run_loop(scheduled_time, interval, logger)


def get_account_snapshot_loop_state() -> dict[str, Any]:
    return {
        "started": _SNAPSHOT_LOOP_STARTED,
        "interval_seconds": _SNAPSHOT_LOOP_INTERVAL_SECONDS,
        "time": _SNAPSHOT_LOOP_TIME,
    }


def run_account_snapshot_once(
    logger: logging.Logger | None = None,
    snapshot_date: date | None = None,
    trade_start: date | None = None,
) -> dict[str, Any]:
    logger = logger or logging.getLogger("investment_knowledge_mcp.account_snapshots")
    today = snapshot_date or datetime.now(SHANGHAI_TZ).date()
    trade_range_start = trade_start or today
    if trade_range_start > today:
        raise ValueError("trade_start must not be after snapshot_date")
    trade_snapshot = get_futu_trade_history(start=trade_range_start.isoformat(), end=today.isoformat())
    position_snapshot = get_futu_positions()
    trade_result = repository.upsert_trade_records(trade_snapshot.deals)
    fetched_at = trade_snapshot.fetched_at.astimezone(SHANGHAI_TZ)
    row = repository.upsert_account_snapshot(
        snapshot_date=today.isoformat(),
        account_info=trade_snapshot.account_info or {},
        positions=position_snapshot.positions,
        fx_rates=_current_fx_rates_for_snapshot(),
        fetched_at=fetched_at.isoformat(),
        metadata={
            "task": "daily_account_snapshot",
            "account_error": trade_snapshot.account_error,
            "position_count": len(position_snapshot.positions),
            "trade_count": len(trade_snapshot.deals),
            "trade_synced_count": trade_result["synced_count"],
            "trade_range_start": trade_range_start.isoformat(),
            "trade_range_end": today.isoformat(),
        },
    )
    logger.info(
        "saved account snapshot: date=%s id=%s trades=%s trade_range=%s:%s",
        row.get("snapshot_date"),
        row.get("id"),
        trade_result["synced_count"],
        trade_range_start.isoformat(),
        today.isoformat(),
    )
    return row


def _run_loop(scheduled_time: time, interval_seconds: int, logger: logging.Logger) -> None:
    last_attempted_date: date | None = None
    while True:
        now = datetime.now(SHANGHAI_TZ)
        if now.time() >= scheduled_time and last_attempted_date != now.date():
            try:
                run_account_snapshot_once(logger=logger, snapshot_date=now.date())
                last_attempted_date = now.date()
            except Exception:
                logger.exception("Account snapshot scheduler failed")
        Event().wait(interval_seconds)


def _wait_forever(interval_seconds: int = 3600) -> None:
    while True:
        Event().wait(interval_seconds)


def _parse_time(value: str) -> time:
    text = (value or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except Exception:
        return time(hour=0, minute=5)


def _current_fx_rates_for_snapshot() -> dict[str, Any]:
    return {
        currency: rate
        for currency in ("USD", "HKD", "CNY")
        if (rate := _fx_to_usd_rate(currency)) is not None
    }


def _fx_to_usd_rate(currency: str) -> float | None:
    normalized = str(currency or "").strip().upper()
    if not normalized or normalized == "UNKNOWN":
        return None
    env_key = f"FX_TO_USD_{normalized}"
    if os.getenv(env_key):
        return _positive_number(os.getenv(env_key))
    if normalized == "HKD" and os.getenv("FX_USD_HKD"):
        usd_hkd = _positive_number(os.getenv("FX_USD_HKD"))
        return 1.0 / usd_hkd if usd_hkd else None
    return DEFAULT_FX_TO_USD.get(normalized)


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=os.getenv("ACCOUNT_SNAPSHOT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return logging.getLogger("investment_knowledge_mcp.account_snapshots")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the standalone account snapshot scheduler.")
    parser.add_argument("--once", action="store_true", help="Save one account snapshot and exit.")
    args = parser.parse_args()

    logger = _setup_logging()
    run_schema()
    if args.once:
        run_account_snapshot_once(logger=logger)
        return
    run_account_snapshot_scheduler_forever(logger=logger)


if __name__ == "__main__":
    main()
