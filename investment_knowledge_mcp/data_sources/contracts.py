"""Immutable contracts for provider-neutral data acquisition."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from numbers import Real
from typing import Any, Iterable, Optional, Tuple


class SourceCapability(str, Enum):
    MARKET_BARS = "market_bars"
    MARKET_ACTIVITY = "market_activity"
    OFFICIAL_FINANCIAL_FACTS = "official_financial_facts"
    MARKET_SNAPSHOT = "market_snapshot"
    OFFICIAL_EVENTS = "official_events"
    NEWS_EVENTS = "news_events"
    POSITIONS = "positions"
    TRADES = "trades"
    OWNERSHIP_CONCENTRATION = "ownership_concentration"
    SHORT_INTEREST = "short_interest"
    OPTIONS_POSITIONING = "options_positioning"
    EVENT_CALENDAR = "event_calendar"


class DataStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


def _non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise ValueError(f"{field} must be non-empty")
    return normalized


def _source_id(value: str) -> str:
    return _non_empty(value, "source ID").casefold()


def _market(value: str) -> str:
    return _non_empty(value, "market").upper()


def _string_tuple(values: Iterable[str], normalizer, field: str) -> Tuple[str, ...]:
    normalized = tuple(normalizer(value) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


def _sanitize_detail(detail: Optional[str]) -> Optional[str]:
    if detail is None:
        return None
    text = str(detail)
    if re.search(
        r"(?i)\b(token|api[_ -]?key|password|secret|authorization)\b|"
        r"\b(bearer|basic)\s+\S+|\bcookie\s*=",
        text,
    ):
        return "[redacted]"
    return text


def _boolean(value: bool, field: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    source_id: str
    retryable: bool
    fallback_allowed: bool
    detail: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _non_empty(self.code, "failure code"))
        object.__setattr__(self, "source_id", _source_id(self.source_id))
        _boolean(self.retryable, "retryable")
        _boolean(self.fallback_allowed, "fallback_allowed")
        object.__setattr__(self, "detail", _sanitize_detail(self.detail))


@dataclass(frozen=True)
class DataRequest:
    capability: SourceCapability
    market: str
    symbols: Tuple[str, ...] = ()
    start: Optional[date] = None
    end: Optional[date] = None
    freshness: str = ""
    required_fields: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.capability, SourceCapability):
            raise ValueError("capability must be a SourceCapability")
        object.__setattr__(self, "market", _market(self.market))
        object.__setattr__(self, "symbols", _string_tuple(self.symbols, lambda value: _non_empty(value, "symbol").upper(), "symbols"))
        object.__setattr__(self, "freshness", _non_empty(self.freshness, "freshness"))
        object.__setattr__(self, "required_fields", _string_tuple(self.required_fields, lambda value: _non_empty(value, "required field"), "required fields"))
        if self.start is not None and (not isinstance(self.start, date) or isinstance(self.start, datetime)):
            raise ValueError("start must be a date, not a datetime")
        if self.end is not None and (not isinstance(self.end, date) or isinstance(self.end, datetime)):
            raise ValueError("end must be a date, not a datetime")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start cannot be after end")


@dataclass(frozen=True)
class SourcePlan:
    capability: SourceCapability
    preferred_sources: Tuple[str, ...]
    allowed_sources: Tuple[str, ...]
    fallback_sources: Tuple[str, ...]
    required: bool
    partial_allowed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.capability, SourceCapability):
            raise ValueError("capability must be a SourceCapability")
        preferred = _string_tuple(self.preferred_sources, _source_id, "preferred sources")
        allowed = _string_tuple(self.allowed_sources, _source_id, "allowed sources")
        fallback = _string_tuple(self.fallback_sources, _source_id, "fallback sources")
        if not allowed:
            raise ValueError("allowed sources must be non-empty")
        if not set(preferred).issubset(allowed) or not set(fallback).issubset(allowed):
            raise ValueError("preferred and fallback sources must be allowed")
        _boolean(self.required, "required")
        _boolean(self.partial_allowed, "partial_allowed")
        object.__setattr__(self, "preferred_sources", preferred)
        object.__setattr__(self, "allowed_sources", allowed)
        object.__setattr__(self, "fallback_sources", fallback)

    def validate_request(self, request: DataRequest) -> None:
        if self.capability != request.capability:
            raise ValueError("plan capability must match request capability")


@dataclass(frozen=True)
class ProviderDescriptor:
    source_id: str
    capabilities: Tuple[SourceCapability, ...]
    markets: Tuple[str, ...]
    timeout_seconds: float
    retry_limit: int
    rate_group: str
    default_ttl_seconds: int

    def __post_init__(self) -> None:
        capabilities = tuple(self.capabilities)
        if not capabilities or any(not isinstance(item, SourceCapability) for item in capabilities):
            raise ValueError("capabilities must be non-empty SourceCapability values")
        if len(set(capabilities)) != len(capabilities):
            raise ValueError("capabilities must not contain duplicates")
        markets = _string_tuple(self.markets, _market, "markets")
        if not markets:
            raise ValueError("markets must be non-empty")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, Real) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a finite positive real number")
        if isinstance(self.retry_limit, bool) or not isinstance(self.retry_limit, int) or self.retry_limit < 0:
            raise ValueError("retry_limit must be a non-negative integer")
        if isinstance(self.default_ttl_seconds, bool) or not isinstance(self.default_ttl_seconds, int) or self.default_ttl_seconds < 0:
            raise ValueError("default_ttl_seconds must be a non-negative integer")
        object.__setattr__(self, "source_id", _source_id(self.source_id))
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "markets", markets)
        object.__setattr__(self, "rate_group", _non_empty(self.rate_group, "rate group"))


@dataclass(frozen=True)
class DataResult:
    status: DataStatus
    records: Tuple[Any, ...]
    selected_source: Optional[str]
    attempted_sources: Tuple[str, ...]
    coverage: float
    fetched_at: datetime
    from_cache: bool
    failures: Tuple[ProviderFailure, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, DataStatus):
            raise ValueError("status must be a DataStatus")
        if isinstance(self.coverage, bool) or not isinstance(self.coverage, Real) or not math.isfinite(self.coverage) or not 0.0 <= self.coverage <= 1.0:
            raise ValueError("coverage must be a finite real number between 0.0 and 1.0")
        selected = None if self.selected_source is None else _source_id(self.selected_source)
        attempted = _string_tuple(self.attempted_sources, _source_id, "attempted sources")
        failures = tuple(self.failures)
        if any(not isinstance(failure, ProviderFailure) for failure in failures):
            raise ValueError("failures must be ProviderFailure values")
        if not isinstance(self.fetched_at, datetime) or self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("fetched_at must be a timezone-aware datetime")
        _boolean(self.from_cache, "from_cache")
        if self.status in (DataStatus.OK, DataStatus.PARTIAL) and selected is None:
            raise ValueError("successful or partial results require a selected source")
        if self.status is DataStatus.OK and self.coverage != 1.0:
            raise ValueError("ok results require complete coverage")
        if selected is not None and selected not in attempted:
            raise ValueError("selected source must be attempted")
        if any(failure.source_id not in attempted for failure in failures):
            raise ValueError("failure sources must be attempted")
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "selected_source", selected)
        object.__setattr__(self, "attempted_sources", attempted)
        object.__setattr__(self, "failures", failures)
