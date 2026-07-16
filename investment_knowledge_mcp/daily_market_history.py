from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import importlib
import json
import math
from threading import BoundedSemaphore, Event, Lock
from time import monotonic, sleep
from typing import Any, Callable


AKSHARE_PROVIDER = "akshare_eastmoney"
MAX_EASTMONEY_HOST_REQUESTS = 2
MAX_ATTEMPTS = 2
HISTORY_LOOKBACK_DAYS = 35
TURNOVER_THRESHOLDS = {"CN": 50_000_000, "HK": 20_000_000, "US": 10_000_000}
MARKET_CAP_THRESHOLDS = {
    "CN": 3_500_000_000,
    "HK": 4_000_000_000,
    "US": 500_000_000,
}


class _DeadlineExpired(Exception):
    pass


class HistoricalActivityCancelled(Exception):
    pass


_EASTMONEY_HOST_GATE = BoundedSemaphore(MAX_EASTMONEY_HOST_REQUESTS)


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


class _QueryCoverage:
    def __init__(self) -> None:
        self._queried: set[str] = set()
        self._lock = Lock()

    def mark_queried(self, symbol: str) -> None:
        with self._lock:
            self._queried.add(symbol)

    def queried_count(self) -> int:
        with self._lock:
            return len(self._queried)


class _AttemptCounter:
    def __init__(self) -> None:
        self._count = 0
        self._lock = Lock()

    def increment(self) -> None:
        with self._lock:
            self._count += 1

    def count(self) -> int:
        with self._lock:
            return self._count


