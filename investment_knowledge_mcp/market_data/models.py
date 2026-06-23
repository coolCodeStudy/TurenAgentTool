from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Generic, TypeVar


T = TypeVar("T")


def to_plain(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class SourceRef:
    provider: str
    domain: str
    label: str
    url: str | None = None


@dataclass(frozen=True)
class FetchResult(Generic[T]):
    status: str
    provider: str
    fetched_at: datetime
    data: T | None = None
    source_refs: list[SourceRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider": self.provider,
            "fetched_at": self.fetched_at.isoformat(),
            "source_refs": to_plain(self.source_refs),
            "warnings": self.warnings,
            "raw_metadata": to_plain(self.raw_metadata),
        }


@dataclass(frozen=True)
class SessionState:
    market: str
    session_date: date
    run_mode: str
    label: str
    timezone: str
    is_open: bool
    elapsed_session_ratio: float | None = None


@dataclass(frozen=True)
class IndexQuote:
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    turnover: float | None = None
    currency: str | None = None


@dataclass(frozen=True)
class TurnoverSnapshot:
    actual_turnover: float | None
    projected_turnover: float | None
    currency: str | None
    average_5d: float | None = None
    average_20d: float | None = None
    average_60d: float | None = None
    metric: str = "turnover"
    projection_confidence: str = "unavailable"


@dataclass(frozen=True)
class BreadthSnapshot:
    advancers: int | None = None
    decliners: int | None = None
    unchanged: int | None = None
    limit_up: int | None = None
    limit_down: int | None = None
    new_highs: int | None = None
    new_lows: int | None = None


@dataclass(frozen=True)
class HotStockCandidate:
    symbol: str
    name: str
    market: str
    move_pct: float | None
    volume_heat: float | None
    turnover: float | None = None
    catalyst: str | None = None
    theme: str | None = None
    relative_move: float | None = None
    user_relevance: str = "unavailable"
    source: str | None = None


@dataclass(frozen=True)
class HotIndustryCandidate:
    industry: str
    market: str
    performance_pct: float | None
    volume_heat: float | None
    representative_stocks: list[str] = field(default_factory=list)
    catalyst: str | None = None
    theme_label: str | None = None
    breadth: float | None = None
    source: str | None = None


@dataclass(frozen=True)
class CatalystSnippet:
    target: str
    market: str
    text: str
    source: str
    quality: str = "low"
