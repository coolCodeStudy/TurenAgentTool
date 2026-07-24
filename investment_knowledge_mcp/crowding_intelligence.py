"""Explainable, direction-specific crowded-trade evidence and scoring."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timezone
from enum import Enum
import math
import statistics
from typing import Any, Mapping

from investment_knowledge_mcp.data_sources.contracts import (
    DataResult,
    DataStatus,
    SourceCapability,
)


class EvidenceDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    TWO_SIDED = "two_sided"
    ATTENTION = "attention"
    FRAGILITY = "fragility"
    CONTEXT = "context"
    COUNTEREVIDENCE = "counterevidence"


class EvidenceQuality(str, Enum):
    INSUFFICIENT = "insufficient"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CrowdingBand(str, Enum):
    INSUFFICIENT = "insufficient_evidence"
    LOW = "low"
    WATCH = "watch"
    ELEVATED = "elevated"
    HIGH = "high"


@dataclass(frozen=True)
class CrowdingEvidence:
    symbol: str
    market: str
    family: str
    metric: str
    direction: EvidenceDirection
    value: float | str
    unit: str
    normalized_value: float | None
    cohort: str
    observed_at: datetime
    published_at: datetime | None
    fetched_at: datetime
    source_id: str
    access_tier: str
    freshness: str
    metadata: Mapping[str, Any]
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FamilyAssessment:
    name: str
    score: float | None
    current: bool
    evidence: tuple[CrowdingEvidence, ...]
    coverage: float
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DirectionalAssessment:
    band: CrowdingBand
    score: float | None
    contributors: tuple[str, ...]
    counterevidence: tuple[str, ...]
    missing_families: tuple[str, ...]
    uncertainty: str


@dataclass(frozen=True)
class CrowdingAssessment:
    canonical: str
    market: str
    as_of: date
    evidence_quality: EvidenceQuality
    long_crowding: DirectionalAssessment
    short_squeeze: DirectionalAssessment
    speculative_attention: DirectionalAssessment
    families: tuple[FamilyAssessment, ...]
    missing_families: tuple[str, ...]
    provider_failures: tuple[str, ...]
    next_event: str | None


_ALLOWED_METRICS = {
    "ownership": {"ownership_top_holders_pct"},
    "short_interest": {"short_percent"},
    "options": {"options_open_interest"},
    "events": {"earnings_event"},
}

_EXPECTED_DIRECTIONS = {
    "ownership": {EvidenceDirection.LONG},
    "short_interest": {EvidenceDirection.SHORT},
    "options": {EvidenceDirection.TWO_SIDED},
    "events": {EvidenceDirection.CONTEXT},
}

_STALE_AFTER_DAYS = {
    "price_volume": 7,
    "ownership": 180,
    "short_interest": 45,
    "options": 3,
    "events": 7,
}

_MIN_PARTIAL_COVERAGE = 0.8

_CAPABILITY_FAMILY = {
    SourceCapability.OWNERSHIP_CONCENTRATION: "ownership",
    SourceCapability.SHORT_INTEREST: "short_interest",
    SourceCapability.OPTIONS_POSITIONING: "options",
    SourceCapability.EVENT_CALENDAR: "events",
}


def evidence_from_record(record: Mapping[str, Any], as_of: date) -> CrowdingEvidence:
    family = _text(record.get("family"), "family").casefold()
    metric = _text(record.get("metric"), "metric").casefold()
    if family not in _ALLOWED_METRICS or metric not in _ALLOWED_METRICS[family]:
        raise ValueError(f"unsupported metric semantics: {family}.{metric}")
    direction = EvidenceDirection(_text(record.get("direction"), "direction").casefold())
    if direction not in _EXPECTED_DIRECTIONS[family]:
        raise ValueError(f"invalid direction for {family}")
    symbol = _text(record.get("symbol"), "symbol").upper()
    market = _text(record.get("market"), "market").upper()
    if not symbol.startswith(f"{market}."):
        raise ValueError("evidence identity mismatch")
    observed_at = _aware_timestamp(record.get("observed_at"), "observed_at")
    published_raw = record.get("published_at")
    published_at = (
        _aware_timestamp(published_raw, "published_at")
        if published_raw not in (None, "")
        else None
    )
    fetched_at = _aware_timestamp(record.get("fetched_at"), "fetched_at")
    as_of_end = datetime.combine(as_of, time.max, tzinfo=timezone.utc)
    if observed_at > as_of_end or (
        published_at is not None and published_at > as_of_end
    ):
        raise ValueError("evidence was not observable by the assessment date")
    if published_at is None and fetched_at > as_of_end:
        raise ValueError(
            "evidence with unknown publication time was fetched after the assessment date"
        )
    quality_flags = []
    if published_at is None:
        quality_flags.append("publication_time_unknown")
    if fetched_at > as_of_end:
        quality_flags.append("fetched_after_as_of")
    raw_value = record.get("value")
    if family == "events":
        value: float | str = _text(raw_value, "value")
    else:
        value = _finite_number(raw_value, "value")
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    return CrowdingEvidence(
        symbol=symbol,
        market=market,
        family=family,
        metric=metric,
        direction=direction,
        value=value,
        unit=_text(record.get("unit"), "unit"),
        normalized_value=None,
        cohort=_text(record.get("cohort"), "cohort"),
        observed_at=observed_at,
        published_at=published_at,
        fetched_at=fetched_at,
        source_id=_text(record.get("source_id"), "source_id").casefold(),
        access_tier=_text(record.get("access_tier"), "access_tier").casefold(),
        freshness=_text(record.get("freshness"), "freshness"),
        metadata=dict(metadata),
        quality_flags=tuple(quality_flags),
    )


def build_crowding_assessment(
    symbol: str,
    market: str,
    bars_result: DataResult,
    family_results: Mapping[SourceCapability, DataResult],
    *,
    as_of: date,
) -> CrowdingAssessment:
    normalized_market = _text(market, "market").upper()
    normalized_symbol = _text(symbol, "symbol").upper()
    canonical = (
        normalized_symbol
        if normalized_symbol.startswith(f"{normalized_market}.")
        else f"{normalized_market}.{normalized_symbol}"
    )
    families: list[FamilyAssessment] = []
    provider_failures: list[str] = []

    price_family = _price_volume_family(canonical, normalized_market, bars_result, as_of)
    provider_failures.extend(_result_failure_codes("price_volume", bars_result))
    if price_family is not None:
        families.append(price_family)

    for capability, expected_family in _CAPABILITY_FAMILY.items():
        result = family_results.get(capability)
        if result is None:
            continue
        provider_failures.extend(_result_failure_codes(expected_family, result))
        if result.status is DataStatus.UNAVAILABLE:
            continue
        accepted: list[CrowdingEvidence] = []
        for raw_record in result.records:
            if not isinstance(raw_record, Mapping):
                continue
            try:
                evidence = evidence_from_record(raw_record, as_of)
            except (TypeError, ValueError):
                continue
            if evidence.symbol != canonical or evidence.market != normalized_market:
                continue
            accepted.append(evidence)
        if not accepted:
            continue
        family = _positioning_family(
            expected_family,
            tuple(accepted),
            price_family,
            as_of,
            coverage=result.coverage,
        )
        if family is not None:
            families.append(family)

    by_name = {family.name: family for family in families}
    long_required = ("price_volume", "ownership", "options")
    short_required = ("price_volume", "short_interest", "options")
    attention_required = ("price_volume", "options", "attention")
    long_result = _directional_result(
        normalized_market,
        by_name,
        long_required,
        label="long",
    )
    short_result = _directional_result(
        normalized_market,
        by_name,
        short_required,
        label="short",
    )
    attention_result = _directional_result(
        normalized_market,
        by_name,
        attention_required,
        label="attention",
    )
    expected = {"price_volume", "ownership", "short_interest", "options", "events", "attention"}
    current_names = {name for name, family in by_name.items() if family.current}
    missing = tuple(sorted(expected - current_names))
    current_positioning = current_names & {"ownership", "short_interest", "options"}
    if "price_volume" not in current_names or not current_positioning:
        quality = EvidenceQuality.INSUFFICIENT
    elif len(current_positioning) == 1:
        quality = EvidenceQuality.LOW
    elif len(current_positioning) == 2:
        quality = EvidenceQuality.MEDIUM
    else:
        quality = EvidenceQuality.HIGH
    next_event = _next_event(by_name.get("events"), as_of)
    return CrowdingAssessment(
        canonical=canonical,
        market=normalized_market,
        as_of=as_of,
        evidence_quality=quality,
        long_crowding=long_result,
        short_squeeze=short_result,
        speculative_attention=attention_result,
        families=tuple(sorted(families, key=lambda item: item.name)),
        missing_families=missing,
        provider_failures=tuple(sorted(set(provider_failures))),
        next_event=next_event,
    )


def render_crowding_assessment(assessment: CrowdingAssessment) -> str:
    lines = [
        f"## 拥挤交易情报 — {assessment.canonical}",
        f"- 截止日期：{assessment.as_of.isoformat()}",
        f"- 市场模式：{'可评分' if assessment.market in {'US', 'HK'} else '证据模式'}",
        f"- 证据质量：{assessment.evidence_quality.value}",
        "- 所有等级均为启发式可能性，不是经过校准的概率。",
        "",
        "### 分方向判断",
        _render_direction("多头拥挤", assessment.long_crowding),
        _render_direction("空头拥挤 / 挤压压力", assessment.short_squeeze),
        _render_direction("投机关注度", assessment.speculative_attention),
        "",
        "### 证据与来源",
    ]
    if assessment.families:
        for family in assessment.families:
            flags = f"，质量标记：{', '.join(family.quality_flags)}" if family.quality_flags else ""
            score = "未知" if family.score is None else f"{family.score:.2f}"
            lines.append(
                f"- {family.name}：family_score={score}，"
                f"coverage={family.coverage:.2f}，"
                f"current={'yes' if family.current else 'no'}{flags}"
            )
            for evidence in family.evidence:
                lines.append(
                    f"  - {evidence.metric}={_format_value(evidence.value, evidence.unit)}；"
                    f"market={evidence.market}；source={evidence.source_id}；"
                    f"observed={evidence.observed_at.date().isoformat()}；"
                    f"published={evidence.published_at.date().isoformat() if evidence.published_at else 'unknown'}；"
                    f"fetched={evidence.fetched_at.date().isoformat()}；"
                    f"use_tier={evidence.access_tier}；cohort={evidence.cohort}；"
                    f"freshness={evidence.freshness}"
                )
    else:
        lines.append("- 没有可验证的当前证据。")
    lines.extend(
        [
            "",
            "### 缺失与不确定性",
            "- 缺失 family：" + (", ".join(assessment.missing_families) or "none"),
            "- 数据源状态：" + (", ".join(assessment.provider_failures) or "没有已记录的 provider failure"),
            f"- 下一已知事件：{assessment.next_event or '未知'}",
            "",
            "> 这是研究辅助工具，基于不完整且滞后不同的市场证据；不是投资建议，也不指示买入、卖出、持有、减仓、对冲或交易。",
        ]
    )
    return "\n".join(lines)


def _render_direction(label: str, result: DirectionalAssessment) -> str:
    score = "" if result.score is None else f"，内部启发式分数 {result.score:.2f}"
    contributors = "、".join(result.contributors) or "无"
    counter = "、".join(result.counterevidence) or "无"
    missing = "、".join(result.missing_families) or "无"
    return (
        f"- {label}：{result.band.value}{score}；主要贡献：{contributors}；"
        f"反向证据：{counter}；缺失：{missing}；不确定性：{result.uncertainty}"
    )


def _price_volume_family(
    canonical: str,
    market: str,
    result: DataResult,
    as_of: date,
) -> FamilyAssessment | None:
    if result.status is DataStatus.UNAVAILABLE:
        return None
    bars: tuple[Mapping[str, Any], ...] | None = None
    for record in result.records:
        if (
            isinstance(record, Mapping)
            and str(record.get("symbol") or "").upper() == canonical
            and isinstance(record.get("bars"), tuple)
        ):
            bars = record["bars"]
            break
    if bars is None:
        return None
    cleaned = []
    for bar in bars:
        if not isinstance(bar, Mapping):
            continue
        try:
            bar_date = date.fromisoformat(str(bar.get("date"))[:10])
            close = _finite_number(bar.get("close"), "close")
            volume = _finite_number(bar.get("volume"), "volume")
        except (TypeError, ValueError):
            continue
        if bar_date <= as_of and close > 0 and volume >= 0:
            cleaned.append((bar_date, close, volume))
    cleaned.sort(key=lambda item: item[0])
    if len(cleaned) < 120:
        return None
    closes = [item[1] for item in cleaned]
    volumes = [item[2] for item in cleaned]
    returns_20 = [closes[index] / closes[index - 20] - 1.0 for index in range(20, len(closes))]
    current_return = returns_20[-1]
    return_percentile = _percentile(returns_20, current_return)
    daily_returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))]
    vol_windows = [
        statistics.pstdev(daily_returns[index - 20 : index])
        for index in range(20, len(daily_returns) + 1)
    ]
    current_vol = vol_windows[-1]
    volatility_percentile = _percentile(vol_windows, current_vol)
    recent_volume = statistics.fmean(volumes[-20:])
    baseline_volume = statistics.fmean(volumes[-80:-20])
    volume_ratio = recent_volume / baseline_volume if baseline_volume > 0 else 1.0
    volume_score = max(0.0, min(1.0, (volume_ratio - 0.75) / 1.5))
    momentum_score = return_percentile if current_return >= 0 else 1.0 - return_percentile
    score = _clamp(statistics.fmean((momentum_score, volatility_percentile, volume_score)))
    observed = datetime.combine(cleaned[-1][0], time.min, tzinfo=timezone.utc)
    fresh = (as_of - cleaned[-1][0]).days <= _STALE_AFTER_DAYS["price_volume"]
    coverage_sufficient = result.coverage >= _MIN_PARTIAL_COVERAGE
    current = fresh and coverage_sufficient
    flags = tuple(
        flag
        for flag, present in (
            ("stale", not fresh),
            (f"partial_coverage:{result.coverage:.2f}", result.coverage < 1.0),
            ("coverage_below_threshold", not coverage_sufficient),
        )
        if present
    )
    evidence = CrowdingEvidence(
        symbol=canonical,
        market=market,
        family="price_volume",
        metric="price_volume_volatility_composite",
        direction=EvidenceDirection.LONG if current_return >= 0 else EvidenceDirection.FRAGILITY,
        value=round(current_return * 100.0, 6),
        unit="percent_20_session_return",
        normalized_value=score,
        cohort="own_history_rolling_20_session",
        observed_at=observed,
        published_at=observed,
        fetched_at=result.fetched_at,
        source_id=result.selected_source or "unknown",
        access_tier="existing_repository",
        freshness="end_of_day",
        metadata={
            "return_percentile": return_percentile,
            "volatility_percentile": volatility_percentile,
            "volume_ratio": volume_ratio,
            "average_volume_20_session": recent_volume,
        },
        quality_flags=flags,
    )
    return FamilyAssessment("price_volume", score, current, (evidence,), result.coverage, flags)


def _positioning_family(
    name: str,
    evidence: tuple[CrowdingEvidence, ...],
    price_family: FamilyAssessment | None,
    as_of: date,
    *,
    coverage: float,
) -> FamilyAssessment | None:
    first = evidence[0]
    age_days = (as_of - first.observed_at.date()).days
    fresh = age_days <= _STALE_AFTER_DAYS[name]
    coverage_sufficient = coverage >= _MIN_PARTIAL_COVERAGE
    current = fresh and coverage_sufficient
    flags = tuple(
        flag
        for flag, present in (
            ("stale", not fresh),
            (f"partial_coverage:{coverage:.2f}", coverage < 1.0),
            ("coverage_below_threshold", not coverage_sufficient),
        )
        if present
    )
    if name == "ownership":
        score = _clamp(float(first.value) / 80.0)
    elif name == "short_interest":
        days = _optional_number(first.metadata.get("days_to_cover")) or 0.0
        score = _clamp((_clamp(float(first.value) / 20.0) * 0.6) + (_clamp(days / 5.0) * 0.4))
    elif name == "options":
        average_volume = _price_average_volume(price_family)
        equivalent_oi = _optional_number(
            first.metadata.get("underlying_equivalent_open_interest")
        )
        option_exposure = equivalent_oi if equivalent_oi is not None else float(first.value)
        oi_ratio = option_exposure / average_volume if average_volume else 0.0
        call_oi = _optional_number(first.metadata.get("call_open_interest_ratio"))
        expiry = _optional_number(first.metadata.get("expiry_concentration")) or 0.0
        score = _clamp(
            (_clamp(oi_ratio / 3.0) * 0.5)
            + ((_clamp(call_oi) if call_oi is not None else 0.5) * 0.25)
            + (_clamp(expiry) * 0.25)
        )
        evidence = (
            replace(
                first,
                normalized_value=score,
                metadata={**dict(first.metadata), "open_interest_to_underlying_volume": oi_ratio},
                quality_flags=tuple(dict.fromkeys((*first.quality_flags, *flags))),
            ),
        )
    elif name == "events":
        score = None
    else:
        return None
    if name != "options":
        evidence = tuple(
            replace(
                item,
                normalized_value=score,
                quality_flags=tuple(dict.fromkeys((*item.quality_flags, *flags))),
            )
            for item in evidence
        )
    return FamilyAssessment(name, score, current, evidence, coverage, flags)


def _price_average_volume(family: FamilyAssessment | None) -> float | None:
    if family is None or not family.evidence:
        return None
    metadata = family.evidence[0].metadata
    average_volume = _optional_number(metadata.get("average_volume_20_session"))
    if average_volume is None or average_volume <= 0:
        return None
    return average_volume


def _directional_result(
    market: str,
    by_name: Mapping[str, FamilyAssessment],
    required: tuple[str, ...],
    *,
    label: str,
) -> DirectionalAssessment:
    missing = tuple(name for name in required if name not in by_name or not by_name[name].current)
    eligible = market in {"US", "HK"} and not missing
    scored = []
    for name in required:
        family = by_name.get(name)
        if family is None or not family.current or family.score is None:
            continue
        directional_score = _directional_family_score(family, label)
        if directional_score is not None:
            scored.append((family, directional_score))
    minimum_scored = 2 if label in {"long", "short"} else 3
    if not eligible or len(scored) < minimum_scored:
        return DirectionalAssessment(
            CrowdingBand.INSUFFICIENT,
            None,
            tuple(
                item.name
                for item, _ in sorted(scored, key=lambda pair: pair[1], reverse=True)[:3]
            ),
            tuple(item.name for item, score in scored if score < 0.35),
            missing,
            "证据 family 或市场覆盖门槛未满足，不能把缺失数据解释为低拥挤。",
        )
    score = _clamp(statistics.fmean(effective_score for _, effective_score in scored))
    contributors = tuple(
        item.name
        for item, _ in sorted(scored, key=lambda pair: pair[1], reverse=True)[:3]
    )
    counter = tuple(item.name for item, effective_score in scored if effective_score < 0.35)
    return DirectionalAssessment(
        _band(score),
        score,
        contributors,
        counter,
        (),
        f"{label} 等级来自确定性 family 规则，尚未经过历史概率校准。",
    )


def _directional_family_score(
    family: FamilyAssessment,
    label: str,
) -> float | None:
    score = _clamp(family.score)
    if (
        label in {"long", "short"}
        and family.evidence
        and family.evidence[0].direction is EvidenceDirection.TWO_SIDED
    ):
        return None
    if family.name != "price_volume" or not family.evidence:
        return score
    direction = family.evidence[0].direction
    if label in {"long", "short"} and direction is EvidenceDirection.FRAGILITY:
        return min(score, 0.2)
    return score


def _band(score: float) -> CrowdingBand:
    if score < 0.35:
        return CrowdingBand.LOW
    if score < 0.55:
        return CrowdingBand.WATCH
    if score < 0.75:
        return CrowdingBand.ELEVATED
    return CrowdingBand.HIGH


def _next_event(family: FamilyAssessment | None, as_of: date) -> str | None:
    if family is None:
        return None
    event_dates = []
    for evidence in family.evidence:
        try:
            event_date = date.fromisoformat(str(evidence.value))
        except ValueError:
            continue
        if event_date >= as_of:
            event_dates.append(event_date)
    return min(event_dates).isoformat() if event_dates else None


def _result_failure_codes(family: str, result: DataResult) -> list[str]:
    if result.failures:
        return [f"{family}:{failure.code}" for failure in result.failures]
    if result.status is DataStatus.UNAVAILABLE:
        return [f"{family}:unavailable"]
    return []


def _percentile(values: list[float], current: float) -> float:
    if not values:
        return 0.5
    below_or_equal = sum(1 for value in values if value <= current)
    return below_or_equal / len(values)


def _aware_timestamp(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=timezone.utc)
    elif isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            raise ValueError(f"{field} must be non-empty")
        if len(text_value) == 10:
            parsed = datetime.combine(date.fromisoformat(text_value), time.min, tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"{field} must be a date or datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone aware")
    return parsed.astimezone(timezone.utc)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not (cleaned := value.strip()):
        raise ValueError(f"{field} must be non-empty")
    return cleaned


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _optional_number(value: object) -> float | None:
    try:
        return _finite_number(value, "value")
    except ValueError:
        return None


def _clamp(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _format_value(value: float | str, unit: str) -> str:
    if isinstance(value, float):
        return f"{value:.4g} {unit}"
    return f"{value} {unit}"
