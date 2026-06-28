from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MarketDataProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketBarSnapshot:
    bars_by_code: dict[str, list[dict[str, Any]]]
    fetched_at: datetime
    start: str
    end: str
    source: str = "yahoo_chart"


YAHOO_SYMBOLS: dict[str, list[str]] = {
    "US.SPX": ["^GSPC"],
    "US.NDX": ["^NDX"],
    "US.SOX": ["^SOX"],
    "HK.HSI": ["^HSI"],
    "HK.HSTECH": ["^HSTECH", "3032.HK"],
    "HK.HSCEI": ["^HSCE", "^HSCEI"],
    "SH.000300": ["000300.SS"],
    "SZ.399006": ["399006.SZ"],
    "SH.000688": ["000688.SS"],
}


def get_yahoo_market_bars(codes: list[str], start: str, end: str, timeout_seconds: float = 5.0) -> MarketBarSnapshot:
    cleaned_codes = [code.strip().upper() for code in codes if code and code.strip()]
    if not cleaned_codes:
        return MarketBarSnapshot(
            bars_by_code={},
            fetched_at=datetime.now(timezone.utc),
            start=start,
            end=end,
        )

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    bars_by_code: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(6, len(cleaned_codes))) as executor:
        futures = {
            executor.submit(_fetch_yahoo_code, code, start_date, end_date, timeout_seconds): code
            for code in cleaned_codes
            if code in YAHOO_SYMBOLS
        }
        unsupported = [code for code in cleaned_codes if code not in YAHOO_SYMBOLS]
        errors.extend(f"{code}: unsupported" for code in unsupported)
        for future in as_completed(futures):
            code = futures[future]
            try:
                bars = future.result()
            except Exception as exc:
                errors.append(f"{code}: {exc}")
                continue
            if bars:
                bars_by_code[code] = bars
            else:
                errors.append(f"{code}: empty")

    if not bars_by_code and errors:
        raise MarketDataProviderError("Yahoo chart fallback returned no usable bars: " + "; ".join(errors[:5]))
    return MarketBarSnapshot(
        bars_by_code=bars_by_code,
        fetched_at=datetime.now(timezone.utc),
        start=start,
        end=end,
    )


def _fetch_yahoo_code(code: str, start: date, end: date, timeout_seconds: float) -> list[dict[str, Any]]:
    errors: list[str] = []
    for symbol in YAHOO_SYMBOLS[code]:
        try:
            bars = _fetch_yahoo_symbol(symbol=symbol, start=start, end=end, timeout_seconds=timeout_seconds)
        except MarketDataProviderError as exc:
            errors.append(f"{symbol}: {exc}")
            continue
        if bars:
            return bars
    raise MarketDataProviderError("; ".join(errors) if errors else "empty")


def _fetch_yahoo_symbol(symbol: str, start: date, end: date, timeout_seconds: float) -> list[dict[str, Any]]:
    period1 = _unix_seconds(start)
    period2 = _unix_seconds(end + timedelta(days=1))
    params = urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "includePrePost": "false",
            "events": "history",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; InvestmentKnowledgeBot/0.1)",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise MarketDataProviderError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MarketDataProviderError(str(exc)) from exc

    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        error = (payload.get("chart") or {}).get("error")
        raise MarketDataProviderError(str(error or "missing chart result"))
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [None])[0] or {}
    opens = quote.get("open") or []
    closes = quote.get("close") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    volumes = quote.get("volume") or []
    bars: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        close = _list_get(closes, index)
        if close is None:
            continue
        bars.append(
            {
                "date": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat(),
                "open": _list_get(opens, index),
                "close": close,
                "high": _list_get(highs, index),
                "low": _list_get(lows, index),
                "volume": _list_get(volumes, index),
                "raw": {"provider_symbol": symbol},
            }
        )
    return bars


def _unix_seconds(value: date) -> int:
    return int(datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp())


def _list_get(values: list[Any], index: int) -> Any:
    if index >= len(values):
        return None
    return values[index]
