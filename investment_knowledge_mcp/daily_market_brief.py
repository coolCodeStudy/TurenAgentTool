from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import importlib
import logging
from threading import Event
from typing import Any, Callable
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.daily_market_history import (
    HISTORICAL_MARKET_ACTIVITY_SOURCE,
    HistoricalActivityCancelled,
    HistoricalActivityProvider,
    HistoricalActivityResult,
    historical_market_activity_source,
    load_historical_market_activity,
)
from investment_knowledge_mcp.data_sources import (
    DataRequest,
    DataResult,
    DataSourcePool,
    DataStatus,
    SourceCapability,
    SourcePlan,
    default_market_bar_pool,
    market_bar_records_by_symbol,
)
from investment_knowledge_mcp.data_sources.market_activity import (
    ActivityFallbackRows,
    MarketActivitySource,
    default_market_activity_pool,
    load_activity_section,
    market_activity_plan,
    market_activity_sections,
)
from investment_knowledge_mcp.market_data_provider import (
    MarketBarSnapshot,
    MarketDataProviderError,
)


SG_TZ = ZoneInfo("Asia/Singapore")


@dataclass(frozen=True)
class DailyMarketBriefResult:
    context: dict[str, Any]
    markdown: str
    saved_report: dict[str, Any] | None = None


def list_daily_market_brief_dates(market: str, limit: int = 120) -> list[str]:
    return repository.list_daily_market_brief_dates(market=market.strip().upper(), limit=limit)


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
            {"code": "SH.000001", "name": "上证指数"},
            {"code": "SZ.399001", "name": "深证成指"},
            {"code": "SH.000300", "name": "沪深300"},
            {"code": "SZ.399006", "name": "创业板指"},
            {"code": "SH.000688", "name": "科创50"},
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
INDEX_DEGRADED_COPY = "核心指数数据源本次未返回可用行情；简报已保留其他可用部分和数据缺口提示。"
AKSHARE_PROVIDER = "akshare_eastmoney"
EASTMONEY_HTTP_PROVIDER = "eastmoney_http"
PUBLIC_HTTP_FALLBACK_PROVIDER = "public_http_fallback"
SINA_FINANCE_PROVIDER = "sina_finance"
LIVE_MARKET_ACTIVITY_SOURCE = "daily_market_activity"
CN_MIN_TURNOVER = 50_000_000
HK_MIN_TURNOVER = 20_000_000
US_MIN_TURNOVER = 10_000_000
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
    market_bar_pool: DataSourcePool | None = None,
    market_activity_pool: DataSourcePool | None = None,
    activity_provider: ActivityProvider | None = None,
    historical_activity_provider: HistoricalActivityProvider | None = None,
    use_fixture: bool = False,
) -> DailyMarketBriefResult:
    context = build_daily_market_brief_context(
        market=market,
        market_date=market_date,
        now=now,
        market_bar_loader=market_bar_loader,
        market_bar_pool=market_bar_pool,
        market_activity_pool=market_activity_pool,
        activity_provider=activity_provider,
        historical_activity_provider=historical_activity_provider,
        use_fixture=use_fixture,
    )
    markdown = render_daily_market_brief_markdown(context)
    if save:
        existing_report = get_daily_market_brief_report(
            context["market"]["code"], context["market_date"]
        )
        _validate_daily_market_brief_context_for_save(
            context, existing_report=existing_report
        )
        saved_report = save_daily_market_brief_report(context=context, markdown=markdown)
    else:
        saved_report = None
    return DailyMarketBriefResult(context=context, markdown=markdown, saved_report=saved_report)


