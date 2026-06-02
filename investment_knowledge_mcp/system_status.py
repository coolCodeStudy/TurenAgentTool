from __future__ import annotations

from datetime import datetime
import socket
from typing import Any

from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.db import connect
from investment_knowledge_mcp.futu_provider import FutuProviderError, get_hk_ipo_list
from investment_knowledge_mcp.account_snapshots import get_account_snapshot_loop_state
from investment_knowledge_mcp.ipo_reminders import (
    SHANGHAI_TZ,
    build_scheduled_reminders,
    get_ipo_reminder_loop_state,
)


def render_system_status() -> str:
    config = get_config()
    account_snapshot_loop = get_account_snapshot_loop_state()
    checks = [
        _database_check(),
        _socket_check("OpenD", config.futu_opend_host, config.futu_opend_port),
        _socket_check("OpenAI", "api.openai.com", 443),
        _config_check("钉钉主动推送 webhook", bool(config.dingtalk_send_webhook)),
        _config_check("钉钉 Stream Client ID", bool(config.dingtalk_stream_client_id)),
        _config_check("每日账户快照任务", config.account_snapshot_scheduler_enabled),
    ]

    lines = [
        "系统状态：",
        f"- 时间：{datetime.now(SHANGHAI_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}",
    ]
    lines.extend(f"- {_status_icon(item['ok'])} {item['name']}：{item['message']}" for item in checks)
    if account_snapshot_loop.get("time"):
        lines.append(
            f"- 每日账户快照时间：{account_snapshot_loop['time']}，"
            f"扫描间隔 {account_snapshot_loop.get('interval_seconds') or '-'} 秒"
        )
    else:
        lines.append(
            f"- 每日账户快照时间：{config.account_snapshot_time}，"
            "由独立 account-snapshot-scheduler 服务负责"
        )

    failed = [item for item in checks if not item["ok"]]
    if failed:
        lines.append("")
        lines.append("下一步：优先处理未通过项；如果 OpenD 或 OpenAI 不通，持仓/分析/提醒都会受影响。")
    else:
        lines.append("")
        lines.append("下一步：基础链路正常，可以继续测试 `我的持仓`、`持仓分析`、`港股新股`。")
    return "\n".join(lines)


def render_ipo_reminder_status() -> str:
    config = get_config()
    now = datetime.now(SHANGHAI_TZ)
    loop_state = get_ipo_reminder_loop_state()

    lines = [
        "IPO提醒状态：",
        f"- 时间：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- 提醒开关：{'开启' if config.dingtalk_ipo_reminders_enabled else '关闭'}",
        f"- 主动推送 webhook：{'已配置' if config.dingtalk_send_webhook else '未配置'}",
        f"- 后台提醒循环：{'已启动' if loop_state.get('started') else '未启动'}",
    ]
    if loop_state.get("interval_seconds"):
        lines.append(f"- 扫描间隔：{loop_state['interval_seconds']} 秒")

    if not config.dingtalk_ipo_reminders_enabled:
        lines.append("")
        lines.append("当前不会主动提醒：`DINGTALK_IPO_REMINDERS_ENABLED=false`。")
        return "\n".join(lines)
    if not config.dingtalk_send_webhook:
        lines.append("")
        lines.append("当前不会主动提醒：缺少 `DINGTALK_SEND_WEBHOOK`。")
        return "\n".join(lines)

    try:
        snapshot = get_hk_ipo_list(include_orders=False)
    except FutuProviderError as exc:
        lines.append("")
        lines.append(f"读取港股新股失败：{exc}")
        return "\n".join(lines)
    except Exception as exc:
        lines.append("")
        lines.append(f"读取港股新股异常：{exc}")
        return "\n".join(lines)

    scheduled = build_scheduled_reminders(snapshot.ipos, now=now)
    recent_sent = _recent_ipo_reminders(limit=3)
    lines.append(f"- 富途返回新股：{len(snapshot.ipos)} 个")
    lines.append(f"- 未来/当前提醒：{len(scheduled)} 个")

    if scheduled:
        lines.append("")
        lines.append("最近待提醒：")
        for reminder in scheduled[:5]:
            sent = _reminder_sent(reminder)
            lines.append(
                f"- {_reminder_type_label(reminder.reminder_type)} "
                f"{reminder.stock_name} {reminder.stock_code}："
                f"{reminder.scheduled_for.strftime('%Y-%m-%d %H:%M')}，"
                f"{'已发送' if sent else '待发送'}"
            )
    else:
        lines.append("")
        lines.append("当前 IPO 列表里没有命中未来提醒窗口的新股。")

    if recent_sent:
        lines.append("")
        lines.append("最近已发送：")
        for row in recent_sent:
            lines.append(
                f"- {_reminder_type_label(row.get('reminder_type'))} "
                f"{row.get('stock_name') or row.get('stock_code')} {row.get('stock_code')}："
                f"{_format_dt(row.get('sent_at'))}"
            )
    return "\n".join(lines)


def _database_check() -> dict[str, Any]:
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        return {"name": "PostgreSQL", "ok": False, "message": str(exc)}
    return {"name": "PostgreSQL", "ok": True, "message": "可连接"}


def _socket_check(name: str, host: str, port: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
    except Exception as exc:
        return {"name": name, "ok": False, "message": f"{host}:{port} 不可达：{exc}"}
    return {"name": name, "ok": True, "message": f"{host}:{port} 可达"}


def _config_check(name: str, ok: bool) -> dict[str, Any]:
    return {"name": name, "ok": ok, "message": "已配置" if ok else "未配置"}


def _reminder_sent(reminder: Any) -> bool:
    try:
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
    except Exception:
        return False


def _recent_ipo_reminders(limit: int) -> list[dict[str, Any]]:
    try:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT reminder_type, stock_code, stock_name, sent_at
                FROM ipo_reminder_events
                ORDER BY sent_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
    except Exception:
        return []
    return list(rows)


def _reminder_type_label(value: Any) -> str:
    if value == "ipo_apply_deadline":
        return "申购截止提醒"
    if value == "ipo_dark_pool":
        return "暗盘提醒"
    return str(value or "提醒")


def _format_dt(value: Any) -> str:
    if not value:
        return "-"
    if hasattr(value, "astimezone"):
        return value.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")
    return str(value)


def _status_icon(ok: bool) -> str:
    return "OK" if ok else "FAIL"
