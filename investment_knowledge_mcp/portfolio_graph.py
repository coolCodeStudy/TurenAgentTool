from __future__ import annotations

from collections import defaultdict
from typing import Any

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.portfolio_analysis import DEFAULT_CURRENCY_BY_MARKET


DEFAULT_FX_TO_USD = {
    "USD": 1.0,
    "HKD": 1.0 / 7.8,
    "CNY": 1.0 / 7.2,
}


def build_portfolio_graph_queue(snapshot: Any, limit_per_currency: int = 8) -> dict[str, Any]:
    positions = _normalize_positions(snapshot.positions)
    currency_totals = _currency_totals(positions)
    entries = [_build_queue_entry(position, currency_totals) for position in positions]
    entries_by_currency = _entries_by_currency(entries, limit_per_currency=limit_per_currency)
    summary = _coverage_summary(entries)
    return {
        "snapshot": {
            "fetched_at": snapshot.fetched_at.isoformat(),
            "cached": snapshot.cached,
            "source": snapshot.source,
        },
        "summary": summary,
        "currency_totals": [
            {
                "currency": currency,
                "market_value": values["market_value"],
                "position_count": values["position_count"],
            }
            for currency, values in sorted(
                currency_totals.items(),
                key=lambda pair: pair[1]["market_value"],
                reverse=True,
            )
        ],
        "entries": sorted(entries, key=_entry_sort_key),
        "entries_by_currency": entries_by_currency,
        "next_actions": _next_actions(entries),
    }


def render_portfolio_graph_queue(context: dict[str, Any]) -> str:
    summary = context["summary"]
    snapshot = context["snapshot"]
    lines = [
        "持仓图谱队列",
        f"- 数据时间：{snapshot['fetched_at']}" + ("（短缓存）" if snapshot.get("cached") else ""),
        f"- 持仓数量：{summary['position_count']}",
        f"- 已入库：{summary['stock_profile_count']} / {summary['position_count']}",
        f"- 已挂主题：{summary['sector_linked_count']} / {summary['position_count']}",
        f"- 有事实知识：{summary['knowledge_count']} / {summary['position_count']}",
        f"- 有正式心得：{summary['insight_count']} / {summary['position_count']}",
    ]
    if summary["position_count"]:
        lines.append(f"- 图谱覆盖率：{summary['coverage_ratio'] * 100:.1f}%")

    lines.extend(["", "按币种排序："])
    for group in context.get("entries_by_currency") or []:
        lines.append(f"\n{group['currency']}：")
        for index, entry in enumerate(group["entries"], start=1):
            status = _status_label(entry)
            lines.append(
                f"{index}. {entry['name']} {entry['code']}："
                f"市值 {_fmt_money(entry['market_value'])} {entry['currency']}，"
                f"币种内占比 {entry['currency_weight'] * 100:.1f}%；{status}"
            )
            if entry["sector_paths"]:
                lines.append("   主题：" + "；".join(entry["sector_paths"][:3]))
            if entry["suggested_action"]:
                lines.append(f"   建议：{entry['suggested_action']}")

    actions = context.get("next_actions") or []
    lines.extend(["", "下一步建议："])
    if actions:
        for item in actions[:5]:
            lines.append(
                f"- {item['name']} {item['code']}："
                f"约 {_fmt_money(item['market_value_usd'])} USD；{item['suggested_action']}"
            )
    else:
        lines.append("- 当前持仓图谱覆盖不错，可以进入主题暴露和复盘验证。")

    lines.append("")
    lines.append("注：这是只读队列，不会自动写入股票、板块或心得。")
    return "\n".join(lines)


def _build_queue_entry(position: dict[str, Any], currency_totals: dict[str, dict[str, float]]) -> dict[str, Any]:
    context = repository.get_stock_context(symbol=position["symbol"], market=position["market"])
    stock = context.get("stock")
    sectors = context.get("sectors") or []
    stock_knowledge = context.get("stock_knowledge") or []
    stock_insights = context.get("stock_insights") or []
    stock_candidates = context.get("stock_candidate_insights") or []
    currency_total = currency_totals.get(position["currency"], {}).get("market_value") or 0.0

    entry = {
        **position,
        "currency_weight": position["market_value"] / currency_total if currency_total else 0.0,
        "market_value_usd": _to_usd(position["market_value"], position["currency"]),
        "stock": stock,
        "stock_profile": stock is not None,
        "sector_count": len(sectors),
        "knowledge_item_count": len(stock_knowledge),
        "insight_count": len(stock_insights),
        "candidate_count": len(stock_candidates),
        "sector_paths": [_format_sector_path(sector) for sector in sectors],
    }
    entry["coverage_score"] = _coverage_score(entry)
    entry["suggested_action"] = _suggest_action(entry)
    return entry


