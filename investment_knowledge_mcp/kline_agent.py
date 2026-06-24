from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median
import math
import re
from typing import Any, Protocol

from investment_knowledge_mcp.config import AppConfig, get_config
from investment_knowledge_mcp.serialization import to_jsonable


RULE_VERSION = "kline-agent-v1.0"
DEFAULT_YEARS = 5
DEFAULT_ADJUST_TYPE = "forward_adjusted"

CURRENCY_BY_MARKET = {
    "US": "USD",
    "HK": "HKD",
    "CN": "CNY",
    "SH": "CNY",
    "SZ": "CNY",
    "KR": "KRW",
    "JP": "JPY",
}

TIMEZONE_BY_MARKET = {
    "US": "America/New_York",
    "HK": "Asia/Hong_Kong",
    "CN": "Asia/Shanghai",
    "SH": "Asia/Shanghai",
    "SZ": "Asia/Shanghai",
    "KR": "Asia/Seoul",
    "JP": "Asia/Tokyo",
}


class KlineProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class KlineBar:
    bar_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    turnover: float | None = None


@dataclass(frozen=True)
class KlineMetadata:
    provider: str
    provider_symbol: str
    symbol: str
    market: str
    currency: str
    timezone: str
    requested_start: date
    requested_end: date
    actual_start: date | None
    actual_end: date | None
    adjustment_type: str
    fetched_at: datetime
    raw_bar_count: int
    normalized_bar_count: int


@dataclass(frozen=True)
class KlineFetchResult:
    metadata: KlineMetadata
    bars: list[KlineBar]
    warnings: list[str]


@dataclass(frozen=True)
class KlineRequest:
    symbol: str
    market: str
    years: int = DEFAULT_YEARS
    adjust_type: str = DEFAULT_ADJUST_TYPE


@dataclass(frozen=True)
class PatternWindowStats:
    forward_window: int
    sample_count: int
    mean_forward_return: float | None
    median_forward_return: float | None
    win_rate: float | None
    best_sample: tuple[date, float] | None
    worst_sample: tuple[date, float] | None
    max_adverse_excursion: float | None
    confidence: str


@dataclass(frozen=True)
class PatternObservation:
    rule_id: str
    timeframe: str
    title: str
    current_status: str
    trigger_date: date | None
    details: str
    stats: list[PatternWindowStats]
    sufficient_evidence: bool
    watch_item: str


@dataclass(frozen=True)
class TimeframeAnalysis:
    timeframe: str
    bars: list[KlineBar]
    facts: list[str]
    observations: list[PatternObservation]
    evidence_limits: list[str]


@dataclass(frozen=True)
class KlineInvestigation:
    request: KlineRequest
    metadata: KlineMetadata | None
    data_warnings: list[str]
    timeframe_analyses: list[TimeframeAnalysis]
    provider_error: str | None = None


class HistoricalBarProvider(Protocol):
    def fetch_daily_bars(
        self,
        *,
        symbol: str,
        market: str,
        years: int,
        adjust_type: str,
    ) -> KlineFetchResult:
        ...


class FutuHistoricalBarProvider:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or get_config()

    def fetch_daily_bars(
        self,
        *,
        symbol: str,
        market: str,
        years: int,
        adjust_type: str,
    ) -> KlineFetchResult:
        try:
            import futu as ft
        except ImportError as exc:
            raise KlineProviderError("futu-api is not installed; cannot fetch historical Kline bars.") from exc

        provider_symbol = provider_symbol_for(symbol=symbol, market=market)
        requested_end = date.today()
        requested_start = requested_end - timedelta(days=max(1, years) * 366)
        quote_context = ft.OpenQuoteContext(host=self.config.futu_opend_host, port=self.config.futu_opend_port)
        rows: list[dict[str, Any]] = []
        page_req_key: Any = None
        try:
            for _ in range(30):
                kwargs = {
                    "code": provider_symbol,
                    "start": requested_start.isoformat(),
                    "end": requested_end.isoformat(),
                    "ktype": _enum_value(ft.KLType, "K_DAY"),
                    "autype": _futu_adjust_type(ft, adjust_type),
                    "max_count": 1000,
                    "page_req_key": page_req_key,
                }
                ret, data, page_req_key = _call_with_keyword_retry(quote_context.request_history_kline, kwargs)
                if ret != ft.RET_OK:
                    raise KlineProviderError(f"Futu historical Kline query failed: {data}")
                rows.extend(_records_from_provider_data(data))
                if page_req_key is None:
                    break
        except Exception as exc:
            if isinstance(exc, KlineProviderError):
                raise
            raise KlineProviderError(f"Futu historical Kline query failed: {exc}") from exc
        finally:
            quote_context.close()

        bars, warnings = normalize_bars(rows)
        metadata = KlineMetadata(
            provider="futu",
            provider_symbol=provider_symbol,
            symbol=symbol.upper(),
            market=market.upper(),
            currency=CURRENCY_BY_MARKET.get(market.upper(), "UNKNOWN"),
            timezone=TIMEZONE_BY_MARKET.get(market.upper(), "UNKNOWN"),
            requested_start=requested_start,
            requested_end=requested_end,
            actual_start=bars[0].bar_date if bars else None,
            actual_end=bars[-1].bar_date if bars else None,
            adjustment_type=normalize_adjust_type(adjust_type),
            fetched_at=datetime.now(timezone.utc),
            raw_bar_count=len(rows),
            normalized_bar_count=len(bars),
        )
        return KlineFetchResult(metadata=metadata, bars=bars, warnings=warnings)


