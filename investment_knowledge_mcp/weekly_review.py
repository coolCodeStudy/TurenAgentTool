from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def resolve_weekly_review_range(value: str | None = None) -> tuple[date, date, str]:
    today = datetime.now(SHANGHAI_TZ).date()
    text = (value or "").strip()
    if text:
        range_match = re.search(
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}).*?(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            text,
        )
        if range_match:
            start = _parse_date(range_match.group(1))
            end = _parse_date(range_match.group(2))
            if end < start:
                start, end = end, start
            return start, end, f"{start.isoformat()} 至 {end.isoformat()}"

    start = today - timedelta(days=today.weekday())
    return start, today, f"{start.isoformat()} 至 {today.isoformat()}"


def build_weekly_review(start: date, end: date) -> dict[str, Any]:
    snapshots = repository.list_account_snapshots(start=start.isoformat(), end=end.isoformat())
    trades = repository.list_trade_records(start=start.isoformat(), end=end.isoformat())
    first_snapshot = snapshots[0] if snapshots else None
    last_snapshot = snapshots[-1] if snapshots else None
    holdings_table = _build_holdings_table(first_snapshot=first_snapshot, last_snapshot=last_snapshot)
    highlights = [
        item
        for item in sorted(holdings_table, key=lambda row: _number(row.get("pl_change")), reverse=True)
        if _number(item.get("pl_change")) > 0
    ][:5]
    blowups = [
        item
        for item in sorted(holdings_table, key=lambda row: _number(row.get("pl_change")))
        if _number(item.get("pl_change")) < 0
    ][:5]
    source_status = {
        "account_snapshots": {
            "available": bool(snapshots),
            "count": len(snapshots),
            "first_date": first_snapshot.get("snapshot_date") if first_snapshot else None,
            "last_date": last_snapshot.get("snapshot_date") if last_snapshot else None,
            "pl_diff_available": len(snapshots) >= 2,
        },
        "trade_records": {"available": bool(trades), "count": len(trades)},
        "index_quotes": {"available": False, "message": "指数行情源暂未接入，本周复盘不做指数对比。"},
        "external_events": {"available": False, "message": "外部新闻/事件源暂未接入，事件归因只基于持仓浮盈亏和成交记录。"},
    }
    next_week = _build_next_week_items(holdings_table=holdings_table, trades=trades, source_status=source_status)
    story = _build_story(
        start=start,
        end=end,
        snapshots=snapshots,
        trades=trades,
        highlights=highlights,
        blowups=blowups,
        holdings_table=holdings_table,
        next_week=next_week,
        source_status=source_status,
    )
    return {
        "report_type": "weekly",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "portfolio_snapshot": {
            "first_snapshot": _snapshot_brief(first_snapshot),
            "last_snapshot": _snapshot_brief(last_snapshot),
            "trade_count": len(trades),
        },
        "summary": story,
        "risks": blowups,
        "opportunities": highlights,
        "new_knowledge_candidates": [],
        "source_status": source_status,
        "highlights": highlights,
        "blowups": blowups,
        "holdings_table": holdings_table,
        "next_week": next_week,
        "story": story,
    }


def build_and_save_weekly_review(start: date, end: date) -> dict[str, Any]:
    report = build_weekly_review(start=start, end=end)
    row = repository.upsert_review_report(
        report_type=report["report_type"],
        period_start=report["period_start"],
        period_end=report["period_end"],
        portfolio_snapshot=report["portfolio_snapshot"],
        summary=report["summary"],
        risks=report["risks"],
        opportunities=report["opportunities"],
        new_knowledge_candidates=report["new_knowledge_candidates"],
        source_status=report["source_status"],
        highlights=report["highlights"],
        blowups=report["blowups"],
        holdings_table=report["holdings_table"],
        next_week=report["next_week"],
        story=report["story"],
    )
    report["id"] = row.get("id")
    return report


