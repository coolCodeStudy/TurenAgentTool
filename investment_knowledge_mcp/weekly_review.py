from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.futu_provider import (
    FutuProviderError,
    get_futu_positions,
    get_futu_trade_history,
    get_hk_ipo_list,
)
from investment_knowledge_mcp.weekly_review_sources import (
    build_budget_warnings,
    load_weekly_review_external_sources,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class WeeklyReviewResult:
    context: dict[str, Any]
    markdown: str
    saved_report: dict[str, Any] | None = None


def build_weekly_review(
    start: date,
    end: date,
    *,
    save: bool = True,
    next_week_only: bool = False,
    force_refresh: bool = False,
    run_id: int | None = None,
) -> WeeklyReviewResult:
    context = build_weekly_review_context(start=start, end=end, force_refresh=force_refresh, run_id=run_id)
    markdown = render_next_week_markdown(context) if next_week_only else render_weekly_review_markdown(context)
    saved_report = None
    if save and not next_week_only:
        saved_report = save_weekly_review_report(context=context, markdown=markdown)
    return WeeklyReviewResult(context=context, markdown=markdown, saved_report=saved_report)


def build_weekly_review_context(
    start: date,
    end: date,
    *,
    force_refresh: bool = False,
    run_id: int | None = None,
) -> dict[str, Any]:
    if end < start:
        start, end = end, start

    source_status: dict[str, Any] = {
        "account_snapshots": {"status": "missing", "count": 0},
        "trades": {"status": "missing", "count": 0},
        "positions": {"status": "missing", "fetched_at": None},
        "indexes": {"status": "missing", "reason": "index provider not fetched yet"},
        "macro": {"status": "missing", "reason": "macro provider not configured"},
        "news_themes": {"status": "missing", "reason": "news/theme provider not configured"},
        "opportunities": {"status": "missing", "reason": "opportunity provider not configured"},
        "ipo": {"status": "missing", "count": 0},
    }
    warnings: list[str] = []
    external_sources = load_weekly_review_external_sources(
        start=start,
        end=end,
        force_refresh=force_refresh,
        run_id=run_id,
        warnings=warnings,
    )
    source_status.update(external_sources.get("source_status") or {})

    snapshots = _load_account_snapshots(start=start, end=end, source_status=source_status, warnings=warnings)
    start_snapshot = snapshots[0] if snapshots else None
    end_snapshot = snapshots[-1] if snapshots else None
    realtime_positions = None
    today = datetime.now(SHANGHAI_TZ).date()
    if end >= today and (end_snapshot is None or _snapshot_date(end_snapshot) < end):
        realtime_positions = _load_realtime_positions(source_status=source_status, warnings=warnings)

    start_positions = _positions_from_snapshot(start_snapshot) if start_snapshot is not None else []
    if realtime_positions is not None:
        end_positions = realtime_positions["positions"]
        end_snapshot_info = realtime_positions["snapshot"]
    elif end_snapshot is not None:
        end_positions = _positions_from_snapshot(end_snapshot)
        end_snapshot_info = _snapshot_info(end_snapshot)
        source_status["positions"] = {
            "status": "snapshot",
            "fetched_at": end_snapshot.get("fetched_at"),
        }
    else:
        end_positions = []
        end_snapshot_info = None

    trades = _load_trade_records(start=start, end=end, source_status=source_status, warnings=warnings)
    trades_by_code = _summarize_trades_by_code(trades)
    position_changes = _build_position_changes(
        start_positions=start_positions,
        end_positions=end_positions,
        trades_by_code=trades_by_code,
        has_start_snapshot=start_snapshot is not None,
        has_end_reference=bool(end_positions),
    )
    _attach_knowledge(position_changes=position_changes, warnings=warnings)

    highlights = _top_highlights(position_changes)
    blowups = _top_blowups(position_changes)
    holdings_table = _build_holdings_table(position_changes)
    ipo_items = _load_ipo_items(source_status=source_status, warnings=warnings)
    next_week = _build_next_week_items(
        position_changes=position_changes,
        ipo_items=ipo_items,
        opportunity_items=external_sources.get("opportunity_items") or [],
    )

    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": f"{start.isoformat()} 至 {end.isoformat()}",
        },
        "source_status": source_status,
        "snapshots": {
            "start": _snapshot_info(start_snapshot) if start_snapshot is not None else None,
            "end": end_snapshot_info,
            "count": len(snapshots),
        },
        "position_changes": position_changes,
        "highlights": highlights,
        "blowups": blowups,
        "holdings_table": holdings_table,
        "trades": {
            "records": trades,
            "by_code": list(trades_by_code.values()),
        },
        "index_summary": external_sources.get("index_summary") or [],
        "macro_events": external_sources.get("macro_events") or [],
        "news_themes": external_sources.get("news_themes") or [],
        "opportunity_items": external_sources.get("opportunity_items") or [],
        "external_source_summary": external_sources.get("source_summary") or {},
        "next_week": next_week,
        "story": _build_story(
            context_warnings=warnings,
            position_changes=position_changes,
            external_sources=external_sources,
        ),
        "candidate_insights": [],
        "warnings": warnings,
    }


