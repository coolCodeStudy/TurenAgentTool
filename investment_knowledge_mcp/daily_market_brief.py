from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
from threading import Event
from typing import Any, Callable
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.market_data_provider import (
    MarketBarSnapshot,
    MarketDataProviderError,
    get_yahoo_market_bars,
)


SG_TZ = ZoneInfo("Asia/Singapore")


@dataclass(frozen=True)
class DailyMarketBriefResult:
    context: dict[str, Any]
    markdown: str
    saved_report: dict[str, Any] | None = None


@dataclass(frozen=True)
class MarketConfig:
    code: str
    display_name: str
    timezone: ZoneInfo
    close_time: time
    index_metric_label: str
    index_configs: tuple[dict[str, str], ...]


MARKET_CONFIGS: dict[str, MarketConfig] = {
    "CN": MarketConfig(
        code="CN",
        display_name="A股",
        timezone=ZoneInfo("Asia/Shanghai"),
        close_time=time(hour=15, minute=30),
        index_metric_label="成交量",
        index_configs=(
            {"code": "SH.000001", "name": "Shanghai Composite"},
            {"code": "SZ.399001", "name": "Shenzhen Component"},
            {"code": "SH.000300", "name": "CSI 300"},
            {"code": "SZ.399006", "name": "ChiNext Index"},
            {"code": "SH.000688", "name": "STAR 50"},
        ),
    ),
    "HK": MarketConfig(
        code="HK",
        display_name="港股",
        timezone=ZoneInfo("Asia/Hong_Kong"),
        close_time=time(hour=16, minute=30),
        index_metric_label="成交量",
        index_configs=(
            {"code": "HK.HSI", "name": "Hang Seng Index"},
            {"code": "HK.HSTECH", "name": "Hang Seng TECH Index"},
            {"code": "HK.HSCEI", "name": "Hang Seng China Enterprises Index"},
        ),
    ),
    "US": MarketConfig(
        code="US",
        display_name="美股",
        timezone=ZoneInfo("America/New_York"),
        close_time=time(hour=16, minute=30),
        index_metric_label="成交量",
        index_configs=(
            {"code": "US.SPX", "name": "S&P 500"},
            {"code": "US.IXIC", "name": "Nasdaq Composite"},
            {"code": "US.DJI", "name": "Dow Jones Industrial Average"},
            {"code": "US.RUT", "name": "Russell 2000"},
        ),
    ),
}

CAPITAL_FLOW_DEGRADED_COPY = "配置的数据源未提供本市场/本交易日的明确资金流指标；本简报其余部分已基于可用行情数据生成。"
INDEX_PROVIDER_DEGRADED_COPY = "核心指数数据源本次未返回可用行情；本简报已保留其他可用数据和数据缺口说明。"
INDEX_PROVIDER_PARTIAL_COPY = "核心指数数据不完整；缺失指数已在数据状态中列出。"
SOURCE_STATUS_LABELS = {
    "indexes": "核心指数",
    "sectors": "行业/板块",
    "gainers": "个股涨幅榜",
    "capital_flow": "资金流",
    "session": "交易日状态",
}
SOURCE_STATE_LABELS = {
    "ok": "可用",
    "partial": "部分可用",
    "missing": "暂不可用",
    "provider_unavailable": "数据源暂不可用",
    "not_available": "暂不提供",
    "no_session": "休市",
}
_SCHEDULER_STATE: dict[str, Any] = {
    "started": False,
    "interval_seconds": None,
    "markets": [],
    "last_attempted": {},
}


MarketBarLoader = Callable[[list[str], str, str], MarketBarSnapshot]
ActivityProvider = Callable[[str, date], dict[str, Any]]


def build_daily_market_brief(
    market: str,
    market_date: date | None = None,
    *,
    save: bool = True,
    now: datetime | None = None,
    market_bar_loader: MarketBarLoader | None = None,
    activity_provider: ActivityProvider | None = None,
    use_fixture: bool = False,
) -> DailyMarketBriefResult:
    context = build_daily_market_brief_context(
        market=market,
        market_date=market_date,
        now=now,
        market_bar_loader=market_bar_loader,
        activity_provider=activity_provider,
        use_fixture=use_fixture,
    )
    markdown = render_daily_market_brief_markdown(context)
    saved_report = save_daily_market_brief_report(context=context, markdown=markdown) if save else None
    return DailyMarketBriefResult(context=context, markdown=markdown, saved_report=saved_report)


