from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
import importlib
import json
from threading import BoundedSemaphore, Lock
from time import monotonic, sleep
from typing import Any, Callable


AKSHARE_PROVIDER = "akshare_eastmoney"
MAX_WORKERS = 4
MAX_EASTMONEY_HOST_REQUESTS = 2
MAX_ATTEMPTS = 2
TURNOVER_THRESHOLDS = {"CN": 50_000_000, "HK": 20_000_000, "US": 10_000_000}


@dataclass(frozen=True)
class HistoricalActivityResult:
    sectors: list[dict[str, Any]]
    gainers: list[dict[str, Any]]
    capital_flow: list[dict[str, Any]]
    source_status: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sectors": self.sectors,
            "gainers": self.gainers,
            "capital_flow": self.capital_flow,
            "source_status": self.source_status,
        }


HistoricalActivityProvider = Callable[[str, date], HistoricalActivityResult]


def load_historical_market_activity(
    market: str,
    market_date: date,
    *,
    akshare_module: Any | None = None,
    universe_limit: int = 200,
    max_workers: int = 4,
    timeout_seconds: float = 90.0,
) -> HistoricalActivityResult:
    market_code = _normalize_market(market)
    deadline = monotonic() + max(0.1, timeout_seconds)
    try:
        ak = akshare_module or importlib.import_module("akshare")
        universe = _build_universe(ak, market_code, max(1, min(universe_limit, 200)))
    except Exception as exc:
        return _unavailable_result(market_code, detail_code=type(exc).__name__)

    gate = BoundedSemaphore(MAX_EASTMONEY_HOST_REQUESTS)
    queried = 0
    queried_lock = Lock()

    def load_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal queried
        with queried_lock:
            queried += 1
        rows = _load_history_with_retry(
            ak=ak,
            market=market_code,
            symbol=candidate["provider_symbol"],
            market_date=market_date,
            deadline=deadline,
            gate=gate,
        )
        rank = _rank_exact_date_history(rows, market_date)
        if rank is None or rank.get("turnover") is None or rank["turnover"] < TURNOVER_THRESHOLDS[market_code]:
            return None
        return {
            "code": candidate["code"],
            "name": candidate["name"],
            "change_pct": rank["change_pct"],
            "turnover": rank["turnover"],
            "session_date": rank["session_date"],
            "provider": AKSHARE_PROVIDER,
            "metric": f"exact_date_turnover_filtered_change_pct_min_{int(TURNOVER_THRESHOLDS[market_code])}",
        }

    rows: list[dict[str, Any]] = []
    workers = max(1, min(int(max_workers), MAX_WORKERS))
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = [executor.submit(load_candidate, candidate) for candidate in universe]
    try:
        for future in as_completed(futures, timeout=max(0, deadline - monotonic())):
            try:
                row = future.result()
            except Exception:
                row = None
            if row is not None:
                rows.append(row)
    except TimeoutError:
        pass
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    ranked = _ranked_top(sorted(rows, key=lambda row: row["change_pct"], reverse=True)[:5])
    usable = len(rows)
    gainers_status: dict[str, Any] = {
        "status": "ok" if usable == queried and usable else ("partial" if usable else "missing"),
        "provider": AKSHARE_PROVIDER,
        "count": len(ranked),
        "queried": queried,
        "usable": usable,
        "universe_size": len(universe),
        "universe_basis": "current_liquid_top_200",
        "message": "Current liquid universe is used only to select candidates; historical rankings use exact-date daily bars and may have survivorship bias.",
    }
    return HistoricalActivityResult(
        sectors=[],
        gainers=ranked,
        capital_flow=[],
        source_status={
            "sectors": _unsupported_section_status("sectors"),
            "gainers": gainers_status,
            "capital_flow": _unsupported_section_status("capital_flow"),
        },
    )


def _build_universe(ak: Any, market: str, limit: int) -> list[dict[str, str]]:
    loader_name = {
        "CN": "stock_zh_a_spot_em",
        "HK": "stock_hk_main_board_spot_em",
        "US": "stock_us_spot_em",
    }[market]
    candidates: list[dict[str, Any]] = []
    for row in _frame_records(getattr(ak, loader_name)()):
        provider_symbol = _text(_first_value(row, "代码", "symbol", "Symbol"))
        name = _text(_first_value(row, "名称", "股票简称", "name", "Name"))
        if not provider_symbol or not name or _excluded_security(market, provider_symbol, name):
            continue
        candidates.append(
            {
                "code": provider_symbol,
                "provider_symbol": provider_symbol,
                "name": name,
                "current_turnover": _number(_first_value(row, "成交额", "金额", "amount", "成交金额")) or 0.0,
            }
        )
    candidates.sort(key=lambda item: item["current_turnover"], reverse=True)
    return candidates[:limit]