def render_weekly_review_markdown(context: dict[str, Any]) -> str:
    period = context["period"]
    lines = [
        f"# 本周复盘 {period['label']}",
        "",
        "## 1. 高光时刻",
    ]
    lines.extend(_render_ranked_table(context.get("highlights") or [], positive=True))
    lines.extend(["", "## 2. 炸裂时刻"])
    lines.extend(_render_ranked_table(context.get("blowups") or [], positive=False))
    lines.extend(["", "## 3. 指数与外部环境"])
    lines.extend(
        _render_external_environment(
            indexes=context.get("index_summary") or [],
            macro_events=context.get("macro_events") or [],
            news_themes=context.get("news_themes") or [],
        )
    )
    lines.extend(["", "## 4. 整体故事"])
    lines.extend(_render_story(context.get("story") or {}))
    lines.extend(["", "## 5. 下周展望"])
    lines.extend(_render_next_week_items(context.get("next_week") or []))
    lines.extend(["", "## 6. 当前持仓分析"])
    lines.extend(_render_holdings_table(context.get("holdings_table") or []))
    lines.extend(["", "## 数据口径"])
    lines.extend(_render_source_status(context.get("source_status") or {}))
    warnings = context.get("warnings") or []
    if warnings:
        lines.extend(["", "## 数据提醒"])
        lines.extend(f"- {item}" for item in warnings[:8])
    lines.append("")
    lines.append("注：本复盘只读分析，不会下单；P1 的周度表现以持仓快照盈亏变化为主，交易记录用于解释仓位变化。")
    return "\n".join(lines)


def render_next_week_markdown(context: dict[str, Any]) -> str:
    period = context["period"]
    lines = [
        f"# 下周节奏 {period['label']}",
        "",
        "## 下周展望",
    ]
    lines.extend(_render_next_week_items(context.get("next_week") or []))
    lines.extend(["", "## 当前持仓节奏"])
    lines.extend(_render_holdings_table(context.get("holdings_table") or []))
    lines.extend(["", "## 数据口径"])
    lines.extend(_render_source_status(context.get("source_status") or {}))
    return "\n".join(lines)