def _coverage_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    position_count = len(entries)
    stock_profile_count = sum(1 for item in entries if item["stock_profile"])
    sector_linked_count = sum(1 for item in entries if item["sector_count"] > 0)
    knowledge_count = sum(1 for item in entries if item["knowledge_item_count"] > 0)
    insight_count = sum(1 for item in entries if item["insight_count"] > 0)
    total_possible = position_count * 4
    total_score = sum(item["coverage_score"] for item in entries)
    return {
        "position_count": position_count,
        "stock_profile_count": stock_profile_count,
        "sector_linked_count": sector_linked_count,
        "knowledge_count": knowledge_count,
        "insight_count": insight_count,
        "coverage_ratio": total_score / total_possible if total_possible else 0.0,
    }


def _coverage_score(entry: dict[str, Any]) -> int:
    return sum(
        [
            1 if entry["stock_profile"] else 0,
            1 if entry["sector_count"] else 0,
            1 if entry["knowledge_item_count"] else 0,
            1 if entry["insight_count"] else 0,
        ]
    )


def _suggest_action(entry: dict[str, Any]) -> str:
    if not entry["stock_profile"]:
        return "优先生成图谱草稿并建立股票画像。"
    if not entry["sector_count"]:
        return "补候选主题/板块关系，确认主线和副线。"
    if not entry["knowledge_item_count"]:
        return "补业务、催化、风险等事实知识。"
    if not entry["insight_count"]:
        return "等待你补一条正式观点，或先生成候选心得。"
    return "已具备基础图谱，可进入主题暴露分析。"


def _next_actions(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [entry for entry in entries if entry["coverage_score"] < 4]
    return sorted(candidates, key=_entry_priority_key)


def _entries_by_currency(entries: list[dict[str, Any]], limit_per_currency: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        buckets[entry["currency"]].append(entry)
    return [
        {
            "currency": currency,
            "entries": sorted(items, key=lambda item: item["market_value"], reverse=True)[:limit_per_currency],
        }
        for currency, items in sorted(
            buckets.items(),
            key=lambda pair: sum(item["market_value"] for item in pair[1]),
            reverse=True,
        )
    ]


def _currency_totals(positions: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"market_value": 0.0, "position_count": 0.0})
    for item in positions:
        bucket = totals[item["currency"]]
        bucket["market_value"] += item["market_value"]
        bucket["position_count"] += 1
    return dict(totals)


def _normalize_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in positions:
        code = str(item.get("code") or "").strip()
        market, symbol = _split_code(code)
        currency = _normalize_currency(item.get("currency"), market)
        if _number(item.get("qty")) <= 0 and _number(item.get("market_val")) <= 0:
            continue
        normalized.append(
            {
                "code": code,
                "market": market,
                "symbol": symbol,
                "name": item.get("stock_name") or code or "unknown",
                "market_value": _number(item.get("market_val")),
                "pl_val": _number(item.get("pl_val")),
                "currency": currency,
            }
        )
    return normalized


def _split_code(code: str) -> tuple[str, str]:
    if "." not in code:
        return "", code.upper()
    market, symbol = code.split(".", 1)
    return market.upper(), symbol.upper()


def _normalize_currency(value: Any, market: str) -> str:
    currency = str(value or "").strip().upper()
    if currency:
        return currency
    return DEFAULT_CURRENCY_BY_MARKET.get(market.upper(), "UNKNOWN")


def _format_sector_path(sector: dict[str, Any]) -> str:
    path = sector.get("path")
    if isinstance(path, list) and path:
        return " > ".join(str(item) for item in path if item)
    return str(sector.get("name") or sector.get("sector_name") or sector.get("sector_id") or "")


def _status_label(entry: dict[str, Any]) -> str:
    parts = [
        "已入库" if entry["stock_profile"] else "未入库",
        f"主题 {entry['sector_count']}",
        f"知识 {entry['knowledge_item_count']}",
        f"心得 {entry['insight_count']}",
    ]
    if entry["candidate_count"]:
        parts.append(f"候选 {entry['candidate_count']}")
    return "，".join(parts)


def _entry_sort_key(entry: dict[str, Any]) -> tuple[str, float]:
    return (entry["currency"], -entry["market_value"])


def _entry_priority_key(entry: dict[str, Any]) -> tuple[float, int]:
    return (-entry["market_value_usd"], entry["coverage_score"])


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_usd(value: float, currency: str) -> float:
    return value * DEFAULT_FX_TO_USD.get(currency.upper(), 0.0)


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"