def parse_kline_command(command: str) -> KlineRequest | None:
    cleaned = command.strip()
    match = re.fullmatch(r"(?:K线|k线|K線|k線|Kline|kline|K线调查|k线调查|K線調查|k線調查)\s+(.+)", cleaned)
    if match is None:
        return None

    parts = match.group(1).split()
    if not parts:
        return None

    symbol = ""
    market = ""
    option_parts: list[str] = []
    first = parts[0]
    if "." in first:
        market, symbol = first.split(".", 1)
        option_parts = parts[1:]
    elif len(parts) >= 2 and _looks_like_market(parts[1]):
        symbol = first
        market = parts[1]
        option_parts = parts[2:]
    else:
        return None

    years = DEFAULT_YEARS
    adjust_type = DEFAULT_ADJUST_TYPE
    option_text = " ".join(option_parts)
    year_match = re.search(r"(\d{1,2})\s*(?:年|y|yr|yrs|year|years)", option_text, flags=re.IGNORECASE)
    if year_match:
        years = max(1, min(20, int(year_match.group(1))))
    if re.search(r"不复权|不復權|raw|none", option_text, flags=re.IGNORECASE):
        adjust_type = "raw"
    elif re.search(r"后复权|後復權|backward|hfq", option_text, flags=re.IGNORECASE):
        adjust_type = "backward_adjusted"
    elif re.search(r"前复权|前復權|forward|qfq", option_text, flags=re.IGNORECASE):
        adjust_type = "forward_adjusted"

    return KlineRequest(symbol=symbol.upper(), market=normalize_market(market), years=years, adjust_type=adjust_type)


def inspect_kline_behavior(
    request: KlineRequest,
    provider: HistoricalBarProvider | None = None,
) -> KlineInvestigation:
    provider = provider or FutuHistoricalBarProvider()
    try:
        fetched = provider.fetch_daily_bars(
            symbol=request.symbol,
            market=request.market,
            years=request.years,
            adjust_type=request.adjust_type,
        )
    except KlineProviderError as exc:
        return KlineInvestigation(
            request=request,
            metadata=None,
            data_warnings=[],
            timeframe_analyses=[],
            provider_error=str(exc),
        )

    bars = fetched.bars
    data_warnings = list(fetched.warnings)
    data_warnings.extend(_gap_warnings(bars))
    if bars and bars[-1].bar_date == date.today():
        data_warnings.append("Latest daily bar is dated today and may be incomplete.")

    quality_penalty = _quality_penalty(data_warnings)
    daily = _analyze_timeframe(
        timeframe="daily",
        bars=bars,
        windows=[5, 20, 60],
        quality_penalty=quality_penalty,
    )
    weekly = _analyze_timeframe(
        timeframe="weekly",
        bars=aggregate_bars(bars, "weekly"),
        windows=[4, 12, 26],
        quality_penalty=quality_penalty,
    )
    monthly = _analyze_timeframe(
        timeframe="monthly",
        bars=aggregate_bars(bars, "monthly"),
        windows=[3, 6, 12],
        quality_penalty=quality_penalty,
    )
    return KlineInvestigation(
        request=request,
        metadata=fetched.metadata,
        data_warnings=data_warnings,
        timeframe_analyses=[daily, weekly, monthly],
    )


def render_kline_report(result: KlineInvestigation) -> str:
    request = result.request
    lines = [f"Kline investigation: {request.market}.{request.symbol}"]
    lines.append("")
    lines.append("Safety: read-only market-behavior evidence; no trading actions or order/allocation instructions.")

    lines.append("")
    lines.append("Metadata")
    if result.metadata is None:
        lines.extend(
            [
                f"- Symbol: {request.symbol}",
                f"- Market: {request.market}",
                f"- Adjustment: {normalize_adjust_type(request.adjust_type)}",
                f"- Requested range: {request.years} years",
                "- Provider: unavailable",
            ]
        )
    else:
        meta = result.metadata
        lines.extend(
            [
                f"- Provider: {meta.provider}",
                f"- Provider symbol: {meta.provider_symbol}",
                f"- Symbol: {meta.symbol}",
                f"- Market: {meta.market}",
                f"- Currency: {meta.currency}",
                f"- Timezone: {meta.timezone}",
                f"- Adjustment: {meta.adjustment_type}",
                f"- Requested date range: {meta.requested_start.isoformat()} to {meta.requested_end.isoformat()}",
                f"- Actual date range: {_format_optional_date(meta.actual_start)} to {_format_optional_date(meta.actual_end)}",
                f"- Fetched at: {meta.fetched_at.isoformat()}",
                f"- Bar count: raw={meta.raw_bar_count}, normalized={meta.normalized_bar_count}",
                f"- Rule version: {RULE_VERSION}",
            ]
        )

    lines.append("")
    lines.append("Data Quality")
    warnings = list(result.data_warnings)
    if result.provider_error:
        warnings.append(f"Provider limitation: {result.provider_error}")
    if warnings:
        lines.extend(f"- Warning: {warning}" for warning in warnings)
    else:
        lines.append("- No blocking data-quality warnings detected.")

    if result.provider_error:
        lines.append("")
        lines.append("Evidence Limits")
        lines.append("- Insufficient evidence: no provider bars were available, so deterministic rules and sample statistics were not computed.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Facts")
    for analysis in result.timeframe_analyses:
        lines.append(f"- {analysis.timeframe.title()}: " + ("; ".join(analysis.facts) if analysis.facts else "No bars available."))

    lines.append("")
    lines.append("Statistics")
    any_observation = False
    for analysis in result.timeframe_analyses:
        shown = analysis.observations[:6]
        if not shown:
            lines.append(f"- {analysis.timeframe.title()}: insufficient current deterministic observations.")
            continue
        any_observation = True
        lines.append(f"- {analysis.timeframe.title()}:")
        for observation in shown:
            suffix = "" if observation.sufficient_evidence else " (insufficient evidence)"
            lines.append(f"  - {observation.title}{suffix}: {observation.current_status}. {observation.details}")
            for stat in observation.stats:
                lines.append(
                    "    "
                    + f"{stat.forward_window} bars: samples={stat.sample_count}, "
                    + f"mean={_format_pct(stat.mean_forward_return)}, "
                    + f"median={_format_pct(stat.median_forward_return)}, "
                    + f"win_rate={_format_pct(stat.win_rate)}, "
                    + f"best={_format_sample(stat.best_sample)}, "
                    + f"worst={_format_sample(stat.worst_sample)}, "
                    + f"adverse={_format_pct(stat.max_adverse_excursion)}, "
                    + f"confidence={stat.confidence}"
                )
    if not any_observation:
        lines.append("- Insufficient evidence: no deterministic current-state observations passed V1 display thresholds.")

    lines.append("")
    lines.append("Interpretation")
    interpretations = _interpretations(result.timeframe_analyses)
    if interpretations:
        lines.extend(f"- {item}" for item in interpretations)
    else:
        lines.append("- Evidence is too thin for a directional market-behavior interpretation.")

    lines.append("")
    lines.append("Watch Items")
    watch_items = _watch_items(result.timeframe_analyses)
    if watch_items:
        lines.extend(f"- {item}" for item in watch_items[:8])
    else:
        lines.append("- Monitor whether future bars create deterministic rule triggers with enough historical samples.")

    lines.append("")
    lines.append("Evidence Limits")
    limits = []
    for analysis in result.timeframe_analyses:
        limits.extend(analysis.evidence_limits)
    if limits:
        lines.extend(f"- {limit}" for limit in dict.fromkeys(limits))
    else:
        lines.append("- Statistics describe this symbol's historical bar behavior only; they do not prove causality or forecast returns.")
    return "\n".join(lines)