def build_daily_market_brief_context(
    market: str,
    market_date: date | None = None,
    *,
    now: datetime | None = None,
    market_bar_loader: MarketBarLoader | None = None,
    activity_provider: ActivityProvider | None = None,
    use_fixture: bool = False,
) -> dict[str, Any]:
    config = _market_config(market)
    resolved_date = market_date or resolve_latest_completed_session_date(config.code, now=now)
    generated_at = now or datetime.now(SG_TZ)
    local_generated_at = generated_at.astimezone(config.timezone)
    sg_generated_at = generated_at.astimezone(SG_TZ)
    source_status: dict[str, Any] = {
        "indexes": {"status": "missing", "provider": "yahoo_chart", "count": 0},
        "sectors": {
            "status": "provider_unavailable",
            "provider": "not_configured",
            "taxonomy": "provider_native",
            "count": 0,
            "message": "当前仓库没有配置可覆盖全市场行业/板块涨幅排行的数据源。",
        },
        "gainers": {
            "status": "provider_unavailable",
            "provider": "not_configured",
            "count": 0,
            "message": "当前仓库没有配置可覆盖全市场普通股流动性筛选和涨幅排行的数据源。",
        },
        "capital_flow": {
            "status": "not_available",
            "provider": "not_configured",
            "count": 0,
            "message": CAPITAL_FLOW_DEGRADED_COPY,
        },
    }
    warnings: list[str] = []

    no_session = _is_weekend(resolved_date)
    if no_session:
        source_status["session"] = {
            "status": "no_session",
            "reason": "weekend",
            "message": "周末无常规交易日；未生成市场涨跌叙事。",
        }
        indexes: list[dict[str, Any]] = []
        activity = _empty_activity(config.code)
    else:
        index_loader = market_bar_loader
        if index_loader is None:
            index_loader = _fixture_market_bar_loader if use_fixture else get_yahoo_market_bars
        indexes = _load_index_rows(
            config=config,
            market_date=resolved_date,
            source_status=source_status,
            warnings=warnings,
            market_bar_loader=index_loader,
        )
        provider = activity_provider or (_fixture_activity_provider if use_fixture else _empty_activity_provider)
        activity = provider(config.code, resolved_date)
        _merge_activity_status(source_status, activity)

    narrative = _build_narrative(
        config=config,
        market_date=resolved_date,
        indexes=indexes,
        sectors=activity.get("sectors") or [],
        gainers=activity.get("gainers") or [],
        flow=activity.get("capital_flow") or [],
        source_status=source_status,
        no_session=no_session,
    )

    return {
        "market": {
            "code": config.code,
            "name": config.display_name,
            "timezone": str(config.timezone),
            "close_time": config.close_time.strftime("%H:%M"),
        },
        "market_date": resolved_date.isoformat(),
        "generated_at": {
            "market_local": local_generated_at.isoformat(),
            "asia_singapore": sg_generated_at.isoformat(),
        },
        "source_status": source_status,
        "warnings": warnings,
        "indexes": indexes,
        "sectors": activity.get("sectors") or [],
        "gainers": activity.get("gainers") or [],
        "capital_flow": activity.get("capital_flow") or [],
        "narrative": narrative,
        "no_session": no_session,
        "provider_mode": "fixture" if use_fixture else "live",
    }


def save_daily_market_brief_report(context: dict[str, Any], markdown: str) -> dict[str, Any]:
    market = context["market"]["code"]
    market_date = context["market_date"]
    return repository.upsert_daily_market_brief_report(
        market=market,
        market_date=market_date,
        summary=markdown,
        context=context,
        source_status=context.get("source_status") or {},
        story={
            "narrative": context.get("narrative") or "",
            "no_session": bool(context.get("no_session")),
            "provider_mode": context.get("provider_mode"),
            "generated_at": context.get("generated_at") or {},
        },
    )


