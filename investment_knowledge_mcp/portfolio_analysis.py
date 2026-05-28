from __future__ import annotations

from collections import defaultdict
from typing import Any

from investment_knowledge_mcp import repository


DEFAULT_CURRENCY_BY_MARKET = {
    "HK": "HKD",
    "US": "USD",
    "SH": "CNY",
    "SZ": "CNY",
    "CN": "CNY",
    "KR": "KRW",
}


def build_portfolio_analysis_context(snapshot: Any) -> dict[str, Any]:
    positions = _normalize_positions(snapshot.positions)
    sorted_positions = sorted(positions, key=lambda item: item["market_value"], reverse=True)
    currency_exposure = _currency_exposure(sorted_positions)
    currencies = {item["currency"] for item in sorted_positions if item["currency"] != "UNKNOWN"}
    has_mixed_currency = len(currencies) > 1
    top_weights_available = not has_mixed_currency

    total_market_value_raw_sum = sum(item["market_value"] for item in sorted_positions)
    total_pl_raw_sum = sum(item["pl_val"] for item in sorted_positions)
    total_market_value = total_market_value_raw_sum if top_weights_available else None
    total_pl = total_pl_raw_sum if top_weights_available else None

    currency_totals = {item["currency"]: item["market_value"] for item in currency_exposure}
    for item in sorted_positions:
        currency_total = currency_totals.get(item["currency"]) or 0
        item["weight"] = item["market_value"] / total_market_value if total_market_value else None
        item["currency_weight"] = item["market_value"] / currency_total if currency_total else None

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

    data_quality_warnings = []
    if has_mixed_currency:
        data_quality_warnings.append(
            "检测到多币种持仓，当前未配置汇率换算；不要把原始 market_val 相加当作准确总市值。"
        )

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
            "total_market_value_raw_sum": total_market_value_raw_sum,
            "total_pl_raw_sum": total_pl_raw_sum,
            "has_mixed_currency": has_mixed_currency,
            "top_weights_available": top_weights_available,
            "top1_weight": _sum_weight(sorted_positions[:1]) if top_weights_available else None,
            "top3_weight": _sum_weight(sorted_positions[:3]) if top_weights_available else None,
            "top5_weight": _sum_weight(sorted_positions[:5]) if top_weights_available else None,
            "top10_weight": _sum_weight(sorted_positions[:10]) if top_weights_available else None,
        },
        "market_exposure": market_exposure,
        "currency_exposure": currency_exposure,
        "top_positions": top_positions,
        "top_positions_by_currency": _top_positions_by_currency(sorted_positions),
        "profit_leaders": profit_leaders,
        "loss_leaders": loss_leaders,
        "loss_leaders_by_currency": _loss_leaders_by_currency(sorted_positions),
        "large_loss_positions": large_loss_positions,
        "knowledge_matches": knowledge_matches,
        "global_insights": global_memory.get("global_insights") or [],
        "global_candidate_insights": global_memory.get("global_candidate_insights") or [],
        "context_warnings": context_warnings,
        "data_quality_warnings": data_quality_warnings,
    }


