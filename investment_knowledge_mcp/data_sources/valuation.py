"""Provider-neutral adapters and source plans for stock valuation inputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timezone
import math
import re
from typing import Any

from .contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    ProviderDescriptor,
    ProviderFailure,
    SourceCapability,
    SourcePlan,
)


VALUATION_FACT_METRICS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "cash",
    "debt",
    "net_debt",
    "shares_outstanding",
    "ebitda",
    "book_value",
)
MARKET_SNAPSHOT_METRICS = ("price", "market_cap", "shares_outstanding")
_MARKETS = ("US", "HK", "KR")
_SOURCE_DESCRIPTORS: dict[str, tuple[str, str, str]] = {
    "sec_companyfacts": ("sec_companyfacts", "sec", "official_financial"),
    "sec_filing": ("sec_filing", "sec", "regulator_filing"),
    "hkexnews": ("hkexnews", "hkex", "regulator_filing"),
    "hkex_filing": ("hkex_filing", "hkex", "regulator_filing"),
    "dart_filing": ("dart_filing", "dart", "regulator_filing"),
    "fss_filing": ("fss_filing", "fss", "regulator_filing"),
    "company_ir": ("company_ir", "company_ir", "company_ir"),
    "company_report": ("company_report", "official_research", "official_financial"),
    "vendor_financial": ("vendor_financial", "vendor", "vendor_financial"),
    "shared_market": ("market_snapshot", "shared_market", "market_snapshot"),
    "yahoo": ("market_snapshot", "yahoo", "market_snapshot"),
}
_FINANCIAL_ORDER = {
    "US": ("sec_companyfacts", "sec_filing", "company_ir", "vendor_financial"),
    "HK": ("hkexnews", "hkex_filing", "company_report", "vendor_financial"),
    "KR": ("dart_filing", "fss_filing", "company_ir", "vendor_financial"),
}
_MARKET_ORDER = ("shared_market", "yahoo")


class ValuationFactsSource:
    """Normalize one injected valuation transport into the shared pool contract."""

    def __init__(
        self,
        source_id: str,
        capability: SourceCapability,
        source_type: str,
        provider: str,
        loader: Callable[[str, str], object],
        *,
        markets: tuple[str, ...] = _MARKETS,
        timeout_seconds: float = 8.0,
        default_ttl_seconds: int = 300,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        descriptor = valuation_source_descriptor(source_id)
        if capability not in {
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            SourceCapability.MARKET_SNAPSHOT,
        }:
            raise ValueError("valuation source requires a valuation capability")
        if descriptor["source_type"] != source_type or descriptor["provider"] != provider:
            raise ValueError("valuation source identity must use the canonical descriptor")
        if capability is SourceCapability.MARKET_SNAPSHOT and source_type != "market_snapshot":
            raise ValueError("market snapshot sources require market_snapshot source type")
        if capability is SourceCapability.OFFICIAL_FINANCIAL_FACTS and source_type == "market_snapshot":
            raise ValueError("financial fact sources cannot use market_snapshot source type")
        self.descriptor = ProviderDescriptor(
            source_id,
            (capability,),
            markets,
            timeout_seconds,
            0,
            "stock_valuation",
            default_ttl_seconds,
        )
        self._source_type = source_type
        self._provider = provider
        self._allowed_metrics = (
            frozenset(MARKET_SNAPSHOT_METRICS)
            if capability is SourceCapability.MARKET_SNAPSHOT
            else frozenset(VALUATION_FACT_METRICS)
        )
        self._loader = loader
        self._now = now or (lambda: datetime.now(timezone.utc))

    def fetch(self, request: DataRequest) -> DataResult:
        source_id = self.descriptor.source_id
        if not _valid_request(request, self.descriptor.capabilities[0]):
            return self._unavailable("invalid_request", fallback_allowed=False)
        try:
            payload = self._loader(request.symbols[0], request.market)
        except Exception as exc:
            return self._unavailable(
                "provider_unavailable",
                retryable=True,
                detail=type(exc).__name__,
            )

        fetched_at = _payload_fetched_at(payload) or self._now()
        if not _aware_datetime(fetched_at):
            return self._unavailable("provider_contract_error", fetched_at=self._now())
        try:
            records = _normalize_records(
                payload,
                source_type=self._source_type,
                provider=self._provider,
                freshness=request.freshness,
                allowed_metrics=self._allowed_metrics,
            )
        except (OverflowError, TypeError, ValueError):
            return self._unavailable("provider_contract_error", fetched_at=fetched_at)
        if not records:
            return self._unavailable("empty_result", fetched_at=fetched_at)

        coverage = _coverage(records, request.required_fields)
        status = DataStatus.OK if coverage == 1.0 else DataStatus.PARTIAL
        failures = () if status is DataStatus.OK else (
            ProviderFailure("incomplete_coverage", source_id, False, True),
        )
        return DataResult(
            status,
            records,
            source_id,
            (source_id,),
            coverage,
            fetched_at,
            False,
            failures,
        )

    def _unavailable(
        self,
        code: str,
        *,
        retryable: bool = False,
        fallback_allowed: bool = True,
        fetched_at: datetime | None = None,
        detail: str | None = None,
    ) -> DataResult:
        source_id = self.descriptor.source_id
        return DataResult(
            DataStatus.UNAVAILABLE,
            (),
            None,
            (source_id,),
            0.0,
            fetched_at or self._now(),
            False,
            (ProviderFailure(code, source_id, retryable, fallback_allowed, detail),),
        )


def valuation_financial_plan(
    market: str,
    *,
    available_sources: tuple[str, ...] | None = None,
) -> SourcePlan:
    """Return official-first financial-fact precedence for one supported market."""
    order = _source_order(_FINANCIAL_ORDER, market, available_sources)
    return SourcePlan(
        SourceCapability.OFFICIAL_FINANCIAL_FACTS,
        order[:1],
        order,
        order[1:],
        False,
        True,
    )


def valuation_market_plan(*, available_sources: tuple[str, ...] | None = None) -> SourcePlan:
    """Return the current shared/free market-snapshot source precedence."""
    order = _filter_sources(_MARKET_ORDER, available_sources)
    return SourcePlan(
        SourceCapability.MARKET_SNAPSHOT,
        order[:1],
        order,
        order[1:],
        False,
        True,
    )


def valuation_source_descriptor(source_id: str) -> dict[str, str]:
    normalized = str(source_id).strip().casefold()
    try:
        source_type, provider, family = _SOURCE_DESCRIPTORS[normalized]
    except KeyError as exc:
        raise ValueError("unknown valuation source") from exc
    return {
        "source_id": normalized,
        "source_type": source_type,
        "provider": provider,
        "family": family,
    }


def _source_order(
    plans: dict[str, tuple[str, ...]],
    market: str,
    available_sources: tuple[str, ...] | None,
) -> tuple[str, ...]:
    normalized_market = str(market).strip().upper()
    try:
        order = plans[normalized_market]
    except KeyError as exc:
        raise ValueError("unsupported valuation market") from exc
    return _filter_sources(order, available_sources)


def _filter_sources(order: tuple[str, ...], available_sources: tuple[str, ...] | None) -> tuple[str, ...]:
    if available_sources is None:
        return order
    available = {str(source_id).strip().casefold() for source_id in available_sources}
    filtered = tuple(source_id for source_id in order if source_id in available)
    if not filtered:
        raise ValueError("valuation plan requires at least one registered source")
    return filtered


def _valid_request(request: DataRequest, capability: SourceCapability) -> bool:
    return (
        request.capability is capability
        and len(request.symbols) == 1
        and request.start is None
        and request.end is None
    )


def _payload_fetched_at(payload: object) -> datetime | None:
    if isinstance(payload, Mapping):
        value = payload.get("fetched_at")
        return value if isinstance(value, datetime) else None
    value = getattr(payload, "fetched_at", None)
    return value if isinstance(value, datetime) else None


def _payload_facts(payload: object) -> Sequence[object]:
    if isinstance(payload, Mapping):
        facts = payload.get("facts", ())
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        facts = payload
    else:
        facts = getattr(payload, "facts", ())
    if not isinstance(facts, Sequence) or isinstance(facts, (str, bytes)):
        raise TypeError("valuation facts must be a sequence")
    return facts


def _normalize_records(
    payload: object,
    *,
    source_type: str,
    provider: str,
    freshness: str,
    allowed_metrics: frozenset[str],
) -> tuple[dict[str, object], ...]:
    records: dict[str, dict[str, object]] = {}
    for raw in _payload_facts(payload):
        if not isinstance(raw, Mapping):
            raise TypeError("valuation fact must be a mapping")
        metric = raw.get("metric")
        if not isinstance(metric, str) or metric not in allowed_metrics:
            continue
        number = _finite(raw.get("value"))
        if number is None:
            continue
        record: dict[str, object] = {
            "metric": metric,
            "value": number,
            "source_type": source_type,
            "provider": provider,
        }
        if currency := _currency(raw.get("currency")):
            record["currency"] = currency
        if period := _period(raw.get("period_end")):
            record["period_end"] = period
        if timestamp := _timestamp(raw.get("timestamp")):
            record["timestamp"] = timestamp
        record["freshness"] = freshness
        records[metric] = record
    return tuple(records[metric] for metric in sorted(records))


def _coverage(records: tuple[dict[str, object], ...], required_fields: tuple[str, ...]) -> float:
    if not required_fields:
        return 1.0
    present = {str(record["metric"]) for record in records}
    return len(present.intersection(required_fields)) / len(required_fields)


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _currency(value: object) -> str | None:
    normalized = value.strip().upper() if isinstance(value, str) else ""
    return normalized if re.fullmatch(r"[A-Z]{3}", normalized) else None


def _period(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if not _aware_datetime(parsed):
        return None
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _aware_datetime(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
