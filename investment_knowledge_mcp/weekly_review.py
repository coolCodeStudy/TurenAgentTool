from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.event_data_provider import (
    EventDataProviderError,
    get_yahoo_finance_news_events,
)
from investment_knowledge_mcp.futu_provider import (
    FutuProviderError,
    get_futu_positions,
    get_futu_trade_history,
    get_hk_ipo_list,
)
from investment_knowledge_mcp.data_sources import (
    DataRequest,
    DataSourcePool,
    DataStatus,
    SourceCapability,
    SourcePlan,
    default_market_bar_pool,
    market_bar_records_by_symbol,
)
from investment_knowledge_mcp.research.official_sources import OfficialResearchProvider


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

REQUIRED_INDEXES: list[dict[str, str]] = [
    {
        "code": "US.SPX",
        "name": "S&P 500",
        "market": "US",
        "role": "broad",
        "relevance": "美股风险偏好和美元资产组合背景",
    },
    {
        "code": "US.NDX",
        "name": "Nasdaq 100",
        "market": "US",
        "role": "growth",
        "relevance": "美股成长和 AI 相关持仓的风险偏好代理",
    },
    {
        "code": "US.SOX",
        "name": "SOX Semiconductor Index",
        "market": "US",
        "role": "semiconductor",
        "relevance": "半导体、AI 基础设施、HBM/memory 持仓代理",
    },
    {
        "code": "HK.HSI",
        "name": "Hang Seng Index",
        "market": "HK",
        "role": "broad",
        "relevance": "港股整体风险偏好",
    },
    {
        "code": "HK.HSTECH",
        "name": "Hang Seng Tech Index",
        "market": "HK",
        "role": "growth",
        "relevance": "港股成长、互联网和科技持仓代理",
    },
    {
        "code": "HK.HSCEI",
        "name": "Hang Seng China Enterprises Index",
        "market": "HK",
        "role": "broad",
        "relevance": "中资港股和国企风险偏好",
    },
    {
        "code": "SH.000300",
        "name": "CSI 300",
        "market": "CN",
        "role": "broad",
        "relevance": "A 股大盘和人民币资产风险偏好",
    },
    {
        "code": "SZ.399006",
        "name": "ChiNext Index",
        "market": "CN",
        "role": "growth",
        "relevance": "A 股成长和题材风险偏好",
    },
    {
        "code": "SH.000688",
        "name": "STAR 50",
        "market": "CN",
        "role": "semiconductor",
        "relevance": "科创和半导体/硬科技主题代理",
    },
]

SOURCE_STATUS_LABELS = {
    "ok": "已读取",
    "partial": "部分可用",
    "checked_empty": "已检查但无材料事件",
    "missing": "缺失",
    "provider_unavailable": "数据源暂不可用",
    "source_blocked": "源数据阻塞",
    "realtime": "实时读取",
    "snapshot": "来自快照",
    "backfilled": "已回补",
    "fallback": "降级可用",
}

THEME_NEWS_PROXY_SYMBOLS: dict[str, list[str]] = {
    "AI 基础设施": ["NVDA", "AVGO", "SMH"],
    "HBM/memory": ["MU", "NVDA", "DRAM"],
    "半导体": ["SMH", "SOXX", "NVDA"],
    "港股成长": ["9988.HK", "3690.HK", "1810.HK"],
    "创新药": ["XBI", "BNTX", "1177.HK"],
    "加密金融": ["CRCL", "COIN", "BTC-USD"],
    "机器人": ["BOTZ", "ISRG", "ROK"],
    "太空": ["RKLB", "LUNR", "ASTS"],
}

THEME_NEWS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AI 基础设施": ("ai", "artificial intelligence", "data center", "infrastructure", "server", "gpu"),
    "HBM/memory": ("hbm", "memory", "dram", "micron", "sk hynix", "sandisk", "high-bandwidth"),
    "半导体": ("semiconductor", "chip", "foundry", "sox", "smh"),
    "港股成长": ("hong kong", "hang seng tech", "alibaba", "meituan", "xiaomi", "china tech"),
    "创新药": ("biotech", "drug", "clinical", "fda", "pharma"),
    "加密金融": ("crypto", "bitcoin", "stablecoin", "circle", "coinbase"),
    "机器人": ("robot", "automation", "surgical robot"),
    "太空": ("space", "rocket", "satellite", "launch"),
}

ATTRIBUTION_SOURCE_TYPES = {"official", "news_or_industry", "market_essay", "social_rumor", "user_knowledge"}
ATTRIBUTION_CONFIDENCE_ORDER = {"rumor_watch": 0, "low": 1, "medium": 2, "high": 3}
COST_DRIVER_KEYWORDS = (
    "cost",
    "margin",
    "inflation",
    "copper",
    "laminate",
    "fiberglass",
    "glass fiber",
    "raw material",
    "upstream",
    "成本",
    "毛利",
    "涨价",
    "通胀",
    "铜",
    "覆铜板",
    "玻纤",
    "玻璃纤维",
    "上游",
    "原材料",
    "pcb",
)
RUMOR_KEYWORDS = ("rumor", "unverified", "xueqiu", "social", "传闻", "雪球", "小作文", "未证实")
MISS_KEYWORDS = ("miss", "below expectation", "performance", "earnings", "q2", "不及预期", "业绩", "二季度", "q2")


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
) -> WeeklyReviewResult:
    context = build_weekly_review_context(start=start, end=end)
    markdown = render_next_week_markdown(context) if next_week_only else render_weekly_review_markdown(context)
    saved_report = None
    if save and not next_week_only:
        saved_report = save_weekly_review_report(context=context, markdown=markdown)
    return WeeklyReviewResult(context=context, markdown=markdown, saved_report=saved_report)


