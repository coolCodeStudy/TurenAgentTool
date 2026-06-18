from __future__ import annotations

import json
import os
import re
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.futu_provider import FutuProviderError, get_futu_index_history, get_hk_ipo_list


@dataclass(frozen=True)
class SourceDefinition:
    source_type: str
    status_key: str
    context_key: str
    env_prefix: str
    payload_keys: tuple[str, ...]


SOURCE_DEFINITIONS = (
    SourceDefinition(
        source_type="indexes",
        status_key="indexes",
        context_key="index_summary",
        env_prefix="WEEKLY_REVIEW_INDEX",
        payload_keys=("indexes", "index_summary", "items"),
    ),
    SourceDefinition(
        source_type="macro",
        status_key="macro",
        context_key="macro_events",
        env_prefix="WEEKLY_REVIEW_MACRO",
        payload_keys=("macro", "macro_events", "events", "items"),
    ),
    SourceDefinition(
        source_type="news_themes",
        status_key="news_themes",
        context_key="news_themes",
        env_prefix="WEEKLY_REVIEW_NEWS_THEMES",
        payload_keys=("news_themes", "themes", "items"),
    ),
    SourceDefinition(
        source_type="opportunities",
        status_key="opportunities",
        context_key="opportunity_items",
        env_prefix="WEEKLY_REVIEW_OPPORTUNITIES",
        payload_keys=("opportunities", "opportunity_items", "items"),
    ),
)


DEFAULT_INDEX_BASKET = (
    {
        "market": "US",
        "name": "Nasdaq 100",
        "codes": [
            {
                "code": "US.QQQ",
                "instrument_type": "proxy_etf",
                "proxy_for": "Nasdaq 100",
                "source_note": "Futu OpenD does not provide direct US index K-line data in this environment; QQQ is used as a tradable Nasdaq 100 proxy.",
            }
        ],
        "portfolio_relevance": "观察美股大型科技和 AI 成长股风险偏好。",
    },
    {
        "market": "US",
        "name": "S&P 500",
        "codes": [
            {
                "code": "US.SPY",
                "instrument_type": "proxy_etf",
                "proxy_for": "S&P 500",
                "source_note": "Futu OpenD does not provide direct US index K-line data in this environment; SPY is used as a tradable S&P 500 proxy.",
            }
        ],
        "portfolio_relevance": "观察美股大盘风险偏好和组合美元资产背景。",
    },
    {
        "market": "US",
        "name": "Dow Jones",
        "codes": [
            {
                "code": "US.DIA",
                "instrument_type": "proxy_etf",
                "proxy_for": "Dow Jones",
                "source_note": "Futu OpenD does not provide direct US index K-line data in this environment; DIA is used as a tradable Dow Jones proxy.",
            }
        ],
        "portfolio_relevance": "观察美股传统蓝筹和风险偏好是否扩散。",
    },
    {
        "market": "HK",
        "name": "恒生指数",
        "codes": [
            {
                "code": "HK.02800",
                "instrument_type": "proxy_etf",
                "proxy_for": "恒生指数",
                "source_note": "Futu OpenD rejected HK.HSI in this environment; Tracker Fund of Hong Kong is used as a tradable Hang Seng Index proxy.",
            },
            "HK.800000",
        ],
        "portfolio_relevance": "观察港股大盘和南向资金情绪背景。",
    },
    {
        "market": "HK",
        "name": "恒生科技",
        "codes": [
            {
                "code": "HK.03033",
                "instrument_type": "proxy_etf",
                "proxy_for": "恒生科技",
                "source_note": "Futu OpenD rejected HK.HSTECH in this environment; a Hang Seng TECH ETF is used as a tradable proxy.",
            },
            "HK.800700",
            "HK.03032",
        ],
        "portfolio_relevance": "影响港股科技成长仓和中概相关情绪。",
    },
    {
        "market": "CN",
        "name": "沪深300",
        "codes": [
            {
                "code": "HK.03188",
                "instrument_type": "proxy_etf",
                "proxy_for": "沪深300",
                "source_note": "The cloud Futu account lacks direct A-share index quote permission; a Hong Kong-listed CSI 300 ETF is used as a tradable proxy.",
            },
            "SH.510300",
            "SH.000300",
            "SZ.399300",
        ],
        "portfolio_relevance": "观察 A 股核心资产风险偏好。",
    },
    {
        "market": "CN",
        "name": "创业板指",
        "codes": [
            {
                "code": "HK.03147",
                "instrument_type": "proxy_etf",
                "proxy_for": "创业板指",
                "source_note": "The cloud Futu account lacks direct A-share index quote permission; a Hong Kong-listed ChiNext ETF is used as a tradable proxy when available.",
            },
            "SZ.159915",
            "SZ.399006",
        ],
        "portfolio_relevance": "观察 A 股成长和题材风险偏好。",
    },
    {
        "market": "CN",
        "name": "科创50",
        "codes": [
            {
                "code": "HK.03151",
                "instrument_type": "proxy_etf",
                "proxy_for": "科创50",
                "source_note": "The cloud Futu account lacks direct A-share index quote permission; a Hong Kong-listed STAR 50 ETF is used as a tradable proxy when available.",
            },
            "SH.588000",
            "SH.000688",
        ],
        "portfolio_relevance": "观察半导体、硬科技和 AI 供应链情绪。",
    },
)