def get_daily_market_brief_report(market: str, market_date: date | str | None = None) -> dict[str, Any] | None:
    config = _market_config(market)
    if market_date is None:
        return repository.get_latest_daily_market_brief_report(market=config.code)
    parsed = _coerce_date(market_date)
    return repository.get_daily_market_brief_report(market=config.code, market_date=parsed.isoformat())


def run_daily_market_brief_once(
    market: str,
    market_date: date | None = None,
    *,
    save: bool = True,
    use_fixture: bool = False,
    logger: logging.Logger | None = None,
) -> DailyMarketBriefResult:
    logger = logger or logging.getLogger("investment_knowledge_mcp.daily_market_brief")
    result = build_daily_market_brief(market=market, market_date=market_date, save=save, use_fixture=use_fixture)
    logger.info(
        "daily market brief generated: market=%s date=%s saved_id=%s",
        result.context["market"]["code"],
        result.context["market_date"],
        (result.saved_report or {}).get("id"),
    )
    return result


def run_daily_market_brief_scheduler_forever(
    markets: list[str] | None = None,
    *,
    interval_seconds: int = 300,
    logger: logging.Logger | None = None,
) -> None:
    logger = logger or logging.getLogger("investment_knowledge_mcp.daily_market_brief")
    selected_markets = [_market_config(item).code for item in (markets or ["CN", "HK", "US"])]
    interval = max(60, interval_seconds)
    _SCHEDULER_STATE.update(
        {
            "started": True,
            "interval_seconds": interval,
            "markets": selected_markets,
            "last_attempted": {},
        }
    )
    logger.info("Daily market brief scheduler started: markets=%s interval_seconds=%s", selected_markets, interval)
    while True:
        now = datetime.now(SG_TZ)
        for market_code in selected_markets:
            session_date = resolve_latest_completed_session_date(market_code, now=now)
            last_attempted = _SCHEDULER_STATE["last_attempted"].get(market_code)
            if should_run_daily_market_brief(market_code, now=now, last_attempted_date=last_attempted):
                try:
                    run_daily_market_brief_once(market=market_code, market_date=session_date, logger=logger)
                    _SCHEDULER_STATE["last_attempted"][market_code] = session_date.isoformat()
                except Exception:
                    logger.exception("Daily market brief scheduler failed: market=%s", market_code)
        Event().wait(interval)


def get_daily_market_brief_scheduler_state() -> dict[str, Any]:
    return dict(_SCHEDULER_STATE)


def should_run_daily_market_brief(
    market: str,
    *,
    now: datetime | None = None,
    last_attempted_date: date | str | None = None,
) -> bool:
    config = _market_config(market)
    current = (now or datetime.now(SG_TZ)).astimezone(config.timezone)
    if current.time() < config.close_time:
        return False
    if _is_weekend(current.date()):
        return False
    attempted = _coerce_date(last_attempted_date) if last_attempted_date else None
    return attempted != current.date()


def resolve_latest_completed_session_date(market: str, *, now: datetime | None = None) -> date:
    config = _market_config(market)
    current = (now or datetime.now(SG_TZ)).astimezone(config.timezone)
    session_date = current.date()
    if current.time() < config.close_time:
        session_date = _previous_weekday(session_date)
    if _is_weekend(session_date):
        session_date = _previous_weekday(session_date)
    return session_date


