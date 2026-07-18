"""Provider-neutral adapters for existing market-bar transports."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from investment_knowledge_mcp.futu_provider import FutuProviderError, get_futu_market_bars
from investment_knowledge_mcp.market_data_provider import MarketDataProviderError, get_yahoo_market_bars

from .contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    ProviderDescriptor,
    ProviderFailure,
    SourceCapability,
)
from .pool import DataSourcePool, ResultCache


_MARKETS = ("CN", "HK", "US", "MULTI")


class _MarketBarsSource:
    descriptor: ProviderDescriptor

    def __init__(self, loader: Callable[[list[str], str, str], object]) -> None:
        self._loader = loader

    def fetch(self, request: DataRequest) -> DataResult:
        if not _valid_request(request):
            return self._unavailable("invalid_request", retryable=False, fallback_allowed=False)

        try:
            snapshot = self._loader(list(request.symbols), request.start.isoformat(), request.end.isoformat())
        except (FutuProviderError, MarketDataProviderError):
            return self._unavailable("provider_unavailable", retryable=True, fallback_allowed=True)

        if getattr(snapshot, "source", None) != self.descriptor.source_id:
            return self._unavailable("provider_contract_error", retryable=False, fallback_allowed=True)
        fetched_at = getattr(snapshot, "fetched_at", None)
        if not _aware_datetime(fetched_at):
            return self._unavailable("provider_contract_error", retryable=False, fallback_allowed=True)

        try:
            records = _records_for_request(getattr(snapshot, "bars_by_code"), request.symbols)
        except (TypeError, ValueError):
            return self._unavailable("provider_contract_error", retryable=False, fallback_allowed=True, fetched_at=fetched_at)

        covered = len(records)
        if not covered:
            return self._unavailable("empty_result", retryable=False, fallback_allowed=True, fetched_at=fetched_at)
        if covered == len(request.symbols):
            return DataResult(
                DataStatus.OK,
                records,
                self.descriptor.source_id,
                (self.descriptor.source_id,),
                1.0,
                fetched_at,
                False,
                (),
            )
        return DataResult(
            DataStatus.PARTIAL,
            records,
            self.descriptor.source_id,
            (self.descriptor.source_id,),
            covered / len(request.symbols),
            fetched_at,
            False,
            (ProviderFailure("incomplete_coverage", self.descriptor.source_id, False, True),),
        )

    def _unavailable(
        self,
        code: str,
        *,
        retryable: bool,
        fallback_allowed: bool,
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
            (ProviderFailure(code, self.descriptor.source_id, retryable, fallback_allowed),),
        )


class FutuMarketBarsSource(_MarketBarsSource):
    descriptor = ProviderDescriptor(
        "futu",
        (SourceCapability.MARKET_BARS,),
        _MARKETS,
        5.0,
        0,
        "market_bars",
        60,
    )

    def __init__(self, loader: Callable[[list[str], str, str], object] = get_futu_market_bars) -> None:
        super().__init__(loader)


class YahooMarketBarsSource(_MarketBarsSource):
    descriptor = ProviderDescriptor(
        "yahoo_chart",
        (SourceCapability.MARKET_BARS,),
        _MARKETS,
        5.0,
        0,
        "market_bars",
        60,
    )

    def __init__(self, loader: Callable[[list[str], str, str], object] = get_yahoo_market_bars) -> None:
        super().__init__(loader)


def default_market_bar_pool(*, cache: ResultCache | None = None) -> DataSourcePool:
    """Create the standard market-bar registry without fetching any data."""
    pool = DataSourcePool(cache=cache)
    pool.register(FutuMarketBarsSource())
    pool.register(YahooMarketBarsSource())
    return pool


def market_bar_records_by_symbol(result: DataResult) -> dict[str, list[dict[str, object]]]:
    """Convert normalized records into fresh legacy-friendly containers."""
    converted: dict[str, list[dict[str, object]]] = {}
    for record in result.records:
        if not isinstance(record, Mapping) or set(record) != {"symbol", "bars"}:
            raise ValueError("market bar record has an invalid shape")
        symbol = record["symbol"]
        bars = record["bars"]
        if not isinstance(symbol, str) or not symbol or symbol != symbol.strip().upper() or symbol in converted:
            raise ValueError("market bar record has an invalid symbol")
        if not isinstance(bars, tuple):
            raise ValueError("market bar record bars must be a tuple")
        if not bars:
            raise ValueError("market bar record bars must not be empty")
        copied_bars: list[dict[str, object]] = []
        for bar in bars:
            if not isinstance(bar, Mapping):
                raise ValueError("market bar value must be a mapping")
            copied_bars.append(dict(bar))
        converted[symbol] = copied_bars
    return converted


def _valid_request(request: DataRequest) -> bool:
    return (
        request.capability is SourceCapability.MARKET_BARS
        and bool(request.symbols)
        and request.start is not None
        and request.end is not None
    )


def _aware_datetime(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _records_for_request(bars_by_code: object, symbols: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    if not isinstance(bars_by_code, Mapping):
        raise ValueError("bars_by_code must be a mapping")
    records: list[dict[str, object]] = []
    for symbol in symbols:
        bars = bars_by_code.get(symbol)
        if not bars:
            continue
        if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)):
            raise ValueError("market bars must be a sequence")
        copied_bars: list[dict[str, object]] = []
        for bar in bars:
            if not isinstance(bar, Mapping):
                raise ValueError("market bar must be a mapping")
            copied_bars.append(dict(bar))
        records.append({"symbol": symbol, "bars": tuple(copied_bars)})
    return tuple(records)
