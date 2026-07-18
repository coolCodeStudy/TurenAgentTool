"""Provider-neutral data source contracts."""

from .contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    ProviderDescriptor,
    ProviderFailure,
    SourceCapability,
    SourcePlan,
)
from .pool import DataSourcePool, ExternalDataSource, MemoryResultCache, ResultCache
from .market_bars import (
    FutuMarketBarsSource,
    YahooMarketBarsSource,
    default_market_bar_pool,
    market_bar_records_by_symbol,
)

__all__ = [
    "DataRequest",
    "DataResult",
    "DataStatus",
    "ProviderDescriptor",
    "ProviderFailure",
    "SourceCapability",
    "SourcePlan",
    "DataSourcePool",
    "ExternalDataSource",
    "MemoryResultCache",
    "ResultCache",
    "FutuMarketBarsSource",
    "YahooMarketBarsSource",
    "default_market_bar_pool",
    "market_bar_records_by_symbol",
]