def load_historical_market_activity(
    market: str,
    market_date: date,
    *,
    akshare_module: Any | None = None,
    universe_limit: int = 200,
    max_workers: int = 4,
    timeout_seconds: float = 90.0,
    cancel_event: Event | None = None,
) -> HistoricalActivityResult:
    _raise_if_cancelled(cancel_event)
    market_code = _normalize_market(market)
    deadline = monotonic() + max(0.001, float(timeout_seconds))
    try:
        ak = akshare_module if akshare_module is not None else importlib.import_module("akshare")
    except Exception as exc:
        return _unavailable_result(detail_code=type(exc).__name__)

    universe_attempts = _AttemptCounter()
    try:
        universe = _load_universe(
            ak=ak,
            market=market_code,
            limit=max(1, min(int(universe_limit), 200)),
            deadline=deadline,
            attempts=universe_attempts,
            cancel_event=cancel_event,
        )
    except _DeadlineExpired:
        return _unavailable_result(
            detail_code="deadline_exceeded",
            timed_out=True,
            universe_attempts=universe_attempts.count(),
        )
    except Exception as exc:
        if isinstance(exc, HistoricalActivityCancelled):
            raise
        return _unavailable_result(
            detail_code=type(exc).__name__,
            universe_attempts=universe_attempts.count(),
        )

    requested = len(universe)
    _raise_if_cancelled(cancel_event)
    coverage = _QueryCoverage()
    rows: list[dict[str, Any]] = []
    completed = 0
    deadline_hit = False
    del max_workers

    for candidate in universe:
        _raise_if_cancelled(cancel_event)
        if monotonic() >= deadline:
            deadline_hit = True
            break
        try:
            row, candidate_timed_out = _load_candidate(
                ak=ak,
                market=market_code,
                market_date=market_date,
                candidate=candidate,
                coverage=coverage,
                deadline=deadline,
                cancel_event=cancel_event,
            )
            if monotonic() >= deadline:
                deadline_hit = True
                row = None
                candidate_timed_out = True
        except _DeadlineExpired:
            deadline_hit = True
            break
        except HistoricalActivityCancelled:
            raise
        except Exception:
            row = None
            candidate_timed_out = False
        completed += 1
        deadline_hit = deadline_hit or candidate_timed_out
        if row is not None:
            rows.append(row)

    queried = coverage.queried_count()
    usable = len(rows)
    incomplete = completed < requested
    timed_out = deadline_hit or (incomplete and monotonic() >= deadline)
    ranked = _ranked_top(sorted(rows, key=lambda row: row["change_pct"], reverse=True)[:5])
    if timed_out:
        status = "timed_out"
    elif usable == queried == requested and usable:
        status = "ok"
    elif usable:
        status = "partial"
    else:
        status = "missing"
    gainers_status: dict[str, Any] = {
        "status": status,
        "provider": AKSHARE_PROVIDER,
        "count": len(ranked),
        "requested": requested,
        "queried": queried,
        "usable": usable,
        "incomplete": incomplete,
        "timed_out": timed_out,
        "universe_attempts": universe_attempts.count(),
        "universe_size": requested,
        "universe_basis": "current_liquid_common_equity_market_cap_top_200",
        "message": "Current spot market capitalization and liquidity are used only to select common-equity candidates; historical rankings use exact-date daily bars and may have survivorship bias.",
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


def _load_universe(
    *,
    ak: Any,
    market: str,
    limit: int,
    deadline: float,
    attempts: _AttemptCounter,
    cancel_event: Event | None,
) -> list[dict[str, Any]]:
    loader_name = {
        "CN": "stock_zh_a_spot_em",
        "HK": "stock_hk_main_board_spot_em",
        "US": "stock_us_spot_em",
    }[market]
    loader = getattr(ak, loader_name)
    records: list[dict[str, Any]] = []
    last_error: Exception | None = None

    def load_once() -> Any:
        _raise_if_cancelled(cancel_event)
        attempts.increment()
        return loader()

    for attempt in range(MAX_ATTEMPTS):
        _raise_if_cancelled(cancel_event)
        if monotonic() >= deadline:
            raise _DeadlineExpired()
        try:
            records = _frame_records(_call_under_host_gate(load_once, deadline=deadline))
            if records:
                break
            last_error = ValueError("empty response")
        except _DeadlineExpired:
            raise
        except Exception as exc:
            if not _retryable_error(exc):
                raise
            last_error = exc
        if attempt + 1 < MAX_ATTEMPTS:
            _raise_if_cancelled(cancel_event)
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise _DeadlineExpired()
            sleep(min(0.1, remaining))
    else:
        if last_error is not None:
            raise last_error

    candidates: list[dict[str, Any]] = []
    for row in records:
        _raise_if_cancelled(cancel_event)
        provider_symbol = _text(_first_value(row, "代码", "symbol", "Symbol"))
        name = _text(_first_value(row, "名称", "股票简称", "name", "Name"))
        current_market_cap = _number(
            _first_value(row, "总市值", "Total Market Value", "Market Cap", "market_cap", "mktcap")
        )
        if not provider_symbol or not name or not _eligible_common_equity(
            market=market,
            code=provider_symbol,
            name=name,
            market_cap=current_market_cap,
            row=row,
        ):
            continue
        candidates.append(
            {
                "code": provider_symbol,
                "provider_symbol": provider_symbol,
                "name": name,
                "current_turnover": _number(_first_value(row, "成交额", "金额", "amount", "成交金额")) or 0.0,
                "current_market_cap": current_market_cap,
            }
        )
    candidates.sort(key=lambda item: item["current_turnover"], reverse=True)
    return candidates[:limit]


def _load_candidate(
    *,
    ak: Any,
    market: str,
    market_date: date,
    candidate: dict[str, Any],
    coverage: _QueryCoverage,
    deadline: float,
    cancel_event: Event | None,
) -> tuple[dict[str, Any] | None, bool]:
    _raise_if_cancelled(cancel_event)
    rows, timed_out = _load_history_with_retry(
        ak=ak,
        market=market,
        symbol=candidate["provider_symbol"],
        market_date=market_date,
        deadline=deadline,
        on_first_request=lambda: coverage.mark_queried(candidate["provider_symbol"]),
        cancel_event=cancel_event,
    )
    rank = _rank_exact_date_history(rows, market_date)
    if rank is None or rank.get("turnover") is None or rank["turnover"] < TURNOVER_THRESHOLDS[market]:
        return None, timed_out
    return (
        {
            "code": candidate["code"],
            "name": candidate["name"],
            "change_pct": rank["change_pct"],
            "turnover": rank["turnover"],
            "session_date": rank["session_date"],
            "current_market_cap": candidate["current_market_cap"],
            "provider": AKSHARE_PROVIDER,
            "metric": _historical_gainer_metric(market),
        },
        timed_out,
    )


def _load_history_with_retry(
    *,
    ak: Any,
    market: str,
    symbol: str,
    market_date: date,
    deadline: float,
    on_first_request: Callable[[], None],
    cancel_event: Event | None,
) -> tuple[list[dict[str, Any]], bool]:
    start_date = (market_date - timedelta(days=HISTORY_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end_date = market_date.strftime("%Y%m%d")
    loader_name = {"CN": "stock_zh_a_hist", "HK": "stock_hk_hist", "US": "stock_us_hist"}[market]
    loader = getattr(ak, loader_name)
    request_started = False

    def load_once() -> Any:
        nonlocal request_started
        _raise_if_cancelled(cancel_event)
        remaining = _remaining(deadline)
        if not request_started:
            on_first_request()
            request_started = True
        if market == "CN":
            return loader(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="",
                timeout=remaining,
            )
        return loader(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="")

    for attempt in range(MAX_ATTEMPTS):
        _raise_if_cancelled(cancel_event)
        if monotonic() >= deadline:
            return [], True
        try:
            rows = _frame_records(_call_under_host_gate(load_once, deadline=deadline))
            if rows:
                return rows, False
        except _DeadlineExpired:
            return [], True
        except HistoricalActivityCancelled:
            raise
        except Exception as exc:
            if not _retryable_error(exc):
                return [], False
        if attempt + 1 < MAX_ATTEMPTS:
            _raise_if_cancelled(cancel_event)
            remaining = deadline - monotonic()
            if remaining <= 0:
                return [], True
            sleep(min(0.1, remaining))
    return [], monotonic() >= deadline


def _raise_if_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise HistoricalActivityCancelled()


def _call_under_host_gate(operation: Callable[[], Any], *, deadline: float) -> Any:
    remaining = deadline - monotonic()
    if remaining <= 0 or not _EASTMONEY_HOST_GATE.acquire(timeout=max(0, remaining)):
        raise _DeadlineExpired()
    try:
        if monotonic() >= deadline:
            raise _DeadlineExpired()
        return operation()
    finally:
        _EASTMONEY_HOST_GATE.release()


def _rank_exact_date_history(rows: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    normalized = sorted((_normalize_history_row(row) for row in rows), key=lambda row: row["date"])
    position = next((idx for idx, row in enumerate(normalized) if row["date"] == target.isoformat()), None)
    if position is None or position == 0:
        return None
    current, previous = normalized[position], normalized[position - 1]
    if previous["close"] is None or previous["close"] == 0 or current["close"] is None:
        return None
    change_pct = (current["close"] - previous["close"]) / previous["close"] * 100
    if not math.isfinite(change_pct):
        return None
    return {
        "change_pct": change_pct,
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


def _unavailable_result(
    *, detail_code: str, timed_out: bool = False, universe_attempts: int = 0
) -> HistoricalActivityResult:
    source_status = {
        "sectors": _unsupported_section_status("sectors"),
        "gainers": {
            "status": "timed_out" if timed_out else "provider_unavailable",
            "provider": AKSHARE_PROVIDER,
            "count": 0,
            "requested": 0,
            "queried": 0,
            "usable": 0,
            "incomplete": timed_out,
            "timed_out": timed_out,
            "universe_attempts": universe_attempts,
            "universe_basis": "current_liquid_common_equity_market_cap_top_200",
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


def _eligible_common_equity(
    *, market: str, code: str, name: str, market_cap: float | None, row: dict[str, Any]
) -> bool:
    min_market_cap = MARKET_CAP_THRESHOLDS.get(market)
    if min_market_cap is None or market_cap is None or not math.isfinite(market_cap):
        return False
    if market_cap < min_market_cap:
        return False
    if market == "CN" and ("ST" in name.upper() or "退" in name):
        return False
    if _looks_like_non_common_security_type(row):
        return False
    if _looks_like_non_common_equity(market=market, code=code, name=name):
        return False
    return not (market == "US" and _looks_like_us_warrant(code, name))


def _looks_like_non_common_security_type(row: dict[str, Any]) -> bool:
    security_type = _text(_first_value(row, "证券类型", "类型", "type", "Type")).upper()
    markers = ("WARRANT", "RIGHT", "UNIT", "PREFERRED", "ETF", "ETN", "FUND", "LEVERAGED", "INVERSE")
    return any(marker in security_type for marker in markers)


def _looks_like_non_common_equity(*, market: str, code: str, name: str) -> bool:
    if market == "US" and _looks_like_us_non_common_symbol(code):
        return True
    upper_name = name.upper()
    markers = (
        "ETF",
        "ETN",
        "FUND",
        "LEVERAGED",
        "INVERSE",
        "WARRANT",
        " RIGHT",
        "UNIT",
        "PREFERRED",
        " PREF",
        " BULL",
        " BEAR",
        " SHORT",
        " 2X",
        " 3X",
        "基金",
        "杠杆",
        "反向",
        "权证",
        "优先股",
    )
    return any(marker in upper_name for marker in markers)


def _looks_like_us_non_common_symbol(code: str) -> bool:
    symbol = code.split(".")[-1].upper()
    if symbol == "DOW":
        return False
    return symbol.endswith(("W", "WS", "WT", "R", "RT", "U", "UN", "P", "PR"))


def _looks_like_us_warrant(code: str, name: str) -> bool:
    symbol = code.split(".")[-1].upper()
    upper_name = name.upper()
    return symbol.endswith(("WS", "WT")) or any(
        word in upper_name for word in (" WARRANT", " WT", " RIGHT")
    )


def _historical_gainer_metric(market: str) -> str:
    return (
        f"exact_date_turnover_filtered_change_pct_min_{int(TURNOVER_THRESHOLDS[market])}_"
        f"current_market_cap_min_{int(MARKET_CAP_THRESHOLDS[market])}"
    )


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
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise _DeadlineExpired()
    return remaining


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
