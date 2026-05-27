from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import re
import time
from typing import Any

from investment_knowledge_mcp.config import AppConfig, get_config
from investment_knowledge_mcp.serialization import to_jsonable


class FutuProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class PositionSnapshot:
    positions: list[dict[str, Any]]
    fetched_at: datetime
    source: str = "futu"
    cached: bool = False


@dataclass(frozen=True)
class IpoSnapshot:
    ipos: list[dict[str, Any]]
    fetched_at: datetime
    market: str = "HK"
    source: str = "futu"
    cached: bool = False


_CACHE: PositionSnapshot | None = None
_CACHE_MONOTONIC: float = 0.0
_IPO_CACHE: IpoSnapshot | None = None
_IPO_CACHE_MONOTONIC: float = 0.0
_IPO_CACHE_SECONDS = 60


def get_futu_positions(config: AppConfig | None = None) -> PositionSnapshot:
    config = config or get_config()
    cached = _get_cached_snapshot(config.futu_position_cache_seconds)
    if cached is not None:
        return PositionSnapshot(
            positions=cached.positions,
            fetched_at=cached.fetched_at,
            source=cached.source,
            cached=True,
        )

    snapshot = _fetch_positions(config)
    _set_cached_snapshot(snapshot)
    return snapshot


def get_hk_ipo_list(config: AppConfig | None = None) -> IpoSnapshot:
    config = config or get_config()
    cached = _get_cached_ipo_snapshot()
    if cached is not None:
        return IpoSnapshot(
            ipos=cached.ipos,
            fetched_at=cached.fetched_at,
            market=cached.market,
            source=cached.source,
            cached=True,
        )

    snapshot = _fetch_hk_ipo_list(config)
    _set_cached_ipo_snapshot(snapshot)
    return snapshot


def _get_cached_snapshot(cache_seconds: int) -> PositionSnapshot | None:
    if cache_seconds <= 0 or _CACHE is None:
        return None
    if time.monotonic() - _CACHE_MONOTONIC > cache_seconds:
        return None
    return _CACHE


def _get_cached_ipo_snapshot() -> IpoSnapshot | None:
    if _IPO_CACHE is None:
        return None
    if time.monotonic() - _IPO_CACHE_MONOTONIC > _IPO_CACHE_SECONDS:
        return None
    return _IPO_CACHE


def _set_cached_snapshot(snapshot: PositionSnapshot) -> None:
    global _CACHE, _CACHE_MONOTONIC
    _CACHE = snapshot
    _CACHE_MONOTONIC = time.monotonic()


def _set_cached_ipo_snapshot(snapshot: IpoSnapshot) -> None:
    global _IPO_CACHE, _IPO_CACHE_MONOTONIC
    _IPO_CACHE = snapshot
    _IPO_CACHE_MONOTONIC = time.monotonic()


def _fetch_positions(config: AppConfig) -> PositionSnapshot:
    try:
        import futu as ft
    except ImportError as exc:
        raise FutuProviderError("futu-api 未安装，无法读取富途持仓。") from exc

    context_cls = _trade_context_class(ft, config.futu_trade_market)
    security_firm = _enum_value(ft.SecurityFirm, config.futu_security_firm)
    trade_env = _enum_value(ft.TrdEnv, config.futu_trade_env)

    context = _create_trade_context(
        context_cls,
        {
            "host": config.futu_opend_host,
            "port": config.futu_opend_port,
            "security_firm": security_firm,
        },
    )
    try:
        kwargs: dict[str, Any] = {
            "trd_env": trade_env,
            "refresh_cache": config.futu_position_refresh_cache,
        }
        if config.futu_account_id:
            kwargs["acc_id"] = config.futu_account_id
        else:
            kwargs["acc_index"] = config.futu_account_index

        ret, data = _position_list_query(context, kwargs)
        if ret != ft.RET_OK:
            raise FutuProviderError(f"富途持仓查询失败：{data}")

        return PositionSnapshot(
            positions=_normalize_positions(data),
            fetched_at=datetime.now(timezone.utc),
        )
    finally:
        context.close()


def _fetch_hk_ipo_list(config: AppConfig) -> IpoSnapshot:
    try:
        import futu as ft
    except ImportError as exc:
        raise FutuProviderError("futu-api 未安装，无法读取港股新股。") from exc

    quote_context = _create_quote_context(
        ft.OpenQuoteContext,
        {
            "host": config.futu_opend_host,
            "port": config.futu_opend_port,
        },
    )
    try:
        ret, data = _ipo_list_query(quote_context, _enum_value(ft.Market, "HK"))
        if ret != ft.RET_OK:
            raise FutuProviderError(f"富途港股新股查询失败：{data}")

        return IpoSnapshot(
            ipos=_normalize_ipos(data),
            fetched_at=datetime.now(timezone.utc),
            market="HK",
        )
    finally:
        quote_context.close()