def investigate_kline_behavior(
    request: KlineRequest,
    provider: HistoricalBarProvider | None = None,
) -> str:
    return render_kline_report(inspect_kline_behavior(request, provider=provider))


def normalize_bars(rows: list[dict[str, Any]]) -> tuple[list[KlineBar], list[str]]:
    warnings: list[str] = []
    bars_by_date: dict[date, KlineBar] = {}
    for row in rows:
        item = to_jsonable(row)
        bar_date = _parse_bar_date(item)
        if bar_date is None:
            warnings.append(f"Dropped row without parseable date: {item}")
            continue
        try:
            bar = KlineBar(
                bar_date=bar_date,
                open=float(item.get("open")),
                high=float(item.get("high")),
                low=float(item.get("low")),
                close=float(item.get("close")),
                volume=_optional_float(item.get("volume")),
                turnover=_optional_float(item.get("turnover")),
            )
        except (TypeError, ValueError):
            warnings.append(f"Dropped row with non-numeric OHLC values on {bar_date.isoformat()}.")
            continue
        if bar.high < bar.low or bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            warnings.append(f"Dropped impossible OHLC row on {bar_date.isoformat()}.")
            continue
        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            warnings.append(f"Dropped non-positive OHLC row on {bar_date.isoformat()}.")
            continue
        if bar_date in bars_by_date:
            warnings.append(f"Duplicate date {bar_date.isoformat()} detected; kept first row.")
            continue
        bars_by_date[bar_date] = bar
    return [bars_by_date[key] for key in sorted(bars_by_date)], warnings


def aggregate_bars(bars: list[KlineBar], period: str) -> list[KlineBar]:
    grouped: dict[tuple[int, int], list[KlineBar]] = {}
    for bar in bars:
        if period == "weekly":
            year, week, _ = bar.bar_date.isocalendar()
            key = (year, week)
        elif period == "monthly":
            key = (bar.bar_date.year, bar.bar_date.month)
        else:
            raise ValueError(f"Unsupported aggregate period: {period}")
        grouped.setdefault(key, []).append(bar)

    aggregated: list[KlineBar] = []
    for key in sorted(grouped):
        group = sorted(grouped[key], key=lambda item: item.bar_date)
        aggregated.append(
            KlineBar(
                bar_date=group[-1].bar_date,
                open=group[0].open,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=group[-1].close,
                volume=_sum_optional(item.volume for item in group),
                turnover=_sum_optional(item.turnover for item in group),
            )
        )
    return aggregated


def provider_symbol_for(*, symbol: str, market: str) -> str:
    market = normalize_market(market)
    symbol = symbol.upper()
    if "." in symbol:
        left, right = symbol.split(".", 1)
        return f"{left.upper()}.{right.upper()}"
    if market == "CN":
        if symbol.startswith(("6", "9")):
            return f"SH.{symbol}"
        return f"SZ.{symbol}"
    return f"{market}.{symbol}"


def normalize_market(market: str) -> str:
    cleaned = market.strip().upper()
    aliases = {"A": "CN", "A股": "CN", "CN": "CN", "沪深": "CN"}
    return aliases.get(cleaned, cleaned)


def normalize_adjust_type(adjust_type: str) -> str:
    cleaned = adjust_type.strip().lower()
    aliases = {
        "qfq": "forward_adjusted",
        "forward": "forward_adjusted",
        "front": "forward_adjusted",
        "前复权": "forward_adjusted",
        "hfq": "backward_adjusted",
        "backward": "backward_adjusted",
        "后复权": "backward_adjusted",
        "none": "raw",
        "no": "raw",
        "raw": "raw",
        "不复权": "raw",
    }
    return aliases.get(cleaned, cleaned or DEFAULT_ADJUST_TYPE)