def render_weekly_review_markdown(report: dict[str, Any]) -> str:
    source_status = report["source_status"]
    lines = [
        f"本周复盘（{report['period_start']} 至 {report['period_end']}）",
        "",
        "数据状态：",
        f"- 账户快照：{source_status['account_snapshots']['count']} 条；"
        f"pl_val 差分{'可用' if source_status['account_snapshots']['pl_diff_available'] else '不可用，需要至少 2 条区间快照'}。",
        f"- 交易记录：{source_status['trade_records']['count']} 笔。",
        f"- 指数行情：{source_status['index_quotes']['message']}",
        f"- 外部事件：{source_status['external_events']['message']}",
        "",
        "高光：",
    ]
    lines.extend(_render_position_list(report["highlights"], empty="- 暂无正向 pl_val 差分；若只有 1 条快照，本项无法计算。"))
    lines.extend(["", "炸裂："])
    lines.extend(_render_position_list(report["blowups"], empty="- 暂无负向 pl_val 差分；若只有 1 条快照，本项无法计算。"))
    lines.extend(["", "下周展望："])
    for item in report["next_week"]:
        lines.append(f"- {item['text']}")
    lines.extend(["", "当前持仓表："])
    if report["holdings_table"]:
        lines.append("| 标的 | 币种 | 市值 | 当前浮盈亏 | 本周pl_val变化 |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for item in report["holdings_table"]:
            lines.append(
                f"| {item['name']} {item['code']} | {item['currency']} | "
                f"{_fmt_money(item['market_val'])} | {_fmt_money(item['pl_val'])} | {_fmt_money(item['pl_change'])} |"
            )
    else:
        lines.append("- 区间内没有可用持仓快照。")
    if report.get("id"):
        lines.extend(["", f"已保存 review_reports #{report['id']}。"])
    return "\n".join(lines)


def _build_holdings_table(first_snapshot: dict[str, Any] | None, last_snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not last_snapshot:
        return []
    first_positions = _positions_by_key(first_snapshot.get("positions") if first_snapshot else [])
    rows = []
    for position in _positions(last_snapshot.get("positions")):
        key = _position_key(position)
        first_position = first_positions.get(key)
        pl_val = _number(position.get("pl_val"))
        pl_change = pl_val - _number(first_position.get("pl_val")) if first_position else 0.0
        rows.append(
            {
                "code": str(position.get("code") or "").strip() or "-",
                "name": str(position.get("stock_name") or position.get("name") or "").strip() or "-",
                "currency": str(position.get("currency") or "UNKNOWN").strip().upper(),
                "qty": _number(position.get("qty")),
                "market_val": _number(position.get("market_val")),
                "pl_val": pl_val,
                "pl_change": pl_change if first_position else None,
            }
        )
    return sorted(rows, key=lambda item: abs(_number(item.get("market_val"))), reverse=True)


def _build_next_week_items(
    holdings_table: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    source_status: dict[str, Any],
) -> list[dict[str, str]]:
    items = [
        {"text": "先补齐下周每日 account_snapshots；没有连续首尾快照时，不把本周 pl_val 差分当作严格收益。"},
        {"text": "指数行情源缺失，暂时不要把组合表现和恒指/纳指作自动归因对比。"},
        {"text": "外部事件源缺失，重大新闻、财报和宏观事件需要人工补充后再做因果判断。"},
    ]
    if trades:
        items.append({"text": f"复核本周 {len(trades)} 笔成交是否都已入库，重点看加仓/减仓后的仓位暴露。"})
    losers = [item for item in holdings_table if _number(item.get("pl_change")) < 0]
    if losers:
        worst = min(losers, key=lambda item: _number(item.get("pl_change")))
        items.append({"text": f"优先复盘拖累最大的 {worst['name']} {worst['code']}，确认是趋势破坏、估值波动还是仓位过重。"})
    if not source_status["account_snapshots"]["pl_diff_available"]:
        items.append({"text": "本周至少缺少 2 条账户快照；下周第一优先级是保证每日快照任务稳定运行。"})
    return items


def _build_story(
    *,
    start: date,
    end: date,
    snapshots: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    highlights: list[dict[str, Any]],
    blowups: list[dict[str, Any]],
    holdings_table: list[dict[str, Any]],
    next_week: list[dict[str, Any]],
    source_status: dict[str, Any],
) -> str:
    net_pl_change = sum(_number(item.get("pl_change")) for item in holdings_table)
    lines = [
        f"{start.isoformat()} 至 {end.isoformat()} 周复盘：区间账户快照 {len(snapshots)} 条，交易记录 {len(trades)} 笔。",
        f"按持仓 pl_val 首尾差分估算，本周持仓浮盈亏变化合计约 {_fmt_money(net_pl_change)}（按各标的原币种直接相加，仅用于方向判断）。",
    ]
    if highlights:
        best = highlights[0]
        lines.append(f"高光来自 {best['name']} {best['code']}，pl_val 变化 {_fmt_money(best['pl_change'])} {best['currency']}。")
    if blowups:
        worst = blowups[0]
        lines.append(f"最大拖累是 {worst['name']} {worst['code']}，pl_val 变化 {_fmt_money(worst['pl_change'])} {worst['currency']}。")
    if not source_status["account_snapshots"]["pl_diff_available"]:
        lines.append("由于区间内不足 2 条账户快照，pl_val 差分不可作为严格周收益。")
    lines.append("指数行情和外部事件源暂未接入，本报告不自动判断跑赢跑输指数，也不自动归因新闻事件。")
    if next_week:
        lines.append("下周节奏：" + next_week[0]["text"])
    return "\n".join(lines)


def _render_position_list(items: list[dict[str, Any]], empty: str) -> list[str]:
    if not items:
        return [empty]
    return [
        f"- {item['name']} {item['code']}: pl_val 变化 {_fmt_money(item['pl_change'])} {item['currency']}，"
        f"当前浮盈亏 {_fmt_money(item['pl_val'])}，市值 {_fmt_money(item['market_val'])}"
        for item in items
    ]


def _positions_by_key(positions: Any) -> dict[str, dict[str, Any]]:
    return {_position_key(position): position for position in _positions(positions)}


def _positions(positions: Any) -> list[dict[str, Any]]:
    if not isinstance(positions, list):
        return []
    return [item for item in positions if isinstance(item, dict)]


def _position_key(position: dict[str, Any]) -> str:
    code = str(position.get("code") or "").strip().upper()
    currency = str(position.get("currency") or "").strip().upper()
    name = str(position.get("stock_name") or position.get("name") or "").strip().upper()
    return "|".join([code, currency, name])


def _snapshot_brief(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    return {
        "snapshot_date": snapshot.get("snapshot_date"),
        "position_count": len(_positions(snapshot.get("positions"))),
        "fetched_at": snapshot.get("fetched_at"),
        "metadata": snapshot.get("metadata") or {},
    }


def _parse_date(value: str) -> date:
    return datetime.strptime(value.replace("/", "-"), "%Y-%m-%d").date()


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt_money(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{_number(value):,.2f}"