def render_daily_market_brief_markdown(context: dict[str, Any]) -> str:
    market = context["market"]
    market_date = context["market_date"]
    generated_at = context["generated_at"]
    lines = [
        f"# 每日市场简报｜{market['name']}（{market['code']}）｜{market_date}",
        "",
        f"- 市场日期：{market_date}（{market['timezone']}）",
        f"- 生成时间：{generated_at['market_local']} / 新加坡 {generated_at['asia_singapore']}",
        f"- 数据模式：{context.get('provider_mode') or 'live'}",
        "",
        "## 一句话总结",
        context.get("narrative") or "暂无可用叙事。",
    ]
    if context.get("no_session"):
        lines.extend(["", "## 休市状态", "- 周末或无常规交易日，未生成市场涨跌叙事。"])
        return "\n".join(lines)

    lines.extend(["", "## 核心指数"])
    lines.extend(_render_index_table(context.get("indexes") or []))
    lines.extend(["", "## 行业/板块涨幅榜"])
    lines.extend(_render_rank_table(context.get("sectors") or [], empty="配置的数据源暂不支持本市场行业/板块涨幅榜。"))
    lines.extend(["", "## 个股涨幅榜"])
    lines.extend(_render_rank_table(context.get("gainers") or [], empty="配置的数据源暂不支持本市场普通股流动性筛选后的涨幅榜。"))
    lines.extend(["", "## 资金流"])
    flow = context.get("capital_flow") or []
    if flow:
        lines.extend(_render_rank_table(flow, empty=CAPITAL_FLOW_DEGRADED_COPY))
    else:
        lines.append(f"- {CAPITAL_FLOW_DEGRADED_COPY}")
    lines.extend(["", "## 数据状态"])
    for key, status in (context.get("source_status") or {}).items():
        raw_label = status.get("status", "unknown") if isinstance(status, dict) else str(status)
        label = SOURCE_STATE_LABELS.get(raw_label, raw_label)
        provider = status.get("provider") if isinstance(status, dict) else None
        message = status.get("message") if isinstance(status, dict) else None
        name = SOURCE_STATUS_LABELS.get(key, key)
        provider_text = f"，来源：{provider}" if provider else ""
        message_text = f"：{message}" if message else ""
        lines.append(f"- {name}：{label}{provider_text}{message_text}")
    lines.append("")
    lines.append("注：本简报只描述市场结构、流动性和数据缺口，不构成买卖建议。")
    return "\n".join(lines)


def _load_index_rows(
    *,
    config: MarketConfig,
    market_date: date,
    source_status: dict[str, Any],
    warnings: list[str],
    market_bar_loader: MarketBarLoader,
) -> list[dict[str, Any]]:
    codes = [item["code"] for item in config.index_configs]
    start = (market_date - timedelta(days=45)).isoformat()
    end = market_date.isoformat()
    try:
        snapshot = market_bar_loader(codes, start, end)
    except MarketDataProviderError:
        source_status["indexes"] = {
            "status": "provider_unavailable",
            "provider": "yahoo_chart",
            "count": 0,
            "message": INDEX_PROVIDER_DEGRADED_COPY,
        }
        warnings.append(INDEX_PROVIDER_DEGRADED_COPY)
        return []
    except Exception:
        source_status["indexes"] = {
            "status": "provider_unavailable",
            "provider": "yahoo_chart",
            "count": 0,
            "message": INDEX_PROVIDER_DEGRADED_COPY,
        }
        warnings.append(INDEX_PROVIDER_DEGRADED_COPY)
        return []

    rows: list[dict[str, Any]] = []
    for index_config in config.index_configs:
        bars = sorted(snapshot.bars_by_code.get(index_config["code"], []), key=lambda item: str(item.get("date") or ""))
        row = _index_row(index_config=index_config, bars=bars, market_date=market_date, metric_label=config.index_metric_label)
        if row is not None:
            rows.append(row)
    index_status = "ok" if len(rows) == len(config.index_configs) else ("partial" if rows else "missing")
    source_status["indexes"] = {
        "status": index_status,
        "provider": snapshot.source,
        "count": len(rows),
        "fetched_at": snapshot.fetched_at.isoformat(),
        "missing": [item["code"] for item in config.index_configs if item["code"] not in {row["code"] for row in rows}],
    }
    if index_status == "partial":
        source_status["indexes"]["message"] = INDEX_PROVIDER_PARTIAL_COPY
    elif index_status == "missing":
        source_status["indexes"]["message"] = INDEX_PROVIDER_DEGRADED_COPY
    return rows