def _position_list_query(context: Any, kwargs: dict[str, Any]) -> tuple[Any, Any]:
    supported_kwargs = _filter_supported_kwargs(context.position_list_query, kwargs)
    return _call_with_keyword_retry(context.position_list_query, supported_kwargs)


def _ipo_list_query(context: Any, market: Any) -> tuple[Any, Any]:
    try:
        return context.get_ipo_list(market=market)
    except TypeError as exc:
        if "keyword" not in str(exc) and "positional" not in str(exc):
            raise
        return context.get_ipo_list(market)


def _create_trade_context(context_cls: Any, kwargs: dict[str, Any]) -> Any:
    supported_kwargs = _filter_supported_kwargs(context_cls, kwargs)
    return _call_with_keyword_retry(context_cls, supported_kwargs)


def _create_quote_context(context_cls: Any, kwargs: dict[str, Any]) -> Any:
    supported_kwargs = _filter_supported_kwargs(context_cls, kwargs)
    return _call_with_keyword_retry(context_cls, supported_kwargs)


def _filter_supported_kwargs(callable_obj: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return kwargs

    parameters = signature.parameters
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in parameters}


def _call_with_keyword_retry(callable_obj: Any, kwargs: dict[str, Any]) -> Any:
    remaining = dict(kwargs)
    while True:
        try:
            return callable_obj(**remaining)
        except TypeError as exc:
            keyword = _unexpected_keyword(str(exc))
            if not keyword or keyword not in remaining:
                raise
            remaining.pop(keyword)


def _unexpected_keyword(message: str) -> str | None:
    patterns = [
        r"unexpected keyword argument '([^']+)'",
        r"got an unexpected keyword argument \"([^\"]+)\"",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    return None


def _trade_context_class(ft: Any, trade_market: str) -> Any:
    market = trade_market.strip().upper()
    if market == "HK":
        return ft.OpenSecTradeContext
    if market in {"US", "CN"}:
        return ft.OpenSecTradeContext
    return ft.OpenSecTradeContext


def _normalize_ipos(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        records = data.to_dict("records")
    elif isinstance(data, list):
        records = data
    else:
        records = []

    normalized = []
    for row in records:
        item = to_jsonable(row)
        normalized.append(
            {
                "code": _clean_empty(item.get("code")),
                "name": _clean_empty(item.get("name")),
                "list_time": _clean_empty(item.get("list_time")),
                "ipo_price_min": _clean_empty(item.get("ipo_price_min")),
                "ipo_price_max": _clean_empty(item.get("ipo_price_max")),
                "list_price": _clean_empty(item.get("list_price")),
                "lot_size": _clean_empty(item.get("lot_size")),
                "entrance_price": _clean_empty(item.get("entrance_price")),
                "is_subscribe_status": item.get("is_subscribe_status"),
                "apply_end_time": _clean_empty(item.get("apply_end_time")),
                "raw": item,
            }
        )
    return normalized


def _clean_empty(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().upper() in {"", "N/A", "NONE", "NULL"}:
        return None
    return value


def _enum_value(enum_cls: Any, name: str) -> Any:
    normalized = name.strip().upper()
    if hasattr(enum_cls, normalized):
        return getattr(enum_cls, normalized)
    for key, value in vars(enum_cls).items():
        if key.upper() == normalized:
            return value
    raise FutuProviderError(f"不支持的富途配置值：{enum_cls.__name__}.{name}")


def _normalize_positions(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        records = data.to_dict("records")
    elif isinstance(data, list):
        records = data
    else:
        records = []

    normalized = []
    for row in records:
        item = to_jsonable(row)
        normalized.append(
            {
                "code": item.get("code"),
                "stock_name": item.get("stock_name") or item.get("name"),
                "qty": item.get("qty"),
                "can_sell_qty": item.get("can_sell_qty"),
                "cost_price": item.get("cost_price"),
                "market_val": item.get("market_val"),
                "nominal_price": item.get("nominal_price"),
                "pl_ratio": item.get("pl_ratio"),
                "pl_val": item.get("pl_val"),
                "currency": item.get("currency"),
                "raw": item,
            }
        )
    return normalized