FED_FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS_SCHEDULE_URL_TEMPLATE = "https://www.bls.gov/schedule/{year}/{month:02d}_sched_list.htm"
BEA_RELEASE_DATES_URL = "https://apps.bea.gov/API/signup/release_dates.json"
GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
SSE_STOCK_CONNECT_URL = "https://www.sse.com.cn/services/hkexsc/disclo/eligible/"
NASDAQ_100_METHODOLOGY_URL = "https://indexes.nasdaqomx.com/docs/Methodology_NDX.pdf"

MONTH_NAMES = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

BLS_IMPORTANT_RELEASES = (
    "Consumer Price Index",
    "Producer Price Index",
    "Employment Situation",
    "Job Openings",
    "Employment Cost Index",
    "Productivity and Costs",
    "Real Earnings",
    "Import and Export Price",
)

BEA_IMPORTANT_RELEASES = (
    "Gross Domestic Product",
    "Personal Income and Outlays",
    "Corporate Profits",
    "International Trade",
    "International Transactions",
)

DEFAULT_THEME_QUERIES = (
    {
        "theme": "AI memory / HBM",
        "terms": ("HBM", "DRAM price", "NAND", "memory price", "SK hynix", "Micron"),
        "portfolio_relevance": ["US.MU", "KR.000660", "HK.07709", "US.DRAM"],
    },
    {
        "theme": "MLCC / passive components",
        "terms": ("MLCC", "passive components", "Murata", "Yageo"),
        "portfolio_relevance": ["electronics supply chain"],
    },
    {
        "theme": "Glass substrate / advanced packaging",
        "terms": ("glass substrate", "advanced packaging", "chip packaging"),
        "portfolio_relevance": ["semiconductor packaging", "AI accelerator supply chain"],
    },
    {
        "theme": "Optical modules / CPO",
        "terms": ("CPO", "optical module", "silicon photonics", "800G", "1.6T"),
        "portfolio_relevance": ["AI data-center networking"],
    },
    {
        "theme": "Hong Kong growth",
        "terms": ("Alibaba", "Meituan", "Xiaomi", "Hang Seng Tech", "Southbound"),
        "portfolio_relevance": ["HK.09988", "HK.03690", "HK.01810", "Hang Seng Tech"],
    },
    {
        "theme": "High-volatility themes",
        "terms": ("space", "quantum", "crypto finance", "Circle", "Rocket Lab"),
        "portfolio_relevance": ["US.RKLB", "crypto finance", "quantum"],
    },
)

_SSL_CONTEXT: ssl.SSLContext | None = None


def diagnose_default_index_provider(*, start: date, end: date) -> dict[str, Any]:
    warnings: list[str] = []
    payload, provider, reason = _fetch_default_index_payload(start=start, end=end, warnings=warnings)
    items = _extract_items(payload, SOURCE_DEFINITIONS[0])
    status = "ok" if items else "missing"
    errors: list[Any] = []
    if isinstance(payload, dict):
        errors = list(payload.get("errors") or [])
        if items and errors:
            status = "partial"
        elif payload is not None and not items:
            status = "empty"
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "provider": provider,
        "status": status,
        "count": len(items),
        "indexes": items,
        "errors": errors,
        "reason": reason,
        "warnings": warnings,
        "basket": [dict(item) for item in DEFAULT_INDEX_BASKET],
    }


def diagnose_weekly_review_sources(*, start: date, end: date) -> dict[str, Any]:
    warnings: list[str] = []
    file_payload = _load_external_source_file(warnings=warnings)
    sources: dict[str, Any] = {}
    for definition in SOURCE_DEFINITIONS:
        payload, provider, reason = _fetch_source_payload(
            definition,
            file_payload=file_payload,
            start=start,
            end=end,
            warnings=warnings,
        )
        items = _extract_items(payload, definition)
        status = "ok" if items else "missing"
        errors: list[Any] = []
        if isinstance(payload, dict):
            errors = list(payload.get("errors") or [])
            if items and errors:
                status = "partial"
            elif payload is not None and not items:
                status = "empty"
        sources[definition.status_key] = {
            "source_type": definition.source_type,
            "provider": provider,
            "status": status,
            "count": len(items),
            "reason": reason,
            "errors": errors[:5],
            "samples": [_diagnostic_sample(item) for item in items[:3]],
        }
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "sources": sources,
        "warnings": warnings,
    }