def _load_history_with_retry(
    *, ak: Any, market: str, symbol: str, market_date: date, deadline: float, gate: BoundedSemaphore
) -> list[dict[str, Any]]:
    start_date = (market_date - timedelta(days=7)).strftime("%Y%m%d")
    end_date = market_date.strftime("%Y%m%d")
    loader_name = {"CN": "stock_zh_a_hist", "HK": "stock_hk_hist", "US": "stock_us_hist"}[market]
    loader = getattr(ak, loader_name)
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        if monotonic() >= deadline:
            break
        try:
            with gate:
                frame = loader(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="")
            rows = _frame_records(frame)
            if rows:
                return rows
            last_error = ValueError("empty response")
        except Exception as exc:
            if not _retryable_error(exc):
                return []
            last_error = exc
        if attempt + 1 < MAX_ATTEMPTS and monotonic() < deadline:
            sleep(min(0.1, max(0, deadline - monotonic())))
    return [] if last_error else []


def _rank_exact_date_history(rows: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    normalized = sorted((_normalize_history_row(row) for row in rows), key=lambda row: row["date"])
    position = next((idx for idx, row in enumerate(normalized) if row["date"] == target.isoformat()), None)
    if position is None or position == 0:
        return None
    current, previous = normalized[position], normalized[position - 1]
    if previous["close"] is None or previous["close"] == 0 or current["close"] is None:
        return None
    return {
        "change_pct": (current["close"] - previous["close"]) / previous["close"] * 100,
        "turnover": current.get("turnover"),
        "session_date": current["date"],
    }


def _normalize_history_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_date = _first_value(row, "日期", "date", "Date")
    if isinstance(raw_date, date):
        session_date = raw_date.isoformat()
    else:
        session_date = str(raw_date)[:10]
    return {
        "date": session_date,
        "close": _number(_first_value(row, "收盘", "close", "Close")),
        "turnover": _number(_first_value(row, "成交额", "turnover", "amount", "成交金额")),
    }


def _unavailable_result(market: str, *, detail_code: str) -> HistoricalActivityResult:
    source_status = {
        "sectors": _unsupported_section_status("sectors"),
        "gainers": {
            "status": "provider_unavailable",
            "provider": AKSHARE_PROVIDER,
            "count": 0,
            "queried": 0,
            "usable": 0,
            "universe_basis": "current_liquid_top_200",
            "detail_code": detail_code,
            "message": "Historical exact-date gainer reconstruction is unavailable from the configured provider.",
        },
        "capital_flow": _unsupported_section_status("capital_flow"),
    }
    return HistoricalActivityResult(sectors=[], gainers=[], capital_flow=[], source_status=source_status)


def _unsupported_section_status(section: str) -> dict[str, Any]:
    label = "sector rankings" if section == "sectors" else "capital flow"
    return {
        "status": "historical_not_supported",
        "provider": AKSHARE_PROVIDER,
        "count": 0,
        "message": f"Historical {label} are not available from a date-correct provider for this market.",
    }


def _excluded_security(market: str, code: str, name: str) -> bool:
    if market == "CN":
        return "ST" in name.upper() or "退" in name
    if market == "US":
        symbol = code.split(".")[-1].upper()
        upper_name = name.upper()
        return symbol.endswith(("W", "WS", "WT")) or any(word in upper_name for word in (" WARRANT", " WT", " RIGHT"))
    return False


def _retryable_error(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, json.JSONDecodeError)):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in ("rate limit", "too many requests", "429", "connection", "timeout", "json", "empty response"))


def _frame_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [dict(row) for row in frame if isinstance(row, dict)]
    records = frame.to_dict(orient="records")
    return [dict(row) for row in records if isinstance(row, dict)]


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _normalize_market(market: str) -> str:
    normalized = market.strip().upper()
    if normalized not in TURNOVER_THRESHOLDS:
        raise ValueError("market must be CN, HK, or US")
    return normalized


def _ranked_top(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        item = dict(row)
        item["rank"] = rank
        ranked.append(item)
    return ranked
