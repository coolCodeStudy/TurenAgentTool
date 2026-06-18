from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
    orders_by_code: dict[str, list[dict[str, Any]]] | None = None
    order_error: str | None = None
    source: str = "futu"
    cached: bool = False


@dataclass(frozen=True)
class TradeHistorySnapshot:
    deals: list[dict[str, Any]]
    fetched_at: datetime
    start: str
    end: str
    account_info: dict[str, Any] | None = None
    account_error: str | None = None
    source: str = "futu"


@dataclass(frozen=True)
class CashFlowSnapshot:
    cash_flows: list[dict[str, Any]]
    fetched_at: datetime
    start: str
    end: str
    errors: list[str]
    source: str = "futu"


@dataclass(frozen=True)
class IndexHistorySnapshot:
    indexes: list[dict[str, Any]]
    fetched_at: datetime
    start: str
    end: str
    errors: list[str]
    source: str = "futu"


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


def get_hk_ipo_list(config: AppConfig | None = None, include_orders: bool = True) -> IpoSnapshot:
    config = config or get_config()
    cached = _get_cached_ipo_snapshot(include_orders=include_orders)
    if cached is not None:
        return IpoSnapshot(
            ipos=cached.ipos,
            fetched_at=cached.fetched_at,
            market=cached.market,
            orders_by_code=cached.orders_by_code,
            order_error=cached.order_error,
            source=cached.source,
            cached=True,
        )

    snapshot = _fetch_hk_ipo_list(config, include_orders=include_orders)
    _set_cached_ipo_snapshot(snapshot)
    return snapshot


def get_futu_trade_history(start: str, end: str, config: AppConfig | None = None) -> TradeHistorySnapshot:
    config = config or get_config()
    return _fetch_trade_history(config=config, start=start, end=end)


def get_futu_cash_flows(start: str, end: str, config: AppConfig | None = None) -> CashFlowSnapshot:
    config = config or get_config()
    return _fetch_cash_flows(config=config, start=start, end=end)


def get_futu_index_history(
    start: str,
    end: str,
    indexes: list[dict[str, Any]],
    config: AppConfig | None = None,
) -> IndexHistorySnapshot:
    config = config or get_config()
    return _fetch_index_history(config=config, start=start, end=end, indexes=indexes)


def _get_cached_snapshot(cache_seconds: int) -> PositionSnapshot | None:
    if cache_seconds <= 0 or _CACHE is None:
        return None
    if time.monotonic() - _CACHE_MONOTONIC > cache_seconds:
        return None
    return _CACHE


def _get_cached_ipo_snapshot(include_orders: bool) -> IpoSnapshot | None:
    if _IPO_CACHE is None:
        return None
    if time.monotonic() - _IPO_CACHE_MONOTONIC > _IPO_CACHE_SECONDS:
        return None
    if include_orders and _IPO_CACHE.orders_by_code is None:
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


def _fetch_hk_ipo_list(config: AppConfig, include_orders: bool) -> IpoSnapshot:
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

        ipos = _normalize_ipos(data)
        orders_by_code: dict[str, list[dict[str, Any]]] | None = None
        order_error: str | None = None
        if include_orders:
            try:
                orders_by_code = _fetch_hk_order_map(config=config, ft=ft, ipos=ipos)
            except Exception as exc:
                order_error = str(exc)

        return IpoSnapshot(
            ipos=ipos,
            fetched_at=datetime.now(timezone.utc),
            market="HK",
            orders_by_code=orders_by_code,
            order_error=order_error,
        )
    finally:
        quote_context.close()


