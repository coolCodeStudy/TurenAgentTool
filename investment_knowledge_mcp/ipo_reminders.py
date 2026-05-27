from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
import threading
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import errors

from investment_knowledge_mcp.config import AppConfig, get_config
from investment_knowledge_mcp.db import connect
from investment_knowledge_mcp.dingtalk_sender import send_text_message
from investment_knowledge_mcp.futu_provider import get_hk_ipo_list


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
REMINDER_WINDOW = timedelta(hours=12)


@dataclass(frozen=True)
class IpoReminder:
    reminder_type: str
    stock_code: str
    stock_name: str
    target_date: date
    scheduled_for: datetime
    message: str


def start_ipo_reminder_loop(config: AppConfig | None = None, logger: logging.Logger | None = None) -> None:
    config = config or get_config()
    logger = logger or logging.getLogger("investment_knowledge_mcp.ipo_reminders")

    if not config.dingtalk_ipo_reminders_enabled:
        logger.info("IPO reminders disabled by DINGTALK_IPO_REMINDERS_ENABLED=false")
        return
    if not config.dingtalk_send_webhook:
        logger.info("IPO reminders disabled: DINGTALK_SEND_WEBHOOK is not configured")
        return

    interval = max(60, config.dingtalk_ipo_reminder_interval_seconds)
    thread = threading.Thread(
        target=_run_loop,
        args=(interval, logger),
        name="ipo-reminder-loop",
        daemon=True,
    )
    thread.start()
    logger.info("IPO reminder loop started: interval_seconds=%s", interval)


def _run_loop(interval_seconds: int, logger: logging.Logger) -> None:
    while True:
        try:
            run_ipo_reminder_once(logger=logger)
        except Exception:
            logger.exception("IPO reminder loop failed")
        threading.Event().wait(interval_seconds)


def run_ipo_reminder_once(logger: logging.Logger | None = None) -> int:
    logger = logger or logging.getLogger("investment_knowledge_mcp.ipo_reminders")
    snapshot = get_hk_ipo_list(include_orders=False)
    now = datetime.now(SHANGHAI_TZ)
    sent_count = 0

    for reminder in _build_due_reminders(snapshot.ipos, now=now):
        if _reminder_already_sent(reminder):
            continue
        send_text_message(reminder.message)
        _record_reminder_sent(reminder)
        sent_count += 1
        logger.info(
            "sent IPO reminder: type=%s code=%s target_date=%s",
            reminder.reminder_type,
            reminder.stock_code,
            reminder.target_date,
        )
    return sent_count


def _build_due_reminders(ipos: list[dict[str, Any]], now: datetime) -> list[IpoReminder]:
    reminders: list[IpoReminder] = []
    for item in ipos:
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or code or "unknown").strip()
        if not code:
            continue

        apply_end_date = _parse_date(item.get("apply_end_time"))
        if apply_end_date:
            scheduled_for = datetime.combine(apply_end_date - timedelta(days=1), time(21, 0), tzinfo=SHANGHAI_TZ)
            if _is_due(now, scheduled_for):
                reminders.append(
                    IpoReminder(
                        reminder_type="ipo_apply_deadline",
                        stock_code=code,
                        stock_name=name,
                        target_date=apply_end_date,
                        scheduled_for=scheduled_for,
                        message=_apply_deadline_message(item=item, scheduled_for=scheduled_for),
                    )
                )

        list_date = _parse_date(item.get("list_time"))
        if list_date:
            scheduled_for = datetime.combine(list_date - timedelta(days=1), time(12, 30), tzinfo=SHANGHAI_TZ)
            if _is_due(now, scheduled_for):
                reminders.append(
                    IpoReminder(
                        reminder_type="ipo_dark_pool",
                        stock_code=code,
                        stock_name=name,
                        target_date=list_date,
                        scheduled_for=scheduled_for,
                        message=_dark_pool_message(item=item, scheduled_for=scheduled_for),
                    )
                )
    return reminders


def _is_due(now: datetime, scheduled_for: datetime) -> bool:
    return scheduled_for <= now <= scheduled_for + REMINDER_WINDOW


def _apply_deadline_message(item: dict[str, Any], scheduled_for: datetime) -> str:
    name = _display(item.get("name"))
    code = _display(item.get("code"))
    return "\n".join(
        [
            "港股新股申购提醒：",
            f"- {name} {code}",
            f"- 招股截止：{_display(item.get('apply_end_time'))}",
            f"- 上市日：{_display(item.get('list_time'))}",
            f"- 发行价：{_price(item)}",
            f"- 每手：{_display(item.get('lot_size'))}",
            f"- 入场费：{_display(item.get('entrance_price'))}",
            f"- 提醒时间：{scheduled_for.strftime('%Y-%m-%d %H:%M %Z')}",
            "",
            "注：只提醒，不会自动申购。",
        ]
    )


def _dark_pool_message(item: dict[str, Any], scheduled_for: datetime) -> str:
    name = _display(item.get("name"))
    code = _display(item.get("code"))
    return "\n".join(
        [
            "港股新股暗盘提醒：",
            f"- {name} {code}",
            f"- 上市日：{_display(item.get('list_time'))}",
            f"- 发行价：{_price(item)}",
            f"- 每手：{_display(item.get('lot_size'))}",
            f"- 入场费：{_display(item.get('entrance_price'))}",
            f"- 提醒时间：{scheduled_for.strftime('%Y-%m-%d %H:%M %Z')}",
            "",
            "注：明天上市，今天中午提醒你留意暗盘表现。",
        ]
    )


def _reminder_already_sent(reminder: IpoReminder) -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM ipo_reminder_events
            WHERE reminder_type = %s
              AND stock_code = %s
              AND target_date = %s
            LIMIT 1
            """,
            (reminder.reminder_type, reminder.stock_code, reminder.target_date),
        ).fetchone()
    return row is not None


def _record_reminder_sent(reminder: IpoReminder) -> None:
    with connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO ipo_reminder_events
                  (reminder_type, stock_code, stock_name, target_date, scheduled_for, message)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    reminder.reminder_type,
                    reminder.stock_code,
                    reminder.stock_name,
                    reminder.target_date,
                    reminder.scheduled_for,
                    reminder.message,
                ),
            )
        except errors.UniqueViolation:
            conn.rollback()


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text[:10], text):
        for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(candidate, pattern).date()
            except ValueError:
                continue
    return None


def _display(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"


def _price(item: dict[str, Any]) -> str:
    min_price = item.get("ipo_price_min")
    max_price = item.get("ipo_price_max")
    list_price = item.get("list_price")
    if min_price is not None and max_price is not None:
        if str(min_price) == str(max_price):
            return str(min_price)
        return f"{min_price}-{max_price}"
    if list_price is not None:
        return str(list_price)
    if min_price is not None:
        return str(min_price)
    if max_price is not None:
        return str(max_price)
    return "-"
