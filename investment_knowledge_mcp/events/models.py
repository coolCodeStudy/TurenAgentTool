from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


EVENT_FORMS = {"4", "144", "8-K", "424B5", "S-3"}
SCAN_STATUSES = {"ok", "partial", "failed"}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class EventSource:
    source_type: str
    publisher: str
    url: str
    title: str | None = None
    published_at: str | None = None
    market: str | None = None
    symbol: str | None = None
    accession_number: str | None = None
    cik: str | None = None
    form_type: str | None = None
    raw_hash: str | None = None
    excerpt: str | None = None
    parsed_facts: dict[str, Any] = field(default_factory=dict)
    fetch_status: str = "ok"

    def to_record(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "publisher": self.publisher,
            "url": self.url,
            "canonical_url": canonical_url(self.url),
            "title": self.title,
            "published_at": self.published_at,
            "market": self.market,
            "symbol": self.symbol,
            "accession_number": self.accession_number,
            "cik": self.cik,
            "form_type": self.form_type,
            "raw_hash": self.raw_hash,
            "excerpt": self.excerpt,
            "parsed_facts": self.parsed_facts,
            "fetch_status": self.fetch_status,
        }


@dataclass(frozen=True)
class EventPacket:
    market: str
    symbol: str
    event_type: str
    event_title: str
    event_date: date | str | None
    priority: str
    confidence: str
    source_facts: list[dict[str, Any]] = field(default_factory=list)
    derived_facts: list[dict[str, Any]] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    media_labels: list[dict[str, Any]] = field(default_factory=list)
    portfolio_relevance: dict[str, Any] = field(default_factory=dict)
    source: EventSource | None = None
    next_trading_date: date | str | None = None
    status: str = "active"
    needs_research: bool = False
    scan_status: str = "ok"

    @property
    def dedupe_key(self) -> str:
        event_date = _date_key(self.event_date)
        source_key = ""
        if self.source is not None:
            source_key = self.source.accession_number or canonical_url(self.source.url)
        return ":".join(
            [
                self.market.upper(),
                self.symbol.upper(),
                self.event_type,
                event_date or "undated",
                source_key or "unknown_source",
            ]
        )

    def to_record(self, source_ids: list[int] | None = None) -> dict[str, Any]:
        return {
            "market": self.market.upper(),
            "symbol": self.symbol.upper(),
            "event_type": self.event_type,
            "event_title": self.event_title,
            "event_date": _date_key(self.event_date),
            "next_trading_date": _date_key(self.next_trading_date),
            "priority": self.priority,
            "confidence": self.confidence,
            "status": self.status,
            "source_ids": source_ids or [],
            "source_facts": self.source_facts,
            "derived_facts": self.derived_facts,
            "media_labels": self.media_labels,
            "uncertainties": self.uncertainties,
            "portfolio_relevance": self.portfolio_relevance,
            "dedupe_key": self.dedupe_key,
            "scan_status": self.scan_status,
            "needs_research": self.needs_research,
        }


@dataclass(frozen=True)
class ScanError:
    market: str | None
    symbol: str | None
    stage: str
    message: str

    def to_record(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "symbol": self.symbol,
            "stage": self.stage,
            "message": self.message,
        }


@dataclass(frozen=True)
class EventScanResult:
    scope: str
    market: str | None
    symbol: str | None
    status: str
    events: list[EventPacket]
    errors: list[ScanError] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    symbols_total: int = 0
    symbols_scanned: int = 0
    persisted_events: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_events(
        cls,
        *,
        scope: str,
        market: str | None,
        symbol: str | None,
        events: list[EventPacket],
        errors: list[ScanError],
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        symbols_total: int = 0,
        symbols_scanned: int = 0,
        persisted_events: list[dict[str, Any]] | None = None,
    ) -> "EventScanResult":
        if errors and events:
            status = "partial"
        elif errors:
            status = "failed"
        else:
            status = "ok"
        return cls(
            scope=scope,
            market=market,
            symbol=symbol,
            status=status,
            events=events,
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
            symbols_total=symbols_total,
            symbols_scanned=symbols_scanned,
            persisted_events=persisted_events or [],
        )


def canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.strip().split("#", 1)[0]


def priority_rank(priority: str) -> int:
    return PRIORITY_ORDER.get(priority, 99)


def _date_key(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10] if value else None
