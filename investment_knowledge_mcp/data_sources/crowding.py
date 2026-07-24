"""Approved source metadata and adapters for crowded-trade evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from investment_knowledge_mcp.futu_provider import (
    FutuCrowdingSnapshot,
    FutuProviderError,
    get_futu_crowding_snapshot,
)

from .contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    ProviderDescriptor,
    ProviderFailure,
    SourceCapability,
)
from .pool import DataSourcePool, ResultCache


def _normalized(value: str, field: str) -> str:
    if not isinstance(value, str) or not (cleaned := value.strip().casefold()):
        raise ValueError(f"{field} must be non-empty")
    return cleaned


def _normalized_tuple(values: tuple[str, ...], field: str, *, upper: bool = False) -> tuple[str, ...]:
    normalized = tuple(
        _normalized(value, field).upper() if upper else _normalized(value, field)
        for value in values
    )
    if not normalized:
        raise ValueError(f"{field} must be non-empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


@dataclass(frozen=True)
class SourceApproval:
    source_id: str
    access_tier: str
    permitted_uses: tuple[str, ...]
    redistribution_allowed: bool
    enabled_markets: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _normalized(self.source_id, "source_id"))
        object.__setattr__(self, "access_tier", _normalized(self.access_tier, "access_tier"))
        object.__setattr__(
            self,
            "permitted_uses",
            _normalized_tuple(tuple(self.permitted_uses), "permitted_uses"),
        )
        object.__setattr__(
            self,
            "enabled_markets",
            _normalized_tuple(tuple(self.enabled_markets), "enabled_markets", upper=True),
        )
        if not isinstance(self.redistribution_allowed, bool):
            raise ValueError("redistribution_allowed must be a boolean")


FUTU_CROWDING_APPROVAL = SourceApproval(
    source_id="futu_crowding",
    access_tier="account_entitled",
    permitted_uses=("private_internal_research",),
    redistribution_allowed=False,
    enabled_markets=("US", "HK"),
)

SOURCE_APPROVALS = {
    FUTU_CROWDING_APPROVAL.source_id: FUTU_CROWDING_APPROVAL,
}


def source_is_approved(source_id: str, use_case: str) -> bool:
    try:
        normalized_source = _normalized(source_id, "source_id")
        normalized_use = _normalized(use_case, "use_case")
    except ValueError:
        return False
    approval = SOURCE_APPROVALS.get(normalized_source)
    return approval is not None and normalized_use in approval.permitted_uses


_CAPABILITIES = (
    SourceCapability.OWNERSHIP_CONCENTRATION,
    SourceCapability.SHORT_INTEREST,
    SourceCapability.OPTIONS_POSITIONING,
    SourceCapability.EVENT_CALENDAR,
)


class _MemoizedBundleLoader:
    def __init__(self, loader: Callable[[list[str], str, str], FutuCrowdingSnapshot]) -> None:
        self._loader = loader
        self._cache: dict[tuple[tuple[str, ...], str, str], FutuCrowdingSnapshot] = {}

    def __call__(self, codes: list[str], start: str, end: str) -> FutuCrowdingSnapshot:
        key = (tuple(codes), start, end)
        if key not in self._cache:
            self._cache[key] = self._loader(codes, start, end)
        return self._cache[key]


class FutuCrowdingSource:
    descriptor = ProviderDescriptor(
        "futu_crowding",
        _CAPABILITIES,
        ("US", "HK"),
        8.0,
        0,
        "crowding",
        3600,
    )

    def __init__(
        self,
        loader: Callable[[list[str], str, str], FutuCrowdingSnapshot] = get_futu_crowding_snapshot,
    ) -> None:
        self._loader = loader

    def fetch(self, request: DataRequest) -> DataResult:
        if not source_is_approved(self.descriptor.source_id, "private_internal_research"):
            return self._unavailable("source_not_approved")
        if request.capability not in _CAPABILITIES:
            return self._unavailable("unsupported_capability")
        if request.market not in self.descriptor.markets:
            return self._unavailable("unsupported_market")
        if len(request.symbols) != 1 or request.start is None or request.end is None:
            return self._unavailable("invalid_request")
        symbol = request.symbols[0]
        if not symbol.startswith(f"{request.market}."):
            return self._unavailable("identity_mismatch")

        try:
            snapshot = self._loader(
                [symbol],
                request.start.isoformat(),
                request.end.isoformat(),
            )
        except (FutuProviderError, ValueError, RuntimeError):
            return self._unavailable("provider_unavailable")
        if not isinstance(snapshot, FutuCrowdingSnapshot) or snapshot.source != "futu":
            return self._unavailable("provider_contract_error")
        record = _normalized_record(snapshot, symbol, request.capability)
        if record is None:
            family = _family_key(request.capability)
            failure_code = snapshot.failures_by_code.get(symbol, {}).get(family)
            return self._unavailable(
                failure_code or "empty_result",
                fetched_at=snapshot.fetched_at,
            )
        return DataResult(
            DataStatus.OK,
            (record,),
            self.descriptor.source_id,
            (self.descriptor.source_id,),
            1.0,
            snapshot.fetched_at,
            False,
            (),
        )

    def _unavailable(
        self,
        code: str,
        *,
        fetched_at: datetime | None = None,
    ) -> DataResult:
        return DataResult(
            DataStatus.UNAVAILABLE,
            (),
            None,
            (self.descriptor.source_id,),
            0.0,
            fetched_at or datetime.now(timezone.utc),
            False,
            (ProviderFailure(code, self.descriptor.source_id, False, False),),
        )


def default_crowding_source_pool(
    *,
    loader: Callable[[list[str], str, str], FutuCrowdingSnapshot] = get_futu_crowding_snapshot,
    cache: ResultCache | None = None,
) -> DataSourcePool:
    pool = DataSourcePool(cache=cache)
    pool.register(FutuCrowdingSource(_MemoizedBundleLoader(loader)))
    return pool


def _family_key(capability: SourceCapability) -> str:
    return {
        SourceCapability.OWNERSHIP_CONCENTRATION: "ownership",
        SourceCapability.SHORT_INTEREST: "short_interest",
        SourceCapability.OPTIONS_POSITIONING: "options",
        SourceCapability.EVENT_CALENDAR: "events",
    }[capability]


def _normalized_record(
    snapshot: FutuCrowdingSnapshot,
    symbol: str,
    capability: SourceCapability,
) -> dict[str, Any] | None:
    fetched = snapshot.fetched_at.isoformat()
    common = {
        "symbol": symbol,
        "market": symbol.split(".", 1)[0],
        "source_id": "futu_crowding",
        "provider": "futu",
        "access_tier": FUTU_CROWDING_APPROVAL.access_tier,
        "fetched_at": fetched,
        "freshness": "end_of_day",
    }
    if capability is SourceCapability.OWNERSHIP_CONCENTRATION:
        rows = snapshot.ownership_by_code.get(symbol) or []
        values = [float(row["holder_pct"]) for row in rows if _number(row.get("holder_pct")) is not None]
        if not values:
            return None
        observed = next((str(row.get("observed_at")) for row in rows if row.get("observed_at")), "")
        return {
            **common,
            "family": "ownership",
            "metric": "ownership_top_holders_pct",
            "value": round(sum(values[:10]), 6),
            "unit": "percent",
            "direction": "long",
            "observed_at": observed,
            "published_at": observed,
            "cohort": "reported_top_holders",
            "metadata": {"holder_count": min(len(values), 10)},
        }
    if capability is SourceCapability.SHORT_INTEREST:
        rows = snapshot.short_interest_by_code.get(symbol) or []
        row = rows[0] if rows else None
        if row is None or _number(row.get("short_percent")) is None:
            return None
        observed = str(row.get("observed_at") or "")
        return {
            **common,
            "family": "short_interest",
            "metric": "short_percent",
            "value": float(row["short_percent"]),
            "unit": "percent",
            "direction": "short",
            "observed_at": observed,
            "published_at": observed,
            "cohort": "provider_reported_outstanding_short",
            "metadata": {
                "days_to_cover": _number(row.get("days_to_cover")),
                "shares_short": _number(row.get("shares_short")),
                "aggregated_short": _number(row.get("aggregated_short")),
            },
        }
    if capability is SourceCapability.OPTIONS_POSITIONING:
        rows = snapshot.options_by_code.get(symbol) or []
        if not rows:
            return None
        total_oi = sum(_number(row.get("open_interest")) or 0.0 for row in rows)
        total_volume = sum(_number(row.get("volume")) or 0.0 for row in rows)
        if total_oi <= 0 and total_volume <= 0:
            return None
        call_oi = sum(
            _number(row.get("open_interest")) or 0.0
            for row in rows
            if str(row.get("option_type") or "").upper() == "CALL"
        )
        call_volume = sum(
            _number(row.get("volume")) or 0.0
            for row in rows
            if str(row.get("option_type") or "").upper() == "CALL"
        )
        expiry_oi: dict[str, float] = {}
        for row in rows:
            expiry = str(row.get("expiry_date") or "unknown")
            expiry_oi[expiry] = expiry_oi.get(expiry, 0.0) + (_number(row.get("open_interest")) or 0.0)
        return {
            **common,
            "family": "options",
            "metric": "options_open_interest",
            "value": total_oi,
            "unit": "contracts",
            "direction": "two_sided",
            "observed_at": snapshot.fetched_at.date().isoformat(),
            "published_at": snapshot.fetched_at.date().isoformat(),
            "cohort": "listed_chain_near_expiries",
            "metadata": {
                "total_volume": total_volume,
                "call_open_interest_ratio": call_oi / total_oi if total_oi else None,
                "call_volume_ratio": call_volume / total_volume if total_volume else None,
                "expiry_concentration": max(expiry_oi.values()) / total_oi if total_oi and expiry_oi else None,
            },
        }
    if capability is SourceCapability.EVENT_CALENDAR:
        rows = snapshot.events_by_code.get(symbol) or []
        dated = sorted((row for row in rows if row.get("event_date")), key=lambda row: str(row["event_date"]))
        if not dated:
            return None
        row = dated[0]
        return {
            **common,
            "family": "events",
            "metric": "earnings_event",
            "value": str(row["event_date"]),
            "unit": "date",
            "direction": "context",
            "observed_at": snapshot.fetched_at.date().isoformat(),
            "published_at": snapshot.fetched_at.date().isoformat(),
            "cohort": "issuer_event_calendar",
            "metadata": {"date_status": str(row.get("date_status") or "unknown")},
        }
    return None


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number