def _index_row(index_config: dict[str, str], bars: list[dict[str, Any]], market_date: date, metric_label: str) -> dict[str, Any] | None:
    latest_index = None
    for idx, bar in enumerate(bars):
        try:
            bar_date = date.fromisoformat(str(bar.get("date")))
        except ValueError:
            continue
        if bar_date <= market_date:
            latest_index = idx
    if latest_index is None:
        return None
    latest = bars[latest_index]
    prior_bars = bars[:latest_index]
    previous = prior_bars[-1] if prior_bars else None
    close = _number(latest.get("close"))
    previous_close = _number(previous.get("close")) if previous else None
    change_pct = None
    if close is not None and previous_close not in (None, 0):
        change_pct = (close - previous_close) / previous_close * 100
    latest_volume = _number(latest.get("volume"))
    prior_volumes = [_number(item.get("volume")) for item in prior_bars if _number(item.get("volume")) is not None]
    return {
        "code": index_config["code"],
        "name": index_config["name"],
        "date": latest.get("date"),
        "close": close,
        "change_pct": change_pct,
        "volume": latest_volume,
        "metric_label": metric_label,
        "baseline": {
            "previous": prior_volumes[-1] if prior_volumes else None,
            "avg_5": _average(prior_volumes[-5:]),
            "avg_20": _average(prior_volumes[-20:]),
            "history_count": len(prior_volumes),
            "state_5": "ok" if len(prior_volumes) >= 5 else "partial_history",
            "state_20": "ok" if len(prior_volumes) >= 20 else "partial_history",
        },
        "provider": (latest.get("raw") or {}).get("provider_symbol") or "unknown",
    }


def _build_narrative(
    *,
    config: MarketConfig,
    market_date: date,
    indexes: list[dict[str, Any]],
    sectors: list[dict[str, Any]],
    gainers: list[dict[str, Any]],
    flow: list[dict[str, Any]],
    source_status: dict[str, Any],
    no_session: bool,
) -> str:
    if no_session:
        return f"{config.display_name} {market_date.isoformat()} 无常规交易日，本次只记录休市状态。"
    index_moves = [item for item in indexes if item.get("change_pct") is not None]
    if index_moves:
        best = max(index_moves, key=lambda item: item["change_pct"])
        worst = min(index_moves, key=lambda item: item["change_pct"])
        move_text = f"核心指数中 {best['name']} 表现最强（{_fmt_pct(best['change_pct'])}），{worst['name']} 相对偏弱（{_fmt_pct(worst['change_pct'])}）。"
    else:
        move_text = "核心指数数据暂不完整，无法形成完整涨跌判断。"
    leadership = f"板块线索集中在 {sectors[0]['name']}。" if sectors else "板块/行业涨幅榜数据暂不可用，不能据此判断市场宽度。"
    gainer_text = f"个股涨幅榜首为 {gainers[0]['name']}（{_fmt_pct(gainers[0].get('change_pct'))}）。" if gainers else "普通股涨幅榜数据暂不可用。"
    flow_text = f"资金流线索显示 {flow[0]['name']} 居前。" if flow else CAPITAL_FLOW_DEGRADED_COPY
    liquidity_text = _liquidity_sentence(indexes)
    gap_keys = [
        key
        for key, status in source_status.items()
        if isinstance(status, dict) and status.get("status") in {"provider_unavailable", "not_available", "missing", "partial"}
    ]
    gap_labels = [SOURCE_STATUS_LABELS.get(key, key) for key in gap_keys]
    gap_text = f"需要注意的数据缺口：{'、'.join(gap_labels)}。" if gap_labels else "主要数据源状态正常。"
    return " ".join([move_text, leadership, gainer_text, liquidity_text, flow_text, gap_text])


def _liquidity_sentence(indexes: list[dict[str, Any]]) -> str:
    rows = [item for item in indexes if item.get("volume") is not None and item.get("baseline", {}).get("avg_20")]
    if not rows:
        return "成交量/成交额历史基线不足，流动性判断保持保守。"
    row = rows[0]
    ratio = row["volume"] / row["baseline"]["avg_20"] if row["baseline"]["avg_20"] else None
    if ratio is None:
        return "成交量/成交额历史基线不足，流动性判断保持保守。"
    return f"{row['name']} 当日{row.get('metric_label', '成交量')}约为 20 日均值的 {ratio:.2f} 倍。"