def build_daily_market_brief_context(
    market: str,
    market_date: date | None = None,
    *,
    now: datetime | None = None,
    market_bar_loader: MarketBarLoader | None = None,
    market_bar_pool: DataSourcePool | None = None,
    market_activity_pool: DataSourcePool | None = None,
    activity_provider: ActivityProvider | None = None,
    historical_activity_provider: HistoricalActivityProvider | None = None,
    use_fixture: bool = False,
) -> dict[str, Any]:
    config = _market_config(market)
    generated_at = now or datetime.now(SG_TZ)
    latest_completed_session = resolve_latest_completed_session_date(config.code, now=generated_at)
    resolved_date = _coerce_date(market_date) if market_date is not None else latest_completed_session
    if resolved_date > latest_completed_session:
        current_market_date = generated_at.astimezone(config.timezone).date()
        if not (_is_weekend(resolved_date) and resolved_date <= current_market_date):
            raise ValueError(f"未来日期不可生成；最近已收盘交易日为 {latest_completed_session.isoformat()}。")
    generation_kind = "historical_reconstruction" if resolved_date < latest_completed_session else "live_rerun"
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
        index_loader = market_bar_loader or (_fixture_market_bar_loader if use_fixture else None)
        indexes = _load_index_rows(
            config=config,
            market_date=resolved_date,
            source_status=source_status,
            warnings=warnings,
            market_bar_loader=index_loader,
            market_bar_pool=(
                None
                if index_loader is not None
                else (market_bar_pool if market_bar_pool is not None else default_market_bar_pool())
            ),
            require_exact_date=generation_kind == "historical_reconstruction",
        )
        has_requested_session = any(row.get("date") == resolved_date.isoformat() for row in indexes)
        has_prior_session_evidence = bool(source_status.get("indexes", {}).get("prior_session_count"))
        if (indexes and not has_requested_session) or (
            generation_kind == "historical_reconstruction" and not indexes and has_prior_session_evidence
        ):
            no_session = True
            indexes = []
            source_status["session"] = {
                "status": "no_session",
                "reason": "provider_calendar",
                "message": "核心指数行情未确认该日期为常规交易日；未生成实时榜单和涨跌叙事。",
            }
            activity = _empty_activity(config.code)
        elif not indexes and not use_fixture:
            source_status["session"] = {
                "status": "unverified",
                "reason": "index_session_unavailable",
                "message": "核心指数行情未能确认该日期已完成交易；为避免混入错误日期的实时榜单，本次未生成榜单。",
            }
            activity = _empty_activity(config.code)
        elif generation_kind == "historical_reconstruction":
            provider = historical_activity_provider or (
                _fixture_historical_activity_provider if use_fixture else load_historical_market_activity
            )
            pool = (
                default_market_activity_pool(
                    MarketActivitySource(
                        HISTORICAL_MARKET_ACTIVITY_SOURCE,
                        lambda market, market_date: _historical_activity(
                            market,
                            market_date,
                            provider=provider,
                        ),
                        cancellation_exceptions=(HistoricalActivityCancelled,),
                    )
                )
                if historical_activity_provider is not None or use_fixture
                else (
                    market_activity_pool
                    if market_activity_pool is not None
                    else default_market_activity_pool(historical_market_activity_source())
                )
            )
            activity = _activity_from_pool(
                config.code,
                resolved_date,
                pool=pool,
                source_id=HISTORICAL_MARKET_ACTIVITY_SOURCE,
                freshness="historical_exact_date",
            )
            _merge_activity_status(source_status, activity)
            _attach_historical_session_provenance(source_status, resolved_date)
        else:
            provider = activity_provider or (_fixture_activity_provider if use_fixture else _akshare_activity_provider)
            pool = (
                default_market_activity_pool(
                    MarketActivitySource(LIVE_MARKET_ACTIVITY_SOURCE, provider)
                )
                if activity_provider is not None or use_fixture
                else (
                    market_activity_pool
                    if market_activity_pool is not None
                    else default_market_activity_pool(
                        MarketActivitySource(LIVE_MARKET_ACTIVITY_SOURCE, provider)
                    )
                )
            )
            activity = _activity_from_pool(
                config.code,
                resolved_date,
                pool=pool,
                source_id=LIVE_MARKET_ACTIVITY_SOURCE,
                freshness="session_close",
            )
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
        "generation_kind": generation_kind,
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
            "generation_kind": context.get("generation_kind"),
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
    lines.extend(_render_rank_table(context.get("sectors") or [], market=market["code"], empty="配置的数据源暂不支持本市场行业/板块涨幅榜。"))
    lines.extend(["", "## 个股涨幅榜"])
    lines.extend(_render_rank_table(context.get("gainers") or [], market=market["code"], empty="配置的数据源暂不支持本市场普通股流动性筛选后的涨幅榜。"))
    lines.extend(["", "## 资金流"])
    flow = context.get("capital_flow") or []
    if flow:
        lines.extend(_render_rank_table(flow, market=market["code"], empty=CAPITAL_FLOW_DEGRADED_COPY))
    else:
        lines.append(f"- {CAPITAL_FLOW_DEGRADED_COPY}")
    lines.extend(["", "## 数据状态"])
    for key, status in (context.get("source_status") or {}).items():
        label = _status_text(status)
        provider = _safe_provider_label(status.get("provider")) if isinstance(status, dict) else None
        message = _status_message(status) if isinstance(status, dict) else None
        provider_text = f"，来源：{provider}" if provider else ""
        message_text = f"：{message}" if message else ""
        lines.append(f"- {_source_label(key)}：{label}{provider_text}{message_text}")
    lines.append("")
    lines.append("注：本简报只描述市场结构、流动性和数据缺口，不构成买卖建议。")
    return "\n".join(lines)


def _load_index_rows(
    *,
    config: MarketConfig,
    market_date: date,
    source_status: dict[str, Any],
    warnings: list[str],
    market_bar_loader: MarketBarLoader | None = None,
    market_bar_pool: DataSourcePool | None = None,
    require_exact_date: bool = False,
) -> list[dict[str, Any]]:
    if (market_bar_loader is None) == (market_bar_pool is None):
        raise ValueError("exactly one market bar source path must be selected")
    codes = [item["code"] for item in config.index_configs]
    start = (market_date - timedelta(days=45)).isoformat()
    end = market_date.isoformat()
    if market_bar_loader is None:
        return _load_index_rows_from_pool(
            config=config,
            market_date=market_date,
            source_status=source_status,
            warnings=warnings,
            market_bar_pool=market_bar_pool,
            codes=codes,
            require_exact_date=require_exact_date,
        )
    try:
        snapshot = market_bar_loader(codes, start, end)
    except MarketDataProviderError as exc:
        source_status["indexes"] = {
            "status": "provider_unavailable",
            "provider": "yahoo_chart",
            "count": 0,
            "message": INDEX_DEGRADED_COPY,
            "detail_code": "provider_unavailable",
        }
        warnings.append(INDEX_DEGRADED_COPY)
        return []
    except Exception as exc:
        source_status["indexes"] = {
            "status": "provider_unavailable",
            "provider": "yahoo_chart",
            "count": 0,
            "message": INDEX_DEGRADED_COPY,
            "detail_code": type(exc).__name__,
        }
        warnings.append(INDEX_DEGRADED_COPY)
        return []

    candidate_rows: list[dict[str, Any]] = []
    for index_config in config.index_configs:
        bars = sorted(snapshot.bars_by_code.get(index_config["code"], []), key=lambda item: str(item.get("date") or ""))
        row = _index_row(index_config=index_config, bars=bars, market_date=market_date, metric_label=config.index_metric_label)
        if row is not None:
            candidate_rows.append(row)
    rows = [
        row for row in candidate_rows if not require_exact_date or row.get("date") == market_date.isoformat()
    ]
    source_status["indexes"] = {
        "status": "ok" if len(rows) == len(config.index_configs) else ("partial" if rows else "missing"),
        "provider": snapshot.source,
        "count": len(rows),
        "fetched_at": snapshot.fetched_at.isoformat(),
        "missing": [item["code"] for item in config.index_configs if item["code"] not in {row["code"] for row in rows}],
        "prior_session_count": sum(row.get("date") != market_date.isoformat() for row in candidate_rows),
    }
    return rows


