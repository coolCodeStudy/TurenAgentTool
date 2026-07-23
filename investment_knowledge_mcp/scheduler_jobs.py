from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
import logging
from time import monotonic
from zoneinfo import ZoneInfo

from investment_knowledge_mcp.account_snapshots import run_account_snapshot_once
from investment_knowledge_mcp.config import AppConfig, get_config
from investment_knowledge_mcp.daily_market_brief import (
    resolve_latest_completed_session_date,
    run_daily_market_brief_once,
    should_run_daily_market_brief,
)
from investment_knowledge_mcp.ipo_reminders import run_ipo_reminder_once
from investment_knowledge_mcp.scheduler_host import JobDefinition, JobExecutor, SchedulerHost


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
MIN_INTERVAL_SECONDS = 60
MAX_INTERVAL_SECONDS = 3600
DAILY_MARKET_BRIEF_INTERVAL_SECONDS = 300
IPO_REMINDER_TIMEOUT_SECONDS = 120
ACCOUNT_SNAPSHOT_TIMEOUT_SECONDS = 300
DAILY_MARKET_BRIEF_TIMEOUT_SECONDS = 900
DEFAULT_MARKETS = ("CN", "HK", "US")
TRADE_RECONCILIATION_DAYS = 14


def build_scheduler_host(
    jobs: Sequence[JobDefinition],
    *,
    clock: Callable[[], float] = monotonic,
    executor: JobExecutor | None = None,
) -> SchedulerHost:
    """Composition boundary for job adapters registered by later migrations."""

    return SchedulerHost(jobs, clock=clock, executor=executor)


def default_scheduler_jobs(
    *,
    config: AppConfig | None = None,
    now: Callable[[], datetime] | None = None,
    logger: logging.Logger | None = None,
) -> tuple[JobDefinition, ...]:
    """Build the enabled production jobs without starting a host or service."""

    resolved_config = config or get_config()
    wall_clock = now or (lambda: datetime.now(SHANGHAI_TZ))
    resolved_logger = logger or logging.getLogger("investment_knowledge_mcp.scheduler_jobs")
    jobs: list[JobDefinition] = []

    if resolved_config.dingtalk_ipo_reminders_enabled and resolved_config.dingtalk_send_webhook:
        jobs.append(
            JobDefinition(
                job_id="ipo-reminder",
                interval_seconds=_bounded_interval(resolved_config.dingtalk_ipo_reminder_interval_seconds),
                run_once=_with_failure_logging(
                    "ipo-reminder",
                    lambda: run_ipo_reminder_once(logger=resolved_logger),
                    resolved_logger,
                ),
                timeout_seconds=IPO_REMINDER_TIMEOUT_SECONDS,
                allow_overlap=False,
            )
        )

    if resolved_config.account_snapshot_scheduler_enabled:
        jobs.append(
            JobDefinition(
                job_id="account-snapshot",
                interval_seconds=_bounded_interval(resolved_config.account_snapshot_interval_seconds),
                run_once=_with_failure_logging(
                    "account-snapshot",
                    _account_snapshot_callback(
                        scheduled_time=_parse_scheduled_time(resolved_config.account_snapshot_time),
                        now=wall_clock,
                        logger=resolved_logger,
                    ),
                    resolved_logger,
                ),
                timeout_seconds=ACCOUNT_SNAPSHOT_TIMEOUT_SECONDS,
                allow_overlap=False,
            )
        )

    for market in DEFAULT_MARKETS:
        jobs.append(
            JobDefinition(
                job_id=f"daily-market-brief-{market.lower()}",
                interval_seconds=DAILY_MARKET_BRIEF_INTERVAL_SECONDS,
                run_once=_with_failure_logging(
                    f"daily-market-brief-{market.lower()}",
                    _daily_market_brief_callback(
                        market=market,
                        now=wall_clock,
                        logger=resolved_logger,
                    ),
                    resolved_logger,
                ),
                timeout_seconds=DAILY_MARKET_BRIEF_TIMEOUT_SECONDS,
                allow_overlap=False,
            )
        )
    return tuple(jobs)


def default_scheduler_host(
    *,
    config: AppConfig | None = None,
    clock: Callable[[], float] = monotonic,
    now: Callable[[], datetime] | None = None,
    executor: JobExecutor | None = None,
    logger: logging.Logger | None = None,
) -> SchedulerHost:
    return build_scheduler_host(
        default_scheduler_jobs(config=config, now=now, logger=logger),
        clock=clock,
        executor=executor,
    )


def _account_snapshot_callback(
    *,
    scheduled_time: time,
    now: Callable[[], datetime],
    logger: logging.Logger,
) -> Callable[[], object | None]:
    last_reconciled_date: date | None = None

    def run_if_due() -> object | None:
        nonlocal last_reconciled_date
        current = _aware_now(now()).astimezone(SHANGHAI_TZ)
        if current.time() < scheduled_time:
            return None
        snapshot_date = current.date()
        if last_reconciled_date != snapshot_date:
            trade_start = snapshot_date - timedelta(days=TRADE_RECONCILIATION_DAYS - 1)
        else:
            trade_start = snapshot_date
        result = run_account_snapshot_once(
            snapshot_date=snapshot_date,
            trade_start=trade_start,
            logger=logger,
        )
        last_reconciled_date = snapshot_date
        return result

    return run_if_due


def _daily_market_brief_callback(
    *,
    market: str,
    now: Callable[[], datetime],
    logger: logging.Logger,
) -> Callable[[], object | None]:
    last_successful_date: date | None = None

    def run_if_due() -> object | None:
        nonlocal last_successful_date
        current = _aware_now(now())
        session_date = resolve_latest_completed_session_date(market, now=current)
        if session_date == last_successful_date:
            return None
        if not should_run_daily_market_brief(
            market,
            now=current,
            last_attempted_date=last_successful_date,
        ):
            return None
        result = run_daily_market_brief_once(
            market=market,
            market_date=session_date,
            logger=logger,
        )
        last_successful_date = session_date
        return result

    return run_if_due


def _with_failure_logging(
    job_id: str,
    callback: Callable[[], object | None],
    logger: logging.Logger,
) -> Callable[[], object | None]:
    def run_with_logging() -> object | None:
        try:
            return callback()
        except Exception as exc:
            logger.error(
                "scheduler job failed: job_id=%s exception_type=%s",
                job_id,
                type(exc).__name__,
            )
            raise

    return run_with_logging


def _bounded_interval(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = MIN_INTERVAL_SECONDS
    return min(MAX_INTERVAL_SECONDS, max(MIN_INTERVAL_SECONDS, parsed))


def _parse_scheduled_time(value: str) -> time:
    text = (value or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except (TypeError, ValueError):
        return time(hour=0, minute=5)


def _aware_now(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler wall clock must return an aware datetime")
    return value