def _analyze_timeframe(
    *,
    timeframe: str,
    bars: list[KlineBar],
    windows: list[int],
    quality_penalty: int,
) -> TimeframeAnalysis:
    facts = _facts_for(timeframe, bars)
    limits: list[str] = []
    if len(bars) < max(30, max(windows) + 5):
        limits.append(f"{timeframe.title()} has only {len(bars)} bars, so historical samples are weak.")

    observations: list[PatternObservation] = []
    observations.extend(_high_observations(timeframe, bars, windows, quality_penalty))
    observations.extend(_moving_average_observations(timeframe, bars, windows, quality_penalty))
    if timeframe == "daily":
        observations.extend(_volume_observations(bars, windows, quality_penalty))
        observations.extend(_gap_observations(bars, windows, quality_penalty))
    observations.extend(_streak_observations(timeframe, bars, windows, quality_penalty))
    observations.extend(_drawdown_observations(timeframe, bars, windows, quality_penalty))

    if not observations:
        limits.append(f"{timeframe.title()} did not have enough current deterministic triggers to show pattern statistics.")
    return TimeframeAnalysis(timeframe=timeframe, bars=bars, facts=facts, observations=observations, evidence_limits=limits)


def _facts_for(timeframe: str, bars: list[KlineBar]) -> list[str]:
    if not bars:
        return []
    latest = bars[-1]
    facts = [
        f"{len(bars)} bars from {bars[0].bar_date.isoformat()} to {latest.bar_date.isoformat()}",
        f"latest close {latest.close:.2f}",
    ]
    for period in _ma_periods(timeframe):
        ma_value = _ma_at(bars, len(bars) - 1, period)
        if ma_value is not None:
            facts.append(f"close is {_format_pct(latest.close / ma_value - 1)} from {period}-bar average")
    lookback = min(len(bars), 252 if timeframe == "daily" else 52 if timeframe == "weekly" else 12)
    recent_high = max(bar.high for bar in bars[-lookback:])
    facts.append(f"drawdown from recent high is {_format_pct(latest.close / recent_high - 1)}")
    return facts


def _high_observations(
    timeframe: str,
    bars: list[KlineBar],
    windows: list[int],
    quality_penalty: int,
) -> list[PatternObservation]:
    lookback = 252 if timeframe == "daily" else 52 if timeframe == "weekly" else 12
    if len(bars) <= lookback:
        return []
    high_indices = [
        idx
        for idx in range(lookback, len(bars))
        if bars[idx].close >= max(bar.high for bar in bars[idx - lookback : idx + 1]) * 0.995
    ]
    observations: list[PatternObservation] = []
    if high_indices and high_indices[-1] == len(bars) - 1:
        observations.append(
            _build_observation(
                rule_id=f"{timeframe}_new_high",
                timeframe=timeframe,
                title=f"{timeframe.title()} new high",
                bars=bars,
                trigger_indices=high_indices,
                windows=windows,
                min_samples=_min_samples(timeframe),
                quality_penalty=quality_penalty,
                current_status="Current bar is near a rolling high",
                details=f"Close is within 0.5% of the {lookback}-bar high.",
                watch_item=f"{timeframe.title()}: watch whether the new-high condition persists or fails back under the breakout area.",
            )
        )

    failed_indices = _failed_breakout_indices(bars, high_indices, lookback)
    if failed_indices and failed_indices[-1] >= len(bars) - 5:
        observations.append(
            _build_observation(
                rule_id=f"{timeframe}_failed_breakout",
                timeframe=timeframe,
                title=f"{timeframe.title()} failed breakout",
                bars=bars,
                trigger_indices=failed_indices,
                windows=windows,
                min_samples=_min_samples(timeframe),
                quality_penalty=quality_penalty,
                current_status="Recent breakout has failed",
                details="A recent rolling high was followed by a close more than 3% below that breakout close.",
                watch_item=f"{timeframe.title()}: watch whether price reclaims the failed breakout close or continues below it.",
            )
        )
    return observations