def _load_index_rows_from_pool(
    *,
    config: MarketConfig,
    market_date: date,
    source_status: dict[str, Any],
    warnings: list[str],
    market_bar_pool: DataSourcePool,
    codes: list[str],
    require_exact_date: bool,
) -> list[dict[str, Any]]:
    request = DataRequest(
        capability=SourceCapability.MARKET_BARS,
        market=config.code,
        symbols=tuple(codes),
        start=market_date - timedelta(days=45),
        end=market_date,
        freshness="daily_market_brief",
    )
    plan = SourcePlan(
        capability=SourceCapability.MARKET_BARS,
        preferred_sources=("yahoo_chart",),
        allowed_sources=("yahoo_chart",),
        fallback_sources=(),
        required=True,
        partial_allowed=True,
    )
    result = market_bar_pool.fetch(request, plan)

    if not isinstance(result, DataResult):
        return _set_pool_index_unavailable(
            source_status=source_status,
            warnings=warnings,
            attempted_sources=[],
            selected_source=None,
            coverage=0.0,
            from_cache=False,
            failures=[_typed_failure("provider_contract_error", "yahoo_chart", retryable=False, fallback_allowed=False)],
        )

    failures = [_typed_failure_from_result(failure) for failure in result.failures]
    if result.status is DataStatus.UNAVAILABLE:
        return _set_pool_index_unavailable(
            source_status=source_status,
            warnings=warnings,
            attempted_sources=list(result.attempted_sources),
            selected_source=result.selected_source,
            coverage=result.coverage,
            from_cache=result.from_cache,
            failures=failures,
        )

    try:
        bars_by_code = market_bar_records_by_symbol(result)
    except ValueError:
        source_id = result.selected_source or (result.attempted_sources[-1] if result.attempted_sources else "yahoo_chart")
        failures.append(_typed_failure("provider_contract_error", source_id, retryable=False, fallback_allowed=False))
        return _set_pool_index_unavailable(
            source_status=source_status,
            warnings=warnings,
            attempted_sources=list(result.attempted_sources),
            selected_source=result.selected_source,
            coverage=0.0,
            from_cache=False,
            failures=failures,
        )

    try:
        candidate_rows: list[dict[str, Any]] = []
        for index_config in config.index_configs:
            bars = sorted(
                bars_by_code.get(index_config["code"], []),
                key=lambda item: str(item.get("date") or ""),
            )
            row = _index_row(
                index_config=index_config,
                bars=bars,
                market_date=market_date,
                metric_label=config.index_metric_label,
            )
            if row is not None:
                candidate_rows.append(row)
    except (AttributeError, TypeError, ValueError):
        source_id = result.selected_source or (result.attempted_sources[-1] if result.attempted_sources else "yahoo_chart")
        failures.append(_typed_failure("provider_contract_error", source_id, retryable=False, fallback_allowed=False))
        return _set_pool_index_unavailable(
            source_status=source_status,
            warnings=warnings,
            attempted_sources=list(result.attempted_sources),
            selected_source=result.selected_source,
            coverage=0.0,
            from_cache=False,
            failures=failures,
        )
    rows = [
        row for row in candidate_rows if not require_exact_date or row.get("date") == market_date.isoformat()
    ]
    source_status["indexes"] = {
        "status": "ok" if len(rows) == len(config.index_configs) else ("partial" if rows else "missing"),
        "provider": result.selected_source,
        "count": len(rows),
        "fetched_at": result.fetched_at.isoformat(),
        "missing": [item["code"] for item in config.index_configs if item["code"] not in {row["code"] for row in rows}],
        "prior_session_count": sum(row.get("date") != market_date.isoformat() for row in candidate_rows),
        "attempted_sources": list(result.attempted_sources),
        "selected_source": result.selected_source,
        "coverage": result.coverage,
        "from_cache": result.from_cache,
        "failures": failures,
    }
    return rows


def _set_pool_index_unavailable(
    *,
    source_status: dict[str, Any],
    warnings: list[str],
    attempted_sources: list[str],
    selected_source: str | None,
    coverage: float,
    from_cache: bool,
    failures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_status["indexes"] = {
        "status": "provider_unavailable",
        "provider": selected_source or "yahoo_chart",
        "count": 0,
        "message": INDEX_DEGRADED_COPY,
        "detail_code": "provider_unavailable",
        "attempted_sources": attempted_sources,
        "selected_source": selected_source,
        "coverage": coverage,
        "from_cache": from_cache,
        "failures": failures,
    }
    warnings.append(INDEX_DEGRADED_COPY)
    return []


def _typed_failure_from_result(failure: Any) -> dict[str, Any]:
    return _typed_failure(
        failure.code,
        failure.source_id,
        retryable=failure.retryable,
        fallback_allowed=failure.fallback_allowed,
    )


def _typed_failure(code: str, source: str, *, retryable: bool, fallback_allowed: bool) -> dict[str, Any]:
    return {
        "code": code,
        "source": source,
        "retryable": retryable,
        "fallback_allowed": fallback_allowed,
    }


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
        if isinstance(status, dict)
        and status.get("status")
        in {"provider_unavailable", "not_available", "missing", "partial", "historical_not_supported", "timed_out"}
    ]
    gap_text = f"需要注意的数据缺口：{', '.join(gap_keys)}。" if gap_keys else "主要数据源状态正常。"
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


