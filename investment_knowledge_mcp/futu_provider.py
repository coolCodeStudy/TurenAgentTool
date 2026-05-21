from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


_CACHE: PositionSnapshot | None = None
_CACHE_MONOTONIC: float = 0.0


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


def _get_cached_snapshot(cache_seconds: int) -> PositionSnapshot | None:
    if cache_seconds <= 0 or _CACHE is None:
        return None
    if time.monotonic() - _CACHE_MONOTONIC > cache_seconds:
        return None
    return _CACHE


def _set_cached_snapshot(snapshot: PositionSnapshot) -> None:
    global _CACHE, _CACHE_MONOTONIC
    _CACHE = snapshot
    _CACHE_MONOTONIC = time.monotonic()


def _fetch_positions(config: AppConfig) -> PositionSnapshot:
    try:
        import futu as ft
    except ImportError as exc:
        raise FutuProviderError("futu-api 未安装，无法读取富途持仓。") from exc

    context_cls = _trade_context_class(ft, config.futu_trade_market)
    security_firm = _enum_value(ft.SecurityFirm, config.futu_security_firm)
    trade_env = _enum_value(ft.TrdEnv, config.futu_trade_env)
    trade_market = _enum_value(ft.TrdMarket, config.futu_trade_market)

    context = context_cls(
        host=config.futu_opend_host,
        port=config.futu_opend_port,
        security_firm=security_firm,
    )
    try:
        kwargs: dict[str, Any] = {
            "trd_env": trade_env,
            "trd_market": trade_market,
            "refresh_cache": config.futu_position_refresh_cache,
        }
        if config.futu_account_id:
            kwargs["acc_id"] = config.futu_account_id
        else:
            kwargs["acc_index"] = config.futu_account_index

        ret, data = context.position_list_query(**kwargs)
        if ret != ft.RET_OK:
            raise FutuProviderError(f"富途持仓查询失败：{data}")

        return PositionSnapshot(
            positions=_normalize_positions(data),
            fetched_at=datetime.now(timezone.utc),
        )
    finally:
        context.close()


def _trade_context_class(ft: Any, trade_market: str) -> Any:
    market = trade_market.strip().upper()
    if market == "HK":
        return ft.OpenSecTradeContext
    if market in {"US", "CN"}:
        return ft.OpenSecTradeContext
    return ft.OpenSecTradeContext


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
