from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import os
from typing import Any

import requests

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.decision_repository import add_stock_observation
from investment_knowledge_mcp.market_symbol_map import ProviderSymbol, resolve_provider_symbol


REQUEST_TIMEOUT_SECONDS = 8
USER_AGENT = "TurenAgentTool decision-data-probe/1.0"


@dataclass(frozen=True)
class ProviderCoverage:
    provider: str
    provider_symbol: str
    ok: bool
    coverage: list[str]
    message: str
    source_url: str | None = None
    diagnostics: dict[str, Any] | None = None


def refresh_external_decision_observations(
    *,
    stock: dict[str, Any],
    mode: str = "focused",
) -> dict[str, Any]:
    if mode == "quick":
        return {"mode": mode, "refreshed": [], "diagnostics": [{"message": "quick mode skips external refresh"}]}
    if os.getenv("DECISION_EXTERNAL_REFRESH_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return {
            "mode": mode,
            "refreshed": [],
            "diagnostics": [{"message": "external decision-data refresh disabled by environment"}],
        }

    symbol = str(stock.get("symbol") or "")
    market = str(stock.get("market") or "")
    stock_id = int(stock["id"])
    refreshed: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    naver = fetch_naver_finance_kr(symbol=symbol, market=market)
    diagnostics.append(_coverage_dict(naver.coverage))
    if naver.data:
        refreshed.extend(_write_naver_observations(stock_id=stock_id, payload=naver))

    yahoo_stock = fetch_yahoo_chart(symbol=symbol, market=market)
    diagnostics.append(_coverage_dict(yahoo_stock.coverage))
    if yahoo_stock.data:
        technical = build_technical_snapshot(yahoo_stock)
        if technical:
            refreshed.append(_write_observation(stock_id, "technical_snapshot", technical, confidence=0.62, stale_days=1))

    if market.upper() == "KR":
        yahoo_index = fetch_yahoo_chart(symbol="^KS11", market="KR", provider_alias="yahoo_kospi")
        diagnostics.append(_coverage_dict(yahoo_index.coverage))
        relative = build_market_relative_strength(stock_chart=yahoo_stock, market_chart=yahoo_index)
        if relative:
            refreshed.append(_write_observation(stock_id, "market_relative_strength", relative, confidence=0.60, stale_days=2))

        sector = build_sector_relative_strength(symbol=symbol, market=market, stock_chart=yahoo_stock)
        if sector:
            refreshed.append(_write_observation(stock_id, "sector_relative_strength", sector, confidence=0.50, stale_days=3))

        ir = probe_company_ir(symbol=symbol, market=market)
        diagnostics.append(_coverage_dict(ir))
        if ir.ok:
            refreshed.append(
                _write_observation(
                    stock_id,
                    "chip_event_snapshot",
                    {
                        "provider": ir.provider,
                        "provider_symbol": ir.provider_symbol,
                        "source_url": ir.source_url,
                        "retrieved_at": _now(),
                        "status": "needs_research_review",
                        "summary": "Official SK hynix IR/newsroom sources are reachable; event details require research extraction.",
                        "coverage": ir.coverage,
                        "diagnostics": ir.diagnostics or {},
                    },
                    confidence=0.35,
                    stale_days=7,
                )
            )

    return {"mode": mode, "refreshed": refreshed, "diagnostics": diagnostics}


def probe_external_decision_data(symbol: str, market: str) -> dict[str, Any]:
    coverages = []
    naver = fetch_naver_finance_kr(symbol=symbol, market=market)
    coverages.append(naver.coverage)
    yahoo_stock = fetch_yahoo_chart(symbol=symbol, market=market)
    coverages.append(yahoo_stock.coverage)
    if market.strip().upper() == "KR":
        coverages.append(fetch_yahoo_chart(symbol="^KS11", market="KR", provider_alias="yahoo_kospi").coverage)
        coverages.append(probe_krx(symbol=symbol, market=market))
        coverages.append(probe_company_ir(symbol=symbol, market=market))
    return {
        "symbol": symbol,
        "market": market,
        "ok": any(item.ok for item in coverages),
        "provider": "external_adapter_ladder",
        "results": coverages,
    }