def load_weekly_review_external_sources(
    *,
    start: date,
    end: date,
    force_refresh: bool = False,
    run_id: int | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_status": {},
        "source_summary": {},
    }
    cached_by_type = {
        row["source_type"]: row
        for row in repository.list_weekly_review_sources(start.isoformat(), end.isoformat())
    }
    file_payload = _load_external_source_file(warnings=warnings)
    for definition in SOURCE_DEFINITIONS:
        cached = cached_by_type.get(definition.source_type)
        if cached and not force_refresh and _cache_is_valid(cached):
            items = _extract_items(cached.get("payload"), definition)
            status = _status_from_items(items, cached=True, provider=cached.get("provider"), reason=cached.get("reason"))
            result[definition.context_key] = items
            result["source_status"][definition.status_key] = status
            result["source_summary"][definition.source_type] = {
                "status": status["status"],
                "count": len(items),
                "provider": cached.get("provider"),
                "cached": True,
            }
            continue

        payload, provider, reason = _fetch_source_payload(
            definition,
            file_payload=file_payload,
            start=start,
            end=end,
            warnings=warnings,
        )
        items = _extract_items(payload, definition)
        status_text = "ok" if items else "missing"
        if payload is not None and not items:
            status_text = "empty"
            reason = reason or "payload contained no items"
        if isinstance(payload, dict) and items and payload.get("errors"):
            status_text = "partial"
            reason = reason or "; ".join(str(item) for item in (payload.get("errors") or [])[:3])
        cache_row = repository.upsert_weekly_review_source(
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            source_type=definition.source_type,
            provider=provider,
            source_key="default",
            status=status_text,
            payload=payload if payload is not None else {},
            reason=reason,
            run_id=run_id,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        )
        status = _status_from_items(
            items,
            cached=False,
            provider=provider,
            reason=reason,
            fetched_at=cache_row.get("fetched_at"),
            status_override=status_text,
        )
        result[definition.context_key] = items
        result["source_status"][definition.status_key] = status
        result["source_summary"][definition.source_type] = {
            "status": status["status"],
            "count": len(items),
            "provider": provider,
            "cached": False,
        }
    return result


def build_budget_warnings(token_usage: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(token_usage, dict) or not token_usage:
        return []
    warnings: list[dict[str, Any]] = []
    total_tokens = _token_total(token_usage)
    token_threshold = _int_env("WEEKLY_REVIEW_TOKEN_WARNING_TOTAL")
    if token_threshold is not None and total_tokens > token_threshold:
        warnings.append(
            {
                "type": "token_threshold",
                "severity": "warning",
                "message": f"Token usage {total_tokens} exceeded warning threshold {token_threshold}.",
                "actual": total_tokens,
                "threshold": token_threshold,
            }
        )
    cost = _float_or_none(token_usage.get("estimated_cost") or token_usage.get("cost"))
    cost_threshold = _float_env("WEEKLY_REVIEW_COST_WARNING")
    if cost_threshold is not None and cost is not None and cost > cost_threshold:
        warnings.append(
            {
                "type": "cost_threshold",
                "severity": "warning",
                "message": f"Estimated cost {cost} exceeded warning threshold {cost_threshold}.",
                "actual": cost,
                "threshold": cost_threshold,
            }
        )
    return warnings


def _load_external_source_file(*, warnings: list[str] | None) -> dict[str, Any]:
    path_text = os.getenv("WEEKLY_REVIEW_EXTERNAL_SOURCE_FILE")
    if not path_text:
        return {}
    try:
        value = json.loads(Path(path_text).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        if warnings is not None:
            warnings.append(f"weekly review external source file failed: {exc}")
        return {}


def _fetch_source_payload(
    definition: SourceDefinition,
    *,
    file_payload: dict[str, Any],
    start: date,
    end: date,
    warnings: list[str] | None,
) -> tuple[Any | None, str, str | None]:
    for key in (definition.source_type, definition.status_key, *definition.payload_keys):
        if key in file_payload:
            return file_payload[key], "json_file", None

    env_json = os.getenv(f"{definition.env_prefix}_JSON")
    if env_json:
        try:
            return json.loads(env_json), "env_json", None
        except json.JSONDecodeError as exc:
            reason = f"invalid JSON env: {exc}"
            if warnings is not None:
                warnings.append(f"{definition.source_type} {reason}")
            return None, "env_json", reason

    env_url = os.getenv(f"{definition.env_prefix}_URL")
    if env_url:
        try:
            request = Request(env_url, headers={"User-Agent": "InvestmentKnowledgeWeeklyReview/1.0"})
            with urlopen(request, timeout=8) as response:
                return json.loads(response.read().decode("utf-8")), "json_url", None
        except (OSError, URLError, json.JSONDecodeError) as exc:
            reason = f"URL fetch failed: {exc}"
            if warnings is not None:
                warnings.append(f"{definition.source_type} {reason}")
            return None, "json_url", reason

    if definition.source_type == "indexes":
        return _fetch_default_index_payload(start=start, end=end, warnings=warnings)
    if definition.source_type == "macro":
        return _fetch_default_macro_payload(start=start, end=end, warnings=warnings)
    if definition.source_type == "news_themes":
        return _fetch_default_news_theme_payload(start=start, end=end, warnings=warnings)
    if definition.source_type == "opportunities":
        return _fetch_default_opportunity_payload(start=start, end=end, warnings=warnings)

    return None, "not_configured", "provider not configured"


def _fetch_default_index_payload(
    *,
    start: date,
    end: date,
    warnings: list[str] | None,
) -> tuple[dict[str, Any] | None, str, str | None]:
    try:
        snapshot = get_futu_index_history(
            start=start.isoformat(),
            end=end.isoformat(),
            indexes=[dict(item) for item in DEFAULT_INDEX_BASKET],
        )
    except FutuProviderError as exc:
        reason = str(exc)
        if warnings is not None:
            warnings.append(f"indexes {reason}")
        return None, "futu.request_history_kline", reason
    except Exception as exc:
        reason = f"Futu index provider failed: {exc}"
        if warnings is not None:
            warnings.append(f"indexes {reason}")
        return None, "futu.request_history_kline", reason

    payload = {
        "indexes": snapshot.indexes,
        "errors": snapshot.errors,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "start": snapshot.start,
        "end": snapshot.end,
        "basket": [dict(item) for item in DEFAULT_INDEX_BASKET],
    }
    reason = "; ".join(snapshot.errors[:3]) if snapshot.errors else None
    if snapshot.errors and warnings is not None:
        warnings.append(f"indexes partial: {reason}")
    return payload, "futu.request_history_kline", reason


def _fetch_default_macro_payload(
    *,
    start: date,
    end: date,
    warnings: list[str] | None,
) -> tuple[dict[str, Any], str, str | None]:
    window_end = end + timedelta(days=14)
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    provider_results = (
        ("fed.fomc_calendar", _fetch_fed_fomc_events),
        ("bls.release_calendar", _fetch_bls_release_events),
        ("bea.release_schedule", _fetch_bea_release_events),
    )
    for provider, fetcher in provider_results:
        try:
            events.extend(fetcher(start, window_end))
        except Exception as exc:
            errors.append(f"{provider}: {exc}")
    events = _dedupe_items(events, keys=("source", "date", "title"))
    events.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("title") or "")))
    payload = {
        "macro_events": events[:16],
        "source_type": "macro",
        "providers": [provider for provider, _fetcher in provider_results],
        "window_start": start.isoformat(),
        "window_end": window_end.isoformat(),
        "errors": errors,
    }
    reason = "; ".join(errors[:3]) if errors else None
    if errors and warnings is not None:
        warnings.append(f"macro partial: {reason}")
    return payload, "fed_bls_bea_calendar", reason


