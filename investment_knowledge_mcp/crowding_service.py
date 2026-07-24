"""Bounded orchestration for single-symbol and portfolio crowding research."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
import math
import re
from typing import Any
from zoneinfo import ZoneInfo

from investment_knowledge_mcp.crowding_intelligence import (
    CrowdingAssessment,
    build_crowding_assessment,
)
from investment_knowledge_mcp.data_sources.contracts import (
    DataRequest,
    DataResult,
    SourceCapability,
    SourcePlan,
)
from investment_knowledge_mcp.data_sources.crowding import default_crowding_source_pool
from investment_knowledge_mcp.data_sources.market_bars import default_market_bar_pool
from investment_knowledge_mcp.data_sources.pool import DataSourcePool, MemoryResultCache


_SUPPORTED_MARKETS = frozenset({"US", "HK", "KR", "CN"})
_SCORABLE_MARKETS = frozenset({"US", "HK"})
_EVIDENCE_CAPABILITIES = (
    SourceCapability.OWNERSHIP_CONCENTRATION,
    SourceCapability.SHORT_INTEREST,
    SourceCapability.OPTIONS_POSITIONING,
    SourceCapability.EVENT_CALENDAR,
)
_SAFE_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9._-]*")
_MARKET_SESSION_RULES = {
    "US": (ZoneInfo("America/New_York"), time(16, 30)),
    "HK": (ZoneInfo("Asia/Hong_Kong"), time(16, 30)),
    "CN": (ZoneInfo("Asia/Shanghai"), time(15, 30)),
    "KR": (ZoneInfo("Asia/Seoul"), time(15, 45)),
}


@dataclass(frozen=True)
class CrowdingTarget:
    market: str
    symbol: str
    canonical: str
    provider_code: str


@dataclass(frozen=True)
class PortfolioCrowdingEntry:
    canonical: str
    name: str
    market: str
    currency: str
    market_value: float
    assessment: CrowdingAssessment


@dataclass(frozen=True)
class PortfolioCrowdingReport:
    as_of: date
    assessments: tuple[PortfolioCrowdingEntry, ...]
    by_market: Mapping[str, tuple[PortfolioCrowdingEntry, ...]]
    omitted_count: int
    failures: tuple[str, ...]


def normalize_crowding_target(symbol: str, market: str) -> CrowdingTarget:
    raw_market = _clean_text(market, "market").upper()
    raw_symbol = _clean_text(symbol, "symbol").upper()
    if "." in raw_symbol and raw_symbol.split(".", 1)[0] in {"US", "HK", "KR", "CN", "SH", "SZ"}:
        prefix, unqualified = raw_symbol.split(".", 1)
        if raw_market in {"CN", "SH", "SZ"} and prefix in {"CN", "SH", "SZ"}:
            raw_market = prefix if prefix in {"SH", "SZ"} else raw_market
            raw_symbol = unqualified
        elif prefix == raw_market:
            raw_symbol = unqualified
        else:
            raise ValueError("symbol market does not match requested market")

    provider_market = raw_market
    product_market = "CN" if raw_market in {"CN", "SH", "SZ"} else raw_market
    if product_market not in _SUPPORTED_MARKETS:
        raise ValueError("unsupported market")
    if product_market == "HK" and raw_symbol.isdigit():
        raw_symbol = raw_symbol.zfill(5)
    if product_market in {"CN", "KR"} and raw_symbol.isdigit():
        raw_symbol = raw_symbol.zfill(6)
    if not _SAFE_SYMBOL.fullmatch(raw_symbol):
        raise ValueError("invalid symbol")

    if product_market == "CN":
        if provider_market not in {"SH", "SZ"}:
            provider_market = _infer_cn_exchange(raw_symbol)
        provider_code = f"{provider_market}.{raw_symbol}"
    else:
        provider_code = f"{product_market}.{raw_symbol}"
    return CrowdingTarget(
        market=product_market,
        symbol=raw_symbol,
        canonical=f"{product_market}.{raw_symbol}",
        provider_code=provider_code,
    )


def futu_only_plan(capability: SourceCapability) -> SourcePlan:
    source_id = "futu" if capability is SourceCapability.MARKET_BARS else "futu_crowding"
    return SourcePlan(
        capability,
        preferred_sources=(source_id,),
        allowed_sources=(source_id,),
        fallback_sources=(),
        required=False,
        partial_allowed=True,
    )


def investigate_symbol_crowding(
    symbol: str,
    market: str,
    *,
    as_of: date | None = None,
    bars_pool: DataSourcePool | None = None,
    evidence_pool: DataSourcePool | None = None,
) -> CrowdingAssessment:
    request_end = as_of or resolve_latest_crowding_session_date(market)
    if not isinstance(request_end, date):
        raise ValueError("as_of must be a date")
    target = normalize_crowding_target(symbol, market)
    bars_registry = bars_pool or default_market_bar_pool(cache=MemoryResultCache())
    evidence_registry = evidence_pool or default_crowding_source_pool(cache=MemoryResultCache())

    bars_request = DataRequest(
        SourceCapability.MARKET_BARS,
        target.market,
        (target.provider_code,),
        request_end - timedelta(days=400),
        request_end,
        "end_of_day",
        ("date", "close", "volume"),
    )
    bars_result = bars_registry.fetch(
        bars_request,
        futu_only_plan(SourceCapability.MARKET_BARS),
    )
    if target.provider_code != target.canonical:
        bars_result = _remap_result_symbol(bars_result, target.provider_code, target.canonical)
    effective_date = (
        as_of
        or resolve_latest_crowding_session_date(
            target.market,
            available_sessions=_bar_session_dates(bars_result, target.canonical),
        )
    )

    family_results: dict[SourceCapability, DataResult] = {}
    if target.market in _SCORABLE_MARKETS:
        evidence_start = effective_date
        evidence_end = effective_date + timedelta(days=14)
        for capability in _EVIDENCE_CAPABILITIES:
            request = DataRequest(
                capability,
                target.market,
                (target.provider_code,),
                evidence_start,
                evidence_end,
                "end_of_day",
                (),
            )
            family_results[capability] = evidence_registry.fetch(
                request,
                futu_only_plan(capability),
            )

    return build_crowding_assessment(
        target.symbol,
        target.market,
        bars_result,
        family_results,
        as_of=effective_date,
    )


def investigate_portfolio_crowding(
    positions: Sequence[Mapping[str, Any]],
    *,
    as_of: date | None = None,
    max_positions: int = 8,
    analyzer: Callable[..., CrowdingAssessment] | None = None,
) -> PortfolioCrowdingReport:
    effective_date = as_of or datetime.now(timezone.utc).date()
    if not isinstance(max_positions, int) or isinstance(max_positions, bool) or max_positions <= 0:
        raise ValueError("max_positions must be a positive integer")
    analyze = analyzer or investigate_symbol_crowding
    failures: list[str] = []
    unique: dict[str, dict[str, Any]] = {}
    if not isinstance(positions, Sequence) or isinstance(positions, (str, bytes)):
        positions = ()

    for position in positions:
        normalized = _normalize_position(position, failures)
        if normalized is None:
            continue
        existing = unique.get(normalized["canonical"])
        if existing is None or normalized["market_value"] > existing["market_value"]:
            unique[normalized["canonical"]] = normalized

    ordered = _bounded_group_order(tuple(unique.values()), max_positions)
    omitted_count = max(0, len(unique) - len(ordered))
    entries: list[PortfolioCrowdingEntry] = []
    for item in ordered:
        try:
            assessment = analyze(
                item["symbol"],
                item["market"],
                as_of=as_of,
            )
        except Exception:
            failures.append(f"analysis_failed:{item['canonical']}")
            continue
        if not isinstance(assessment, CrowdingAssessment):
            failures.append(f"analysis_contract_error:{item['canonical']}")
            continue
        entries.append(
            PortfolioCrowdingEntry(
                canonical=item["canonical"],
                name=item["name"],
                market=item["market"],
                currency=item["currency"],
                market_value=item["market_value"],
                assessment=assessment,
            )
        )

    by_market: dict[str, tuple[PortfolioCrowdingEntry, ...]] = {}
    for market in sorted({entry.market for entry in entries}):
        by_market[market] = tuple(entry for entry in entries if entry.market == market)
    return PortfolioCrowdingReport(
        as_of=effective_date,
        assessments=tuple(entries),
        by_market=by_market,
        omitted_count=omitted_count,
        failures=tuple(dict.fromkeys(failures)),
    )


def render_portfolio_crowding(report: PortfolioCrowdingReport) -> str:
    lines = [
        "## 持仓拥挤交易情报",
        f"- 报告日期：{report.as_of.isoformat()}",
        "- 结果按市场分组；不同市场的数据覆盖和口径不可直接比较。",
    ]
    if not report.by_market:
        lines.append("- 没有可分析的持仓。")
    for market, entries in report.by_market.items():
        mode = "可评分" if market in _SCORABLE_MARKETS else "证据模式"
        lines.extend(["", f"### {market}（{mode}）"])
        for entry in entries:
            assessment = entry.assessment
            contributors = (
                assessment.long_crowding.contributors
                or assessment.short_squeeze.contributors
                or assessment.speculative_attention.contributors
            )
            current_families = tuple(
                family.name
                for family in assessment.families
                if family.current
            )
            minimum_coverage = min(
                (family.coverage for family in assessment.families),
                default=0.0,
            )
            lines.append(
                f"- {entry.name}（{entry.canonical}）："
                f"多头={assessment.long_crowding.band.value}；"
                f"空头/挤压={assessment.short_squeeze.band.value}；"
                f"关注={assessment.speculative_attention.band.value}；"
                f"证据质量={assessment.evidence_quality.value}；"
                f"市场交易日={assessment.as_of.isoformat()}；"
                f"覆盖率下限={minimum_coverage:.2f}；"
                f"当前families={','.join(current_families) or 'none'}；"
                f"主要证据={(contributors[0] if contributors else '无')}；"
                f"缺失={','.join(assessment.missing_families) or 'none'}；"
                f"数据源状态={','.join(assessment.provider_failures) or 'ok'}"
            )
    if report.omitted_count:
        lines.extend(["", f"- 受单次最多 8 个持仓限制，另有 {report.omitted_count} 个有效持仓未分析。"])
    if report.failures:
        lines.append("- 降级状态：" + ", ".join(report.failures))
    lines.extend(
        [
            "",
            "> “拥挤”表示多信号证据下的启发式可能性，不是投资建议，也不构成任何交易指令。",
        ]
    )
    return "\n".join(lines)


def _normalize_position(
    position: Mapping[str, Any],
    failures: list[str],
) -> dict[str, Any] | None:
    if not isinstance(position, Mapping):
        failures.append("malformed_position")
        return None
    code = str(position.get("code") or "").strip().upper()
    market = str(position.get("market") or "").strip().upper()
    symbol = str(position.get("symbol") or "").strip().upper()
    if code and "." in code:
        market, symbol = code.split(".", 1)
    if not market or not symbol:
        failures.append("malformed_position")
        return None
    try:
        target = normalize_crowding_target(symbol, market)
    except ValueError:
        normalized_market = "CN" if market in {"SH", "SZ"} else market
        failures.append(
            f"unsupported_market:{normalized_market}"
            if normalized_market not in _SUPPORTED_MARKETS
            else "malformed_position"
        )
        return None
    market_value = _number(position.get("market_val", position.get("market_value")))
    currency = str(position.get("currency") or _default_currency(target.market)).strip().upper()
    name = str(position.get("stock_name") or position.get("name") or target.canonical).strip()
    return {
        "canonical": target.canonical,
        "market": target.market,
        "symbol": target.symbol,
        "name": name or target.canonical,
        "market_value": market_value,
        "currency": currency or "UNKNOWN",
    }


def _bounded_group_order(
    positions: tuple[dict[str, Any], ...],
    limit: int,
) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in positions:
        grouped[(item["market"], item["currency"])].append(item)
    queues: dict[tuple[str, str], deque[dict[str, Any]]] = {}
    for key in sorted(grouped):
        queues[key] = deque(
            sorted(
                grouped[key],
                key=lambda item: (-item["market_value"], item["canonical"]),
            )
        )
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(queues.values()):
        for key in sorted(queues):
            if queues[key] and len(selected) < limit:
                selected.append(queues[key].popleft())
    return tuple(selected)


def _remap_result_symbol(result: DataResult, provider_code: str, canonical: str) -> DataResult:
    records = []
    for record in result.records:
        if isinstance(record, Mapping) and str(record.get("symbol") or "").upper() == provider_code:
            records.append({**dict(record), "symbol": canonical})
        else:
            records.append(record)
    return replace(result, records=tuple(records))


def _infer_cn_exchange(symbol: str) -> str:
    if not symbol.isdigit():
        raise ValueError("CN symbols require an SH or SZ exchange prefix")
    return "SH" if symbol.startswith(("5", "6", "9")) else "SZ"


def resolve_latest_crowding_session_date(
    market: str,
    *,
    now: datetime | None = None,
    available_sessions: Sequence[date] = (),
) -> date:
    normalized_market = "CN" if market.strip().upper() in {"SH", "SZ"} else market.strip().upper()
    if normalized_market not in _MARKET_SESSION_RULES:
        raise ValueError("unsupported market")
    market_timezone, close_time = _MARKET_SESSION_RULES[normalized_market]
    current = (now or datetime.now(timezone.utc)).astimezone(market_timezone)
    session_date = current.date()
    if current.time() < close_time:
        session_date -= timedelta(days=1)
    while session_date.weekday() >= 5:
        session_date -= timedelta(days=1)
    eligible_sessions = tuple(
        item
        for item in available_sessions
        if isinstance(item, date)
        and not isinstance(item, datetime)
        and item <= session_date
    )
    if eligible_sessions:
        return max(eligible_sessions)
    return session_date


def _bar_session_dates(result: DataResult, canonical: str) -> tuple[date, ...]:
    sessions: set[date] = set()
    for record in result.records:
        if (
            not isinstance(record, Mapping)
            or str(record.get("symbol") or "").upper() != canonical
        ):
            continue
        bars = record.get("bars")
        if not isinstance(bars, tuple):
            continue
        for bar in bars:
            if not isinstance(bar, Mapping):
                continue
            try:
                sessions.add(date.fromisoformat(str(bar.get("date"))[:10]))
            except ValueError:
                continue
    return tuple(sorted(sessions))


def _clean_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not (cleaned := value.strip()):
        raise ValueError(f"{field} must be non-empty")
    return cleaned


def _number(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _default_currency(market: str) -> str:
    return {"US": "USD", "HK": "HKD", "KR": "KRW", "CN": "CNY"}.get(market, "UNKNOWN")