@dataclass(frozen=True)
class NaverPayload:
    coverage: ProviderCoverage
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class YahooChartPayload:
    coverage: ProviderCoverage
    data: dict[str, Any] | None = None


def fetch_naver_finance_kr(symbol: str, market: str) -> NaverPayload:
    try:
        provider_symbol = resolve_provider_symbol(symbol, market, "naver_finance_kr")
    except ValueError as exc:
        return NaverPayload(_coverage("naver_finance_kr", symbol, False, [], str(exc)))

    try:
        from bs4 import BeautifulSoup

        response = _http_get(provider_symbol.source_url or "")
        soup = BeautifulSoup(response.text, "html.parser")
        data = _parse_naver_main_page(soup, provider_symbol)
    except Exception as exc:
        return NaverPayload(
            _coverage(
                "naver_finance_kr",
                provider_symbol.symbol,
                False,
                [],
                f"{type(exc).__name__}: {exc}",
                provider_symbol.source_url,
            )
        )

    coverage = ["latest_quote_snapshot"]
    if data.get("valuation") or data.get("financial_table"):
        coverage.append("valuation_snapshot")
    if data.get("peer_comparison"):
        coverage.append("peer_comparison")
    return NaverPayload(
        _coverage(
            "naver_finance_kr",
            provider_symbol.symbol,
            True,
            coverage,
            "Naver Finance KR page parsed.",
            provider_symbol.source_url,
            {"fields": sorted(data.keys())},
        ),
        data,
    )


def fetch_yahoo_chart(symbol: str, market: str, provider_alias: str = "yahoo_finance") -> YahooChartPayload:
    try:
        provider_symbol = resolve_provider_symbol(symbol, market, provider_alias)
    except ValueError as exc:
        return YahooChartPayload(_coverage("yahoo_finance", symbol, False, [], str(exc)))

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{provider_symbol.symbol}?range=6mo&interval=1d"
    )
    try:
        response = _http_get(url)
        payload = response.json()
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not result:
            error = (payload.get("chart") or {}).get("error")
            raise ValueError(f"empty chart result: {error}")
        data = _parse_yahoo_chart(result, provider_symbol, url)
    except Exception as exc:
        return YahooChartPayload(
            _coverage(
                "yahoo_finance",
                provider_symbol.symbol,
                False,
                [],
                f"{type(exc).__name__}: {exc}",
                provider_symbol.source_url,
            )
        )
    return YahooChartPayload(
        _coverage(
            "yahoo_finance",
            provider_symbol.symbol,
            True,
            ["ohlcv", "technical_snapshot"],
            "Yahoo Finance chart parsed.",
            provider_symbol.source_url,
            {"points": len(data.get("bars") or [])},
        ),
        data,
    )


def probe_krx(symbol: str, market: str) -> ProviderCoverage:
    try:
        provider_symbol = resolve_provider_symbol(symbol, market, "krx_data_marketplace")
    except ValueError as exc:
        return _coverage("krx_data_marketplace", symbol, False, [], str(exc))
    try:
        response = _http_get(provider_symbol.source_url or "")
        ok = response.status_code < 400
    except Exception as exc:
        return _coverage(
            "krx_data_marketplace",
            provider_symbol.symbol,
            False,
            [],
            f"{type(exc).__name__}: {exc}",
            provider_symbol.source_url,
        )
    return _coverage(
        "krx_data_marketplace",
        provider_symbol.symbol,
        ok,
        ["official_market_data_catalog"] if ok else [],
        "KRX Data Marketplace reachable." if ok else f"HTTP {response.status_code}",
        provider_symbol.source_url,
        {"status_code": response.status_code},
    )