def _fetch_default_news_theme_payload(
    *,
    start: date,
    end: date,
    warnings: list[str] | None,
) -> tuple[dict[str, Any], str, str | None]:
    themes: list[dict[str, Any]] = []
    errors: list[str] = []
    previous_start = start - timedelta(days=7)
    previous_end = end - timedelta(days=7)
    try:
        current_pool = _fetch_gdelt_articles(_all_theme_terms(), start=start, end=end, max_records=50)
        previous_pool = _fetch_gdelt_articles(_all_theme_terms(), start=previous_start, end=previous_end, max_records=50)
    except Exception as exc:
        current_pool = []
        previous_pool = []
        errors.append(f"gdelt.batch: {exc}")
    for definition in DEFAULT_THEME_QUERIES:
        current_articles = _theme_articles(current_pool, definition["terms"])[:8]
        previous_articles = _theme_articles(previous_pool, definition["terms"])[:8]
        if not current_articles:
            try:
                current_articles = _fetch_google_news_articles(
                    definition["terms"],
                    start=start,
                    end=end,
                    max_records=5,
                )
            except Exception as exc:
                errors.append(f"{definition['theme']} google_news: {exc}")
        if not current_articles and not previous_articles:
            continue
        current_count = len(current_articles)
        previous_count = len(previous_articles)
        heat_change = _heat_change(current_count=current_count, previous_count=previous_count)
        source = _theme_source(current_articles)
        source_label = "Google News RSS fallback" if source == "google_news.rss" else "GDELT"
        themes.append(
            {
                "theme": definition["theme"],
                "name": definition["theme"],
                "article_count": current_count,
                "previous_article_count": previous_count,
                "heat_change": heat_change,
                "summary": (
                    f"{source_label} 本周命中 {current_count} 条，前周 {previous_count} 条，热度{_heat_change_text(heat_change)}；"
                    f"关联：{', '.join(definition['portfolio_relevance'])}。"
                ),
                "top_evidence": current_articles[:3],
                "portfolio_relevance": list(definition["portfolio_relevance"]),
                "confidence": _theme_confidence(current_count=current_count, previous_count=previous_count),
                "source": source,
                "source_url": _theme_source_url(current_articles, definition["terms"], start=start, end=end),
            }
        )
    themes.sort(key=lambda item: (item.get("confidence") != "high", -(int(item.get("article_count") or 0))))
    provider = "gdelt.doc/google_news.rss" if any(str(item.get("source") or "") != "gdelt.doc" for item in themes) else "gdelt.doc"
    payload = {
        "news_themes": themes,
        "source_type": "theme_news",
        "provider": provider,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "errors": errors,
    }
    reason = "; ".join(errors[:3]) if errors else None
    if errors and warnings is not None:
        warnings.append(f"news themes partial: {reason}")
    return payload, provider, reason