def build_weekly_review_context(start: date, end: date) -> dict[str, Any]:
    if end < start:
        start, end = end, start

    source_status: dict[str, Any] = {
        "account_snapshots": {"status": "missing", "count": 0},
        "trades": {"status": "missing", "count": 0},
        "positions": {"status": "missing", "fetched_at": None},
        "indexes": {"status": "missing", "provider": "futu", "count": 0},
        "events": {"status": "missing", "providers": ["official_sources"], "count": 0},
        "local_knowledge": {"status": "missing", "count": 0},
        "ipo": {"status": "missing", "count": 0},
    }
    warnings: list[str] = []

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
    active_markets = _active_portfolio_markets(position_changes=position_changes, trades=trades)
    detected_themes = _detect_portfolio_themes(position_changes)
    index_summary = _load_index_summary(
        start=start,
        end=end,
        source_status=source_status,
        warnings=warnings,
        active_markets=active_markets,
        detected_themes=detected_themes,
    )
    source_evidence = _build_source_evidence(
        start=start,
        end=end,
        position_changes=position_changes,
        source_status=source_status,
        warnings=warnings,
        detected_themes=detected_themes,
    )
    next_week = _build_next_week_items(position_changes=position_changes, ipo_items=ipo_items)
    holder_attribution = _build_holder_attribution(
        position_changes=position_changes,
        highlights=highlights,
        blowups=blowups,
        holdings_table=holdings_table,
        event_summary=source_evidence["events"],
        index_summary=index_summary,
        knowledge_evidence=source_evidence["knowledge"],
        trades_by_code=trades_by_code,
        source_status=source_status,
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
        "index_summary": index_summary,
        "event_summary": source_evidence["events"],
        "knowledge_evidence": source_evidence["knowledge"],
        "holder_attribution": holder_attribution,
        "detected_themes": detected_themes,
        "next_week": next_week,
        "story": _build_story(
            context_warnings=warnings,
            position_changes=position_changes,
            index_summary=index_summary,
            event_summary=source_evidence["events"],
            knowledge_evidence=source_evidence["knowledge"],
            source_status=source_status,
            detected_themes=detected_themes,
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
    lines.extend(["", "## 3. 指数"])
    lines.extend(_render_index_summary(context.get("index_summary") or [], context.get("source_status", {}).get("indexes")))
    lines.extend(["", "## 4. 整体故事"])
    lines.extend(_render_story(context.get("story") or {}))
    lines.extend(["", "## 5. 下周展望"])
    lines.extend(_render_next_week_items(context.get("next_week") or []))
    lines.extend(["", "## 6. 当前持仓分析"])
    lines.extend(_render_holdings_table(context.get("holdings_table") or []))
    lines.extend(["", "## 7. 持仓归因卡"])
    lines.extend(_render_holder_attribution(context.get("holder_attribution") or []))
    lines.extend(["", "## 数据口径"])
    lines.extend(_render_source_status(context.get("source_status") or {}))
    warnings = context.get("warnings") or []
    if warnings:
        lines.extend(["", "## 数据提醒"])
        lines.extend(f"- {item}" for item in warnings[:8])
    lines.append("")
    lines.append("注：本复盘只读分析，不会下单；周度表现优先用交易记录估算已实现盈亏，并结合持仓快照未实现盈亏变化。")
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


def _load_index_summary(
    start: date,
    end: date,
    source_status: dict[str, Any],
    warnings: list[str],
    active_markets: set[str],
    detected_themes: list[str],
    data_source_pool: DataSourcePool | None = None,
) -> list[dict[str, Any]]:
    request = DataRequest(
        capability=SourceCapability.MARKET_BARS,
        market="MULTI",
        symbols=tuple(index["code"] for index in REQUIRED_INDEXES),
        start=start,
        end=end,
        freshness="weekly_review",
    )
    plan = SourcePlan(
        capability=SourceCapability.MARKET_BARS,
        preferred_sources=("futu",),
        allowed_sources=("futu", "yahoo_chart"),
        fallback_sources=("yahoo_chart",),
        required=True,
        partial_allowed=True,
    )
    result = (data_source_pool or default_market_bar_pool()).fetch(request, plan)
    provider_name = result.selected_source
    provider_errors = [f"{failure.source_id}: {failure.code}" for failure in result.failures]
    failures = [
        {
            "code": failure.code,
            "source": failure.source_id,
            "retryable": failure.retryable,
            "fallback_allowed": failure.fallback_allowed,
        }
        for failure in result.failures
    ]

    def set_provider_unavailable_status(*, coverage: float, from_cache: bool) -> list[dict[str, Any]]:
        missing = [index["name"] for index in REQUIRED_INDEXES]
        reason = "指数行情数据源暂不可用。"
        source_status["indexes"] = {
            "status": "provider_unavailable",
            "provider": None,
            "providers": list(result.attempted_sources),
            "count": 0,
            "fetched_at": result.fetched_at.isoformat(),
            "metric": "close_to_close",
            "missing": missing,
            "active_markets": sorted(active_markets),
            "uncovered_active_markets": sorted(active_markets),
            "provider_errors": provider_errors,
            "reason": reason,
            "attempted_sources": list(result.attempted_sources),
            "selected_source": None,
            "coverage": coverage,
            "from_cache": from_cache,
            "failures": failures,
        }
        warnings.append(f"指数行情读取失败：{reason}")
        return []

    if result.status is DataStatus.UNAVAILABLE:
        return set_provider_unavailable_status(coverage=result.coverage, from_cache=result.from_cache)

    try:
        bars_by_code = market_bar_records_by_symbol(result)
    except ValueError:
        source_id = provider_name or result.attempted_sources[-1]
        provider_errors.append(f"{source_id}: provider_contract_error")
        failures.append(
            {
                "code": "provider_contract_error",
                "source": source_id,
                "retryable": False,
                "fallback_allowed": False,
            }
        )
        return set_provider_unavailable_status(coverage=0.0, from_cache=False)

    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for index in REQUIRED_INDEXES:
        bars = bars_by_code.get(index["code"]) or []
        metric = _index_metric(index=index, bars=bars, detected_themes=detected_themes, provider=provider_name)
        if metric is None:
            missing.append(index["name"])
            continue
        rows.append(metric)

    covered_markets = {_market_family(row.get("market")) for row in rows}
    uncovered_active = sorted(market for market in active_markets if market not in covered_markets)
    status = "ok"
    if missing or provider_errors:
        status = "partial"
    if uncovered_active or not rows:
        status = "source_blocked"
    source_status["indexes"] = {
        "status": status,
        "provider": provider_name,
        "providers": list(result.attempted_sources),
        "count": len(rows),
        "fetched_at": result.fetched_at.isoformat(),
        "metric": "close_to_close",
        "missing": missing,
        "active_markets": sorted(active_markets),
        "uncovered_active_markets": uncovered_active,
        "provider_errors": provider_errors,
        "reason": _index_status_reason(status=status, missing=missing, uncovered_active=uncovered_active),
        "attempted_sources": list(result.attempted_sources),
        "selected_source": provider_name,
        "coverage": result.coverage,
        "from_cache": result.from_cache,
        "failures": failures,
    }
    if provider_name == "yahoo_chart" and "futu" in result.attempted_sources:
        warnings.append("富途指数行情不可用，已使用 Yahoo chart 作为云端备用指数源。")
    if status == "source_blocked":
        warnings.append(source_status["indexes"]["reason"])
    return rows


def _build_source_evidence(
    start: date,
    end: date,
    position_changes: list[dict[str, Any]],
    source_status: dict[str, Any],
    warnings: list[str],
    detected_themes: list[str],
) -> dict[str, list[dict[str, Any]]]:
    knowledge = _collect_local_knowledge_evidence(position_changes)
    source_status["local_knowledge"] = {
        "status": "ok" if knowledge else "checked_empty",
        "count": len(knowledge),
        "sources": sorted({item.get("source_type", "local") for item in knowledge}),
    }

    official_events = _collect_official_event_evidence(
        start=start,
        end=end,
        position_changes=position_changes,
        warnings=warnings,
    )
    news_events = _collect_dated_news_event_evidence(
        start=start,
        end=end,
        position_changes=position_changes,
        detected_themes=detected_themes,
        warnings=warnings,
    )
    events = _dedupe_events([*official_events, *news_events])[:10]
    if not events:
        events = _collect_reference_event_evidence(
            end=end,
            position_changes=position_changes,
            knowledge_evidence=knowledge,
        )
    if events:
        has_reference_only = all(str(item.get("freshness")) == "reference_source" for item in events)
        has_dated_external = any(_is_dated_external_event(item) for item in events)
        providers = ["official_sources", "local_theme_context"]
        if news_events:
            providers.insert(1, "yahoo_finance_rss")
        if has_reference_only:
            providers.insert(1, "official_reference_fallback")
        checked_categories = ["company_announcements_or_filings", "sector_theme_context", "user_knowledge"]
        if news_events:
            checked_categories.insert(1, "dated_company_or_theme_news")
        source_status["events"] = {
            "status": "partial",
            "providers": providers,
            "count": len(events),
            "checked_categories": checked_categories,
            "source_blocked_categories": (
                ["dated_company_events", "macro_calendar", "general_news_theme_feed"]
                if has_reference_only
                else (["macro_calendar"] if has_dated_external else ["macro_calendar", "general_news_theme_feed"])
            ),
            "themes": detected_themes,
            "reason": (
                "已接入公司披露入口和本地主题证据；仍缺少本周 dated company events、宏观日历和通用新闻源。"
                if has_reference_only
                else (
                    "已接入本周 dated company/theme news 和本地主题证据；宏观日历仍待接入。"
                    if has_dated_external
                    else "公司公告/财报和本地主题证据已接入；宏观日历和通用新闻源仍待接入。"
                )
            ),
        }
    else:
        source_status["events"] = {
            "status": "source_blocked",
            "providers": ["official_sources", "local_theme_context"],
            "count": 0,
            "checked_categories": ["company_announcements_or_filings", "sector_theme_context", "user_knowledge"],
            "source_blocked_categories": ["macro_calendar", "general_news_theme_feed"],
            "themes": detected_themes,
            "reason": "未取得可引用的公司公告/财报/主题事件证据；宏观日历和通用新闻源仍待接入。",
        }
        warnings.append(source_status["events"]["reason"])
    return {"events": events, "knowledge": knowledge}


def _index_metric(
    index: dict[str, str],
    bars: list[dict[str, Any]],
    detected_themes: list[str],
    provider: str,
) -> dict[str, Any] | None:
    clean_bars = [bar for bar in bars if _optional_number(bar.get("close")) is not None]
    if len(clean_bars) < 2:
        return None
    first_close = _number(clean_bars[0].get("close"))
    last_close = _number(clean_bars[-1].get("close"))
    weekly_change_pct = ((last_close - first_close) / first_close * 100.0) if first_close else 0.0
    largest_move: dict[str, Any] = {}
    previous_close = first_close
    for bar in clean_bars[1:]:
        close = _number(bar.get("close"))
        change_pct = ((close - previous_close) / previous_close * 100.0) if previous_close else 0.0
        if not largest_move or abs(change_pct) > abs(_number(largest_move.get("change_pct"))):
            largest_move = {
                "date": bar.get("date"),
                "change_pct": change_pct,
                "direction": "up" if change_pct >= 0 else "down",
            }
        previous_close = close
    return {
        "code": index["code"],
        "name": index["name"],
        "market": index["market"],
        "role": index["role"],
        "weekly_change_pct": weekly_change_pct,
        "largest_daily_move": largest_move,
        "environment_label": _index_environment_label(index=index, weekly_change_pct=weekly_change_pct),
        "portfolio_relevance": _index_relevance(index=index, detected_themes=detected_themes),
        "source": {
            "provider": provider,
            "metric": "close_to_close",
            "start_date": clean_bars[0].get("date"),
            "end_date": clean_bars[-1].get("date"),
        },
    }


def _collect_official_event_evidence(
    start: date,
    end: date,
    position_changes: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    targets = _event_targets(position_changes)
    if not targets:
        return []
    provider = OfficialResearchProvider(timeout_seconds=8.0, max_excerpt_chars=1000, max_sources=2)
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for target in targets[:6]:
        market = str(target.get("market") or "").upper()
        if market not in {"US", "HK"}:
            continue
        try:
            bundle = provider.collect(
                symbol=str(target.get("symbol") or ""),
                market=market,
                company_name=target.get("name"),
            )
        except Exception as exc:
            errors.append(f"{target.get('code')}: {_friendly_provider_error(str(exc), family='外部事件')}")
            continue
        for source in bundle.sources[:2]:
            source_payload = source.to_draft_source()
            published_date = _date_from_any(source_payload.get("published_at"))
            events.append(
                {
                    "category": "company_announcements_or_filings",
                    "code": target.get("code"),
                    "name": target.get("name"),
                    "theme": target.get("theme"),
                    "source_name": source_payload.get("publisher") or "official source",
                    "source_type": source_payload.get("source_type"),
                    "published_at": source_payload.get("published_at"),
                    "title": source_payload.get("title"),
                    "url": source_payload.get("url"),
                    "freshness": _freshness_label(published_date=published_date, start=start, end=end),
                    "summary": _trim(source_payload.get("content_excerpt") or source_payload.get("notes") or source_payload.get("title"), 220),
                    "citation": _citation_label(source_payload.get("publisher") or "official", source_payload.get("title")),
                }
            )
    if errors:
        warnings.append("部分外部事件源读取失败：" + "；".join(errors[:3]))
    return _dedupe_events(events)[:10]


def _collect_dated_news_event_evidence(
    start: date,
    end: date,
    position_changes: list[dict[str, Any]],
    detected_themes: list[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    targets = _news_event_targets(position_changes=position_changes, detected_themes=detected_themes)
    if not targets:
        return []
    symbols = [target["news_symbol"] for target in targets]
    try:
        snapshot = get_yahoo_finance_news_events(symbols=symbols, start=start, end=end, timeout_seconds=6.0)
    except EventDataProviderError as exc:
        warnings.append("部分外部新闻源读取失败：" + _friendly_provider_error(str(exc), family="外部新闻"))
        return []

    target_by_symbol = {target["news_symbol"]: target for target in targets}
    events: list[dict[str, Any]] = []
    for item in snapshot.events:
        target = target_by_symbol.get(str(item.get("query_symbol") or "").upper())
        if target is None:
            continue
        if not _news_item_matches_target(item=item, target=target):
            continue
        published_date = _date_from_any(item.get("published_at"))
        category = "dated_company_news" if target.get("code") else "dated_theme_news"
        linked_theme = target.get("theme") or target.get("linked_theme")
        events.append(
            {
                "category": category,
                "code": target.get("code"),
                "name": target.get("name") or linked_theme,
                "theme": linked_theme,
                "linked_ticker": target.get("code"),
                "linked_theme": linked_theme,
                "source_name": item.get("source_name") or "Yahoo Finance",
                "source_type": item.get("source_type") or "financial_news_rss",
                "source_id": item.get("source_id"),
                "published_at": item.get("published_at"),
                "checked_at": snapshot.fetched_at.isoformat(),
                "title": item.get("title"),
                "url": item.get("url"),
                "freshness": _freshness_label(published_date=published_date, start=start, end=end),
                "summary": _trim(item.get("summary") or item.get("title"), 260),
                "citation": _citation_label(item.get("source_name") or "Yahoo Finance", item.get("title")),
            }
        )
    return _dedupe_events(events)[:10]


def _collect_reference_event_evidence(
    end: date,
    position_changes: list[dict[str, Any]],
    knowledge_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for target in _event_targets(position_changes)[:6]:
        reference = _official_reference_for_target(target)
        if reference is None:
            continue
        events.append(
            {
                "category": "company_disclosure_reference",
                "code": target.get("code"),
                "name": target.get("name"),
                "theme": target.get("theme"),
                "source_name": reference["publisher"],
                "source_type": reference["source_type"],
                "published_at": None,
                "checked_at": end.isoformat(),
                "title": reference["title"],
                "url": reference["url"],
                "freshness": "reference_source",
                "summary": reference["summary"],
                "citation": _citation_label(reference["publisher"], reference["title"]),
            }
        )
    if not events:
        for entry in knowledge_evidence[:6]:
            source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
            if not source or not source.get("url"):
                continue
            events.append(
                {
                    "category": "local_research_source",
                    "code": entry.get("code"),
                    "name": entry.get("name"),
                    "theme": None,
                    "source_name": source.get("publisher") or "local research source",
                    "source_type": "local_research_source",
                    "published_at": None,
                    "checked_at": end.isoformat(),
                    "title": source.get("title") or entry.get("summary"),
                    "url": source.get("url"),
                    "freshness": "reference_source",
                    "summary": _trim(entry.get("summary"), 220),
                    "citation": _citation_label(source.get("publisher") or "local research source", source.get("title")),
                }
            )
    return _dedupe_events(events)[:10]


def _official_reference_for_target(target: dict[str, Any]) -> dict[str, str] | None:
    code = str(target.get("code") or "").upper()
    market = str(target.get("market") or "").upper()
    symbol = str(target.get("symbol") or "").upper()
    name = str(target.get("name") or symbol or code).strip()
    known_urls = {
        "US.DRAM": {
            "publisher": "Roundhill Investments",
            "source_type": "fund_page",
            "title": "Roundhill Memory ETF product page",
            "url": "https://www.roundhillinvestments.com/etf/dram/",
        },
        "US.TLT": {
            "publisher": "iShares",
            "source_type": "fund_page",
            "title": "iShares 20+ Year Treasury Bond ETF product page",
            "url": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
        },
        "US.PSLV": {
            "publisher": "Sprott",
            "source_type": "fund_page",
            "title": "Sprott Physical Silver Trust product page",
            "url": "https://sprott.com/investment-strategies/physical-bullion-trusts/silver/",
        },
    }
    if code in known_urls:
        reference = dict(known_urls[code])
        reference["summary"] = f"{name} 的官方产品/披露入口，用于核对基金或产品层面的持仓主题和风险披露。"
        return reference
    if market == "US" and symbol:
        return {
            "publisher": "SEC EDGAR",
            "source_type": "company_disclosure_reference",
            "title": f"SEC company filings search for {symbol}",
            "url": f"https://www.sec.gov/edgar/search/#/q={symbol}",
            "summary": f"{name} 的 SEC 披露检索入口，用于核对本周或近前公告、财报和 8-K/10-Q/10-K 文件。",
        }
    if market == "HK" and symbol:
        stock = symbol.lstrip("0") or symbol
        return {
            "publisher": "HKEXnews",
            "source_type": "company_disclosure_reference",
            "title": f"HKEXnews disclosure search for {symbol}",
            "url": f"https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en&category=0&market=SEHK&stock={stock}",
            "summary": f"{name} 的港交所公告检索入口，用于核对本周或近前公告、业绩和交易披露。",
        }
    if market in {"SH", "SZ", "CN"} and symbol:
        publisher = "SSE" if market == "SH" else "SZSE"
        base = "https://www.sse.com.cn/disclosure/listedinfo/announcement/" if market == "SH" else "https://www.szse.cn/disclosure/listed/notice/index.html"
        return {
            "publisher": publisher,
            "source_type": "company_disclosure_reference",
            "title": f"{publisher} disclosure search for {symbol}",
            "url": base,
            "summary": f"{name} 的交易所公告入口，用于核对本周或近前公告、业绩和交易披露。",
        }
    return None


def _collect_local_knowledge_evidence(position_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in position_changes:
        for entry in item.get("knowledge_evidence") or []:
            key = "|".join(str(entry.get(part) or "") for part in ("source_type", "id", "summary"))
            if key in seen:
                continue
            seen.add(key)
            evidence.append(entry)
    return evidence[:16]


def _knowledge_evidence_from_context(context: dict[str, Any], stock: dict[str, Any]) -> list[dict[str, Any]]:
    source_by_id = {str(source.get("id")): source for source in context.get("sources") or [] if source.get("id") is not None}
    entries: list[dict[str, Any]] = []
    for sector in context.get("sectors") or []:
        text = _sector_path_text(sector)
        if text:
            entries.append(
                {
                    "source_type": "sector_mapping",
                    "id": sector.get("relation_id") or sector.get("sector_id"),
                    "code": stock.get("code"),
                    "name": stock.get("name"),
                    "summary": text,
                    "citation": f"sector_mapping:{sector.get('relation_id') or sector.get('sector_id')}",
                }
            )
    evidence_groups = [
        ("stock_knowledge", context.get("stock_knowledge") or []),
        ("stock_insight", context.get("stock_insights") or []),
        ("stock_candidate_insight", context.get("stock_candidate_insights") or []),
        ("sector_knowledge", context.get("sector_knowledge") or []),
        ("sector_insight", context.get("sector_insights") or []),
        ("global_insight", context.get("global_insights") or []),
        ("global_candidate_insight", context.get("global_candidate_insights") or []),
    ]
    for source_type, rows in evidence_groups:
        for row in rows[:3]:
            source = source_by_id.get(str(row.get("source_id")))
            summary = _first_nonempty(row.get("normalized_summary"), row.get("content"), row.get("insight"))
            if not summary:
                continue
            entries.append(
                {
                    "source_type": source_type,
                    "id": row.get("id"),
                    "code": stock.get("code"),
                    "name": stock.get("name"),
                    "summary": _trim(summary, 180),
                    "source": {
                        "id": source.get("id") if source else None,
                        "title": source.get("title") if source else None,
                        "publisher": source.get("publisher") if source else None,
                        "url": source.get("url") if source else None,
                    },
                    "citation": f"{source_type}:{row.get('id')}",
                }
            )
    return entries[:8]


def _positions_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return _normalize_positions(snapshot.get("positions") or [])


def _active_portfolio_markets(position_changes: list[dict[str, Any]], trades: list[dict[str, Any]]) -> set[str]:
    markets: set[str] = set()
    for item in position_changes:
        if item.get("start") or item.get("end") or _number(item.get("current_market_val")):
            market = _market_family(item.get("market"))
            if market:
                markets.add(market)
    for trade in trades:
        code = str(trade.get("code") or "")
        market, _symbol = _split_code(code)
        family = _market_family(market)
        if family:
            markets.add(family)
    return markets


def _detect_portfolio_themes(position_changes: list[dict[str, Any]]) -> list[str]:
    theme_markers = [
        ("AI 基础设施", ("ai", "人工智能", "基础设施", "服务器", "光通信", "cpo", "pcb", "玻璃基板")),
        ("HBM/memory", ("hbm", "memory", "dram", "内存", "存储", "海力士", "sk hynix")),
        ("半导体", ("semiconductor", "半导体", "芯片", "科创")),
        ("港股成长", ("港股", "恒生科技", "互联网", "美团", "阿里", "小米")),
        ("创新药", ("创新药", "biotech", "医药", "药")),
        ("加密金融", ("crypto", "bitcoin", "circle", "加密")),
        ("机器人", ("robot", "机器人")),
        ("太空", ("space", "rocket", "太空")),
    ]
    text = " ".join(
        " ".join(
            [
                str(item.get("code") or ""),
                str(item.get("name") or ""),
                " ".join(str(theme) for theme in item.get("themes") or []),
                str(item.get("knowledge_note") or ""),
            ]
        ).lower()
        for item in position_changes
    )
    detected = [name for name, markers in theme_markers if any(marker.lower() in text for marker in markers)]
    return detected or ["组合持仓"]


def _market_family(market: Any) -> str:
    value = str(market or "").upper()
    if value in {"US"}:
        return "US"
    if value in {"HK"}:
        return "HK"
    if value in {"CN", "SH", "SZ"}:
        return "CN"
    return value


def _friendly_provider_error(message: str, family: str) -> str:
    text = str(message or "").strip()
    lower = text.lower()
    if "未安装" in text or "import" in lower:
        return f"{family}数据依赖未安装，当前环境只能生成源数据阻塞草稿。"
    if any(
        marker in lower
        for marker in (
            "connection",
            "connect",
            "timeout",
            "refused",
            "dns",
            "network",
            "nodename",
            "name or service",
            "temporary failure",
            "urlopen",
        )
    ):
        return f"{family}数据源暂时不可连接，当前环境只能生成源数据阻塞草稿。"
    if "opend" in lower or "127.0.0.1" in lower or "localhost" in lower:
        return f"{family}数据源暂时不可用，当前环境只能生成源数据阻塞草稿。"
    if "富途" in text:
        return f"{family}数据源暂时不可用，当前环境只能生成源数据阻塞草稿。"
    return text or f"{family}数据源暂时不可用。"


def _index_status_reason(status: str, missing: list[str], uncovered_active: list[str]) -> str:
    if status == "ok":
        return "必需指数篮子已读取。"
    parts: list[str] = []
    if missing:
        parts.append("缺少指数：" + "、".join(missing[:6]))
    if uncovered_active:
        parts.append("活跃市场缺少代表指数：" + "、".join(uncovered_active))
    return "；".join(parts) if parts else "指数数据部分可用。"


def _index_environment_label(index: dict[str, str], weekly_change_pct: float) -> str:
    role = index.get("role")
    if weekly_change_pct >= 1.0:
        if role == "semiconductor":
            return "semiconductor-led"
        if role == "growth":
            return "growth-led"
        return "broad risk-on"
    if weekly_change_pct <= -1.0:
        return "broad risk-off"
    return "mixed/rotation"


def _index_relevance(index: dict[str, str], detected_themes: list[str]) -> str:
    relevance = index.get("relevance") or "组合市场环境代理"
    role = index.get("role")
    if role == "semiconductor" and any(theme in {"AI 基础设施", "HBM/memory", "半导体"} for theme in detected_themes):
        return relevance + "；本周组合检测到 AI/半导体相关主题"
    if role == "growth" and any(theme in {"港股成长", "机器人", "加密金融"} for theme in detected_themes):
        return relevance + "；本周组合检测到成长/高波动主题"
    return relevance


def _event_targets(position_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        [item for item in position_changes if item.get("code")],
        key=lambda item: (abs(_rank_amount(item)), _number(item.get("current_market_val"))),
        reverse=True,
    )
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ranked:
        code = str(item.get("code") or "")
        if code in seen:
            continue
        seen.add(code)
        targets.append(
            {
                "code": code,
                "symbol": item.get("symbol"),
                "market": item.get("market"),
                "name": item.get("name"),
                "theme": " / ".join(item.get("themes") or []),
            }
        )
    return targets


def _news_event_targets(position_changes: list[dict[str, Any]], detected_themes: list[str]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for target in _event_targets(position_changes)[:8]:
        news_symbol = _yahoo_news_symbol(target)
        if not news_symbol or news_symbol in seen_symbols:
            continue
        seen_symbols.add(news_symbol)
        targets.append({**target, "news_symbol": news_symbol, "keywords": _target_keywords(target)})

    for theme in detected_themes[:6]:
        for symbol in THEME_NEWS_PROXY_SYMBOLS.get(theme, [])[:2]:
            news_symbol = symbol.upper()
            if news_symbol in seen_symbols:
                continue
            seen_symbols.add(news_symbol)
            targets.append(
                {
                    "code": None,
                    "symbol": symbol,
                    "market": None,
                    "name": theme,
                    "theme": theme,
                    "linked_theme": theme,
                    "news_symbol": news_symbol,
                    "keywords": _theme_keywords(theme),
                }
            )
    return targets[:14]


def _yahoo_news_symbol(target: dict[str, Any]) -> str:
    market = str(target.get("market") or "").upper()
    symbol = str(target.get("symbol") or "").strip().upper()
    if not symbol:
        return ""
    if market == "US":
        return symbol
    if market == "HK":
        stripped = symbol.lstrip("0") or symbol
        return f"{stripped}.HK"
    if market == "SH":
        return f"{symbol}.SS"
    if market in {"SZ", "CN"}:
        return f"{symbol}.SZ"
    return ""


def _target_keywords(target: dict[str, Any]) -> list[str]:
    keywords = [
        str(target.get("symbol") or "").lower(),
        str(target.get("name") or "").lower(),
        str(target.get("code") or "").lower(),
    ]
    for piece in str(target.get("theme") or "").replace("/", " ").split():
        if len(piece) >= 3:
            keywords.append(piece.lower())
    for theme, markers in THEME_NEWS_KEYWORDS.items():
        if theme in str(target.get("theme") or ""):
            keywords.extend(marker.lower() for marker in markers)
    return [keyword for keyword in dict.fromkeys(keywords) if len(keyword) >= 2]


def _theme_keywords(theme: str) -> list[str]:
    keywords = [theme.lower()]
    keywords.extend(marker.lower() for marker in THEME_NEWS_KEYWORDS.get(theme, ()))
    return [keyword for keyword in dict.fromkeys(keywords) if len(keyword) >= 2]


def _news_item_matches_target(item: dict[str, Any], target: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(part) or "") for part in ("title", "summary")).lower()
    keywords = target.get("keywords") or []
    if any(keyword and keyword in text for keyword in keywords):
        return True
    query_symbol = str(item.get("query_symbol") or "").split(".")[0].lower()
    return bool(query_symbol and query_symbol in text)


def _date_from_any(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _freshness_label(published_date: date | None, start: date, end: date) -> str:
    if published_date is None:
        return "undated_source"
    if start <= published_date <= end:
        return "review_week"
    if published_date < start:
        return "nearest_prior"
    return "future_or_next_window"


def _trim(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _citation_label(source_name: Any, title: Any) -> str:
    source = str(source_name or "source").strip()
    clean_title = _trim(title, 80)
    return f"{source}: {clean_title}" if clean_title else source


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        key = "|".join(str(event.get(part) or "") for part in ("code", "url", "title"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def _is_dated_external_event(event: dict[str, Any]) -> bool:
    if str(event.get("freshness")) == "reference_source":
        return False
    if not event.get("published_at"):
        return False
    return str(event.get("category") or "").startswith(("dated_", "company_announcements"))


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
        period_pl = _estimate_period_pl(start=start, end=end, trade_summary=trade_summary)
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
                "period_pl": period_pl["amount"],
                "period_pl_method": period_pl["method"],
                "realized_pl_estimate": period_pl["realized_pl"],
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
        item["knowledge_evidence"] = _knowledge_evidence_from_context(context=context, stock=item)


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
        "realized_pl_estimate": item.get("realized_pl_estimate", 0.0),
        "period_pl_method": item.get("period_pl_method") or "snapshot_pl_delta",
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
                "weekly_pl_delta": _rank_amount(item),
                "snapshot_pl_delta": item["pl_val_delta"],
                "realized_pl_estimate": item.get("realized_pl_estimate", 0.0),
                "period_pl_method": item.get("period_pl_method") or "snapshot_pl_delta",
                "movement": item["movement"],
                "status": "、".join(statuses),
                "knowledge_note": item.get("knowledge_note") or "知识库观点待补",
                "next_step": next_step,
            }
        )
    return rows


def _build_next_week_items(position_changes: list[dict[str, Any]], ipo_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
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


def _build_holder_attribution(
    position_changes: list[dict[str, Any]],
    highlights: list[dict[str, Any]],
    blowups: list[dict[str, Any]],
    holdings_table: list[dict[str, Any]],
    event_summary: list[dict[str, Any]],
    index_summary: list[dict[str, Any]],
    knowledge_evidence: list[dict[str, Any]],
    trades_by_code: dict[str, dict[str, Any]],
    source_status: dict[str, Any],
) -> list[dict[str, Any]]:
    position_by_code = {str(item.get("code") or ""): item for item in position_changes if item.get("code")}
    holding_by_code = {str(item.get("code") or ""): item for item in holdings_table if item.get("code")}
    highlight_codes = {str(item.get("code") or "") for item in highlights if item.get("code")}
    blowup_codes = {str(item.get("code") or "") for item in blowups if item.get("code")}
    covered_codes: list[str] = []
    for item in [*highlights, *blowups]:
        code = str(item.get("code") or "")
        if code and code not in covered_codes:
            covered_codes.append(code)

    material_rows = sorted(holdings_table, key=lambda row: _number(row.get("market_val")), reverse=True)
    for row in material_rows[:8]:
        code = str(row.get("code") or "")
        status = str(row.get("status") or "")
        if not code or code in covered_codes:
            continue
        if any(label in status for label in ("核心持仓", "高波动", "补研究")):
            covered_codes.append(code)

    cards: list[dict[str, Any]] = []
    for code in covered_codes[:8]:
        item = position_by_code.get(code)
        if item is None:
            continue
        holding = holding_by_code.get(code, {})
        matching_events = _matching_attribution_events(item=item, events=event_summary)
        matching_knowledge = _matching_knowledge_evidence(item=item, evidence=knowledge_evidence)
        candidates = _event_cause_candidates(item=item, events=matching_events)
        market_candidate = _market_cause_candidate(item=item, index_summary=index_summary)
        if market_candidate is not None:
            candidates.append(market_candidate)
        theme_candidate = _theme_or_knowledge_candidate(item=item, knowledge=matching_knowledge)
        if theme_candidate is not None:
            candidates.append(theme_candidate)
        position_candidate = _position_trade_candidate(item=item, trade_summary=trades_by_code.get(code))
        if position_candidate is not None:
            candidates.append(position_candidate)

        candidates = _dedupe_candidates(candidates)[:4]
        source_gaps = _attribution_source_gaps(
            item=item,
            candidates=candidates,
            source_status=source_status,
            matching_events=matching_events,
        )
        confidence = _aggregate_attribution_confidence(candidates)
        thesis_impact = _aggregate_thesis_impact(candidates)
        lenses = [str(candidate.get("lens") or "") for candidate in candidates if candidate.get("lens")]
        external_lenses = [lens for lens in lenses if lens not in {"position_trade_behavior", "user_thesis_knowledge"}]
        no_supported_external_cause = not external_lenses
        verdict = _attribution_verdict(candidates=candidates, no_supported_external_cause=no_supported_external_cause)
        cards.append(
            {
                "code": code,
                "name": item.get("name") or holding.get("name") or code,
                "currency": item.get("currency") or holding.get("currency") or "UNKNOWN",
                "weekly_pl": _rank_amount(item),
                "movement": item.get("movement"),
                "position_confidence": item.get("confidence"),
                "attribution_verdict": verdict,
                "dominant_lens": _dominant_lens(candidates),
                "confidence": confidence,
                "thesis_impact": thesis_impact,
                "cause_candidates": candidates,
                "evidence": [_candidate_evidence_payload(candidate) for candidate in candidates if candidate.get("source_type")],
                "source_gaps": source_gaps,
                "no_supported_external_cause": no_supported_external_cause,
                "thesis_relationship": _thesis_relationship_text(
                    item=item,
                    candidates=candidates,
                    no_supported_external_cause=no_supported_external_cause,
                ),
                "next_validation": _card_next_validation(candidates=candidates, source_gaps=source_gaps),
                "links": {
                    "highlight": code if code in highlight_codes else None,
                    "blowup": code if code in blowup_codes else None,
                    "holding": code if code in holding_by_code else None,
                    "events": [_event_link_id(event) for event in matching_events],
                    "knowledge": [entry.get("citation") or entry.get("id") for entry in matching_knowledge],
                    "trades": code if (trades_by_code.get(code) or {}).get("count") else None,
                },
            }
        )
    return cards


def _matching_attribution_events(item: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    code = str(item.get("code") or "")
    themes = {str(theme).lower() for theme in item.get("themes") or [] if theme}
    matches: list[dict[str, Any]] = []
    for event in events:
        event_code = str(event.get("code") or event.get("linked_ticker") or "")
        event_theme = str(event.get("theme") or event.get("linked_theme") or "").lower()
        if event_code and event_code == code:
            matches.append(event)
            continue
        if event_theme and any(event_theme in theme or theme in event_theme for theme in themes):
            matches.append(event)
    return matches[:6]


def _matching_knowledge_evidence(item: dict[str, Any], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    code = str(item.get("code") or "")
    themes = {str(theme).lower() for theme in item.get("themes") or [] if theme}
    matches: list[dict[str, Any]] = []
    for entry in evidence:
        entry_code = str(entry.get("code") or "")
        summary = str(entry.get("summary") or "").lower()
        if entry_code and entry_code == code:
            matches.append(entry)
            continue
        if any(theme and theme in summary for theme in themes):
            matches.append(entry)
    return matches[:4]


def _event_cause_candidates(item: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("freshness") or "") == "reference_source":
            continue
        source_type = _classify_attribution_source(event)
        text = " ".join(str(event.get(part) or "") for part in ("title", "summary", "source_type", "source_name")).lower()
        lens = "fundamentals_cost_drivers" if _contains_any(text, COST_DRIVER_KEYWORDS) else "single_stock_event"
        title = _candidate_title_from_event(event=event, lens=lens, source_type=source_type)
        candidates.append(
            {
                "lens": lens,
                "title": title,
                "claim": _candidate_claim(event=event, lens=lens, source_type=source_type),
                "source_type": source_type,
                "source_name": event.get("source_name") or event.get("source") or "source",
                "source_date": _source_date_text(event),
                "url": event.get("url"),
                "source_id": event.get("source_id") or event.get("citation"),
                "confidence": _source_confidence(source_type=source_type, event=event),
                "thesis_impact": _candidate_thesis_impact(item=item, lens=lens, source_type=source_type, text=text),
                "evidence": _trim(event.get("summary") or event.get("title"), 260),
                "next_validation": _candidate_next_validation(lens=lens, source_type=source_type),
                "observed_inferred_unverified": _evidence_nature(source_type),
            }
        )
    return candidates


def _market_cause_candidate(item: dict[str, Any], index_summary: list[dict[str, Any]]) -> dict[str, Any] | None:
    market = _market_family(item.get("market"))
    market_indexes = [row for row in index_summary if _market_family(row.get("market")) == market]
    if not market_indexes:
        return None
    best = max(market_indexes, key=lambda row: abs(_number(row.get("weekly_change_pct"))), default=None)
    if best is None:
        return None
    index_move = _number(best.get("weekly_change_pct"))
    weekly_pl = _rank_amount(item)
    same_direction = (index_move >= 0 and weekly_pl >= 0) or (index_move <= 0 and weekly_pl <= 0)
    if abs(index_move) < 0.5 and not same_direction:
        return None
    relation = "同向" if same_direction else "背离"
    return {
        "lens": "market_benchmark",
        "title": f"{best.get('name')} market benchmark {relation}",
        "claim": f"{best.get('name')} 本周 {_fmt_signed_percent(index_move)}，与该持仓周度影响{relation}，可作为市场/基准解释候选。",
        "source_type": "official" if best.get("source") else "news_or_industry",
        "source_name": (best.get("source") or {}).get("provider") or "index_summary",
        "source_date": (best.get("source") or {}).get("end_date"),
        "url": None,
        "source_id": f"index:{best.get('code')}",
        "confidence": "medium",
        "thesis_impact": "neutral_noise" if same_direction else "needs_research",
        "evidence": best.get("portfolio_relevance") or best.get("environment_label") or "",
        "next_validation": "Compare the holding against its market and sector proxy again next week before assigning a single-stock cause.",
        "observed_inferred_unverified": "observed_and_inferred",
    }


def _theme_or_knowledge_candidate(item: dict[str, Any], knowledge: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not knowledge:
        return None
    entry = knowledge[0] if knowledge else {}
    summary = entry.get("summary") or "本地主题映射待补"
    source_type = "user_knowledge" if entry else "user_knowledge"
    return {
        "lens": "user_thesis_knowledge" if entry else "theme_sector",
        "title": "User thesis / theme context",
        "claim": f"本地知识或主题映射提示：{_trim(summary, 180)}",
        "source_type": source_type,
        "source_name": entry.get("source_type") or "local_knowledge",
        "source_date": None,
        "url": (entry.get("source") or {}).get("url") if isinstance(entry.get("source"), dict) else None,
        "source_id": entry.get("citation") or entry.get("id") or "theme_mapping",
        "confidence": "medium" if entry else "low",
        "thesis_impact": "needs_research" if _rank_amount(item) < 0 else "supports_thesis",
        "evidence": _trim(summary, 240),
        "next_validation": "Check whether this week's evidence changes the stored thesis, or only changes short-term timing.",
        "observed_inferred_unverified": "inferred",
    }


def _position_trade_candidate(item: dict[str, Any], trade_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    trade_summary = trade_summary or {}
    trade_text = ""
    if trade_summary.get("count"):
        trade_text = (
            f"{int(trade_summary.get('buy_count') or 0)} buys / {int(trade_summary.get('sell_count') or 0)} sells; "
            f"buy amount {_fmt_money(trade_summary.get('buy_amount'), trade_summary.get('currency'))}, "
            f"sell amount {_fmt_money(trade_summary.get('sell_amount'), trade_summary.get('currency'))}"
        )
    else:
        trade_text = "No interval trades found for this holding; weekly impact mainly came from holding performance."
    return {
        "lens": "position_trade_behavior",
        "title": "Position / trade behavior",
        "claim": f"{item.get('movement') or '仓位变化待确认'}；{trade_text}",
        "source_type": "official",
        "source_name": "account_snapshots_and_trade_records",
        "source_date": None,
        "url": None,
        "source_id": f"holding:{item.get('code')}",
        "confidence": _position_confidence_for_attribution(item.get("confidence")),
        "thesis_impact": "neutral_noise",
        "evidence": trade_text,
        "next_validation": "Review whether position size amplified the weekly contribution or drawdown.",
        "observed_inferred_unverified": "observed",
    }


def _attribution_source_gaps(
    item: dict[str, Any],
    candidates: list[dict[str, Any]],
    source_status: dict[str, Any],
    matching_events: list[dict[str, Any]],
) -> list[str]:
    lenses = {str(candidate.get("lens") or "") for candidate in candidates}
    gaps: list[str] = []
    event_status = (source_status.get("events") or {}).get("status")
    if "single_stock_event" not in lenses:
        gaps.append("No supported single-stock event cause found; check company announcement, earnings/guidance, dated news, or supplied market-essay/rumor artifact.")
    if "fundamentals_cost_drivers" not in lenses:
        gaps.append("No supported fundamentals/cost-driver source found; check margin commentary, upstream input prices, supplier cost data, and peer PCB movement.")
    if event_status in {"missing", "provider_unavailable", "source_blocked"} and not matching_events:
        gaps.append("External event source coverage is blocked or empty for this holding.")
    if not item.get("knowledge_evidence") and not item.get("knowledge_note"):
        gaps.append("Local thesis/knowledge evidence is missing for this holding.")
    return gaps[:4]


def _classify_attribution_source(source: dict[str, Any]) -> str:
    raw = " ".join(
        str(source.get(part) or "")
        for part in ("source_type", "source_name", "category", "publisher", "platform")
    ).lower()
    if _contains_any(raw, RUMOR_KEYWORDS) or "forum" in raw or "twitter" in raw or "xueqiu" in raw:
        return "social_rumor"
    if "market_essay" in raw or "essay" in raw or "analyst" in raw or "opinion" in raw or "小作文" in raw:
        return "market_essay"
    if "user" in raw or "knowledge" in raw or "insight" in raw or "candidate" in raw or "sector_mapping" in raw:
        return "user_knowledge"
    if "official" in raw or "filing" in raw or "announcement" in raw or "exchange" in raw or "hkex" in raw or "sec" in raw or "disclosure" in raw:
        return "official"
    if "news" in raw or "rss" in raw or "industry" in raw or "yahoo" in raw or "financial" in raw or "provider" in raw:
        return "news_or_industry"
    explicit = str(source.get("normalized_source_type") or "").lower()
    return explicit if explicit in ATTRIBUTION_SOURCE_TYPES else "news_or_industry"


def _position_confidence_for_attribution(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"高", "high"}:
        return "high"
    if text in {"中", "medium"}:
        return "medium"
    if text in {"低", "low"}:
        return "low"
    return "medium"


def _source_confidence(source_type: str, event: dict[str, Any]) -> str:
    if source_type == "social_rumor":
        return "rumor_watch"
    if source_type == "official":
        return "high" if event.get("published_at") else "medium"
    if source_type == "news_or_industry":
        return "medium"
    if source_type == "market_essay":
        return "medium" if event.get("evidence_based") else "low"
    if source_type == "user_knowledge":
        text = str(event.get("source_type") or event.get("category") or "").lower()
        return "low" if "candidate" in text else "medium"
    return "low"


def _candidate_title_from_event(event: dict[str, Any], lens: str, source_type: str) -> str:
    text = " ".join(str(event.get(part) or "") for part in ("title", "summary")).lower()
    if source_type == "social_rumor" and _contains_any(text, MISS_KEYWORDS):
        return "Q2 performance miss rumor / social discussion"
    if source_type == "market_essay" and _contains_any(text, MISS_KEYWORDS):
        return "Q2 performance miss market essay"
    if lens == "fundamentals_cost_drivers":
        return "Upstream cost / margin pressure candidate"
    return _trim(event.get("title") or event.get("summary") or "Single-stock event candidate", 120)


def _candidate_claim(event: dict[str, Any], lens: str, source_type: str) -> str:
    summary = _trim(event.get("summary") or event.get("title"), 220)
    if source_type == "social_rumor":
        return f"Unverified social/rumor source says: {summary}. Treat this only as a market-watch candidate, not a fact."
    if source_type == "market_essay":
        return f"Dated market essay frames a possible driver: {summary}. Treat opinion separately from confirmed facts."
    if lens == "fundamentals_cost_drivers":
        return f"Industry/source evidence points to a possible cost or margin driver: {summary}"
    return summary


def _candidate_thesis_impact(item: dict[str, Any], lens: str, source_type: str, text: str) -> str:
    if source_type == "social_rumor":
        return "needs_research"
    if lens == "fundamentals_cost_drivers":
        return "challenges_thesis"
    if _rank_amount(item) < 0 and source_type in {"official", "news_or_industry", "market_essay"}:
        return "challenges_thesis" if not _contains_any(text, RUMOR_KEYWORDS) else "needs_research"
    if _rank_amount(item) > 0 and source_type in {"official", "news_or_industry"}:
        return "supports_thesis"
    return "neutral_noise"


def _candidate_next_validation(lens: str, source_type: str) -> str:
    if source_type == "social_rumor":
        return "Check company announcement, earnings/guidance, and reputable dated follow-up before treating the rumor as real."
    if lens == "fundamentals_cost_drivers":
        return "Validate gross margin guidance, upstream material prices, supplier commentary, and peer PCB movement."
    if lens == "single_stock_event":
        return "Check the dated source against company filings, earnings calendar, and follow-up news."
    return "Compare market/theme movement with holding-specific evidence next week."


def _evidence_nature(source_type: str) -> str:
    if source_type == "social_rumor":
        return "unverified"
    if source_type == "market_essay":
        return "inferred"
    return "observed" if source_type in {"official", "news_or_industry"} else "inferred"


def _source_date_text(source: dict[str, Any]) -> str | None:
    value = source.get("published_at") or source.get("checked_at") or source.get("date")
    if not value:
        return None
    return str(value)[:10]


def _event_link_id(event: dict[str, Any]) -> str:
    return str(event.get("source_id") or event.get("citation") or event.get("url") or event.get("title") or "event")


def _candidate_evidence_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": candidate.get("source_type"),
        "source_name": candidate.get("source_name"),
        "source_date": candidate.get("source_date"),
        "url": candidate.get("url"),
        "source_id": candidate.get("source_id"),
        "claim": candidate.get("claim"),
        "confidence": candidate.get("confidence"),
    }


def _aggregate_attribution_confidence(candidates: list[dict[str, Any]]) -> str:
    source_confidences = [
        str(candidate.get("confidence") or "low")
        for candidate in candidates
        if candidate.get("lens") != "position_trade_behavior"
    ]
    if not source_confidences:
        return "low"
    non_rumor = [value for value in source_confidences if value != "rumor_watch"]
    if not non_rumor:
        return "rumor_watch"
    return max(non_rumor, key=lambda value: ATTRIBUTION_CONFIDENCE_ORDER.get(value, 1))


def _aggregate_thesis_impact(candidates: list[dict[str, Any]]) -> str:
    impacts = [str(candidate.get("thesis_impact") or "neutral_noise") for candidate in candidates]
    for value in ("invalidates_unless_confirmed", "challenges_thesis", "needs_research", "supports_thesis"):
        if value in impacts:
            return value
    return "neutral_noise"


def _dominant_lens(candidates: list[dict[str, Any]]) -> str:
    lenses = [str(candidate.get("lens") or "") for candidate in candidates if candidate.get("lens")]
    external = [lens for lens in lenses if lens not in {"position_trade_behavior", "user_thesis_knowledge"}]
    if len(set(external)) >= 2:
        return "mixed"
    if external:
        return external[0]
    if lenses:
        return lenses[0]
    return "unexplained"


def _attribution_verdict(candidates: list[dict[str, Any]], no_supported_external_cause: bool) -> str:
    if no_supported_external_cause:
        return "unexplained / no_supported_external_cause"
    lens_labels = []
    for lens in dict.fromkeys(str(candidate.get("lens") or "") for candidate in candidates):
        if lens == "single_stock_event":
            lens_labels.append("single_stock_event_watch")
        elif lens == "fundamentals_cost_drivers":
            lens_labels.append("fundamentals_cost_watch")
        elif lens == "market_benchmark":
            lens_labels.append("market_benchmark")
        elif lens == "theme_sector":
            lens_labels.append("theme_sector")
        elif lens == "user_thesis_knowledge":
            lens_labels.append("user_thesis")
    if len(lens_labels) > 1:
        return "mixed / " + " + ".join(lens_labels[:4])
    return lens_labels[0] if lens_labels else "unexplained"


def _thesis_relationship_text(
    item: dict[str, Any],
    candidates: list[dict[str, Any]],
    no_supported_external_cause: bool,
) -> str:
    themes = " / ".join(str(theme) for theme in item.get("themes") or []) or "current thesis"
    if no_supported_external_cause:
        return f"{themes}: no supported external cause was found, so treat the weekly move as a research queue item rather than a thesis change."
    if any(candidate.get("thesis_impact") == "challenges_thesis" for candidate in candidates):
        return f"{themes}: cost, event, or negative evidence may challenge the thesis; validate whether it affects long-term demand, margin, or only short-term sentiment."
    if any(candidate.get("thesis_impact") == "supports_thesis" for candidate in candidates):
        return f"{themes}: available evidence is directionally supportive, but still requires source follow-through."
    return f"{themes}: evidence is not strong enough to update the thesis without more validation."


def _card_next_validation(candidates: list[dict[str, Any]], source_gaps: list[str]) -> list[str]:
    validations: list[str] = []
    for candidate in candidates:
        text = str(candidate.get("next_validation") or "").strip()
        if text and text not in validations:
            validations.append(text)
    for gap in source_gaps[:2]:
        if "single-stock" in gap:
            validations.append("Find a dated company or reputable-news source before assigning a single-stock cause.")
        elif "fundamentals/cost" in gap:
            validations.append("Check margin/cost trend, upstream input prices, and peer supply-chain moves.")
    return validations[:5] or ["Continue monitoring price action, source evidence, and user thesis notes next week."]


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = "|".join(str(candidate.get(part) or "") for part in ("lens", "title", "source_id", "source_type"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lower = str(text or "").lower()
    return any(keyword.lower() in lower for keyword in keywords)


def _build_story(
    context_warnings: list[str],
    position_changes: list[dict[str, Any]],
    index_summary: list[dict[str, Any]],
    event_summary: list[dict[str, Any]],
    knowledge_evidence: list[dict[str, Any]],
    source_status: dict[str, Any],
    detected_themes: list[str],
) -> dict[str, Any]:
    leaders = [item for item in sorted(position_changes, key=_rank_amount, reverse=True)[:3] if _rank_amount(item) > 0]
    laggards = [item for item in sorted(position_changes, key=_rank_amount)[:3] if _rank_amount(item) < 0]
    strongest_index = max(index_summary, key=lambda item: _number(item.get("weekly_change_pct")), default=None)
    weakest_index = min(index_summary, key=lambda item: _number(item.get("weekly_change_pct")), default=None)
    claims: list[dict[str, Any]] = []
    if strongest_index:
        claims.append(
            {
                "type": "index",
                "text": (
                    f"{strongest_index.get('name')} 本周 {_fmt_signed_percent(strongest_index.get('weekly_change_pct'))}，"
                    f"市场标签为 {strongest_index.get('environment_label')}。"
                ),
                "citations": [f"index:{strongest_index.get('code')}"],
            }
        )
    if leaders:
        claims.append(
            {
                "type": "portfolio",
                "text": f"组合高光主要来自 {_names(leaders)}。",
                "citations": [f"holding:{item.get('code')}" for item in leaders[:3]],
            }
        )
    if laggards:
        claims.append(
            {
                "type": "portfolio",
                "text": f"组合拖累主要来自 {_names(laggards)}。",
                "citations": [f"holding:{item.get('code')}" for item in laggards[:3]],
            }
        )
    if event_summary:
        event = event_summary[0]
        event_date = _date_from_any(event.get("published_at"))
        date_text = f"{event_date.isoformat()} " if event_date else ""
        claims.append(
            {
                "type": "external_event",
                "text": f"{event.get('name') or event.get('code') or event.get('theme')} 有{date_text}可追溯外部材料：{event.get('title')}",
                "citations": [event.get("citation") or f"event:{event.get('code')}"],
            }
        )
    if knowledge_evidence:
        entry = knowledge_evidence[0]
        claims.append(
            {
                "type": "user_knowledge",
                "text": f"本地知识提示 {entry.get('name') or entry.get('code') or '组合'}：{entry.get('summary')}",
                "citations": [entry.get("citation") or "local_knowledge"],
            }
        )

    index_status = (source_status.get("indexes") or {}).get("status")
    event_status = (source_status.get("events") or {}).get("status")
    source_blockers = []
    if index_status in {"source_blocked", "provider_unavailable", "missing"}:
        source_blockers.append("指数")
    if event_status in {"source_blocked", "provider_unavailable", "missing"}:
        source_blockers.append("外部事件")

    market_environment = "、".join(
        f"{item.get('name')} {_fmt_signed_percent(item.get('weekly_change_pct'))}"
        for item in index_summary[:4]
    )
    if not market_environment:
        market_environment = "指数源暂不可用，本周只能把市场环境标记为源数据阻塞草稿。"

    event_text = _event_story_text(event_summary=event_summary, knowledge_evidence=knowledge_evidence, source_blockers=source_blockers)
    relation_parts = []
    if strongest_index:
        relation_parts.append(f"{strongest_index.get('name')} 对应 {strongest_index.get('portfolio_relevance')}")
    if weakest_index and weakest_index is not strongest_index:
        relation_parts.append(f"{weakest_index.get('name')} 是本周较弱市场代理")
    if detected_themes:
        relation_parts.append("检测到主题：" + "、".join(detected_themes[:5]))
    if source_blockers:
        relation_parts.append("仍有源数据阻塞：" + "、".join(source_blockers))

    return {
        "mainline": _story_mainline(leaders=leaders, index_summary=index_summary, detected_themes=detected_themes),
        "market_environment": market_environment,
        "portfolio_attribution": _portfolio_attribution_text(leaders=leaders, laggards=laggards),
        "event_evidence": event_text,
        "negative_signals": _names(laggards) or "暂未从快照差分中识别明显拖累项。",
        "portfolio_relation": "；".join(relation_parts) or "本周组合关系仍需要更多指数、事件和知识库证据。",
        "next_validation": _next_validation_text(leaders=leaders, laggards=laggards, source_blockers=source_blockers),
        "data_gaps": context_warnings[:5],
        "claims": claims,
    }


def _story_mainline(leaders: list[dict[str, Any]], index_summary: list[dict[str, Any]], detected_themes: list[str]) -> str:
    pieces: list[str] = []
    if detected_themes:
        pieces.append("主题上以 " + "、".join(detected_themes[:3]) + " 为主")
    if index_summary:
        strongest = max(index_summary, key=lambda item: _number(item.get("weekly_change_pct")))
        pieces.append(f"市场代理中 {strongest.get('name')} 最强({_fmt_signed_percent(strongest.get('weekly_change_pct'))})")
    if leaders:
        pieces.append("组合贡献来自 " + _names(leaders[:3]))
    return "；".join(pieces) if pieces else "本周缺少足够快照和市场证据，暂不归纳主线。"


def _portfolio_attribution_text(leaders: list[dict[str, Any]], laggards: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if leaders:
        parts.append("高光：" + "、".join(f"{item['name']} {_fmt_money(_rank_amount(item), item.get('currency'))}" for item in leaders[:3]))
    if laggards:
        parts.append("拖累：" + "、".join(f"{item['name']} {_fmt_money(_rank_amount(item), item.get('currency'))}" for item in laggards[:3]))
    return "；".join(parts) if parts else "组合归因需要至少两端快照或交易记录。"


def _event_story_text(
    event_summary: list[dict[str, Any]],
    knowledge_evidence: list[dict[str, Any]],
    source_blockers: list[str],
) -> str:
    parts: list[str] = []
    if event_summary:
        event = event_summary[0]
        event_date = _date_from_any(event.get("published_at"))
        freshness = {
            "review_week": "本周材料",
            "nearest_prior": "近前材料",
            "undated_source": "未标日期材料",
            "future_or_next_window": "后续窗口材料",
            "reference_source": "公司披露入口",
        }.get(str(event.get("freshness")), str(event.get("freshness") or "材料"))
        date_suffix = f"（{event_date.isoformat()}）" if event_date else ""
        parts.append(f"{freshness}{date_suffix}：{event.get('source_name')}《{event.get('title')}》")
    if knowledge_evidence:
        evidence = knowledge_evidence[0]
        parts.append(f"本地知识：{evidence.get('summary')}")
    if source_blockers:
        parts.append("仍阻塞：" + "、".join(source_blockers))
    return "；".join(parts) if parts else "公司公告/财报、主题新闻和本地知识均未形成可引用证据。"


def _next_validation_text(
    leaders: list[dict[str, Any]],
    laggards: list[dict[str, Any]],
    source_blockers: list[str],
) -> str:
    names = [f"{item['name']} {item['code']}" for item in [*leaders[:2], *laggards[:2]]]
    parts = []
    if names:
        parts.append("验证 " + "、".join(names) + " 的贡献/拖累逻辑是否延续")
    if source_blockers:
        parts.append("补齐 " + "、".join(source_blockers) + " 源数据后重新生成故事")
    return "；".join(parts) if parts else "下周继续积累快照、交易、指数和事件证据。"


def save_weekly_review_report(context: dict[str, Any], markdown: str) -> dict[str, Any]:
    period = context["period"]
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
    lines = [
        f"- 主线：{story.get('mainline') or '待观察'}",
        f"- 市场环境：{story.get('market_environment') or '待观察'}",
        f"- 组合归因：{story.get('portfolio_attribution') or '待观察'}",
        f"- 事件/主题证据：{story.get('event_evidence') or '待补'}",
        f"- 负向信号：{story.get('negative_signals') or '待观察'}",
        f"- 和我组合的关系：{story.get('portfolio_relation') or '待观察'}",
        f"- 下周验证点：{story.get('next_validation') or '待观察'}",
    ]
    claims = story.get("claims") or []
    if claims:
        lines.extend(["", "证据链："])
        for claim in claims[:6]:
            citations = "；".join(str(item) for item in claim.get("citations") or [])
            suffix = f"（来源：{citations}）" if citations else ""
            lines.append(f"- {claim.get('type', '观察')}：{claim.get('text', '')}{suffix}")
    return lines


def _render_index_summary(items: list[dict[str, Any]], status: dict[str, Any] | None) -> list[str]:
    lines: list[str] = []
    if status and status.get("status") in {"provider_unavailable", "source_blocked"}:
        reason = status.get("reason") or "指数数据暂时不可用"
        lines.append(f"- 指数源状态：{_status_text(status)}。{reason}")
    if not items:
        return lines or ["- 指数数据已检查但暂无可用行情，本周不做指数归因。"]
    lines.extend(
        [
            "| 指数 | 市场 | 本周涨跌 | 最大单日波动 | 市场环境 | 对组合影响 |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for item in items:
        move = item.get("largest_daily_move") or {}
        move_text = (
            f"{move.get('date')} {_fmt_signed_percent(move.get('change_pct'))}"
            if move.get("date")
            else "待补"
        )
        lines.append(
            f"| {item.get('name')} | {item.get('market')} | {_fmt_signed_percent(item.get('weekly_change_pct'))} | "
            f"{move_text} | {item.get('environment_label') or '待观察'} | {item.get('portfolio_relevance') or '待观察'} |"
        )
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


def _render_holder_attribution(cards: list[dict[str, Any]]) -> list[str]:
    if not cards:
        return ["- 暂无持仓归因卡。"]
    lines: list[str] = []
    for card in cards:
        lines.extend(
            [
                f"### 持仓归因卡：{card.get('code')} {card.get('name')}",
                "",
                (
                    f"- 本周影响：{_fmt_money(card.get('weekly_pl'), card.get('currency'))}；"
                    f"{card.get('movement') or '仓位变化待确认'}；"
                    f"归因置信度：position {card.get('position_confidence') or '待确认'} / cause {card.get('confidence') or 'low'}"
                ),
                f"- 归因判断：{card.get('attribution_verdict') or 'unexplained'}",
                f"- Thesis impact：{card.get('thesis_impact') or 'needs_research'}",
                "- 可能原因：",
            ]
        )
        candidates = card.get("cause_candidates") or []
        if candidates:
            for index, candidate in enumerate(candidates, start=1):
                lines.append(f"  {index}. {candidate.get('title') or candidate.get('lens') or 'Cause candidate'}")
                lines.append(f"     - Evidence: {_candidate_evidence_text(candidate)}")
                lines.append(
                    f"     - Confidence: {candidate.get('confidence') or 'low'}；"
                    f"Thesis impact: {candidate.get('thesis_impact') or 'needs_research'}；"
                    f"Nature: {candidate.get('observed_inferred_unverified') or 'inferred'}"
                )
                lines.append(f"     - Next validation: {candidate.get('next_validation') or '待补'}")
        else:
            lines.append("  1. No supported cause found from current structured sources.")
        source_gaps = card.get("source_gaps") or []
        if source_gaps:
            lines.append("- Source gaps:")
            for gap in source_gaps:
                lines.append(f"  - {gap}")
        thesis = card.get("thesis_relationship")
        if thesis:
            lines.append(f"- 和我的逻辑关系：{thesis}")
        validations = card.get("next_validation") or []
        if validations:
            lines.append("- 下周验证点：" + "；".join(str(item) for item in validations))
        lines.append("")
    return lines


def _candidate_evidence_text(candidate: dict[str, Any]) -> str:
    pieces = [
        str(candidate.get("source_type") or "source"),
        str(candidate.get("source_name") or ""),
        str(candidate.get("source_date") or ""),
    ]
    source = " / ".join(piece for piece in pieces if piece)
    link = candidate.get("url") or candidate.get("source_id")
    evidence = str(candidate.get("evidence") or candidate.get("claim") or "").strip()
    link_text = f" / {link}" if link else ""
    return f"{source}{link_text}；{evidence}".strip("；")


def _render_source_status(source_status: dict[str, Any]) -> list[str]:
    return [
        f"- 账户快照：{_status_text(source_status.get('account_snapshots'))}",
        f"- 交易记录：{_status_text(source_status.get('trades'))}",
        f"- 当前持仓：{_status_text(source_status.get('positions'))}",
        f"- 指数：{_status_text(source_status.get('indexes'))}",
        f"- 外部事件：{_status_text(source_status.get('events'))}",
        f"- 本地知识：{_status_text(source_status.get('local_knowledge'))}",
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
        item["records"].append(trade)
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
        "records": [],
    }


def _estimate_period_pl(
    start: dict[str, Any] | None,
    end: dict[str, Any] | None,
    trade_summary: dict[str, Any],
) -> dict[str, Any]:
    """Approximate Futu interval P/L using realized sells plus unrealized P/L delta."""
    start_pl = start["pl_val"] if start else 0.0
    end_pl = end["pl_val"] if end else 0.0
    snapshot_delta = end_pl - start_pl
    realized_result = _estimate_realized_pl(start=start, trades=trade_summary.get("records") or [])
    if realized_result["usable"]:
        return {
            "amount": snapshot_delta + realized_result["realized_pl"],
            "realized_pl": realized_result["realized_pl"],
            "method": "realized_plus_snapshot_delta",
        }
    if end is None and start is not None:
        return {
            "amount": start_pl,
            "realized_pl": 0.0,
            "method": "closed_position_start_pl_fallback",
        }
    return {
        "amount": snapshot_delta,
        "realized_pl": 0.0,
        "method": "snapshot_pl_delta",
    }


def _estimate_realized_pl(start: dict[str, Any] | None, trades: list[dict[str, Any]]) -> dict[str, Any]:
    qty = _number(start.get("qty")) if start else 0.0
    cost_price = _optional_number(start.get("cost_price")) if start else None
    total_cost = qty * cost_price if cost_price is not None else 0.0
    realized_pl = 0.0
    usable = False

    for trade in sorted(trades, key=_trade_sort_key):
        side = str(trade.get("trd_side") or "").lower()
        trade_qty = abs(_number(trade.get("qty")))
        price = _optional_number(trade.get("price"))
        amount = abs(_number(trade.get("amount")))
        if trade_qty <= 0:
            continue
        if price is None and amount <= 0:
            continue
        trade_amount = amount if amount > 0 else trade_qty * float(price)
        if "buy" in side or "买" in side:
            qty += trade_qty
            total_cost += trade_amount
        elif "sell" in side or "卖" in side:
            if qty <= 0:
                continue
            avg_cost = total_cost / qty if total_cost > 0 else (float(cost_price) if cost_price is not None else 0.0)
            realized_pl += trade_amount - avg_cost * trade_qty
            cost_to_remove = avg_cost * min(qty, trade_qty)
            qty -= trade_qty
            total_cost = max(0.0, total_cost - cost_to_remove)
            if qty <= 0:
                qty = 0.0
                total_cost = 0.0
            usable = True

    return {"realized_pl": realized_pl, "usable": usable}


def _trade_sort_key(trade: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(trade.get("trade_date") or ""),
        str(trade.get("create_time") or ""),
        int(trade.get("id") or 0),
    )


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
    return _number(item.get("period_pl", item.get("pl_val_delta")))


def _status_labels(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    if item["current_market_val"] > 0 and item.get("themes"):
        labels.append("核心持仓")
    if _rank_amount(item) > 0:
        labels.append("强势贡献")
    if _rank_amount(item) < 0:
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
        return "缺失"
    status = item.get("status") or "unknown"
    label = SOURCE_STATUS_LABELS.get(str(status), str(status))
    count = item.get("count")
    reason = item.get("reason")
    missing = item.get("missing")
    suffixes: list[str] = []
    if count is not None:
        suffixes.append(f"{count} 条")
    if missing:
        if isinstance(missing, list):
            suffixes.append("缺少 " + "、".join(str(value) for value in missing[:4]))
        else:
            suffixes.append(f"缺少 {missing}")
    if reason:
        suffixes.append(str(reason))
    return "，".join([label, *suffixes])


def _fmt_money(value: Any, currency: str | None = None) -> str:
    number = _number(value)
    suffix = f" {currency}" if currency and currency != "UNKNOWN" else ""
    return f"{number:,.2f}{suffix}"


def _fmt_ratio_suffix(value: Any) -> str:
    ratio = _optional_ratio(value)
    if ratio is None:
        return ""
    return f" / {ratio * 100:.2f}%"


def _fmt_signed_percent(value: Any) -> str:
    number = _number(value)
    return f"{number:+.2f}%"


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