def probe_company_ir(symbol: str, market: str) -> ProviderCoverage:
    try:
        provider_symbol = resolve_provider_symbol(symbol, market, "company_ir_skhynix")
    except ValueError as exc:
        return _coverage("company_ir_and_newsroom", symbol, False, [], str(exc))
    urls = [
        provider_symbol.source_url or "https://www.skhynix.com/ir/UI-FR-IR06/",
        "https://news.skhynix.com/",
    ]
    results = []
    for url in urls:
        try:
            response = _http_get(url)
            results.append({"url": url, "status_code": response.status_code, "ok": response.status_code < 400})
        except Exception as exc:
            results.append({"url": url, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    ok = any(item.get("ok") for item in results)
    return _coverage(
        "company_ir_and_newsroom",
        provider_symbol.symbol,
        ok,
        ["chip_event_snapshot_source"] if ok else [],
        "Official company IR/newsroom reachable." if ok else "Official company sources are not reachable.",
        provider_symbol.source_url,
        {"urls": results},
    )


def build_technical_snapshot(chart: YahooChartPayload) -> dict[str, Any] | None:
    bars = (chart.data or {}).get("bars") or []
    closes = [bar["close"] for bar in bars if _is_number(bar.get("close"))]
    if len(closes) < 5:
        return None
    latest = closes[-1]
    ma20 = _average(closes[-20:]) if len(closes) >= 20 else None
    ma60 = _average(closes[-60:]) if len(closes) >= 60 else None
    return {
        "provider": "yahoo_finance",
        "provider_symbol": chart.coverage.provider_symbol,
        "source_url": chart.coverage.source_url,
        "retrieved_at": _now(),
        "latest_close": latest,
        "return_5d": _window_return(closes, 5),
        "return_20d": _window_return(closes, 20),
        "return_60d": _window_return(closes, 60),
        "ma20": ma20,
        "ma60": ma60,
        "above_ma20": latest > ma20 if ma20 else None,
        "above_ma60": latest > ma60 if ma60 else None,
        "bars": bars[-80:],
        "coverage": ["technical_snapshot"],
    }


def build_market_relative_strength(
    *,
    stock_chart: YahooChartPayload,
    market_chart: YahooChartPayload,
) -> dict[str, Any] | None:
    stock_bars = (stock_chart.data or {}).get("bars") or []
    market_bars = (market_chart.data or {}).get("bars") or []
    stock_closes = [bar["close"] for bar in stock_bars if _is_number(bar.get("close"))]
    market_closes = [bar["close"] for bar in market_bars if _is_number(bar.get("close"))]
    if len(stock_closes) < 20 or len(market_closes) < 20:
        return None
    values = {}
    for window in (20, 60, 120):
        stock_return = _window_return(stock_closes, window)
        market_return = _window_return(market_closes, window)
        values[f"relative_return_{window}d"] = (
            round(stock_return - market_return, 6) if stock_return is not None and market_return is not None else None
        )
    return {
        "provider": "yahoo_finance",
        "provider_symbol": stock_chart.coverage.provider_symbol,
        "benchmark_symbol": market_chart.coverage.provider_symbol,
        "source_url": stock_chart.coverage.source_url,
        "retrieved_at": _now(),
        **values,
        "coverage": ["market_relative_strength"],
    }


def build_sector_relative_strength(
    *,
    symbol: str,
    market: str,
    stock_chart: YahooChartPayload,
) -> dict[str, Any] | None:
    if market.strip().upper() != "KR":
        return None
    stock_closes = [bar["close"] for bar in ((stock_chart.data or {}).get("bars") or []) if _is_number(bar.get("close"))]
    if len(stock_closes) < 20:
        return None
    basket_returns = []
    basket_symbols = ["005930.KS", "MU", "SOXX"]
    for basket_symbol in basket_symbols:
        chart = fetch_yahoo_chart(symbol=basket_symbol, market="US")
        closes = [bar["close"] for bar in ((chart.data or {}).get("bars") or []) if _is_number(bar.get("close"))]
        value = _window_return(closes, 20) if len(closes) >= 20 else None
        if value is not None:
            basket_returns.append({"symbol": chart.coverage.provider_symbol, "return_20d": value})
    if not basket_returns:
        return None
    stock_return = _window_return(stock_closes, 20)
    basket_average = _average([item["return_20d"] for item in basket_returns])
    return {
        "provider": "yahoo_finance",
        "provider_symbol": stock_chart.coverage.provider_symbol,
        "basket": basket_returns,
        "basket_average_return_20d": basket_average,
        "relative_return_20d": round(stock_return - basket_average, 6) if stock_return is not None else None,
        "source_url": stock_chart.coverage.source_url,
        "retrieved_at": _now(),
        "coverage": ["sector_relative_strength"],
    }


def _write_naver_observations(stock_id: int, payload: NaverPayload) -> list[dict[str, Any]]:
    if not payload.data:
        return []
    rows = []
    quote = payload.data.get("quote")
    if quote:
        rows.append(_write_observation(stock_id, "latest_quote_snapshot", quote, confidence=0.70, stale_days=1))
    valuation = {
        key: value
        for key, value in {
            "provider": "naver_finance_kr",
            "provider_symbol": payload.coverage.provider_symbol,
            "source_url": payload.coverage.source_url,
            "retrieved_at": _now(),
            "valuation": payload.data.get("valuation") or {},
            "financial_table": payload.data.get("financial_table") or [],
            "peer_comparison": payload.data.get("peer_comparison") or [],
            "coverage": ["valuation_snapshot"],
        }.items()
        if value not in ({}, [])
    }
    if valuation.get("valuation") or valuation.get("financial_table") or valuation.get("peer_comparison"):
        rows.append(_write_observation(stock_id, "valuation_snapshot", valuation, confidence=0.58, stale_days=5))
    return rows


def _write_observation(
    stock_id: int,
    observation_type: str,
    value: dict[str, Any],
    *,
    confidence: float,
    stale_days: int,
) -> dict[str, Any]:
    source_id = None
    source_url = value.get("source_url")
    if source_url:
        source = repository.add_source(
            source_type="external_market_data",
            title=f"{value.get('provider')} {value.get('provider_symbol')} {observation_type}",
            url=source_url,
            publisher=value.get("provider"),
        )
        source_id = int(source["id"])
    observed_at = value.get("retrieved_at") or _now()
    stale_after = (datetime.now(timezone.utc) + timedelta(days=stale_days)).isoformat()
    return add_stock_observation(
        stock_id=stock_id,
        observation_type=observation_type,
        value=value,
        observed_at=observed_at,
        source_id=source_id,
        confidence=confidence,
        stale_after=stale_after,
    )


def _parse_naver_main_page(soup: BeautifulSoup, provider_symbol: ProviderSymbol) -> dict[str, Any]:
    quote = {
        "provider": "naver_finance_kr",
        "provider_symbol": provider_symbol.symbol,
        "source_url": provider_symbol.source_url,
        "retrieved_at": _now(),
        "last_price": _parse_number(_first_text(soup.select("p.no_today span.blind"))),
        "previous_close": _parse_number(_dt_value(soup, "전일")),
        "open_price": _parse_number(_dt_value(soup, "시가")),
        "high_price": _parse_number(_dt_value(soup, "고가")),
        "low_price": _parse_number(_dt_value(soup, "저가")),
        "volume": _parse_number(_dt_value(soup, "거래량")),
        "trading_value": _parse_number(_dt_value(soup, "거래대금")),
        "foreign_ownership": _parse_number(_dt_value(soup, "외국인한도주식수")),
        "coverage": ["latest_quote_snapshot"],
    }
    quote = {key: value for key, value in quote.items() if value is not None}
    return {
        "quote": quote,
        "valuation": _parse_naver_valuation(soup, provider_symbol),
        "financial_table": _parse_naver_financial_table(soup),
        "peer_comparison": _parse_naver_peer_table(soup),
    }


def _parse_naver_valuation(soup: BeautifulSoup, provider_symbol: ProviderSymbol) -> dict[str, Any]:
    fields = {}
    for label in ("PER", "EPS", "PBR", "BPS", "배당수익률", "시가총액"):
        value = _dt_value(soup, label)
        if value is not None:
            fields[label] = _parse_number(value)
    return {
        "provider": "naver_finance_kr",
        "provider_symbol": provider_symbol.symbol,
        "source_url": provider_symbol.source_url,
        "retrieved_at": _now(),
        "raw_fields": fields,
    }


def _parse_naver_financial_table(soup: BeautifulSoup) -> list[dict[str, Any]]:
    table = soup.select_one("table.tb_type1.tb_num.tb_type1_ifrs")
    if not table:
        return []
    headers = [_clean_text(item.get_text(" ", strip=True)) for item in table.select("thead th")]
    rows = []
    for tr in table.select("tbody tr")[:20]:
        cells = [_clean_text(item.get_text(" ", strip=True)) for item in tr.select("th,td")]
        if len(cells) >= 2:
            rows.append({"label": cells[0], "values": cells[1:], "headers": headers[1:]})
    return rows


def _parse_naver_peer_table(soup: BeautifulSoup) -> list[dict[str, Any]]:
    rows = []
    for tr in soup.select("table.tb_type1 tr")[:80]:
        cells = [_clean_text(item.get_text(" ", strip=True)) for item in tr.select("th,td")]
        if len(cells) >= 3 and any(cell for cell in cells):
            text = " ".join(cells)
            if "PER" in text or "PBR" in text:
                continue
            if any(token in text for token in ("삼성전자", "SK하이닉스", "Micron", "마이크론")):
                rows.append({"cells": cells[:12]})
    return rows[:10]


def _parse_yahoo_chart(result: dict[str, Any], provider_symbol: ProviderSymbol, url: str) -> dict[str, Any]:
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [{}])[0]) or {}
    closes = quote.get("close") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    volumes = quote.get("volume") or []
    bars = []
    for index, timestamp in enumerate(timestamps):
        close = _safe_index(closes, index)
        if close is None:
            continue
        bars.append(
            {
                "date": datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat(),
                "open": _safe_index(opens, index),
                "high": _safe_index(highs, index),
                "low": _safe_index(lows, index),
                "close": close,
                "volume": _safe_index(volumes, index),
            }
        )
    return {
        "provider": "yahoo_finance",
        "provider_symbol": provider_symbol.symbol,
        "source_url": provider_symbol.source_url,
        "chart_url": url,
        "retrieved_at": _now(),
        "bars": bars,
    }


