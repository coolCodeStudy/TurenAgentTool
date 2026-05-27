from __future__ import annotations

from collections import defaultdict
from typing import Any

from investment_knowledge_mcp import repository


def build_portfolio_analysis_context(snapshot: Any) -> dict[str, Any]:
    positions = _normalize_positions(snapshot.positions)
    total_market_value = sum(item["market_value"] for item in positions)
    total_pl = sum(item["pl_val"] for item in positions)

    sorted_positions = sorted(positions, key=lambda item: item["market_value"], reverse=True)
    for item in sorted_positions:
        item["weight"] = item["market_value"] / total_market_value if total_market_value else 0

    market_exposure = _market_exposure(sorted_positions, total_market_value)
    by_profit = sorted(sorted_positions, key=lambda item: item["pl_val"], reverse=True)
    by_loss = sorted(sorted_positions, key=lambda item: item["pl_val"])
    profit_leaders = [item for item in by_profit if item["pl_val"] > 0][:8]
    loss_leaders = [item for item in by_loss if item["pl_val"] < 0][:8]
    large_loss_positions = [
        item for item in sorted_positions if item["pl_ratio"] is not None and item["pl_ratio"] <= -0.15
    ][:10]
    top_positions = sorted_positions[:10]
    context_warnings = []
    try:
        knowledge_matches = _knowledge_matches(sorted_positions[:12])
    except Exception as exc:
        knowledge_matches = []
        context_warnings.append(f"知识库个股匹配失败：{exc}")
    try:
        global_memory = repository.get_global_user_memory()
    except Exception as exc:
        global_memory = {"global_insights": [], "global_candidate_insights": []}
        context_warnings.append(f"组合/策略级心得读取失败：{exc}")

    return {
        "snapshot": {
            "fetched_at": snapshot.fetched_at.isoformat(),
            "cached": snapshot.cached,
            "source": snapshot.source,
        },
        "summary": {
            "position_count": len(sorted_positions),
            "total_market_value": total_market_value,
            "total_pl": total_pl,
            "top1_weight": _sum_weight(sorted_positions[:1]),
            "top3_weight": _sum_weight(sorted_positions[:3]),
            "top5_weight": _sum_weight(sorted_positions[:5]),
            "top10_weight": _sum_weight(sorted_positions[:10]),
        },
        "market_exposure": market_exposure,
        "top_positions": top_positions,
        "profit_leaders": profit_leaders,
        "loss_leaders": loss_leaders,
        "large_loss_positions": large_loss_positions,
        "knowledge_matches": knowledge_matches,
        "global_insights": global_memory.get("global_insights") or [],
        "global_candidate_insights": global_memory.get("global_candidate_insights") or [],
        "context_warnings": context_warnings,
    }


def render_portfolio_analysis_fallback(context: dict[str, Any]) -> str:
    summary = context["summary"]
    top_positions = context["top_positions"]
    market_exposure = context["market_exposure"]
    loss_leaders = context["loss_leaders"]
    large_loss_positions = context["large_loss_positions"]
    global_insights = context.get("global_insights") or []

    lines = [
        "## 组合概览",
        f"- 持仓数量：{summary['position_count']}",
        f"- 总市值：{_fmt_money(summary['total_market_value'])}",
        f"- 浮动盈亏：{_fmt_money(summary['total_pl'])}",
        f"- 前 1 / 3 / 5 大持仓占比：{_fmt_pct(summary['top1_weight'])} / "
        f"{_fmt_pct(summary['top3_weight'])} / {_fmt_pct(summary['top5_weight'])}",
        "",
        "## 仓位结构",
    ]
    lines.extend(
        f"- {item['market']}：{_fmt_money(item['market_value'])}，占比 {_fmt_pct(item['weight'])}"
        for item in market_exposure
    )
    lines.extend(["", "## 主要持仓"])
    lines.extend(
        f"- {item['name']} {item['code']}：占比 {_fmt_pct(item['weight'])}，盈亏 {_fmt_pct(item['pl_ratio'])}"
        for item in top_positions[:8]
    )
    lines.extend(["", "## 主要风险"])
    lines.append(f"- 集中度：前三大持仓占比 {_fmt_pct(summary['top3_weight'])}，前五大持仓占比 {_fmt_pct(summary['top5_weight'])}。")
    if large_loss_positions:
        lines.append(
            "- 亏损较大持仓："
            + "；".join(
                f"{item['name']} {item['code']} {_fmt_pct(item['pl_ratio'])}"
                for item in large_loss_positions[:5]
            )
        )
    else:
        lines.append("- 当前没有按盈亏比例筛出的较大亏损持仓。")
    if loss_leaders:
        lines.append(
            "- 主要拖累项："
            + "；".join(
                f"{item['name']} {item['code']} {_fmt_money(item['pl_val'])}"
                for item in loss_leaders[:5]
            )
        )
    else:
        lines.append("- 当前没有可分析的持仓盈亏数据。")
    lines.extend(["", "## 和用户偏好的关系"])
    if global_insights:
        for insight in global_insights[:5]:
            text = insight.get("normalized_summary") or insight.get("insight")
            if text:
                lines.append(f"- {text}")
    else:
        lines.append("- 目前组合/策略级心得还不多，后续可以把你的仓位管理偏好沉淀进系统。")
    lines.extend(["", "## 后续跟踪"])
    lines.append("- 建议优先补全前十大持仓的股票画像和板块归属，组合分析会更准。")
    lines.append("- 这版分析只基于持仓、已入库知识和用户心得，不包含实时新闻或公告。")
    return "\n".join(lines)


def _normalize_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in positions:
        code = str(item.get("code") or "").strip()
        market, symbol = _split_code(code)
        normalized.append(
            {
                "code": code,
                "market": market,
                "symbol": symbol,
                "name": item.get("stock_name") or code or "unknown",
                "market_value": _number(item.get("market_val")),
                "pl_val": _number(item.get("pl_val")),
                "pl_ratio": _ratio(item.get("pl_ratio")),
                "qty": item.get("qty"),
                "currency": item.get("currency"),
            }
        )
    return normalized


def _knowledge_matches(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for position in positions:
        symbol = position["symbol"]
        market = position["market"]
        if not symbol or not market:
            continue
        context = repository.get_stock_context(symbol=symbol, market=market)
        stock = context.get("stock")
        if not stock:
            continue
        matches.append(
            {
                "position": position,
                "stock": stock,
                "sectors": context.get("sectors") or [],
                "stock_insights": (context.get("stock_insights") or [])[:3],
                "sector_insights": (context.get("sector_insights") or [])[:3],
                "stock_knowledge": (context.get("stock_knowledge") or [])[:3],
            }
        )
    return matches


def _market_exposure(positions: list[dict[str, Any]], total_market_value: float) -> list[dict[str, Any]]:
    buckets: dict[str, float] = defaultdict(float)
    for item in positions:
        buckets[item["market"] or "UNKNOWN"] += item["market_value"]
    return [
        {
            "market": market,
            "market_value": value,
            "weight": value / total_market_value if total_market_value else 0,
        }
        for market, value in sorted(buckets.items(), key=lambda pair: pair[1], reverse=True)
    ]


def _split_code(code: str) -> tuple[str, str]:
    if "." not in code:
        return "", code
    market, symbol = code.split(".", 1)
    return market.upper(), symbol.upper()


def _sum_weight(positions: list[dict[str, Any]]) -> float:
    return sum(item.get("weight") or 0 for item in positions)


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ratio(value: Any) -> float | None:
    if value is None:
        return None
    number = _number(value)
    if abs(number) > 1:
        return number / 100
    return number


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"