def _historical_activity(
    market: str,
    market_date: date,
    provider: HistoricalActivityProvider = load_historical_market_activity,
) -> dict[str, Any]:
    try:
        return provider(market, market_date).as_dict()
    except HistoricalActivityCancelled:
        raise
    except Exception as exc:
        status = "timed_out" if isinstance(exc, TimeoutError) else "provider_unavailable"
        return {
            "sectors": [],
            "gainers": [],
            "capital_flow": [],
            "source_status": {
                "sectors": {"status": "historical_not_supported", "count": 0},
                "gainers": {
                    "status": status,
                    "provider": "historical_activity_provider",
                    "count": 0,
                    "message": "历史精确日期涨幅榜暂不可用；未保存空白历史简报。",
                },
                "capital_flow": {"status": "historical_not_supported", "count": 0},
            },
        }


def _activity_from_pool(
    market: str,
    market_date: date,
    *,
    pool: DataSourcePool,
    source_id: str,
    freshness: str,
) -> dict[str, Any]:
    result = pool.fetch(
        DataRequest(
            capability=SourceCapability.MARKET_ACTIVITY,
            market=market,
            start=market_date,
            end=market_date,
            freshness=freshness,
        ),
        market_activity_plan(source_id),
    )
    if any(failure.code == "cancelled" for failure in result.failures):
        raise HistoricalActivityCancelled()
    decoded = market_activity_sections(result)
    if not decoded:
        provider = ",".join(result.attempted_sources) or source_id
        return _empty_activity(
            market,
            provider=provider,
            status="provider_unavailable",
            message="Configured market activity providers did not return usable data.",
        )
    return {
        section: decoded[section]["rows"]
        for section in ("sectors", "gainers", "capital_flow")
    } | {
        "source_status": {
            section: decoded[section]["source_status"]
            for section in ("sectors", "gainers", "capital_flow")
        }
    }


def _fixture_historical_activity_provider(market: str, market_date: date) -> HistoricalActivityResult:
    activity = _fixture_activity_provider(market, market_date)
    session_date = market_date.isoformat()
    for section in ("sectors", "gainers", "capital_flow"):
        for row in activity.get(section) or []:
            row["session_date"] = session_date
        status = activity.get("source_status", {}).get(section)
        if isinstance(status, dict):
            status["session_date"] = session_date
    return HistoricalActivityResult(
        sectors=activity.get("sectors") or [],
        gainers=activity.get("gainers") or [],
        capital_flow=activity.get("capital_flow") or [],
        source_status=activity.get("source_status") or {},
    )


def _attach_historical_session_provenance(source_status: dict[str, Any], market_date: date) -> None:
    session_date = market_date.isoformat()
    for key in ("sectors", "gainers", "capital_flow"):
        status = source_status.get(key)
        if isinstance(status, dict):
            status.setdefault("session_date", session_date)


def _validate_daily_market_brief_context_for_save(
    context: dict[str, Any], *, existing_report: dict[str, Any] | None = None
) -> None:
    if context.get("generation_kind") != "historical_reconstruction" or context.get("no_session"):
        return

    expected_session_date = str(context.get("market_date") or "")
    source_status = context.get("source_status") or {}
    indexes = context.get("indexes") or []
    if any(str(row.get("date") or "") != expected_session_date for row in indexes if isinstance(row, dict)):
        raise ValueError("历史指数日期未通过校验，未保存简报。")

    for section in ("sectors", "gainers", "capital_flow"):
        rows = context.get(section) or []
        if not rows:
            continue
        status = source_status.get(section) if isinstance(source_status, dict) else None
        if not isinstance(status, dict) or status.get("session_date") != expected_session_date:
            raise ValueError("历史数据日期未通过校验，未保存简报。")
        if any(str(row.get("session_date") or "") != expected_session_date for row in rows if isinstance(row, dict)):
            raise ValueError("历史数据日期未通过校验，未保存简报。")

    gainers_status = source_status.get("gainers") if isinstance(source_status, dict) else {}
    if not isinstance(gainers_status, dict):
        return
    useful_activity = any(
        context.get(section) for section in ("sectors", "gainers", "capital_flow")
    )
    useful_evidence = bool(indexes) or useful_activity
    if not useful_evidence:
        raise ValueError("历史市场活动数据暂不可用，未保存空白历史简报。")
    if not useful_activity and _report_has_market_activity(existing_report):
        raise ValueError("历史市场活动数据暂不可用，未覆盖已有完整简报。")


def _report_has_market_activity(report: dict[str, Any] | None) -> bool:
    snapshot = (report or {}).get("portfolio_snapshot") or {}
    return isinstance(snapshot, dict) and any(
        snapshot.get(section) for section in ("sectors", "gainers", "capital_flow")
    )


def validate_daily_market_brief_context_for_save(
    context: dict[str, Any], *, existing_report: dict[str, Any] | None = None
) -> None:
    _validate_daily_market_brief_context_for_save(
        context, existing_report=existing_report
    )


def _akshare_activity_provider(market: str, market_date: date) -> dict[str, Any]:
    market = _market_config(market).code
    try:
        ak = importlib.import_module("akshare")
    except Exception:
        if market == "CN":
            return _eastmoney_cn_activity(market_date)
        return _empty_activity(market, provider=AKSHARE_PROVIDER, status="provider_unavailable", message="AKShare 未安装或不可导入。")

    if market == "CN":
        return _akshare_cn_activity(ak, market_date)
    if market == "HK":
        return _akshare_hk_activity(ak, market_date)
    if market == "US":
        return _akshare_us_activity(ak, market_date)
    return _empty_activity(market)