def _moving_average_observations(
    timeframe: str,
    bars: list[KlineBar],
    windows: list[int],
    quality_penalty: int,
) -> list[PatternObservation]:
    observations: list[PatternObservation] = []
    for period in _ma_periods(timeframe):
        if len(bars) <= period + 2:
            continue
        current_ma = _ma_at(bars, len(bars) - 1, period)
        previous_ma = _ma_at(bars, len(bars) - 2, period)
        if current_ma is None or previous_ma is None:
            continue
        current = bars[-1]
        previous = bars[-2]
        break_indices = [
            idx
            for idx in range(period, len(bars))
            if _ma_at(bars, idx, period) is not None
            and _ma_at(bars, idx - 1, period) is not None
            and bars[idx - 1].close >= _ma_at(bars, idx - 1, period)
            and bars[idx].close < _ma_at(bars, idx, period)
        ]
        reclaim_indices = [
            idx
            for idx in range(period, len(bars))
            if _ma_at(bars, idx, period) is not None
            and _ma_at(bars, idx - 1, period) is not None
            and bars[idx - 1].close <= _ma_at(bars, idx - 1, period)
            and bars[idx].close > _ma_at(bars, idx, period)
        ]
        distance_threshold = 0.08 if timeframe == "daily" else 0.12
        distance_indices = [
            idx
            for idx in range(period, len(bars))
            if (ma_value := _ma_at(bars, idx, period)) is not None and abs(bars[idx].close / ma_value - 1) >= distance_threshold
        ]
        if previous.close >= previous_ma and current.close < current_ma:
            observations.append(
                _build_observation(
                    rule_id=f"{timeframe}_ma{period}_break",
                    timeframe=timeframe,
                    title=f"{timeframe.title()} {period}-bar average break",
                    bars=bars,
                    trigger_indices=break_indices,
                    windows=windows,
                    min_samples=_min_samples(timeframe),
                    quality_penalty=quality_penalty,
                    current_status=f"Close crossed below the {period}-bar average",
                    details=f"Latest close is {_format_pct(current.close / current_ma - 1)} from the average.",
                    watch_item=f"{timeframe.title()}: watch whether the {period}-bar average is reclaimed on future bars.",
                )
            )
        elif previous.close <= previous_ma and current.close > current_ma:
            observations.append(
                _build_observation(
                    rule_id=f"{timeframe}_ma{period}_reclaim",
                    timeframe=timeframe,
                    title=f"{timeframe.title()} {period}-bar average reclaim",
                    bars=bars,
                    trigger_indices=reclaim_indices,
                    windows=windows,
                    min_samples=_min_samples(timeframe),
                    quality_penalty=quality_penalty,
                    current_status=f"Close crossed above the {period}-bar average",
                    details=f"Latest close is {_format_pct(current.close / current_ma - 1)} from the average.",
                    watch_item=f"{timeframe.title()}: watch whether price remains above the {period}-bar average.",
                )
            )
        elif distance_indices and distance_indices[-1] == len(bars) - 1:
            observations.append(
                _build_observation(
                    rule_id=f"{timeframe}_ma{period}_distance",
                    timeframe=timeframe,
                    title=f"{timeframe.title()} {period}-bar average distance",
                    bars=bars,
                    trigger_indices=distance_indices,
                    windows=windows,
                    min_samples=_min_samples(timeframe),
                    quality_penalty=quality_penalty,
                    current_status=f"Close is extended from the {period}-bar average",
                    details=f"Latest distance is {_format_pct(current.close / current_ma - 1)}.",
                    watch_item=f"{timeframe.title()}: watch whether extension narrows through consolidation or reversal.",
                )
            )
    return observations


def _volume_observations(
    bars: list[KlineBar],
    windows: list[int],
    quality_penalty: int,
) -> list[PatternObservation]:
    if len(bars) < 25 or bars[-1].volume is None:
        return []
    avg_volume = _average_volume(bars, len(bars) - 1, 20)
    if avg_volume is None or avg_volume <= 0:
        return []
    current = bars[-1]
    previous = bars[-2]
    observations: list[PatternObservation] = []
    high_volume_indices = [
        idx
        for idx in range(20, len(bars))
        if bars[idx].volume is not None
        and (avg := _average_volume(bars, idx, 20)) is not None
        and avg > 0
        and bars[idx].volume >= 1.8 * avg
    ]
    if current.volume is not None and current.volume >= 1.8 * avg_volume:
        direction = "up" if current.close > previous.close else "down" if current.close < previous.close else "flat"
        trigger_indices = [
            idx
            for idx in high_volume_indices
            if idx > 0
            and (
                (direction == "up" and bars[idx].close > bars[idx - 1].close)
                or (direction == "down" and bars[idx].close < bars[idx - 1].close)
                or (direction == "flat" and abs(bars[idx].close / bars[idx - 1].close - 1) < 0.005)
            )
        ]
        observations.append(
            _build_observation(
                rule_id=f"daily_high_volume_{direction}",
                timeframe="daily",
                title=f"Daily high-volume {direction} day",
                bars=bars,
                trigger_indices=trigger_indices,
                windows=windows,
                min_samples=_min_samples("daily"),
                quality_penalty=quality_penalty,
                current_status=f"Volume is {current.volume / avg_volume:.1f}x the 20-day average",
                details=f"Close was {direction} versus the prior close.",
                watch_item="Daily: watch whether high volume confirms continuation or becomes a stalling signal.",
            )
        )
    if current.volume is not None and current.volume >= 1.5 * avg_volume and current.close >= max(bar.close for bar in bars[-20:]):
        breakout_indices = [
            idx
            for idx in high_volume_indices
            if idx >= 20 and bars[idx].close >= max(bar.close for bar in bars[idx - 20 : idx + 1])
        ]
        observations.append(
            _build_observation(
                rule_id="daily_volume_breakout",
                timeframe="daily",
                title="Daily volume breakout",
                bars=bars,
                trigger_indices=breakout_indices,
                windows=windows,
                min_samples=_min_samples("daily"),
                quality_penalty=quality_penalty,
                current_status="Close is at a 20-day closing high on above-average volume",
                details=f"Volume is {current.volume / avg_volume:.1f}x the 20-day average.",
                watch_item="Daily: watch whether price remains above the volume-breakout level on later bars.",
            )
        )
    elif current.volume is not None and current.volume >= 1.8 * avg_volume and abs(current.close / previous.close - 1) <= 0.01:
        stall_indices = [
            idx
            for idx in high_volume_indices
            if idx > 0 and abs(bars[idx].close / bars[idx - 1].close - 1) <= 0.01
        ]
        observations.append(
            _build_observation(
                rule_id="daily_volume_stalling",
                timeframe="daily",
                title="Daily volume stalling",
                bars=bars,
                trigger_indices=stall_indices,
                windows=windows,
                min_samples=_min_samples("daily"),
                quality_penalty=quality_penalty,
                current_status="High volume produced little close-to-close progress",
                details=f"Close changed {_format_pct(current.close / previous.close - 1)} on {current.volume / avg_volume:.1f}x volume.",
                watch_item="Daily: watch whether stalling resolves into renewed progress or a reversal.",
            )
        )
    return observations