def _fetch_hk_order_map(config: AppConfig, ft: Any, ipos: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    context = _create_trade_context(
        ft.OpenSecTradeContext,
        {
            "host": config.futu_opend_host,
            "port": config.futu_opend_port,
            "security_firm": _enum_value(ft.SecurityFirm, config.futu_security_firm),
        },
    )
    try:
        trade_env = _enum_value(ft.TrdEnv, config.futu_trade_env)
        trade_market = _optional_enum_value(getattr(ft, "TrdMarket", None), "HK")
        base_kwargs: dict[str, Any] = {
            "trd_env": trade_env,
            "refresh_cache": True,
        }
        if trade_market is not None:
            base_kwargs["order_market"] = trade_market
        if config.futu_account_id:
            base_kwargs["acc_id"] = config.futu_account_id
        else:
            base_kwargs["acc_index"] = config.futu_account_index

        orders: list[dict[str, Any]] = []
        errors: list[str] = []
        successful_queries = 0
        if hasattr(context, "order_list_query"):
            ret, data = _call_with_keyword_retry(context.order_list_query, dict(base_kwargs))
            if ret == ft.RET_OK:
                successful_queries += 1
                orders.extend(_normalize_orders(data))
            else:
                errors.append(f"当前订单查询失败：{data}")

        if hasattr(context, "history_order_list_query"):
            history_kwargs = dict(base_kwargs)
            now = datetime.now()
            history_kwargs["start"] = (now - timedelta(days=90)).strftime("%Y-%m-%d")
            history_kwargs["end"] = now.strftime("%Y-%m-%d")
            ret, data = _call_with_keyword_retry(context.history_order_list_query, history_kwargs)
            if ret == ft.RET_OK:
                successful_queries += 1
                orders.extend(_normalize_orders(data))
            else:
                errors.append(f"历史订单查询失败：{data}")

        if successful_queries == 0 and errors:
            raise FutuProviderError("；".join(errors))

        return _map_orders_to_ipos(orders=orders, ipos=ipos)
    finally:
        context.close()


def _fetch_trade_history(config: AppConfig, start: str, end: str) -> TradeHistorySnapshot:
    try:
        import futu as ft
    except ImportError as exc:
        raise FutuProviderError("futu-api 未安装，无法读取富途交易记录。") from exc

    context = _create_trade_context(
        ft.OpenSecTradeContext,
        {
            "host": config.futu_opend_host,
            "port": config.futu_opend_port,
            "security_firm": _enum_value(ft.SecurityFirm, config.futu_security_firm),
        },
    )
    try:
        kwargs = _trade_query_kwargs(config=config, ft=ft, refresh_cache=True)
        kwargs["start"] = start
        kwargs["end"] = end

        ret, data = _history_deal_list_query(context, kwargs)
        if ret != ft.RET_OK:
            raise FutuProviderError(f"富途历史成交查询失败：{data}")

        account_info: dict[str, Any] | None = None
        account_error: str | None = None
        try:
            account_info = _fetch_account_info(context=context, config=config, ft=ft)
        except Exception as exc:
            account_error = str(exc)

        return TradeHistorySnapshot(
            deals=_normalize_deals(data),
            fetched_at=datetime.now(timezone.utc),
            start=start,
            end=end,
            account_info=account_info,
            account_error=account_error,
        )
    finally:
        context.close()


def _fetch_cash_flows(config: AppConfig, start: str, end: str) -> CashFlowSnapshot:
    try:
        import futu as ft
    except ImportError as exc:
        raise FutuProviderError("futu-api 未安装，无法读取富途资金流水。") from exc

    context = _create_trade_context(
        ft.OpenSecTradeContext,
        {
            "host": config.futu_opend_host,
            "port": config.futu_opend_port,
            "security_firm": _enum_value(ft.SecurityFirm, config.futu_security_firm),
        },
    )
    try:
        if not hasattr(context, "get_acc_cash_flow"):
            raise FutuProviderError("当前 futu-api 版本没有 get_acc_cash_flow，无法读取资金流水。")

        kwargs = _cash_flow_query_kwargs(config=config, ft=ft)
        kwargs["start"] = start
        kwargs["end"] = end
        kwargs["clearing_date"] = ""
        ret, data = _call_with_keyword_retry(context.get_acc_cash_flow, _filter_supported_kwargs(context.get_acc_cash_flow, kwargs))
        if ret == ft.RET_OK:
            return CashFlowSnapshot(
                cash_flows=_normalize_cash_flows(data),
                fetched_at=datetime.now(timezone.utc),
                start=start,
                end=end,
                errors=[],
            )

        errors = [f"区间资金流水查询失败：{data}"]
        start_date = _parse_iso_date(start)
        end_date = _parse_iso_date(end)
        days = _date_range(start_date, end_date)
        if len(days) > 20:
            return CashFlowSnapshot(
                cash_flows=[],
                fetched_at=datetime.now(timezone.utc),
                start=start,
                end=end,
                errors=errors
                + [
                    "富途证券账户资金流水通常需要按清算日逐日查询；本区间超过 20 天，"
                    "为避免触发频率限制，当前命令未逐日回补。"
                ],
            )

        rows: list[dict[str, Any]] = []
        for day in days:
            daily_kwargs = _cash_flow_query_kwargs(config=config, ft=ft)
            daily_kwargs["clearing_date"] = day.isoformat()
            ret, data = _call_with_keyword_retry(
                context.get_acc_cash_flow,
                _filter_supported_kwargs(context.get_acc_cash_flow, daily_kwargs),
            )
            if ret == ft.RET_OK:
                rows.extend(_normalize_cash_flows(data))
            else:
                errors.append(f"{day.isoformat()} 资金流水查询失败：{data}")

        return CashFlowSnapshot(
            cash_flows=rows,
            fetched_at=datetime.now(timezone.utc),
            start=start,
            end=end,
            errors=errors,
        )
    finally:
        context.close()


def _fetch_index_history(
    config: AppConfig,
    start: str,
    end: str,
    indexes: list[dict[str, Any]],
) -> IndexHistorySnapshot:
    try:
        import futu as ft
    except ImportError as exc:
        raise FutuProviderError("futu-api 未安装，无法读取富途指数行情。") from exc

    quote_context = _create_quote_context(
        ft.OpenQuoteContext,
        {
            "host": config.futu_opend_host,
            "port": config.futu_opend_port,
        },
    )
    try:
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for item in indexes:
            name = str(item.get("name") or "").strip() or "unknown index"
            market = str(item.get("market") or "").strip()
            relevance = str(item.get("portfolio_relevance") or item.get("relevance") or "").strip()
            code_candidates = _normalize_index_code_candidates(item)
            result, error = _fetch_one_index_history(
                quote_context=quote_context,
                ft=ft,
                name=name,
                market=market,
                relevance=relevance,
                code_candidates=code_candidates,
                start=start,
                end=end,
            )
            if result is not None:
                rows.append(result)
            elif error:
                errors.append(error)
        return IndexHistorySnapshot(
            indexes=rows,
            fetched_at=datetime.now(timezone.utc),
            start=start,
            end=end,
            errors=errors,
        )
    finally:
        quote_context.close()


def _fetch_one_index_history(
    *,
    quote_context: Any,
    ft: Any,
    name: str,
    market: str,
    relevance: str,
    code_candidates: list[dict[str, Any]],
    start: str,
    end: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if not code_candidates:
        return None, f"{name} 缺少 Futu code 候选。"

    errors: list[str] = []
    for candidate in code_candidates:
        code = candidate["code"]
        try:
            kwargs = {
                "code": code,
                "start": start,
                "end": end,
                "ktype": _optional_enum_value(getattr(ft, "KLType", None), "K_DAY"),
                "max_count": 100,
            }
            kwargs = {key: value for key, value in kwargs.items() if value is not None}
            ret, data, _page_key = _request_history_kline(quote_context, kwargs)
            if ret != ft.RET_OK:
                errors.append(f"{code}: {data}")
                continue
            candles = _normalize_klines(data)
            if not candles:
                errors.append(f"{code}: no kline rows")
                continue
            return _summarize_index_history(
                name=name,
                market=market,
                code=code,
                relevance=relevance,
                candles=candles,
                start=start,
                end=end,
                instrument_type=candidate.get("instrument_type"),
                proxy_for=candidate.get("proxy_for"),
                source_note=candidate.get("source_note"),
            ), None
        except Exception as exc:
            errors.append(f"{code}: {exc}")
    return None, f"{name} 指数行情读取失败：" + "；".join(errors[:3])


def _normalize_index_code_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_candidates = item.get("codes") or []
    if not raw_candidates and item.get("code"):
        raw_candidates = [item["code"]]
    candidates: list[dict[str, Any]] = []
    for raw in raw_candidates:
        if isinstance(raw, dict):
            code = str(raw.get("code") or "").strip()
            if not code:
                continue
            candidates.append(
                {
                    "code": code,
                    "instrument_type": str(raw.get("instrument_type") or "index").strip() or "index",
                    "proxy_for": _clean_optional_text(raw.get("proxy_for")),
                    "source_note": _clean_optional_text(raw.get("source_note")),
                }
            )
            continue
        code = str(raw).strip()
        if code:
            candidates.append(
                {
                    "code": code,
                    "instrument_type": "index",
                    "proxy_for": None,
                    "source_note": None,
                }
            )
    return candidates


def _clean_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _request_history_kline(context: Any, kwargs: dict[str, Any]) -> tuple[Any, Any, Any]:
    if not hasattr(context, "request_history_kline"):
        raise FutuProviderError("当前 futu-api 版本没有 request_history_kline，无法读取指数行情。")
    supported_kwargs = _filter_supported_kwargs(context.request_history_kline, kwargs)
    return _call_with_keyword_retry(context.request_history_kline, supported_kwargs)


def _position_list_query(context: Any, kwargs: dict[str, Any]) -> tuple[Any, Any]:
    supported_kwargs = _filter_supported_kwargs(context.position_list_query, kwargs)
    return _call_with_keyword_retry(context.position_list_query, supported_kwargs)


def _history_deal_list_query(context: Any, kwargs: dict[str, Any]) -> tuple[Any, Any]:
    if not hasattr(context, "history_deal_list_query"):
        raise FutuProviderError("当前 futu-api 版本没有 history_deal_list_query，无法读取历史成交。")
    supported_kwargs = _filter_supported_kwargs(context.history_deal_list_query, kwargs)
    return _call_with_keyword_retry(context.history_deal_list_query, supported_kwargs)


def _fetch_account_info(context: Any, config: AppConfig, ft: Any) -> dict[str, Any]:
    if not hasattr(context, "accinfo_query"):
        raise FutuProviderError("当前 futu-api 版本没有 accinfo_query。")
    kwargs = _trade_query_kwargs(config=config, ft=ft, refresh_cache=True)
    ret, data = _call_with_keyword_retry(context.accinfo_query, _filter_supported_kwargs(context.accinfo_query, kwargs))
    if ret != ft.RET_OK:
        raise FutuProviderError(f"富途账户信息查询失败：{data}")
    return _normalize_account_info(data)


def _trade_query_kwargs(config: AppConfig, ft: Any, refresh_cache: bool) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "trd_env": _enum_value(ft.TrdEnv, config.futu_trade_env),
        "refresh_cache": refresh_cache,
    }
    trade_market = _optional_enum_value(getattr(ft, "TrdMarket", None), config.futu_trade_market)
    if trade_market is not None:
        kwargs["trd_market"] = trade_market
        kwargs["order_market"] = trade_market
    if config.futu_account_id:
        kwargs["acc_id"] = config.futu_account_id
    else:
        kwargs["acc_index"] = config.futu_account_index
    return kwargs


def _cash_flow_query_kwargs(config: AppConfig, ft: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "trd_env": _enum_value(ft.TrdEnv, config.futu_trade_env),
    }
    cashflow_direction = _optional_enum_value(getattr(ft, "CashFlowDirection", None), "NONE")
    if cashflow_direction is not None:
        kwargs["cashflow_direction"] = cashflow_direction
    if config.futu_account_id:
        kwargs["acc_id"] = config.futu_account_id
    else:
        kwargs["acc_index"] = config.futu_account_index
    return kwargs


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


def _normalize_klines(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        records = data.to_dict("records")
    elif isinstance(data, list):
        records = data
    else:
        records = []
    return [to_jsonable(row) for row in records]


def _summarize_index_history(
    *,
    name: str,
    market: str,
    code: str,
    relevance: str,
    candles: list[dict[str, Any]],
    start: str,
    end: str,
    instrument_type: str | None = None,
    proxy_for: str | None = None,
    source_note: str | None = None,
) -> dict[str, Any]:
    first = candles[0]
    last = candles[-1]
    base = _float_or_none(first.get("last_close")) or _float_or_none(first.get("open")) or _float_or_none(first.get("close"))
    close = _float_or_none(last.get("close"))
    weekly_change_pct = None
    if base not in (None, 0) and close is not None:
        weekly_change_pct = (close - base) / base * 100
    max_move = _max_daily_move(candles)
    result = {
        "name": name,
        "market": market,
        "code": code,
        "instrument_type": instrument_type or "index",
        "source": "futu.request_history_kline",
        "period_start": start,
        "period_end": end,
        "start_reference": base,
        "close": close,
        "weekly_change_pct": weekly_change_pct,
        "weekly_change": _pct_text(weekly_change_pct),
        "max_daily_move_pct": max_move.get("change_pct"),
        "max_daily_move": max_move.get("text"),
        "portfolio_relevance": relevance,
        "summary": _index_summary_text(
            name=name,
            weekly_change_pct=weekly_change_pct,
            max_move=max_move,
            relevance=relevance,
        ),
        "candles": candles,
    }
    if proxy_for:
        result["proxy_for"] = proxy_for
    if source_note:
        result["source_note"] = source_note
    return result


def _max_daily_move(candles: list[dict[str, Any]]) -> dict[str, Any]:
    best: dict[str, Any] = {}
    best_abs = -1.0
    for candle in candles:
        change = _float_or_none(candle.get("change_rate"))
        if change is None:
            last_close = _float_or_none(candle.get("last_close"))
            close = _float_or_none(candle.get("close"))
            if last_close not in (None, 0) and close is not None:
                change = (close - last_close) / last_close * 100
        if change is None:
            continue
        if abs(change) > best_abs:
            best_abs = abs(change)
            best = {
                "change_pct": change,
                "time_key": candle.get("time_key"),
                "text": f"{_display_kline_date(candle.get('time_key'))} {_pct_text(change)}",
            }
    return best


def _display_kline_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    return text.split()[0]


def _index_summary_text(
    *,
    name: str,
    weekly_change_pct: float | None,
    max_move: dict[str, Any],
    relevance: str,
) -> str:
    change_text = _pct_text(weekly_change_pct) if weekly_change_pct is not None else "本周涨跌缺失"
    move_text = max_move.get("text") or "最大单日波动缺失"
    if relevance:
        return f"{name} 本周 {change_text}，最大单日波动 {move_text}；{relevance}"
    return f"{name} 本周 {change_text}，最大单日波动 {move_text}。"


def _pct_text(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _enum_value(enum_cls: Any, name: str) -> Any:
    normalized = name.strip().upper()
    if hasattr(enum_cls, normalized):
        return getattr(enum_cls, normalized)
    for key, value in vars(enum_cls).items():
        if key.upper() == normalized:
            return value
    raise FutuProviderError(f"不支持的富途配置值：{enum_cls.__name__}.{name}")


def _optional_enum_value(enum_cls: Any, name: str) -> Any | None:
    if enum_cls is None:
        return None
    try:
        return _enum_value(enum_cls, name)
    except Exception:
        return None


def _normalize_orders(data: Any) -> list[dict[str, Any]]:
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
                "stock_name": _clean_empty(item.get("stock_name") or item.get("name")),
                "qty": _clean_empty(item.get("qty")),
                "price": _clean_empty(item.get("price")),
                "order_status": _clean_empty(item.get("order_status")),
                "trd_side": _clean_empty(item.get("trd_side")),
                "order_type": _clean_empty(item.get("order_type")),
                "create_time": _clean_empty(item.get("create_time")),
                "updated_time": _clean_empty(item.get("updated_time") or item.get("update_time")),
                "raw": item,
            }
        )
    return normalized


def _normalize_deals(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        records = data.to_dict("records")
    elif isinstance(data, list):
        records = data
    else:
        records = []

    normalized = []
    for row in records:
        item = to_jsonable(row)
        qty = _clean_empty(item.get("qty") or item.get("deal_qty"))
        price = _clean_empty(item.get("price") or item.get("deal_price"))
        amount = _deal_amount(qty=qty, price=price)
        code = _clean_empty(item.get("code"))
        normalized.append(
            {
                "deal_id": _clean_empty(item.get("deal_id")),
                "order_id": _clean_empty(item.get("order_id")),
                "code": code,
                "stock_name": _clean_empty(item.get("stock_name") or item.get("name")),
                "trd_side": _clean_empty(item.get("trd_side")),
                "qty": qty,
                "price": price,
                "amount": amount,
                "currency": _clean_empty(item.get("currency")) or _currency_from_code(code),
                "create_time": _clean_empty(
                    item.get("create_time")
                    or item.get("deal_time")
                    or item.get("time")
                    or item.get("updated_time")
                ),
                "raw": item,
            }
        )
    return normalized


def _normalize_account_info(data: Any) -> dict[str, Any]:
    if hasattr(data, "to_dict"):
        records = data.to_dict("records")
    elif isinstance(data, list):
        records = data
    else:
        records = []
    item = to_jsonable(records[0]) if records else to_jsonable(data)
    return {
        "total_assets": _clean_empty(item.get("total_assets") or item.get("total_asset")),
        "market_val": _clean_empty(item.get("market_val") or item.get("market_value")),
        "cash": _clean_empty(item.get("cash")),
        "power": _clean_empty(item.get("power")),
        "avl_withdrawal_cash": _clean_empty(item.get("avl_withdrawal_cash")),
        "currency": _clean_empty(item.get("currency")),
        "raw": item,
    }


def _normalize_cash_flows(data: Any) -> list[dict[str, Any]]:
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
                "cashflow_id": _clean_empty(item.get("cashflow_id")),
                "clearing_date": _clean_empty(item.get("clearing_date")),
                "settlement_date": _clean_empty(item.get("settlement_date")),
                "currency": _clean_empty(item.get("currency")),
                "cashflow_type": _clean_empty(item.get("cashflow_type")),
                "cashflow_direction": _clean_empty(item.get("cashflow_direction")),
                "cashflow_amount": _clean_empty(item.get("cashflow_amount")),
                "cashflow_remark": _clean_empty(item.get("cashflow_remark")),
                "raw": item,
            }
        )
    return normalized


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _date_range(start: date, end: date) -> list[date]:
    if end < start:
        start, end = end, start
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _deal_amount(qty: Any, price: Any) -> float | None:
    try:
        return float(qty) * float(price)
    except (TypeError, ValueError):
        return None