def render_portfolio_analysis_fallback(context: dict[str, Any]) -> str:
    summary = context["summary"]
    top_positions = context["top_positions"]
    top_positions_by_currency = context.get("top_positions_by_currency") or []
    market_exposure = context["market_exposure"]
    currency_exposure = context["currency_exposure"]
    loss_leaders = context["loss_leaders"]
    loss_leaders_by_currency = context.get("loss_leaders_by_currency") or []
    large_loss_positions = context["large_loss_positions"]
    global_insights = context.get("global_insights") or []
    has_mixed_currency = bool(summary.get("has_mixed_currency"))

    lines = [
        "## 数据口径",
        f"- 持仓数量：{summary['position_count']}",
    ]
    if has_mixed_currency:
        lines.append("- 检测到多币种持仓，当前未配置汇率换算；本次不输出单一总市值或全组合 TopN 占比。")
        lines.append("- 下方市值、盈亏和占比按币种分组展示，避免 HKD/USD 等资产被直接相加。")
    else:
        currency = currency_exposure[0]["currency"] if currency_exposure else ""
        lines.extend(
            [
                f"- 总市值：{_fmt_money(summary['total_market_value'], currency)}",
                f"- 浮动盈亏：{_fmt_money(summary['total_pl'], currency)}",
                f"- 前 1 / 3 / 5 大持仓占比：{_fmt_pct(summary['top1_weight'])} / "
                f"{_fmt_pct(summary['top3_weight'])} / {_fmt_pct(summary['top5_weight'])}",
            ]
        )

    lines.extend(
        [
            "",
            "## 组合概览",
        ]
    )
    lines.extend(
        f"- {item['currency']}：市值 {_fmt_money(item['market_value'], item['currency'])}，"
        f"浮动盈亏 {_fmt_money(item['pl_val'], item['currency'])}，持仓 {item['position_count']} 个"
        for item in currency_exposure
    )
    lines.extend(
        [
            "",
            "## 仓位结构",
        ]
    )
    lines.extend(
        f"- {item['market']}：{_fmt_money(item['market_value'], item.get('currency'))}"
        + (f"，全组合占比 {_fmt_pct(item['weight'])}" if item.get("weight") is not None else "，跨币种未折算占比")
        for item in market_exposure
    )
    lines.extend(["", "## 主要持仓"])
    if has_mixed_currency:
        for group in top_positions_by_currency:
            rendered = "；".join(
                f"{item['name']} {item['code']} {_fmt_money(item['market_value'], item['currency'])}"
                f"（币种内 {_fmt_pct(item['currency_weight'])}）"
                for item in group["positions"][:4]
            )
            lines.append(f"- {group['currency']}：{rendered}")
    else:
        lines.extend(
            f"- {item['name']} {item['code']}：市值 {_fmt_money(item['market_value'], item['currency'])}，"
            f"占比 {_fmt_pct(item['weight'])}，盈亏 {_fmt_pct(item['pl_ratio'])}"
            for item in top_positions[:8]
        )
    lines.extend(["", "## 主要风险"])
    if has_mixed_currency:
        lines.append("- 口径风险：未配置汇率前，不应把不同币种市值直接相加判断组合集中度。")
    else:
        lines.append(
            f"- 集中度：前三大持仓占比 {_fmt_pct(summary['top3_weight'])}，前五大持仓占比 {_fmt_pct(summary['top5_weight'])}。"
        )
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
    if has_mixed_currency and loss_leaders_by_currency:
        lines.append(
            "- 主要拖累项按币种展示："
            + "；".join(
                f"{group['currency']} "
                + "、".join(
                    f"{item['name']} {item['code']} {_fmt_money(item['pl_val'], item['currency'])}"
                    for item in group["positions"][:3]
                )
                for group in loss_leaders_by_currency
            )
        )
    elif loss_leaders:
        lines.append(
            "- 主要拖累项按原币种展示："
            + "；".join(
                f"{item['name']} {item['code']} {_fmt_money(item['pl_val'], item['currency'])}"
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
        lines.append("- 目前组合/策略级心得还不多，等持仓口径稳定后再沉淀仓位管理偏好更合适。")
    lines.extend(["", "## 后续跟踪"])
    lines.append("- 先补齐汇率/基准币种口径，再做前十大持仓知识初始化和组合级心得入库。")
    lines.append("- 这版分析只基于持仓、已入库知识和用户心得，不包含实时新闻或公告。")
    return "\n".join(lines)


def _normalize_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in positions:
        code = str(item.get("code") or "").strip()
        market, symbol = _split_code(code)
        currency = _normalize_currency(item.get("currency"), market)
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
                "currency": currency,
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


def _market_exposure(positions: list[dict[str, Any]], total_market_value: float | None) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"market_value": 0.0, "currency": None})
    for item in positions:
        key = item["market"] or "UNKNOWN"
        buckets[key]["market_value"] += item["market_value"]
        if buckets[key]["currency"] is None:
            buckets[key]["currency"] = item["currency"]
        elif buckets[key]["currency"] != item["currency"]:
            buckets[key]["currency"] = "MIXED"
    return [
        {
            "market": market,
            "currency": value["currency"],
            "market_value": value["market_value"],
            "weight": value["market_value"] / total_market_value if total_market_value else None,
        }
        for market, value in sorted(buckets.items(), key=lambda pair: pair[1]["market_value"], reverse=True)
    ]


def _currency_exposure(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"market_value": 0.0, "pl_val": 0.0, "position_count": 0})
    for item in positions:
        bucket = buckets[item["currency"]]
        bucket["market_value"] += item["market_value"]
        bucket["pl_val"] += item["pl_val"]
        bucket["position_count"] += 1
    return [
        {
            "currency": currency,
            "market_value": value["market_value"],
            "pl_val": value["pl_val"],
            "position_count": value["position_count"],
        }
        for currency, value in sorted(buckets.items(), key=lambda pair: pair[1]["market_value"], reverse=True)
    ]


def _top_positions_by_currency(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in positions:
        buckets[item["currency"]].append(item)
    return [
        {
            "currency": currency,
            "positions": sorted(items, key=lambda item: item["market_value"], reverse=True)[:8],
        }
        for currency, items in sorted(
            buckets.items(),
            key=lambda pair: sum(item["market_value"] for item in pair[1]),
            reverse=True,
        )
    ]


def _loss_leaders_by_currency(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in positions:
        if item["pl_val"] < 0:
            buckets[item["currency"]].append(item)
    return [
        {
            "currency": currency,
            "positions": sorted(items, key=lambda item: item["pl_val"])[:5],
        }
        for currency, items in sorted(
            buckets.items(),
            key=lambda pair: sum(item["pl_val"] for item in pair[1]),
        )
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


def _normalize_currency(value: Any, market: str) -> str:
    currency = str(value or "").strip().upper()
    if currency:
        return currency
    return DEFAULT_CURRENCY_BY_MARKET.get(market.upper(), "UNKNOWN")


def _fmt_money(value: float | None, currency: str | None = None) -> str:
    if value is None:
        return "-"
    suffix = f" {currency}" if currency and currency not in {"UNKNOWN", "MIXED"} else ""
    return f"{value:,.2f}{suffix}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"