def _gap_observations(
    bars: list[KlineBar],
    windows: list[int],
    quality_penalty: int,
) -> list[PatternObservation]:
    if len(bars) < 3:
        return []
    current = bars[-1]
    previous = bars[-2]
    gap_up_indices = [idx for idx in range(1, len(bars)) if bars[idx].open > bars[idx - 1].high * 1.005]
    gap_down_indices = [idx for idx in range(1, len(bars)) if bars[idx].open < bars[idx - 1].low * 0.995]
    observations: list[PatternObservation] = []
    if current.open > previous.high * 1.005:
        filled = current.low <= previous.high
        persisted = current.close > previous.high
        observations.append(
            _build_observation(
                rule_id="daily_gap_up",
                timeframe="daily",
                title="Daily gap up",
                bars=bars,
                trigger_indices=gap_up_indices,
                windows=windows,
                min_samples=_min_samples("daily"),
                quality_penalty=quality_penalty,
                current_status="Current bar opened above the prior high",
                details=f"Gap {'filled intraday' if filled else 'remained unfilled intraday'}; close {'persisted above' if persisted else 'did not persist above'} the prior high.",
                watch_item="Daily: watch whether the gap remains open or gets filled on future bars.",
            )
        )
    if current.open < previous.low * 0.995:
        filled = current.high >= previous.low
        persisted = current.close < previous.low
        observations.append(
            _build_observation(
                rule_id="daily_gap_down",
                timeframe="daily",
                title="Daily gap down",
                bars=bars,
                trigger_indices=gap_down_indices,
                windows=windows,
                min_samples=_min_samples("daily"),
                quality_penalty=quality_penalty,
                current_status="Current bar opened below the prior low",
                details=f"Gap {'filled intraday' if filled else 'remained unfilled intraday'}; close {'persisted below' if persisted else 'did not persist below'} the prior low.",
                watch_item="Daily: watch whether the gap remains open or gets filled on future bars.",
            )
        )
    return observations


def _streak_observations(
    timeframe: str,
    bars: list[KlineBar],
    windows: list[int],
    quality_penalty: int,
) -> list[PatternObservation]:
    if len(bars) < 6:
        return []
    up_streak, down_streak = _current_streaks(bars)
    observations: list[PatternObservation] = []
    if up_streak >= 3:
        trigger_indices = [idx for idx in range(3, len(bars)) if _ending_streak(bars, idx, "up") >= up_streak]
        observations.append(
            _build_observation(
                rule_id=f"{timeframe}_up_streak",
                timeframe=timeframe,
                title=f"{timeframe.title()} consecutive up streak",
                bars=bars,
                trigger_indices=trigger_indices,
                windows=windows,
                min_samples=_min_samples(timeframe),
                quality_penalty=quality_penalty,
                current_status=f"{up_streak} consecutive up bars",
                details="Close has risen for multiple consecutive bars.",
                watch_item=f"{timeframe.title()}: watch whether the streak extends or reverses on the next bars.",
            )
        )
    if down_streak >= 3:
        trigger_indices = [idx for idx in range(3, len(bars)) if _ending_streak(bars, idx, "down") >= down_streak]
        observations.append(
            _build_observation(
                rule_id=f"{timeframe}_down_streak",
                timeframe=timeframe,
                title=f"{timeframe.title()} consecutive down streak",
                bars=bars,
                trigger_indices=trigger_indices,
                windows=windows,
                min_samples=_min_samples(timeframe),
                quality_penalty=quality_penalty,
                current_status=f"{down_streak} consecutive down bars",
                details="Close has fallen for multiple consecutive bars.",
                watch_item=f"{timeframe.title()}: watch whether the streak stabilizes or continues.",
            )
        )
    if len(bars) >= 5:
        prev_up = _ending_streak(bars[:-1], len(bars) - 2, "up")
        prev_down = _ending_streak(bars[:-1], len(bars) - 2, "down")
        if prev_up >= 3 and bars[-1].close < bars[-2].close:
            trigger_indices = [
                idx
                for idx in range(4, len(bars))
                if _ending_streak(bars[:idx], idx - 1, "up") >= 3 and bars[idx].close < bars[idx - 1].close
            ]
            observations.append(
                _build_observation(
                    rule_id=f"{timeframe}_up_streak_reversal",
                    timeframe=timeframe,
                    title=f"{timeframe.title()} reversal after up streak",
                    bars=bars,
                    trigger_indices=trigger_indices,
                    windows=windows,
                    min_samples=_min_samples(timeframe),
                    quality_penalty=quality_penalty,
                    current_status=f"Down close after {prev_up} up bars",
                    details="The latest close reversed a multi-bar up streak.",
                    watch_item=f"{timeframe.title()}: watch whether reversal remains one bar or changes the structure.",
                )
            )
        if prev_down >= 3 and bars[-1].close > bars[-2].close:
            trigger_indices = [
                idx
                for idx in range(4, len(bars))
                if _ending_streak(bars[:idx], idx - 1, "down") >= 3 and bars[idx].close > bars[idx - 1].close
            ]
            observations.append(
                _build_observation(
                    rule_id=f"{timeframe}_down_streak_reversal",
                    timeframe=timeframe,
                    title=f"{timeframe.title()} reversal after down streak",
                    bars=bars,
                    trigger_indices=trigger_indices,
                    windows=windows,
                    min_samples=_min_samples(timeframe),
                    quality_penalty=quality_penalty,
                    current_status=f"Up close after {prev_down} down bars",
                    details="The latest close reversed a multi-bar down streak.",
                    watch_item=f"{timeframe.title()}: watch whether reversal remains in place or fades.",
                )
            )
    return observations