def _fetch_default_opportunity_payload(
    *,
    start: date,
    end: date,
    warnings: list[str] | None,
) -> tuple[dict[str, Any], str, str | None]:
    window_end = end + timedelta(days=14)
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        items.extend(_fetch_hk_ipo_opportunities(start=start, window_end=window_end))
    except Exception as exc:
        errors.append(f"futu.hk_ipo: {exc}")
    items.extend(_scheduled_opportunity_windows(start=start, window_end=window_end))
    items = _dedupe_items(items, keys=("category", "title", "effective_date"))
    items.sort(key=lambda item: (str(item.get("effective_date") or item.get("date") or ""), str(item.get("title") or "")))
    payload = {
        "opportunities": items[:12],
        "source_type": "opportunities",
        "providers": ["futu.hk_ipo", "sse.stock_connect_reference", "nasdaq100.methodology_reference"],
        "window_start": start.isoformat(),
        "window_end": window_end.isoformat(),
        "errors": errors,
    }
    reason = "; ".join(errors[:3]) if errors else None
    if errors and warnings is not None:
        warnings.append(f"opportunities partial: {reason}")
    return payload, "futu_ipo_official_windows", reason


def _extract_items(payload: Any, definition: SourceDefinition) -> list[dict[str, Any]]:
    if payload is None:
        return []
    raw_items: Any = payload
    if isinstance(payload, dict):
        for key in definition.payload_keys:
            if key in payload:
                raw_items = payload[key]
                break
        else:
            raw_items = payload.get("items", payload)
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []
    return [_normalize_item(item) for item in raw_items if isinstance(item, dict)]


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in item.items() if value is not None}


def _diagnostic_sample(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "name": item.get("name"),
            "title": item.get("title"),
            "theme": item.get("theme"),
            "date": item.get("date") or item.get("effective_date"),
            "summary": item.get("summary") or item.get("reason"),
            "source": item.get("source"),
        }.items()
        if value
    }


def _fetch_fed_fomc_events(start: date, window_end: date) -> list[dict[str, Any]]:
    lines = _html_lines(_fetch_text_url(FED_FOMC_CALENDAR_URL))
    events: list[dict[str, Any]] = []
    for year in range(start.year, window_end.year + 1):
        section = _section_lines(lines, f"{year} FOMC Meetings", "FOMC Meetings")
        current_month = ""
        for line in section:
            if line in MONTH_NAMES:
                current_month = line
                continue
            if not current_month:
                continue
            match = re.match(r"^(\d{1,2})(?:-(\d{1,2}))?(\*)?(?:\s|\(|$)", line)
            if not match:
                continue
            start_day = int(match.group(1))
            end_day = int(match.group(2) or match.group(1))
            sep = bool(match.group(3))
            meeting_start = date(year, MONTH_NAMES[current_month], start_day)
            meeting_end = date(year, MONTH_NAMES[current_month], end_day)
            if not _date_windows_overlap(meeting_start, meeting_end, start, window_end):
                continue
            title = "FOMC meeting"
            if sep:
                title += " with SEP"
            events.append(
                {
                    "date": meeting_end.isoformat(),
                    "start_date": meeting_start.isoformat(),
                    "end_date": meeting_end.isoformat(),
                    "region": "US",
                    "title": title,
                    "name": title,
                    "importance": "high",
                    "summary": "Federal Reserve policy meeting window; rates and SEP can affect USD rates, risk appetite, and long-duration growth assets.",
                    "why_it_matters": "Affects USD rates, risk appetite, Hong Kong growth stocks, AI infrastructure duration exposure, and leveraged ETFs.",
                    "source": "Federal Reserve FOMC calendar",
                    "source_url": FED_FOMC_CALENDAR_URL,
                    "period_relation": _period_relation(meeting_end, start, window_end),
                }
            )
    return events


