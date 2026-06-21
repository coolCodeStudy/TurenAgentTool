from __future__ import annotations

from typing import Any

from investment_knowledge_mcp.events.models import EventPacket, EventScanResult, priority_rank


def render_scan_result(result: EventScanResult, *, title: str | None = None, max_events: int = 5) -> str:
    lines: list[str] = []
    if title:
        lines.append(title)
    else:
        lines.append("持仓事件雷达" if result.scope == "portfolio" else f"{result.symbol} 事件雷达")
    lines.append("")
    if result.status == "failed":
        lines.append("今日未完成事件扫描：核心数据源访问失败。")
        lines.extend(_render_errors(result.errors))
        return "\n".join(lines)
    if result.status == "partial":
        lines.append(
            f"事件扫描部分完成：{result.symbols_scanned}/{result.symbols_total or result.symbols_scanned} 个标的扫描成功。"
        )
        lines.extend(_render_errors(result.errors[:5]))
        lines.append("")
    visible_events = sorted(result.events, key=lambda event: (priority_rank(event.priority), event.event_date or ""), reverse=False)
    high_events = [event for event in visible_events if event.priority == "high"]
    medium_events = [event for event in visible_events if event.priority == "medium"]
    selected = (high_events[:3] + medium_events[:2])[:max_events]
    if not selected:
        if result.status == "ok":
            lines.append("今日无高优先级持仓事件。")
        else:
            lines.append("本次未发现可展示的高优先级事件，但扫描结果不完整。")
        return "\n".join(lines)
    for label, events in (("高优先级", high_events[:3]), ("中优先级", medium_events[:2])):
        if not events:
            continue
        lines.append(label)
        for index, event in enumerate(events, 1):
            lines.extend(_render_event(event, index=index))
        lines.append("")
    return "\n".join(lines).rstrip()


def render_stock_events_from_rows(symbol: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"{symbol.upper()} 暂无已入库的 active 持仓事件。"
    lines = [f"{symbol.upper()} 已入库事件", ""]
    for index, row in enumerate(rows[:10], 1):
        lines.append(
            f"{index}. {row.get('event_title') or row.get('event_type')}"
            f"（{row.get('priority')}, {row.get('confidence')}）"
        )
        if row.get("event_date"):
            lines.append(f"   事件日：{row['event_date']}")
        facts = row.get("source_facts") or []
        if facts:
            first = facts[0]
            form = first.get("form")
            filed_at = first.get("filed_at")
            lines.append(f"   证据：SEC {form or ''} {filed_at or ''}".rstrip())
        uncertainties = row.get("uncertainties") or []
        if uncertainties:
            lines.append(f"   不确定点：{uncertainties[0]}")
    return "\n".join(lines)


def render_muted_event(result: dict[str, Any] | None, *, symbol: str) -> str:
    if result is None:
        return f"没有找到 {symbol.upper()} 可静音的 active 事件。"
    event = result["event"]
    return f"已不再主动提醒 {event['symbol']} 这件事：{event['event_title']}。主动查询和周复盘仍可显示。"


def _render_event(event: EventPacket, *, index: int) -> list[str]:
    lines = [f"{index}. {event.event_title}"]
    if event.event_date:
        lines.append(f"   事件日：{event.event_date}")
    if event.source:
        evidence = f"SEC {event.source.form_type or ''} {event.source.accession_number or ''}".strip()
        lines.append(f"   证据：{evidence}")
    if event.source_facts:
        summary = _fact_summary(event.source_facts[0])
        if summary:
            lines.append(f"   事实：{summary}")
    if event.uncertainties:
        lines.append(f"   不确定点：{event.uncertainties[0]}")
    if event.needs_research:
        lines.append("   下一步：需要进一步解析原文条款。")
    return lines


def _fact_summary(fact: dict[str, Any]) -> str | None:
    form = fact.get("form")
    if form == "4":
        owner = fact.get("owner")
        codes = fact.get("transaction_codes")
        shares = fact.get("total_shares")
        parts = []
        if owner:
            parts.append(str(owner))
        if codes:
            parts.append(f"交易代码 {codes}")
        if shares:
            parts.append(f"约 {shares:g} 股")
        return "，".join(parts) if parts else None
    if form == "144":
        seller = fact.get("seller")
        shares = fact.get("shares")
        parts = []
        if seller:
            parts.append(str(seller))
        if shares:
            parts.append(f"拟售 {shares:g} 股" if isinstance(shares, (int, float)) else f"拟售 {shares}")
        return "，".join(parts) if parts else None
    return f"SEC {form} filed {fact.get('filed_at')}" if form else None


def _render_errors(errors: list[Any]) -> list[str]:
    lines: list[str] = []
    for error in errors:
        if hasattr(error, "to_record"):
            payload = error.to_record()
        else:
            payload = error
        symbol = payload.get("symbol") or "portfolio"
        lines.append(f"- {symbol} {payload.get('stage')}: {payload.get('message')}")
    return lines