def _merge_activity_status(source_status: dict[str, Any], activity: dict[str, Any]) -> None:
    status = activity.get("source_status") or {}
    for key in ("sectors", "gainers", "capital_flow"):
        if key in status:
            source_status[key] = status[key]


def _empty_activity_provider(market: str, market_date: date) -> dict[str, Any]:
    return _empty_activity(market)


def _empty_activity(market: str) -> dict[str, Any]:
    return {
        "sectors": [],
        "gainers": [],
        "capital_flow": [],
        "source_status": {
            "sectors": {
                "status": "provider_unavailable",
                "provider": "not_configured",
                "taxonomy": "provider_native",
                "count": 0,
                "message": "当前仓库没有配置可覆盖全市场行业/板块涨幅排行的数据源。",
            },
            "gainers": {
                "status": "provider_unavailable",
                "provider": "not_configured",
                "count": 0,
                "message": "当前仓库没有配置可覆盖全市场普通股流动性筛选和涨幅排行的数据源。",
            },
            "capital_flow": {
                "status": "not_available",
                "provider": "not_configured",
                "count": 0,
                "message": CAPITAL_FLOW_DEGRADED_COPY,
            },
        },
    }


def _fixture_activity_provider(market: str, market_date: date) -> dict[str, Any]:
    market = _market_config(market).code
    sector_prefix = {"CN": "AI服务器链", "HK": "互联网医疗", "US": "Semiconductors"}[market]
    stock_prefix = {"CN": "沪深样本", "HK": "港股样本", "US": "US Sample"}[market]
    sectors = [
        {"rank": idx, "name": f"{sector_prefix}{idx}", "change_pct": 4.8 - idx * 0.4, "provider": "fixture", "taxonomy": "fixture_native"}
        for idx in range(1, 6)
    ]
    gainers = [
        {"rank": idx, "code": f"{market}.F{idx:03d}", "name": f"{stock_prefix}{idx}", "change_pct": 9.5 - idx * 0.5, "turnover": 1000000 * idx, "provider": "fixture"}
        for idx in range(1, 6)
    ]
    flow = [] if market == "US" else [
        {"rank": idx, "name": f"{sector_prefix}资金{idx}", "flow_value": 50000000 - idx * 1000000, "provider": "fixture", "metric": "fixture_explicit_flow"}
        for idx in range(1, 6)
    ]
    flow_status = (
        {"status": "not_available", "provider": "fixture", "count": 0, "message": CAPITAL_FLOW_DEGRADED_COPY}
        if market == "US"
        else {"status": "ok", "provider": "fixture", "count": len(flow), "metric": "fixture_explicit_flow"}
    )
    return {
        "sectors": sectors,
        "gainers": gainers,
        "capital_flow": flow,
        "source_status": {
            "sectors": {"status": "ok", "provider": "fixture", "taxonomy": "fixture_native", "count": len(sectors)},
            "gainers": {"status": "ok", "provider": "fixture", "count": len(gainers)},
            "capital_flow": flow_status,
        },
    }


def _fixture_market_bar_loader(codes: list[str], start: str, end: str) -> MarketBarSnapshot:
    end_date = date.fromisoformat(end)
    start_date = date.fromisoformat(start)
    bars_by_code: dict[str, list[dict[str, Any]]] = {}
    for offset, code in enumerate(codes):
        bars: list[dict[str, Any]] = []
        current = start_date
        close = 1000.0 + offset * 25.0
        while current <= end_date:
            if current.weekday() < 5:
                close += 3.0 + offset
                bars.append(
                    {
                        "date": current.isoformat(),
                        "close": close,
                        "volume": 1000000 + len(bars) * 15000 + offset * 5000,
                        "raw": {"provider_symbol": f"fixture:{code}"},
                    }
                )
            current += timedelta(days=1)
        bars_by_code[code] = bars
    return MarketBarSnapshot(
        bars_by_code=bars_by_code,
        fetched_at=datetime(2026, 6, 30, 8, 0, tzinfo=ZoneInfo("UTC")),
        start=start,
        end=end,
        source="fixture_bars",
    )