def _load_account_snapshots(
    start: date,
    end: date,
    source_status: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    try:
        snapshots = repository.list_account_snapshots(start=start.isoformat(), end=end.isoformat())
    except Exception as exc:
        warnings.append(f"账户快照读取失败：{exc}")
        return []

    status = "ok" if len(snapshots) >= 2 else ("partial" if snapshots else "missing")
    source_status["account_snapshots"] = {"status": status, "count": len(snapshots)}
    if len(snapshots) < 2:
        warnings.append("账户快照少于 2 天，本周表现会降级为当前/可用快照参考。")
    return snapshots


def _load_realtime_positions(
    source_status: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any] | None:
    try:
        snapshot = get_futu_positions()
    except Exception as exc:
        warnings.append(f"实时持仓读取失败：{exc}")
        return None
    source_status["positions"] = {
        "status": "realtime",
        "fetched_at": snapshot.fetched_at.isoformat(),
        "cached": snapshot.cached,
    }
    return {
        "positions": _normalize_positions(snapshot.positions),
        "snapshot": {
            "source": snapshot.source,
            "fetched_at": snapshot.fetched_at.isoformat(),
            "cached": snapshot.cached,
        },
    }


def _load_trade_records(
    start: date,
    end: date,
    source_status: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    try:
        trades = repository.list_trade_records(start=start.isoformat(), end=end.isoformat())
    except Exception as exc:
        warnings.append(f"交易记录读取失败：{exc}")
        trades = []

    if trades:
        source_status["trades"] = {"status": "ok", "count": len(trades)}
        return trades

    try:
        snapshot = get_futu_trade_history(start=start.isoformat(), end=end.isoformat())
        repository.upsert_trade_records(snapshot.deals)
        trades = repository.list_trade_records(start=start.isoformat(), end=end.isoformat())
        source_status["trades"] = {
            "status": "backfilled",
            "count": len(trades),
            "fetched_at": snapshot.fetched_at.isoformat(),
        }
        return trades
    except FutuProviderError as exc:
        warnings.append(f"交易记录缺失，富途回补失败：{exc}")
    except Exception as exc:
        warnings.append(f"交易记录缺失，回补失败：{exc}")

    source_status["trades"] = {"status": "missing", "count": 0}
    return []


def _load_ipo_items(source_status: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    try:
        snapshot = get_hk_ipo_list(include_orders=False)
    except Exception as exc:
        warnings.append(f"港股 IPO 数据读取失败：{exc}")
        return []
    ipos = snapshot.ipos
    source_status["ipo"] = {
        "status": "ok",
        "count": len(ipos),
        "fetched_at": snapshot.fetched_at.isoformat(),
        "cached": snapshot.cached,
    }
    return ipos


def _positions_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return _normalize_positions(snapshot.get("positions") or [])


def _normalize_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in positions:
        code = str(item.get("code") or "").strip()
        market, symbol = _split_code(code)
        currency = str(item.get("currency") or _currency_for_market(market) or "UNKNOWN").upper()
        normalized.append(
            {
                "code": code,
                "market": market,
                "symbol": symbol,
                "name": item.get("stock_name") or item.get("name") or code or "unknown",
                "qty": _number(item.get("qty")),
                "cost_price": _optional_number(item.get("cost_price")),
                "market_val": _number(item.get("market_val") or item.get("market_value")),
                "pl_val": _number(item.get("pl_val")),
                "pl_ratio": _optional_ratio(item.get("pl_ratio")),
                "currency": currency,
            }
        )
    return normalized


def _build_position_changes(
    start_positions: list[dict[str, Any]],
    end_positions: list[dict[str, Any]],
    trades_by_code: dict[str, dict[str, Any]],
    has_start_snapshot: bool,
    has_end_reference: bool,
) -> list[dict[str, Any]]:
    start_by_code = {item["code"]: item for item in start_positions if item.get("code")}
    end_by_code = {item["code"]: item for item in end_positions if item.get("code")}
    codes = sorted(set(start_by_code) | set(end_by_code))
    changes = []
    for code in codes:
        start = start_by_code.get(code)
        end = end_by_code.get(code)
        base = end or start or {"code": code}
        start_qty = start["qty"] if start else 0.0
        end_qty = end["qty"] if end else 0.0
        start_pl = start["pl_val"] if start else 0.0
        end_pl = end["pl_val"] if end else 0.0
        start_market_val = start["market_val"] if start else 0.0
        end_market_val = end["market_val"] if end else 0.0
        movement = _movement_label(start=start, end=end, has_start_snapshot=has_start_snapshot, has_end_reference=has_end_reference)
        confidence = _confidence_label(movement)
        trade_summary = trades_by_code.get(code, _empty_trade_summary(code=code))
        changes.append(
            {
                "code": code,
                "market": base.get("market") or _split_code(code)[0],
                "symbol": base.get("symbol") or _split_code(code)[1],
                "name": base.get("name") or code,
                "currency": base.get("currency") or "UNKNOWN",
                "start": start,
                "end": end,
                "qty_delta": end_qty - start_qty,
                "cost_price_delta": _delta_optional(
                    end.get("cost_price") if end else None,
                    start.get("cost_price") if start else None,
                ),
                "market_val_delta": end_market_val - start_market_val,
                "pl_val_delta": end_pl - start_pl,
                "current_pl_val": end_pl,
                "current_pl_ratio": end.get("pl_ratio") if end else None,
                "current_market_val": end_market_val,
                "movement": movement,
                "confidence": confidence,
                "trade_summary": trade_summary,
                "themes": [],
                "knowledge_note": "",
                "status": [],
                "next_step": "",
            }
        )
    return sorted(changes, key=lambda item: item["current_market_val"], reverse=True)


def _attach_knowledge(position_changes: list[dict[str, Any]], warnings: list[str]) -> None:
    for item in position_changes:
        if not item.get("symbol") or not item.get("market"):
            continue
        try:
            context = repository.get_stock_context(symbol=item["symbol"], market=item["market"])
        except Exception as exc:
            warnings.append(f"{item['code']} 知识库匹配失败：{exc}")
            continue
        sectors = context.get("sectors") or []
        item["themes"] = [_sector_path_text(sector) for sector in sectors[:3] if _sector_path_text(sector)]
        note = _first_text(context.get("stock_insights") or []) or _first_text(context.get("stock_knowledge") or [])
        item["knowledge_note"] = note


def _top_highlights(position_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [item for item in position_changes if _rank_amount(item) > 0]
    return [_ranked_item(item, positive=True) for item in sorted(items, key=_rank_amount, reverse=True)[:3]]


def _top_blowups(position_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [item for item in position_changes if _rank_amount(item) < 0]
    return [_ranked_item(item, positive=False) for item in sorted(items, key=_rank_amount)[:3]]


def _ranked_item(item: dict[str, Any], positive: bool) -> dict[str, Any]:
    amount = _rank_amount(item)
    return {
        "code": item["code"],
        "name": item["name"],
        "currency": item["currency"],
        "type": _highlight_type(item) if positive else _blowup_type(item),
        "amount": amount,
        "pl_val_delta": item["pl_val_delta"],
        "current_pl_val": item["current_pl_val"],
        "movement": item["movement"],
        "confidence": item["confidence"],
        "review_question": _review_question(item, positive=positive),
    }


def _build_holdings_table(position_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in sorted(position_changes, key=lambda row: row["current_market_val"], reverse=True):
        if not item.get("end"):
            continue
        statuses = _status_labels(item)
        next_step = _next_step(item, statuses)
        item["status"] = statuses
        item["next_step"] = next_step
        rows.append(
            {
                "market": item["market"],
                "code": item["code"],
                "name": item["name"],
                "theme": " / ".join(item.get("themes") or []) or "待补",
                "currency": item["currency"],
                "market_val": item["current_market_val"],
                "current_pl_val": item["current_pl_val"],
                "current_pl_ratio": item["current_pl_ratio"],
                "weekly_pl_delta": item["pl_val_delta"],
                "movement": item["movement"],
                "status": "、".join(statuses),
                "knowledge_note": item.get("knowledge_note") or "知识库观点待补",
                "next_step": next_step,
            }
        )
    return rows


def _build_next_week_items(
    position_changes: list[dict[str, Any]],
    ipo_items: list[dict[str, Any]],
    opportunity_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for opportunity in (opportunity_items or [])[:5]:
        title = opportunity.get("title") or opportunity.get("name") or opportunity.get("item") or "外部机会"
        reason = opportunity.get("reason") or opportunity.get("summary") or opportunity.get("note") or "来自外部机会列表。"
        items.append(
            {
                "type": "机会",
                "item": str(title),
                "reason": str(reason),
                "needs_decision": str(opportunity.get("needs_decision") or "是"),
            }
        )
    active_ipos = [ipo for ipo in ipo_items if _is_active_ipo(ipo)]
    if active_ipos:
        names = "、".join(str(ipo.get("name") or ipo.get("code") or "") for ipo in active_ipos[:5] if ipo)
        items.append(
            {
                "type": "新股",
                "item": f"港股新股申购列表：{names or len(active_ipos)}",
                "reason": "已接入富途港股 IPO 列表，需要按申购状态单独判断。",
                "needs_decision": "是",
            }
        )
    top_loss = sorted(position_changes, key=_rank_amount)[:3]
    if top_loss:
        names = "、".join(f"{item['name']} {item['code']}" for item in top_loss if _rank_amount(item) < 0)
        if names:
            items.append(
                {
                    "type": "持仓处理",
                    "item": names,
                    "reason": "本周盈亏变化靠后，适合下周先复盘逻辑是否变化。",
                    "needs_decision": "是",
                }
            )
    high_vol = [item for item in position_changes if "高波动" in _status_labels(item)][:5]
    if high_vol:
        items.append(
            {
                "type": "风险控制",
                "item": "、".join(f"{item['name']} {item['code']}" for item in high_vol),
                "reason": "高波动或杠杆属性持仓需要提前定义观察条件。",
                "needs_decision": "是",
            }
        )
    missing_knowledge = [item for item in position_changes if item.get("end") and not item.get("knowledge_note")][:5]
    if missing_knowledge:
        items.append(
            {
                "type": "补研究",
                "item": "、".join(f"{item['name']} {item['code']}" for item in missing_knowledge[:3]),
                "reason": "当前持仓仍缺少知识库观点，周复盘只能做数字判断。",
                "needs_decision": "否",
            }
        )
    if not items:
        items.append(
            {
                "type": "复盘",
                "item": "继续积累每日快照和交易记录",
                "reason": "数据资产稳定后，下周复盘会更容易分清价格贡献和仓位调整。",
                "needs_decision": "否",
            }
        )
    return items


def _build_story(
    context_warnings: list[str],
    position_changes: list[dict[str, Any]],
    external_sources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    leaders = [item for item in sorted(position_changes, key=_rank_amount, reverse=True)[:3] if _rank_amount(item) > 0]
    laggards = [item for item in sorted(position_changes, key=_rank_amount)[:3] if _rank_amount(item) < 0]
    external_sources = external_sources or {}
    indexes = external_sources.get("index_summary") or []
    macro_events = external_sources.get("macro_events") or []
    news_themes = external_sources.get("news_themes") or []
    external_text = _external_story_text(indexes=indexes, macro_events=macro_events, news_themes=news_themes)
    portfolio_relation = (
        "本周组合关系主要基于持仓 snapshot 的盈亏变化，并结合外部环境源做辅助判断。"
        if external_text
        else "本周故事主要基于持仓 snapshot 的盈亏变化；外部环境源未配置。"
    )
    return {
        "mainline": _names(leaders) or "本周缺少足够快照，暂不归纳主线。",
        "external_context": external_text or "外部环境源未配置。",
        "negative_signals": _names(laggards) or "暂未从快照差分中识别明显拖累项。",
        "portfolio_relation": portfolio_relation,
        "next_validation": "下周优先验证本周贡献/拖累标的的逻辑是否延续，并继续补齐每日交易与快照。",
        "data_gaps": context_warnings[:5],
    }


def _external_story_text(
    *,
    indexes: list[dict[str, Any]],
    macro_events: list[dict[str, Any]],
    news_themes: list[dict[str, Any]],
) -> str:
    parts = []
    if indexes:
        parts.append("指数：" + "；".join(_short_item_text(item) for item in indexes[:3]))
    if macro_events:
        parts.append("宏观：" + "；".join(_short_item_text(item) for item in macro_events[:3]))
    if news_themes:
        parts.append("主题：" + "；".join(_short_item_text(item) for item in news_themes[:3]))
    if not parts:
        return ""
    return "本周外部环境参考：" + " / ".join(parts)


def _short_item_text(item: dict[str, Any]) -> str:
    name = item.get("name") or item.get("title") or item.get("theme") or item.get("symbol") or "未命名"
    summary = item.get("summary") or item.get("note") or item.get("change") or item.get("reason") or ""
    return f"{name}{'：' + str(summary) if summary else ''}"


def save_weekly_review_report(
    context: dict[str, Any],
    markdown: str,
    *,
    refreshed: bool = False,
    token_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    period = context["period"]
    budget_warnings = build_budget_warnings(token_usage)
    return repository.upsert_review_report(
        report_date=period["end"],
        report_type="weekly",
        period_start=period["start"],
        period_end=period["end"],
        summary=markdown,
        portfolio_snapshot=context,
        risks=context.get("blowups") or [],
        opportunities=(context.get("highlights") or []) + (context.get("next_week") or []),
        new_knowledge_candidates=context.get("candidate_insights") or [],
        source_status=context.get("source_status") or {},
        highlights=context.get("highlights") or [],
        blowups=context.get("blowups") or [],
        holdings_table=context.get("holdings_table") or [],
        next_week=context.get("next_week") or [],
        story=context.get("story") or {},
        refreshed=refreshed,
        token_usage=token_usage,
        budget_warnings=budget_warnings,
    )


def _render_ranked_table(items: list[dict[str, Any]], positive: bool) -> list[str]:
    if not items:
        return ["- 暂未识别到明显高光。" if positive else "- 暂未识别到明显拖累。"]
    lines = [
        "| 标的 | 类型 | 金额 | 仓位变化 | 置信度 | 复盘问题 |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for item in items:
        lines.append(
            f"| {item['name']} {item['code']} | {item['type']} | "
            f"{_fmt_money(item.get('amount', item['pl_val_delta']), item['currency'])} | {item['movement']} | "
            f"{item['confidence']} | {item['review_question']} |"
        )
    return lines


def _render_story(story: dict[str, Any]) -> list[str]:
    return [
        f"- 主线：{story.get('mainline') or '待观察'}",
        f"- 外部环境：{story.get('external_context') or '外部环境源未配置。'}",
        f"- 负向信号：{story.get('negative_signals') or '待观察'}",
        f"- 和我组合的关系：{story.get('portfolio_relation') or '待观察'}",
        f"- 下周验证点：{story.get('next_validation') or '待观察'}",
    ]


def _render_external_environment(
    *,
    indexes: list[dict[str, Any]],
    macro_events: list[dict[str, Any]],
    news_themes: list[dict[str, Any]],
) -> list[str]:
    lines: list[str] = []
    if indexes:
        lines.append("### 指数")
        lines.extend(_render_named_items(indexes, empty_text="指数数据源未接入，本周不做指数归因。"))
    else:
        lines.append("- 指数数据源未接入，本周不做指数归因。")
    if macro_events:
        lines.extend(["", "### 宏观"])
        lines.extend(_render_named_items(macro_events, empty_text="宏观数据源未接入。"))
    if news_themes:
        lines.extend(["", "### 新闻/主题"])
        lines.extend(_render_named_items(news_themes, empty_text="新闻/主题数据源未接入。"))
    return lines


def _render_named_items(items: list[dict[str, Any]], *, empty_text: str) -> list[str]:
    if not items:
        return [f"- {empty_text}"]
    lines = []
    for item in items[:8]:
        name = item.get("name") or item.get("title") or item.get("theme") or item.get("symbol") or "未命名"
        summary = item.get("summary") or item.get("note") or item.get("change") or item.get("reason") or ""
        lines.append(f"- {name}{'：' + str(summary) if summary else ''}")
    return lines


def _render_next_week_items(items: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| 类型 | 事项 | 为什么重要 | 需要用户决定 |",
        "| --- | --- | --- | --- |",
    ]
    for item in items:
        lines.append(f"| {item['type']} | {item['item']} | {item['reason']} | {item['needs_decision']} |")
    return lines


def _render_holdings_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- 当前没有可展示持仓。"]
    lines = [
        "| 市场 | 标的 | 主题 | 市值 | 当前盈亏 | 本周盈亏变化 | 仓位变化 | 状态 | 下周节奏 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['market']} | {row['name']} {row['code']} | {row['theme']} | "
            f"{_fmt_money(row['market_val'], row['currency'])} | "
            f"{_fmt_money(row['current_pl_val'], row['currency'])}"
            f"{_fmt_ratio_suffix(row.get('current_pl_ratio'))} | "
            f"{_fmt_money(row['weekly_pl_delta'], row['currency'])} | "
            f"{row['movement']} | {row['status']} | {row['next_step']} |"
        )
    return lines


def _render_source_status(source_status: dict[str, Any]) -> list[str]:
    return [
        f"- 账户快照：{_status_text(source_status.get('account_snapshots'))}",
        f"- 交易记录：{_status_text(source_status.get('trades'))}",
        f"- 当前持仓：{_status_text(source_status.get('positions'))}",
        f"- 指数：{_status_text(source_status.get('indexes'))}",
        f"- 宏观：{_status_text(source_status.get('macro'))}",
        f"- 新闻/主题：{_status_text(source_status.get('news_themes'))}",
        f"- 机会列表：{_status_text(source_status.get('opportunities'))}",
        f"- 港股 IPO：{_status_text(source_status.get('ipo'))}",
    ]


def _snapshot_info(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "snapshot_date": snapshot.get("snapshot_date"),
        "source": snapshot.get("source"),
        "fetched_at": snapshot.get("fetched_at"),
        "position_count": len(snapshot.get("positions") or []),
    }


def _snapshot_date(snapshot: dict[str, Any]) -> date:
    value = snapshot.get("snapshot_date")
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _summarize_trades_by_code(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for trade in trades:
        code = str(trade.get("code") or "").strip()
        if not code:
            continue
        item = result.setdefault(code, _empty_trade_summary(code=code))
        item["name"] = trade.get("stock_name") or item.get("name") or code
        item["currency"] = trade.get("currency") or item.get("currency") or "UNKNOWN"
        item["count"] += 1
        amount = abs(_number(trade.get("amount")))
        side = str(trade.get("trd_side") or "").lower()
        if "buy" in side or "买" in side:
            item["buy_count"] += 1
            item["buy_amount"] += amount
        elif "sell" in side or "卖" in side:
            item["sell_count"] += 1
            item["sell_amount"] += amount
    return result


def _empty_trade_summary(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": code,
        "currency": "UNKNOWN",
        "count": 0,
        "buy_count": 0,
        "sell_count": 0,
        "buy_amount": 0.0,
        "sell_amount": 0.0,
    }


def _movement_label(
    start: dict[str, Any] | None,
    end: dict[str, Any] | None,
    has_start_snapshot: bool,
    has_end_reference: bool,
) -> str:
    if not has_start_snapshot:
        return "缺少期初快照"
    if not has_end_reference:
        return "缺少期末快照"
    if start is None and end is not None:
        return "新开仓"
    if start is not None and end is None:
        return "清仓"
    start_qty = start["qty"] if start else 0.0
    end_qty = end["qty"] if end else 0.0
    if abs(end_qty - start_qty) < 1e-9:
        return "持仓未变"
    return "加仓" if end_qty > start_qty else "减仓"


def _confidence_label(movement: str) -> str:
    if movement == "持仓未变":
        return "高"
    if movement in {"加仓", "减仓"}:
        return "中"
    return "低"


def _highlight_type(item: dict[str, Any]) -> str:
    if item["movement"] == "清仓":
        return "止盈清仓"
    if item["movement"] == "新开仓":
        return "新开仓当前盈利"
    if item["movement"] == "加仓":
        return "加仓后贡献"
    if item["current_pl_val"] < 0 and item["pl_val_delta"] > 0:
        return "亏损收窄"
    return "持仓浮盈改善"


def _blowup_type(item: dict[str, Any]) -> str:
    if item["movement"] == "清仓":
        return "割肉清仓"
    if item["movement"] == "新开仓":
        return "新开仓当前亏损"
    if item["movement"] == "加仓":
        return "加仓后拖累"
    if item["current_pl_val"] > 0 and item["pl_val_delta"] < 0:
        return "盈利回撤"
    if item["current_pl_val"] < 0:
        return "浮亏扩大"
    return "本周拖累"


def _review_question(item: dict[str, Any], positive: bool) -> str:
    if positive:
        if item["movement"] == "清仓":
            return "清仓前仍有浮盈，需要复盘退出纪律是否执行到位"
        if item["confidence"] == "高":
            return "这次贡献来自持仓表现，是否可复用判断框架"
        return "这次贡献包含仓位变化，需要复盘加减仓节奏"
    if item["movement"] == "清仓":
        return "清仓前仍是浮亏，需要复盘是否是主动纠错还是情绪化割肉"
    if item["confidence"] == "高":
        return "拖累来自持仓表现，需要确认逻辑是否变化"
    return "拖累包含仓位变化，需要区分价格波动和操作影响"


def _rank_amount(item: dict[str, Any]) -> float:
    if item["movement"] == "清仓" and item.get("start"):
        return _number(item["start"].get("pl_val"))
    return _number(item.get("pl_val_delta"))


def _status_labels(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    if item["current_market_val"] > 0 and item.get("themes"):
        labels.append("核心持仓")
    if item["pl_val_delta"] > 0:
        labels.append("强势贡献")
    if item["pl_val_delta"] < 0:
        labels.append("本周拖累")
    if item["current_pl_val"] < 0:
        labels.append("历史拖累")
    text = f"{item.get('code', '')} {item.get('name', '')} {' '.join(item.get('themes') or [])}".lower()
    if any(marker in text for marker in ("2x", "两倍", "lever", "量子", "quantum", "太空", "rocket", "crypto", "bitcoin", "ipo")):
        labels.append("高波动")
    if item["current_market_val"] > 0 and not item.get("knowledge_note"):
        labels.append("补研究")
    return _dedupe(labels) or ["观察"]


def _next_step(item: dict[str, Any], statuses: list[str]) -> str:
    if "高波动" in statuses:
        return "确认风险边界和止盈/止损观察条件"
    if "本周拖累" in statuses or "历史拖累" in statuses:
        return "复盘逻辑是否变化，列入下周观察"
    if "补研究" in statuses:
        return "补齐知识库观点"
    if "强势贡献" in statuses:
        return "观察是否过热，保留验证点"
    return "继续观察"


def _is_active_ipo(item: dict[str, Any]) -> bool:
    status = str(item.get("is_subscribe_status") or "").lower()
    return any(marker in status for marker in ("sub", "可", "认购", "subscribe", "applying"))


def _split_code(code: str) -> tuple[str, str]:
    if "." not in code:
        return "", code
    market, symbol = code.split(".", 1)
    return market.upper(), symbol.upper()


def _currency_for_market(market: str) -> str | None:
    return {
        "HK": "HKD",
        "US": "USD",
        "SH": "CNY",
        "SZ": "CNY",
        "CN": "CNY",
        "KR": "KRW",
    }.get(str(market or "").upper())


def _sector_path_text(sector: dict[str, Any]) -> str:
    path = sector.get("path")
    if isinstance(path, list):
        return "/".join(str(item) for item in path if item)
    return str(path or sector.get("name") or "").strip()


def _first_text(items: list[dict[str, Any]]) -> str:
    for item in items:
        text = item.get("normalized_summary") or item.get("content") or item.get("insight")
        if text:
            return str(text)
    return ""


def _names(items: list[dict[str, Any]]) -> str:
    return "、".join(f"{item['name']} {item['code']}" for item in items)


def _status_text(item: dict[str, Any] | None) -> str:
    if not item:
        return "missing"
    status = item.get("status") or "unknown"
    count = item.get("count")
    if count is not None:
        return f"{status}，{count} 条"
    return str(status)


def _fmt_money(value: Any, currency: str | None = None) -> str:
    number = _number(value)
    suffix = f" {currency}" if currency and currency != "UNKNOWN" else ""
    return f"{number:,.2f}{suffix}"


def _fmt_ratio_suffix(value: Any) -> str:
    ratio = _optional_ratio(value)
    if ratio is None:
        return ""
    return f" / {ratio * 100:.2f}%"


def _delta_optional(end_value: Any, start_value: Any) -> float | None:
    if end_value is None or start_value is None:
        return None
    return _number(end_value) - _number(start_value)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_ratio(value: Any) -> float | None:
    number = _optional_number(value)
    if number is None:
        return None
    return number / 100 if abs(number) > 1 else number


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