def _drawdown_observations(
    timeframe: str,
    bars: list[KlineBar],
    windows: list[int],
    quality_penalty: int,
) -> list[PatternObservation]:
    lookback = 60 if timeframe == "daily" else 26 if timeframe == "weekly" else 12
    if len(bars) < lookback:
        return []
    recent = bars[-lookback:]
    recent_high = max(bar.high for bar in recent)
    drawdown = bars[-1].close / recent_high - 1
    observations: list[PatternObservation] = []
    drawdown_indices = [
        idx
        for idx in range(lookback, len(bars))
        if bars[idx].close / max(bar.high for bar in bars[idx - lookback : idx + 1]) - 1 <= -0.10
    ]
    if drawdown <= -0.10:
        observations.append(
            _build_observation(
                rule_id=f"{timeframe}_recent_high_drawdown",
                timeframe=timeframe,
                title=f"{timeframe.title()} drawdown from recent high",
                bars=bars,
                trigger_indices=drawdown_indices,
                windows=windows,
                min_samples=_min_samples(timeframe),
                quality_penalty=quality_penalty,
                current_status=f"Close is {_format_pct(drawdown)} from the recent high",
                details=f"Recent high uses the last {lookback} {timeframe} bars.",
                watch_item=f"{timeframe.title()}: watch whether drawdown deepens or starts a recovery path.",
            )
        )
    recovery_indices = [
        idx
        for idx in range(lookback, len(bars))
        if _had_drawdown_before(bars, idx, lookback, threshold=-0.10)
        and bars[idx].close / max(bar.high for bar in bars[idx - lookback : idx + 1]) - 1 >= -0.03
    ]
    if recovery_indices and recovery_indices[-1] == len(bars) - 1:
        observations.append(
            _build_observation(
                rule_id=f"{timeframe}_drawdown_recovery",
                timeframe=timeframe,
                title=f"{timeframe.title()} recovery from drawdown",
                bars=bars,
                trigger_indices=recovery_indices,
                windows=windows,
                min_samples=_min_samples(timeframe),
                quality_penalty=quality_penalty,
                current_status="Close has recovered within 3% of the recent high after a drawdown",
                details=f"Recovery check uses the last {lookback} {timeframe} bars.",
                watch_item=f"{timeframe.title()}: watch whether recovery reaches a new high or fails below the prior high.",
            )
        )
    return observations


def _build_observation(
    *,
    rule_id: str,
    timeframe: str,
    title: str,
    bars: list[KlineBar],
    trigger_indices: list[int],
    windows: list[int],
    min_samples: int,
    quality_penalty: int,
    current_status: str,
    details: str,
    watch_item: str,
) -> PatternObservation:
    stats = [
        _stats_for_window(
            bars=bars,
            trigger_indices=trigger_indices,
            forward_window=window,
            min_samples=min_samples,
            quality_penalty=quality_penalty,
        )
        for window in windows
    ]
    sufficient = any(item.sample_count >= min_samples for item in stats)
    return PatternObservation(
        rule_id=rule_id,
        timeframe=timeframe,
        title=title,
        current_status=current_status,
        trigger_date=bars[-1].bar_date if bars else None,
        details=details,
        stats=stats,
        sufficient_evidence=sufficient,
        watch_item=watch_item,
    )


def _stats_for_window(
    *,
    bars: list[KlineBar],
    trigger_indices: list[int],
    forward_window: int,
    min_samples: int,
    quality_penalty: int,
) -> PatternWindowStats:
    usable = [idx for idx in trigger_indices if idx + forward_window < len(bars)]
    returns: list[tuple[date, float]] = []
    adverse: list[float] = []
    for idx in usable:
        start_close = bars[idx].close
        end_close = bars[idx + forward_window].close
        returns.append((bars[idx].bar_date, end_close / start_close - 1))
        min_low = min(bar.low for bar in bars[idx + 1 : idx + forward_window + 1])
        adverse.append(min_low / start_close - 1)
    if not returns:
        return PatternWindowStats(
            forward_window=forward_window,
            sample_count=0,
            mean_forward_return=None,
            median_forward_return=None,
            win_rate=None,
            best_sample=None,
            worst_sample=None,
            max_adverse_excursion=None,
            confidence="insufficient",
        )
    return_values = [item[1] for item in returns]
    return PatternWindowStats(
        forward_window=forward_window,
        sample_count=len(returns),
        mean_forward_return=mean(return_values),
        median_forward_return=median(return_values),
        win_rate=sum(1 for value in return_values if value > 0) / len(return_values),
        best_sample=max(returns, key=lambda item: item[1]),
        worst_sample=min(returns, key=lambda item: item[1]),
        max_adverse_excursion=min(adverse) if adverse else None,
        confidence=_confidence(len(returns), min_samples, quality_penalty),
    )