def _currency_from_code(code: Any) -> str | None:
    if not code:
        return None
    market = str(code).split(".", 1)[0].upper()
    if market == "HK":
        return "HKD"
    if market == "US":
        return "USD"
    if market in {"SH", "SZ", "CN"}:
        return "CNY"
    return None


def _map_orders_to_ipos(orders: list[dict[str, Any]], ipos: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {str(ipo.get("code") or ""): [] for ipo in ipos}
    for order in orders:
        order_keys = _code_keys(order.get("code"))
        order_name = str(order.get("stock_name") or "").strip()
        for ipo in ipos:
            ipo_code = str(ipo.get("code") or "")
            ipo_name = str(ipo.get("name") or "").strip()
            if order_keys & _code_keys(ipo_code) or (ipo_name and order_name and ipo_name in order_name):
                result.setdefault(ipo_code, []).append(order)

    for matched_orders in result.values():
        matched_orders.sort(
            key=lambda item: str(item.get("updated_time") or item.get("create_time") or ""),
            reverse=True,
        )
    return result


def _code_keys(value: Any) -> set[str]:
    if value is None:
        return set()
    raw = str(value).strip().upper()
    if not raw:
        return set()
    keys = {raw}
    if "." in raw:
        keys.add(raw.split(".")[-1])
    digits = re.sub(r"\D", "", raw)
    if digits:
        keys.add(digits)
        keys.add(digits.lstrip("0") or "0")
    return keys


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