def _coverage(
    provider: str,
    provider_symbol: str,
    ok: bool,
    coverage: list[str],
    message: str,
    source_url: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> ProviderCoverage:
    return ProviderCoverage(
        provider=provider,
        provider_symbol=provider_symbol,
        ok=ok,
        coverage=coverage,
        message=message,
        source_url=source_url,
        diagnostics=diagnostics,
    )


def _coverage_dict(coverage: ProviderCoverage) -> dict[str, Any]:
    return {
        "provider": coverage.provider,
        "provider_symbol": coverage.provider_symbol,
        "ok": coverage.ok,
        "coverage": coverage.coverage,
        "message": coverage.message,
        "source_url": coverage.source_url,
        "diagnostics": coverage.diagnostics or {},
    }


def _http_get(url: str) -> requests.Response:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
    if not response.encoding:
        response.encoding = response.apparent_encoding
    if response.status_code >= 400:
        raise requests.HTTPError(f"HTTP {response.status_code}: {response.text[:200]}")
    return response


def _dt_value(soup: BeautifulSoup, label: str) -> str | None:
    for dt in soup.select("dt"):
        text = _clean_text(dt.get_text(" ", strip=True))
        if label not in text:
            continue
        dd = dt.find_next_sibling("dd")
        if dd:
            return _clean_text(dd.get_text(" ", strip=True))
    return None


def _first_text(nodes: list[Any]) -> str | None:
    for node in nodes:
        text = _clean_text(node.get_text(" ", strip=True))
        if text:
            return text
    return None


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"N/A", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _safe_index(values: list[Any], index: int) -> Any:
    try:
        value = values[index]
    except IndexError:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isnan(float(value))


def _average(values: list[float]) -> float | None:
    clean = [float(value) for value in values if _is_number(value)]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _window_return(values: list[float], window: int) -> float | None:
    clean = [float(value) for value in values if _is_number(value)]
    if len(clean) <= window:
        return None
    start = clean[-window - 1]
    end = clean[-1]
    if not start:
        return None
    return round((end - start) / start, 6)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_probe_result_dict(coverage: ProviderCoverage) -> dict[str, Any]:
    return {
        "name": coverage.provider,
        "supported": bool(coverage.coverage or coverage.ok),
        "ok": coverage.ok,
        "message": coverage.message,
        "summary": {
            "provider_symbol": coverage.provider_symbol,
            "coverage": coverage.coverage,
            "source_url": coverage.source_url,
            "diagnostics": coverage.diagnostics or {},
        },
    }