def _records_from_provider_data(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        return list(data.to_dict("records"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _futu_adjust_type(ft: Any, adjust_type: str) -> Any:
    normalized = normalize_adjust_type(adjust_type)
    if normalized == "raw":
        return _enum_value(ft.AuType, "NONE")
    if normalized == "backward_adjusted":
        return _enum_value(ft.AuType, "HFQ")
    return _enum_value(ft.AuType, "QFQ")


def _enum_value(enum_cls: Any, name: str) -> Any:
    if hasattr(enum_cls, name):
        return getattr(enum_cls, name)
    return name


def _call_with_keyword_retry(callable_obj: Any, kwargs: dict[str, Any]) -> Any:
    remaining = {key: value for key, value in kwargs.items() if value is not None}
    while True:
        try:
            return callable_obj(**remaining)
        except TypeError as exc:
            match = re.search(r"unexpected keyword argument '([^']+)'", str(exc))
            if match is None:
                match = re.search(r'got an unexpected keyword argument "([^"]+)"', str(exc))
            if match is None or match.group(1) not in remaining:
                raise
            remaining.pop(match.group(1))


def _parse_bar_date(item: dict[str, Any]) -> date | None:
    value = item.get("time_key") or item.get("date") or item.get("time") or item.get("bar_date")
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def _sum_optional(values: Any) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(sum(present))


def _looks_like_market(value: str) -> bool:
    return normalize_market(value) in {"US", "HK", "CN", "SH", "SZ", "KR", "JP"}


def _ma_periods(timeframe: str) -> list[int]:
    if timeframe == "daily":
        return [20, 60]
    if timeframe == "weekly":
        return [20, 40]
    return [10]


def _ma_at(bars: list[KlineBar], idx: int, period: int) -> float | None:
    if idx < period - 1 or idx >= len(bars):
        return None
    return mean(bar.close for bar in bars[idx - period + 1 : idx + 1])


def _average_volume(bars: list[KlineBar], idx: int, period: int) -> float | None:
    if idx < period - 1:
        return None
    volumes = [bar.volume for bar in bars[idx - period + 1 : idx + 1]]
    if any(value is None for value in volumes):
        return None
    return mean(value for value in volumes if value is not None)


def _failed_breakout_indices(bars: list[KlineBar], high_indices: list[int], lookback: int) -> list[int]:
    failed: list[int] = []
    high_set = set(high_indices)
    for idx in range(lookback + 1, len(bars)):
        recent_highs = [high_idx for high_idx in range(max(lookback, idx - 10), idx) if high_idx in high_set]
        if not recent_highs:
            continue
        breakout_idx = recent_highs[-1]
        if bars[idx].close <= bars[breakout_idx].close * 0.97:
            failed.append(idx)
    return failed


def _current_streaks(bars: list[KlineBar]) -> tuple[int, int]:
    return _ending_streak(bars, len(bars) - 1, "up"), _ending_streak(bars, len(bars) - 1, "down")


def _ending_streak(bars: list[KlineBar], idx: int, direction: str) -> int:
    if idx <= 0 or idx >= len(bars):
        return 0
    count = 0
    for current_idx in range(idx, 0, -1):
        if direction == "up" and bars[current_idx].close > bars[current_idx - 1].close:
            count += 1
        elif direction == "down" and bars[current_idx].close < bars[current_idx - 1].close:
            count += 1
        else:
            break
    return count


def _had_drawdown_before(bars: list[KlineBar], idx: int, lookback: int, threshold: float) -> bool:
    start = max(lookback, idx - lookback)
    for candidate in range(start, idx):
        recent_high = max(bar.high for bar in bars[candidate - lookback : candidate + 1])
        if bars[candidate].close / recent_high - 1 <= threshold:
            return True
    return False


def _min_samples(timeframe: str) -> int:
    if timeframe == "daily":
        return 8
    if timeframe == "weekly":
        return 5
    return 3


def _confidence(sample_count: int, min_samples: int, quality_penalty: int) -> str:
    if sample_count < min_samples:
        return "insufficient"
    if sample_count >= min_samples * 3:
        level = 3
    elif sample_count >= min_samples * 2:
        level = 2
    else:
        level = 1
    level = max(1, level - quality_penalty)
    return {1: "low", 2: "medium", 3: "high"}[level]


def _quality_penalty(warnings: list[str]) -> int:
    if not warnings:
        return 0
    severe = sum(1 for warning in warnings if "Dropped" in warning or "Duplicate" in warning)
    return 2 if severe >= 3 else 1


def _gap_warnings(bars: list[KlineBar]) -> list[str]:
    warnings: list[str] = []
    for previous, current in zip(bars, bars[1:]):
        gap = (current.bar_date - previous.bar_date).days
        if gap > 10:
            warnings.append(
                f"Large calendar gap between {previous.bar_date.isoformat()} and {current.bar_date.isoformat()}; provider or market holiday data may be incomplete."
            )
            if len(warnings) >= 3:
                break
    return warnings


def _interpretations(analyses: list[TimeframeAnalysis]) -> list[str]:
    items: list[str] = []
    for analysis in analyses:
        sufficient = [item for item in analysis.observations if item.sufficient_evidence]
        insufficient = [item for item in analysis.observations if not item.sufficient_evidence]
        if sufficient:
            titles = ", ".join(item.title for item in sufficient[:3])
            items.append(f"{analysis.timeframe.title()} has deterministic observations with sample support: {titles}.")
        elif insufficient:
            titles = ", ".join(item.title for item in insufficient[:3])
            items.append(f"{analysis.timeframe.title()} has current deterministic triggers but sample support is weak: {titles}.")
    return items


def _watch_items(analyses: list[TimeframeAnalysis]) -> list[str]:
    items: list[str] = []
    for analysis in analyses:
        for observation in analysis.observations:
            items.append(observation.watch_item)
    return list(dict.fromkeys(items))


def _format_optional_date(value: date | None) -> str:
    return value.isoformat() if value else "n/a"


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _format_sample(sample: tuple[date, float] | None) -> str:
    if sample is None:
        return "n/a"
    return f"{sample[0].isoformat()} {_format_pct(sample[1])}"