def _render_index_table(indexes: list[dict[str, Any]]) -> list[str]:
    if not indexes:
        return ["- 暂无可用核心指数数据。"]
    lines = [
        "| 指数 | 收盘 | 涨跌幅 | 当日量 | 前一日 | 5日均值 | 20日均值 | 基线状态 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in indexes:
        baseline = item.get("baseline") or {}
        state = f"5日:{baseline.get('state_5')};20日:{baseline.get('state_20')}"
        lines.append(
            "| {name} | {close} | {change} | {volume} | {previous} | {avg5} | {avg20} | {state} |".format(
                name=item.get("name") or item.get("code"),
                close=_fmt_number(item.get("close")),
                change=_fmt_pct(item.get("change_pct")),
                volume=_fmt_number(item.get("volume")),
                previous=_fmt_number(baseline.get("previous")),
                avg5=_fmt_number(baseline.get("avg_5")),
                avg20=_fmt_number(baseline.get("avg_20")),
                state=state,
            )
        )
    return lines


def _render_rank_table(items: list[dict[str, Any]], *, empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    lines = ["| 排名 | 名称 | 代码/指标 | 涨跌幅/数值 | 来源 |", "| ---: | --- | --- | ---: | --- |"]
    for idx, item in enumerate(items[:5], start=1):
        metric = item.get("change_pct")
        if metric is None:
            metric = item.get("flow_value") or item.get("turnover")
            metric_text = _fmt_number(metric)
        else:
            metric_text = _fmt_pct(metric)
        lines.append(
            f"| {item.get('rank') or idx} | {item.get('name') or '-'} | {item.get('code') or item.get('metric') or '-'} | {metric_text} | {item.get('provider') or '-'} |"
        )
    return lines


def _market_config(market: str) -> MarketConfig:
    normalized = _normalize_market(market)
    if normalized not in MARKET_CONFIGS:
        raise ValueError("market must be one of CN, HK, US")
    return MARKET_CONFIGS[normalized]


def _normalize_market(market: str) -> str:
    text = str(market or "").strip().upper()
    aliases = {
        "A": "CN",
        "A股": "CN",
        "ASHARE": "CN",
        "A-SHARE": "CN",
        "A-SHARES": "CN",
        "沪深": "CN",
        "港股": "HK",
        "香港": "HK",
        "美股": "US",
        "美国": "US",
    }
    return aliases.get(text, text)


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _previous_weekday(value: date) -> date:
    current = value - timedelta(days=1)
    while _is_weekend(current):
        current -= timedelta(days=1)
    return current


def _is_weekend(value: date) -> bool:
    return value.weekday() >= 5


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    return sum(cleaned) / len(cleaned) if cleaned else None


def _fmt_pct(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "-"
    return f"{number:+.2f}%"


def _fmt_number(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "-"
    if abs(number) >= 100000000:
        return f"{number / 100000000:.2f}亿"
    if abs(number) >= 10000:
        return f"{number / 10000:.2f}万"
    return f"{number:.2f}"


def _setup_logging() -> logging.Logger:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return logging.getLogger("investment_knowledge_mcp.daily_market_brief")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily market brief generation or scheduler.")
    parser.add_argument("--once", action="store_true", help="Generate one brief and exit.")
    parser.add_argument("--market", choices=["CN", "HK", "US"], help="Market for --once.")
    parser.add_argument("--date", help="Market date for --once, YYYY-MM-DD.")
    parser.add_argument("--fixture", action="store_true", help="Use deterministic fixture activity data.")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Scheduler polling interval.")
    args = parser.parse_args()

    logger = _setup_logging()
    if args.once:
        if not args.market:
            raise SystemExit("--market is required with --once")
        result = run_daily_market_brief_once(
            market=args.market,
            market_date=date.fromisoformat(args.date) if args.date else None,
            use_fixture=args.fixture,
            logger=logger,
        )
        print(result.markdown)
        return
    run_daily_market_brief_scheduler_forever(interval_seconds=args.interval_seconds, logger=logger)


if __name__ == "__main__":
    main()