def _fetch_bls_release_events(start: date, window_end: date) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for year, month in _months_between(start, window_end):
        url = BLS_SCHEDULE_URL_TEMPLATE.format(year=year, month=month)
        lines = _html_lines(_fetch_text_url(url))
        for index, line in enumerate(lines):
            release_date = _parse_bls_date(line)
            if release_date is None or not start <= release_date <= window_end:
                continue
            time_or_title = _line_at(lines, index + 1)
            title = _line_at(lines, index + 2) if _looks_like_time(time_or_title) else time_or_title
            if not title or not _is_important_bls_release(title):
                continue
            events.append(
                {
                    "date": release_date.isoformat(),
                    "region": "US",
                    "title": title,
                    "name": title,
                    "importance": _macro_importance(title),
                    "summary": f"BLS scheduled release: {title}.",
                    "why_it_matters": _macro_reason(title),
                    "source": "BLS release calendar",
                    "source_url": url,
                    "period_relation": _period_relation(release_date, start, window_end),
                }
            )
    return events


def _fetch_bea_release_events(start: date, window_end: date) -> list[dict[str, Any]]:
    payload = _fetch_json_url(BEA_RELEASE_DATES_URL)
    events: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return events
    for title, value in payload.items():
        if not isinstance(value, dict) or not _is_important_bea_release(str(title)):
            continue
        for raw_date in value.get("release_dates") or []:
            release_date = _parse_iso_date(raw_date)
            if release_date is None or not start <= release_date <= window_end:
                continue
            events.append(
                {
                    "date": release_date.isoformat(),
                    "region": "US",
                    "title": str(title),
                    "name": str(title),
                    "importance": _macro_importance(str(title)),
                    "summary": f"BEA scheduled release: {title}.",
                    "why_it_matters": _macro_reason(str(title)),
                    "source": "BEA release schedule",
                    "source_url": BEA_RELEASE_DATES_URL,
                    "period_relation": _period_relation(release_date, start, window_end),
                }
            )
    return events


def _fetch_gdelt_articles(
    terms: tuple[str, ...],
    *,
    start: date,
    end: date,
    max_records: int,
) -> list[dict[str, Any]]:
    payload = _fetch_json_url(_gdelt_query_url(terms, start=start, end=end, max_records=max_records))
    articles = payload.get("articles") if isinstance(payload, dict) else []
    if not isinstance(articles, list):
        return []
    result: list[dict[str, Any]] = []
    for article in articles[:max_records]:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        if not title or not url:
            continue
        result.append(
            {
                "title": title,
                "publisher": article.get("domain") or article.get("sourceCountry") or "",
                "published_at": _gdelt_date(article.get("seendate")),
                "url": url,
            }
        )
    return result


def _fetch_google_news_articles(
    terms: tuple[str, ...],
    *,
    start: date,
    end: date,
    max_records: int,
) -> list[dict[str, Any]]:
    url = _google_news_query_url(terms, start=start, end=end)
    root = ET.fromstring(_fetch_text_url(url, timeout=8))
    result: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:max_records]:
        title = _xml_text(item, "title")
        link = _xml_text(item, "link")
        published_at = _rss_date(_xml_text(item, "pubDate"))
        if published_at:
            article_date = _parse_iso_date(published_at)
            if article_date is not None and not start <= article_date <= end:
                continue
        if not title or not link:
            continue
        result.append(
            {
                "title": title,
                "publisher": _xml_text(item, "source"),
                "published_at": published_at,
                "url": link,
                "source": "google_news.rss",
            }
        )
    return result


def _all_theme_terms() -> tuple[str, ...]:
    terms: list[str] = []
    for definition in DEFAULT_THEME_QUERIES:
        terms.extend(str(term) for term in definition["terms"])
    return tuple(dict.fromkeys(terms))