def _akshare_cn_activity(ak: Any, market_date: date) -> dict[str, Any]:
    sectors, sector_status = load_activity_section(
        provider=AKSHARE_PROVIDER,
        section="sectors",
        fallback_message="AKShare 未返回可用的 A 股行业板块涨幅榜。",
        loader=lambda: _akshare_cn_sectors(ak.stock_board_industry_name_em()),
        fallback_provider=EASTMONEY_HTTP_PROVIDER,
        fallback_loader=_eastmoney_cn_sectors,
    )
    gainers, gainer_status = load_activity_section(
        provider=AKSHARE_PROVIDER,
        section="gainers",
        fallback_message="AKShare 未返回可用的 A 股个股涨幅榜。",
        loader=lambda: _akshare_stock_gainers(ak.stock_zh_a_spot_em(), market="CN", min_turnover=CN_MIN_TURNOVER),
        fallback_provider=PUBLIC_HTTP_FALLBACK_PROVIDER,
        fallback_loader=_cn_gainers_http_fallback,
    )
    flow, flow_status = load_activity_section(
        provider=AKSHARE_PROVIDER,
        section="capital_flow",
        fallback_message=CAPITAL_FLOW_DEGRADED_COPY,
        loader=lambda: _akshare_cn_capital_flow(ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")),
        fallback_provider=EASTMONEY_HTTP_PROVIDER,
        fallback_loader=_eastmoney_cn_capital_flow,
    )
    return {
        "sectors": sectors,
        "gainers": gainers,
        "capital_flow": flow,
        "source_status": {
            "sectors": sector_status,
            "gainers": gainer_status,
            "capital_flow": flow_status,
        },
    }


def _akshare_hk_activity(ak: Any, market_date: date) -> dict[str, Any]:
    gainers, gainer_status = load_activity_section(
        provider=AKSHARE_PROVIDER,
        section="gainers",
        fallback_message="AKShare 未返回可用的港股主板涨幅榜。",
        loader=lambda: _akshare_stock_gainers(ak.stock_hk_main_board_spot_em(), market="HK", min_turnover=HK_MIN_TURNOVER),
        fallback_provider=PUBLIC_HTTP_FALLBACK_PROVIDER,
        fallback_loader=_hk_gainers_http_fallback,
    )
    activity = _empty_activity(market="HK", provider=AKSHARE_PROVIDER, status="not_available")
    activity["gainers"] = gainers
    activity["source_status"]["gainers"] = gainer_status
    activity["source_status"]["sectors"] = {
        "status": "not_available",
        "provider": AKSHARE_PROVIDER,
        "taxonomy": "provider_native",
        "count": 0,
        "message": "AKShare 当前未提供可直接用于港股全市场的行业/板块涨幅榜；本简报保留个股榜和数据缺口提示。",
    }
    activity["source_status"]["capital_flow"] = {
        "status": "not_available",
        "provider": AKSHARE_PROVIDER,
        "count": 0,
        "message": CAPITAL_FLOW_DEGRADED_COPY,
    }
    return activity


def _akshare_us_activity(ak: Any, market_date: date) -> dict[str, Any]:
    gainers, gainer_status = load_activity_section(
        provider=AKSHARE_PROVIDER,
        section="gainers",
        fallback_message="AKShare 未返回可用的美股涨幅榜。",
        loader=lambda: _akshare_stock_gainers(ak.stock_us_spot_em(), market="US", min_turnover=US_MIN_TURNOVER),
        fallback_provider=PUBLIC_HTTP_FALLBACK_PROVIDER,
        fallback_loader=_us_gainers_http_fallback,
    )
    activity = _empty_activity(market="US", provider=AKSHARE_PROVIDER, status="not_available")
    activity["gainers"] = gainers
    activity["source_status"]["gainers"] = gainer_status
    activity["source_status"]["sectors"] = {
        "status": "not_available",
        "provider": AKSHARE_PROVIDER,
        "taxonomy": "provider_native",
        "count": 0,
        "message": "AKShare 当前未提供可直接用于美股全市场的行业/板块涨幅榜；本简报保留个股榜和数据缺口提示。",
    }
    activity["source_status"]["capital_flow"] = {
        "status": "not_available",
        "provider": AKSHARE_PROVIDER,
        "count": 0,
        "message": CAPITAL_FLOW_DEGRADED_COPY,
    }
    return activity


def _eastmoney_cn_activity(market_date: date) -> dict[str, Any]:
    sectors, sector_status = load_activity_section(
        provider=EASTMONEY_HTTP_PROVIDER,
        section="sectors",
        fallback_message="Eastmoney 未返回可用的 A 股行业板块涨幅榜。",
        loader=_eastmoney_cn_sectors,
    )
    gainers, gainer_status = load_activity_section(
        provider=EASTMONEY_HTTP_PROVIDER,
        section="gainers",
        fallback_message="Eastmoney 未返回可用的 A 股个股涨幅榜。",
        loader=_eastmoney_cn_gainers,
    )
    flow, flow_status = load_activity_section(
        provider=EASTMONEY_HTTP_PROVIDER,
        section="capital_flow",
        fallback_message=CAPITAL_FLOW_DEGRADED_COPY,
        loader=_eastmoney_cn_capital_flow,
    )
    return {
        "sectors": sectors,
        "gainers": gainers,
        "capital_flow": flow,
        "source_status": {
            "sectors": sector_status,
            "gainers": gainer_status,
            "capital_flow": flow_status,
        },
    }


def _eastmoney_cn_sectors() -> list[dict[str, Any]]:
    rows = _eastmoney_clist(
        {
            "fid": "f3",
            "po": "1",
            "pz": "50",
            "pn": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": "m:90+t:2",
            "fields": "f12,f14,f3,f20,f8,f104,f105,f128,f136",
        }
    )
    normalized = [
        {
            "排名": index + 1,
            "板块代码": row.get("f12"),
            "板块名称": row.get("f14"),
            "涨跌幅": row.get("f3"),
            "总市值": row.get("f20"),
            "换手率": row.get("f8"),
            "上涨家数": row.get("f104"),
            "下跌家数": row.get("f105"),
            "领涨股票": row.get("f128"),
            "领涨股票-涨跌幅": row.get("f136"),
        }
        for index, row in enumerate(rows)
    ]
    return _akshare_cn_sectors(normalized)


def _eastmoney_cn_gainers() -> list[dict[str, Any]]:
    rows = _eastmoney_clist(
        {
            "fid": "f3",
            "po": "1",
            "pz": "200",
            "pn": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f3,f6",
        }
    )
    normalized = [
        {
            "代码": row.get("f12"),
            "名称": row.get("f14"),
            "涨跌幅": row.get("f3"),
            "成交额": row.get("f6"),
        }
        for row in rows
    ]
    return _akshare_stock_gainers(normalized, market="CN", min_turnover=CN_MIN_TURNOVER)


def _eastmoney_hk_gainers() -> list[dict[str, Any]]:
    return _eastmoney_market_gainers(
        market="HK",
        market_filter="m:128 t:3",
        min_turnover=HK_MIN_TURNOVER,
    )


def _eastmoney_us_gainers() -> list[dict[str, Any]]:
    return _eastmoney_market_gainers(
        market="US",
        market_filter="m:105,m:106,m:107",
        min_turnover=US_MIN_TURNOVER,
    )


def _hk_gainers_http_fallback() -> list[dict[str, Any]]:
    return _public_http_gainers_with_sina_fallback(
        eastmoney_loader=_eastmoney_hk_gainers,
        sina_loader=_sina_hk_gainers,
    )


def _us_gainers_http_fallback() -> list[dict[str, Any]]:
    return _public_http_gainers_with_sina_fallback(
        eastmoney_loader=_eastmoney_us_gainers,
        sina_loader=_sina_us_gainers,
    )


def _sina_hk_gainers() -> list[dict[str, Any]]:
    import requests

    response = requests.get(
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHKStockData",
        params={
            "page": "1",
            "num": "100",
            "sort": "changepercent",
            "asc": "0",
            "node": "qbgg_hk",
            "_s_r_a": "page",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    return _normalize_sina_hk_gainers(
        [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, list)
        else []
    )


def _sina_us_gainers() -> list[dict[str, Any]]:
    import json
    import requests
    from akshare.stock.cons import (
        js_hash_text,
        us_sina_stock_dict_payload,
        us_sina_stock_list_url,
    )
    from py_mini_racer import MiniRacer

    query = "US_CategoryService.getList?page=1&num=20&sort=chg&asc=0&market=&id="
    decoder = MiniRacer()
    decoder.eval(js_hash_text)
    callback_key = decoder.call("d", query)
    params = dict(us_sina_stock_dict_payload)
    params.update({"page": "1", "num": "20", "sort": "chg", "asc": "0"})
    response = requests.get(
        us_sina_stock_list_url.format(callback_key), params=params, timeout=12
    )
    response.raise_for_status()
    start = response.text.find("({")
    end = response.text.rfind(");")
    if start < 0 or end <= start:
        return []
    payload = json.loads(response.text[start + 1 : end])
    rows = payload.get("data") if isinstance(payload, dict) else []
    return _normalize_sina_us_gainers(
        [row for row in rows if isinstance(row, dict)]
        if isinstance(rows, list)
        else []
    )


def _normalize_sina_hk_gainers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [
        {
            "代码": row.get("symbol") or row.get("code"),
            "名称": row.get("name"),
            "涨跌幅": row.get("changepercent"),
            "成交额": row.get("amount"),
        }
        for row in rows
    ]
    return _with_gainer_provider(
        _akshare_stock_gainers(
            normalized, market="HK", min_turnover=HK_MIN_TURNOVER
        ),
        provider=SINA_FINANCE_PROVIDER,
        min_turnover=HK_MIN_TURNOVER,
    )


def _normalize_sina_us_gainers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        price = _number(row.get("price"))
        volume = _number(row.get("volume"))
        normalized.append(
            {
                "代码": row.get("symbol"),
                "名称": row.get("cname") or row.get("name"),
                "涨跌幅": row.get("chg"),
                "成交额": price * volume if price is not None and volume is not None else None,
            }
        )
    return _with_gainer_provider(
        _akshare_stock_gainers(
            normalized, market="US", min_turnover=US_MIN_TURNOVER
        ),
        provider=SINA_FINANCE_PROVIDER,
        min_turnover=US_MIN_TURNOVER,
    )


def _with_gainer_provider(
    rows: list[dict[str, Any]], *, provider: str, min_turnover: float
) -> list[dict[str, Any]]:
    for row in rows:
        row["provider"] = provider
        row["metric"] = (
            f"{provider}_turnover_filtered_change_pct_min_{int(min_turnover)}"
        )
    return rows


def _eastmoney_market_gainers(
    *, market: str, market_filter: str, min_turnover: float
) -> list[dict[str, Any]]:
    rows = _eastmoney_clist(
        {
            "fid": "f3",
            "po": "1",
            "pz": "200",
            "pn": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": market_filter,
            "fields": "f12,f14,f3,f6",
        }
    )
    normalized = [
        {
            "代码": row.get("f12"),
            "名称": row.get("f14"),
            "涨跌幅": row.get("f3"),
            "成交额": row.get("f6"),
        }
        for row in rows
    ]
    gainers = _akshare_stock_gainers(
        normalized, market=market, min_turnover=min_turnover
    )
    for row in gainers:
        row["provider"] = EASTMONEY_HTTP_PROVIDER
        row["metric"] = (
            f"eastmoney_turnover_filtered_change_pct_min_{int(min_turnover)}"
        )
    return gainers


def _cn_gainers_http_fallback() -> list[dict[str, Any]]:
    return _public_http_gainers_with_sina_fallback(
        eastmoney_loader=_eastmoney_cn_gainers,
        sina_loader=_sina_cn_gainers,
    )


def _public_http_gainers_with_sina_fallback(
    *,
    eastmoney_loader: Callable[[], list[dict[str, Any]]],
    sina_loader: Callable[[], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    try:
        rows = eastmoney_loader()
        nested_reason = "empty_result"
    except Exception as exc:
        rows = []
        nested_reason = type(exc).__name__
    if rows:
        return rows
    sina_rows = sina_loader()
    if not sina_rows:
        return []
    return ActivityFallbackRows(
        sina_rows,
        selected_provider=SINA_FINANCE_PROVIDER,
        fallback_chain=(EASTMONEY_HTTP_PROVIDER, SINA_FINANCE_PROVIDER),
        fallback_reasons=(nested_reason,),
    )


def _sina_cn_gainers() -> list[dict[str, Any]]:
    import requests

    response = requests.get(
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
        params={
            "page": "1",
            "num": "50",
            "sort": "changepercent",
            "asc": "0",
            "node": "hs_a",
            "symbol": "",
            "_s_r_a": "page",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=12,
    )
    response.raise_for_status()
    rows = response.json()
    normalized = [
        {
            "代码": row.get("code") or row.get("symbol"),
            "名称": row.get("name"),
            "涨跌幅": row.get("changepercent"),
            "成交额": row.get("amount"),
        }
        for row in rows
        if isinstance(row, dict)
    ]
    gainers = _akshare_stock_gainers(normalized, market="CN", min_turnover=CN_MIN_TURNOVER)
    for row in gainers:
        row["provider"] = SINA_FINANCE_PROVIDER
        row["metric"] = f"sina_turnover_filtered_change_pct_min_{CN_MIN_TURNOVER}"
    return gainers


def _eastmoney_cn_capital_flow() -> list[dict[str, Any]]:
    rows = _eastmoney_clist(
        {
            "fid": "f62",
            "po": "1",
            "pz": "50",
            "pn": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": "m:90+t:2",
            "fields": "f12,f14,f3,f62",
        }
    )
    normalized = [
        {
            "名称": row.get("f14"),
            "今日涨跌幅": row.get("f3"),
            "今日主力净流入-净额": row.get("f62"),
        }
        for row in rows
    ]
    return _akshare_cn_capital_flow(normalized)


def _eastmoney_clist(params: dict[str, str]) -> list[dict[str, Any]]:
    import requests

    base_params = {
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    }
    last_exc: Exception | None = None
    for host in (
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://81.push2.eastmoney.com/api/qt/clist/get",
        "https://72.push2.eastmoney.com/api/qt/clist/get",
        "https://push2.eastmoney.com/api/qt/clist/get",
    ):
        try:
            response = requests.get(host, params={**base_params, **params}, headers=headers, timeout=12)
            response.raise_for_status()
            payload = response.json()
            rows = ((payload.get("data") or {}).get("diff") or [])
            return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    return []


def _akshare_cn_sectors(frame: Any) -> list[dict[str, Any]]:
    rows = _frame_records(frame)
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        name = _first_value(row, "板块名称", "名称")
        if not name:
            continue
        cleaned.append(
            {
                "rank": _number(_first_value(row, "排名", "序号")) or len(cleaned) + 1,
                "code": _text(_first_value(row, "板块代码", "代码")),
                "name": _text(name),
                "change_pct": _number(_first_value(row, "涨跌幅", "今日涨跌幅")),
                "turnover": _number(_first_value(row, "成交额", "总市值")),
                "provider": AKSHARE_PROVIDER,
                "taxonomy": "eastmoney_industry_board",
                "metric": "industry_change_pct",
            }
        )
    cleaned = [item for item in cleaned if item.get("change_pct") is not None]
    return _ranked_top(sorted(cleaned, key=lambda item: item["change_pct"], reverse=True)[:5])


def _akshare_stock_gainers(frame: Any, *, market: str, min_turnover: float) -> list[dict[str, Any]]:
    rows = _frame_records(frame)
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        code = _text(_first_value(row, "代码", "symbol"))
        name = _text(_first_value(row, "名称", "股票简称"))
        change_pct = _number(_first_value(row, "涨跌幅", "涨幅"))
        turnover = _number(_first_value(row, "成交额", "金额"))
        if not code or not name or change_pct is None:
            continue
        if turnover is not None and turnover < min_turnover:
            continue
        if market == "CN" and ("ST" in name.upper() or "退" in name):
            continue
        if market == "US" and _looks_like_us_warrant(code, name):
            continue
        cleaned.append(
            {
                "rank": len(cleaned) + 1,
                "code": code,
                "name": name,
                "change_pct": change_pct,
                "turnover": turnover,
                "provider": AKSHARE_PROVIDER,
                "metric": f"turnover_filtered_change_pct_min_{int(min_turnover)}",
            }
        )
    return _ranked_top(sorted(cleaned, key=lambda item: item["change_pct"], reverse=True)[:5])


def _akshare_cn_capital_flow(frame: Any) -> list[dict[str, Any]]:
    rows = _frame_records(frame)
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        name = _text(_first_value(row, "名称", "板块名称"))
        flow_value = _number(_first_value(row, "今日主力净流入-净额", "主力净流入-净额"))
        if not name or flow_value is None:
            continue
        cleaned.append(
            {
                "rank": len(cleaned) + 1,
                "name": name,
                "flow_value": flow_value,
                "change_pct": _number(_first_value(row, "今日涨跌幅", "涨跌幅")),
                "provider": AKSHARE_PROVIDER,
                "metric": "main_net_inflow",
            }
        )
    return _ranked_top(sorted(cleaned, key=lambda item: item["flow_value"], reverse=True)[:5])


def _ranked_top(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        item = dict(row)
        item["rank"] = rank
        ranked.append(item)
    return ranked


def _frame_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        records = frame.to_dict(orient="records")
        return [dict(item) for item in records if isinstance(item, dict)]
    if isinstance(frame, list):
        return [dict(item) for item in frame if isinstance(item, dict)]
    return []


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _looks_like_us_warrant(code: str, name: str) -> bool:
    symbol = code.split(".")[-1].upper()
    upper_name = name.upper()
    return symbol.endswith(("W", "WS", "WT")) or any(word in upper_name for word in (" WARRANT", " WT", " RIGHT"))


def _empty_activity(market: str, *, provider: str = "not_configured", status: str = "provider_unavailable", message: str | None = None) -> dict[str, Any]:
    return {
        "sectors": [],
        "gainers": [],
        "capital_flow": [],
        "source_status": {
            "sectors": {
                "status": status,
                "provider": provider,
                "taxonomy": "provider_native",
                "count": 0,
                "message": message or "当前配置的数据源没有返回可覆盖全市场行业/板块涨幅排行的数据。",
            },
            "gainers": {
                "status": status,
                "provider": provider,
                "count": 0,
                "message": message or "当前配置的数据源没有返回可覆盖全市场普通股流动性筛选和涨幅排行的数据。",
            },
            "capital_flow": {
                "status": "not_available",
                "provider": provider,
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
    bars_by_code: dict[str, list[dict[str, Any]]] = {}
    for offset, code in enumerate(codes):
        bars: list[dict[str, Any]] = []
        current = date.fromisoformat(start)
        close = 1000.0 + offset * 25
        while current <= end_date:
            if not _is_weekend(current):
                close += 2.5 + offset
                bars.append(
                    {
                        "date": current.isoformat(),
                        "close": close,
                        "volume": 1_000_000 + len(bars) * 25_000 + offset * 10_000,
                        "raw": {"provider_symbol": f"fixture:{code}"},
                    }
                )
            current += timedelta(days=1)
        bars_by_code[code] = bars
    return MarketBarSnapshot(
        bars_by_code=bars_by_code,
        fetched_at=datetime.combine(end_date, time(hour=8), tzinfo=SG_TZ),
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


def _render_rank_table(items: list[dict[str, Any]], *, market: str, empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    lines = [
        "| 排名 | 名称 | 代码/指标 | 涨跌幅/数值 | 成交额 | 来源 |",
        "| ---: | --- | --- | ---: | ---: | --- |",
    ]
    for idx, item in enumerate(items[:5], start=1):
        metric = item.get("change_pct")
        if metric is None:
            metric = item.get("flow_value")
            metric_text = _fmt_number(metric)
        else:
            metric_text = _fmt_pct(metric)
        turnover_text = format_market_amount(item.get("turnover"), market)
        lines.append(
            f"| {item.get('rank') or idx} | {item.get('name') or '-'} | {item.get('code') or item.get('metric') or '-'} | {metric_text} | {turnover_text} | {item.get('provider') or '-'} |"
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


MARKET_CURRENCIES = {
    "CN": {"code": "CNY", "unit": "元"},
    "HK": {"code": "HKD", "unit": "港元"},
    "US": {"code": "USD", "unit": "美元"},
}


def format_market_amount(value: Any, market: str) -> str:
    number = _number(value)
    if number is None:
        return "-"
    currency = MARKET_CURRENCIES[_normalize_market(market)]
    absolute = abs(number)
    if absolute >= 100_000_000:
        return f"{number / 100_000_000:.2f} 亿{currency['unit']} {currency['code']}"
    if absolute >= 10_000:
        return f"{number / 10_000:.2f} 万{currency['unit']} {currency['code']}"
    return f"{number:.2f} {currency['unit']} {currency['code']}"


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


def _source_label(key: str) -> str:
    labels = {
        "indexes": "核心指数",
        "sectors": "行业/板块",
        "gainers": "个股涨幅榜",
        "capital_flow": "资金流",
        "session": "交易日",
    }
    return labels.get(key, key)


def _status_text(status: Any) -> str:
    value = status.get("status", "unknown") if isinstance(status, dict) else str(status)
    labels = {
        "ok": "可用",
        "partial": "部分可用",
        "missing": "暂缺",
        "provider_unavailable": "数据源暂不可用",
        "not_available": "未提供",
        "historical_not_supported": "不支持历史榜单",
        "timed_out": "历史数据获取超时，已保留可用结果",
        "unverified": "交易日未确认",
        "no_session": "无常规交易",
        "unknown": "状态未知",
    }
    return labels.get(str(value), str(value))


def _status_message(status: dict[str, Any]) -> str | None:
    message = status.get("message")
    if not message:
        return None
    return _sanitize_user_message(str(message))


def _sanitize_user_message(message: str) -> str:
    blocked_fragments = (
        "CERTIFICATE_VERIFY_FAILED",
        "Yahoo chart fallback",
        "Traceback",
        "psycopg",
        "UniqueViolation",
    )
    if any(fragment.lower() in message.lower() for fragment in blocked_fragments):
        return "数据源本次未返回可用结果；简报已保留其他可用部分和数据缺口提示。"
    return message


def _safe_provider_label(provider: Any) -> str | None:
    if provider is None:
        return None
    text = str(provider)
    if "CERTIFICATE_VERIFY_FAILED" in text or "Traceback" in text:
        return "configured_provider"
    return text


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