def _theme_articles(articles: list[dict[str, Any]], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    return [article for article in articles if _article_matches_terms(article, terms)]


def _article_matches_terms(article: dict[str, Any], terms: tuple[str, ...]) -> bool:
    haystack = " ".join(
        str(article.get(key) or "")
        for key in ("title", "publisher", "url")
    ).lower()
    return any(str(term).lower() in haystack for term in terms)


def _theme_source(articles: list[dict[str, Any]]) -> str:
    sources = {str(article.get("source") or "gdelt.doc") for article in articles}
    if not sources:
        return "gdelt.doc"
    return "/".join(sorted(sources))


def _theme_source_url(articles: list[dict[str, Any]], terms: tuple[str, ...], *, start: date, end: date) -> str:
    source = _theme_source(articles)
    if source == "google_news.rss":
        return _google_news_query_url(terms, start=start, end=end)
    return _gdelt_query_url(terms, start=start, end=end, max_records=8)


def _google_news_query_url(terms: tuple[str, ...], *, start: date, end: date) -> str:
    query = " OR ".join(_gdelt_term(term) for term in terms)
    params = {
        "q": f"{query} after:{start.isoformat()} before:{(end + timedelta(days=1)).isoformat()}",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    return f"{GOOGLE_NEWS_RSS_URL}?{urlencode(params)}"


def _xml_text(item: ET.Element, name: str) -> str:
    child = item.find(name)
    return str(child.text or "").strip() if child is not None else ""


def _rss_date(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        return datetime.strptime(text, "%a, %d %b %Y %H:%M:%S %Z").date().isoformat()
    except ValueError:
        return text


def _fetch_hk_ipo_opportunities(*, start: date, window_end: date) -> list[dict[str, Any]]:
    snapshot = get_hk_ipo_list(include_orders=False)
    items: list[dict[str, Any]] = []
    for ipo in snapshot.ipos:
        code = str(ipo.get("code") or "").strip()
        name = str(ipo.get("name") or "").strip() or code
        list_date = _parse_fuzzy_date(ipo.get("list_time"))
        apply_end = _parse_fuzzy_date(ipo.get("apply_end_time"))
        target_date = apply_end or list_date
        if target_date is None or not start <= target_date <= window_end:
            continue
        status = str(ipo.get("is_subscribe_status") or "").strip() or "unknown"
        items.append(
            {
                "category": "hk_ipo",
                "type": "新股",
                "title": f"{name} {code} 港股 IPO",
                "item": f"{name} {code}",
                "effective_date": target_date.isoformat(),
                "affected_symbols": [code] if code else [],
                "portfolio_relevance": "港股新股申购/上市窗口，适合单独判断是否参与。",
                "reason": f"富途 IPO 列表状态：{status}；申购截止 {ipo.get('apply_end_time') or 'n/a'}，上市 {ipo.get('list_time') or 'n/a'}。",
                "summary": f"富途 IPO 列表：{status}；申购截止 {ipo.get('apply_end_time') or 'n/a'}，上市 {ipo.get('list_time') or 'n/a'}。",
                "needs_decision": "是" if _is_subscribable_status(status) else "否",
                "source": "futu.get_ipo_list",
                "source_url": "https://openapi.futunn.com/futu-api-doc/en/quote/get-ipo-list.html",
            }
        )
    return items


def _scheduled_opportunity_windows(*, start: date, window_end: date) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if start.month <= 12 <= window_end.month and start.year == window_end.year:
        items.append(
            {
                "category": "nasdaq_100_rebalance_window",
                "type": "指数调整",
                "title": "Nasdaq-100 annual reconstitution watch window",
                "item": "Nasdaq-100 annual reconstitution watch window",
                "effective_date": date(start.year, 12, 1).isoformat(),
                "portfolio_relevance": "可能影响大型科技、AI 成长和相关 ETF 成分权重。",
                "reason": "官方方法论定义 Nasdaq-100 年度重构/再平衡流程；进入 12 月需要关注公告和成分调整。",
                "summary": "Nasdaq-100 年度重构观察窗口，需关注官方公告。",
                "needs_decision": "否",
                "source": "nasdaq100.methodology",
                "source_url": NASDAQ_100_METHODOLOGY_URL,
            }
        )
    if _window_crosses_quarter_end(start, window_end):
        items.append(
            {
                "category": "stock_connect_review_window",
                "type": "互联互通",
                "title": "Stock Connect eligible securities list review window",
                "item": "Stock Connect eligible securities list review window",
                "effective_date": _quarter_end_inside(start, window_end).isoformat(),
                "portfolio_relevance": "可能影响港股/A 股互联互通流动性和南向资金可买范围。",
                "reason": "进入季末名单观察窗口，需检查官方互联互通可买证券列表是否变化。",
                "summary": "互联互通名单观察窗口，需检查官方列表变化。",
                "needs_decision": "否",
                "source": "sse.stock_connect_eligible",
                "source_url": SSE_STOCK_CONNECT_URL,
            }
        )
    return items


def _fetch_text_url(url: str, *, timeout: int = 10) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 InvestmentKnowledgeWeeklyReview/1.0",
            "Accept": "application/json,text/html,text/calendar,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout, context=_https_context()) as response:
        return response.read().decode("utf-8", errors="replace")


def _fetch_json_url(url: str, *, timeout: int = 10) -> Any:
    return json.loads(_fetch_text_url(url, timeout=timeout))


def _https_context() -> ssl.SSLContext:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is not None:
        return _SSL_CONTEXT
    try:
        import certifi

        _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT


def _gdelt_query_url(terms: tuple[str, ...], *, start: date, end: date, max_records: int) -> str:
    query = " OR ".join(_gdelt_term(term) for term in terms)
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "sort": "hybridrel",
        "startdatetime": f"{start:%Y%m%d}000000",
        "enddatetime": f"{end:%Y%m%d}235959",
    }
    return f"{GDELT_DOC_API_URL}?{urlencode(params)}"


def _gdelt_term(term: str) -> str:
    return f'"{term}"' if " " in term else term


def _html_lines(value: str) -> list[str]:
    text = re.sub(r"(?is)<(script|style).*?</\\1>", " ", value)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    return [unescape(line).strip() for line in text.splitlines() if unescape(line).strip()]


def _section_lines(lines: list[str], start_marker: str, repeated_marker: str) -> list[str]:
    start_index = next((index for index, line in enumerate(lines) if start_marker in line), None)
    if start_index is None:
        return []
    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        if repeated_marker in lines[index] and start_marker not in lines[index]:
            end_index = index
            break
    return lines[start_index + 1 : end_index]


def _line_at(lines: list[str], index: int) -> str:
    return lines[index].strip() if 0 <= index < len(lines) else ""


def _months_between(start: date, end: date) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        result.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def _parse_bls_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%A, %B %d, %Y").date()
    except ValueError:
        return None


def _parse_iso_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_fuzzy_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text[: len(pattern)], pattern).date()
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def _gdelt_date(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _looks_like_time(value: str) -> bool:
    return bool(re.match(r"^\d{1,2}:\d{2}\s*(AM|PM)$", value.strip(), re.IGNORECASE))


def _is_important_bls_release(title: str) -> bool:
    return any(marker.lower() in title.lower() for marker in BLS_IMPORTANT_RELEASES)


def _is_important_bea_release(title: str) -> bool:
    return any(marker.lower() in title.lower() for marker in BEA_IMPORTANT_RELEASES)


def _macro_importance(title: str) -> str:
    lower = title.lower()
    if any(marker in lower for marker in ("fomc", "consumer price", "employment situation", "gross domestic product", "personal income")):
        return "high"
    if any(marker in lower for marker in ("producer price", "job openings", "corporate profits")):
        return "medium"
    return "low"


def _macro_reason(title: str) -> str:
    lower = title.lower()
    if "consumer price" in lower or "producer price" in lower or "personal income" in lower:
        return "Inflation and income data affect rates, USD, and long-duration growth valuation."
    if "employment" in lower or "job openings" in lower:
        return "Labor-market data affects Fed expectations, risk appetite, and growth-stock duration."
    if "gross domestic product" in lower or "corporate profits" in lower:
        return "Growth and profit data affects broad market earnings expectations."
    if "fomc" in lower:
        return "Fed policy affects rates, liquidity, and market risk appetite."
    return "Macro data point that can affect rates, liquidity, or risk appetite."


def _period_relation(event_date: date, start: date, window_end: date) -> str:
    if start <= event_date <= start + timedelta(days=6):
        return "review_week"
    if start + timedelta(days=7) <= event_date <= window_end:
        return "next_two_weeks"
    return "context_window"


def _date_windows_overlap(left_start: date, left_end: date, right_start: date, right_end: date) -> bool:
    return left_start <= right_end and right_start <= left_end


def _heat_change(*, current_count: int, previous_count: int) -> str:
    if current_count >= previous_count * 1.5 and current_count >= 3:
        return "up"
    if previous_count >= current_count * 1.5 and previous_count >= 3:
        return "down"
    return "flat"


def _heat_change_text(value: str) -> str:
    return {"up": "上升", "down": "下降", "flat": "持平"}.get(value, value)


def _theme_confidence(*, current_count: int, previous_count: int) -> str:
    if current_count >= 6 and current_count >= previous_count:
        return "high"
    if current_count >= 2:
        return "medium"
    return "low"


def _is_subscribable_status(value: str) -> bool:
    return any(marker in value.lower() for marker in ("sub", "可", "认购", "subscribe", "applying"))


def _window_crosses_quarter_end(start: date, window_end: date) -> bool:
    return any(start <= candidate <= window_end for candidate in _quarter_ends(start.year, window_end.year))


def _quarter_end_inside(start: date, window_end: date) -> date:
    for candidate in _quarter_ends(start.year, window_end.year):
        if start <= candidate <= window_end:
            return candidate
    return window_end


def _quarter_ends(start_year: int, end_year: int) -> list[date]:
    return [date(year, month, day) for year in range(start_year, end_year + 1) for month, day in ((3, 31), (6, 30), (9, 30), (12, 31))]


def _dedupe_items(items: list[dict[str, Any]], *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        marker = tuple(item.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def _status_from_items(
    items: list[dict[str, Any]],
    *,
    cached: bool,
    provider: str | None,
    reason: str | None = None,
    fetched_at: str | None = None,
    status_override: str | None = None,
) -> dict[str, Any]:
    status = status_override or ("cached" if cached and items else ("ok" if items else "missing"))
    result: dict[str, Any] = {
        "status": status,
        "count": len(items),
        "provider": provider or "unknown",
        "cached": cached,
    }
    if reason:
        result["reason"] = reason
    if fetched_at:
        result["fetched_at"] = fetched_at
    return result


def _cache_is_valid(row: dict[str, Any]) -> bool:
    expires_at = row.get("expires_at")
    if not expires_at:
        return True
    try:
        expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)


def _token_total(token_usage: dict[str, Any]) -> int:
    for key in ("total_tokens", "tokens"):
        value = _int_or_none(token_usage.get(key))
        if value is not None:
            return value
    return sum(
        _int_or_none(token_usage.get(key)) or 0
        for key in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens")
    )


def _int_env(name: str) -> int | None:
    return _int_or_none(os.getenv(name))


def _float_env(name: str) -> float | None:
    return _float_or_none(os.getenv(name))


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
