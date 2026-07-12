from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, TimeoutError as FutureTimeoutError, wait
from dataclasses import dataclass
from datetime import date, timedelta
import importlib
import json
import math
from queue import Full, Queue
from threading import BoundedSemaphore, Lock, Thread
from time import monotonic, sleep
from typing import Any, Callable


AKSHARE_PROVIDER = "akshare_eastmoney"
MAX_WORKERS = 4
MAX_EASTMONEY_HOST_REQUESTS = 2
MAX_ATTEMPTS = 2
MAX_PENDING_TASKS = 16
HISTORY_LOOKBACK_DAYS = 35
TURNOVER_THRESHOLDS = {"CN": 50_000_000, "HK": 20_000_000, "US": 10_000_000}


class _DeadlineExpired(Exception):
    pass


class _DaemonWorkerPool:
    def __init__(self, *, worker_count: int, queue_size: int) -> None:
        self._queue: Queue[tuple[Future[Any], Callable[[], Any], float]] = Queue(maxsize=queue_size)
        self._threads = [
            Thread(target=self._run, name=f"daily-market-history-{index + 1}", daemon=True)
            for index in range(worker_count)
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, operation: Callable[[], Any], *, deadline: float) -> Future[Any] | None:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return None
        future: Future[Any] = Future()
        try:
            self._queue.put((future, operation, deadline), timeout=remaining)
        except Full:
            return None
        return future

    def _run(self) -> None:
        while True:
            future, operation, deadline = self._queue.get()
            try:
                if not future.set_running_or_notify_cancel():
                    continue
                if monotonic() >= deadline:
                    future.set_exception(_DeadlineExpired())
                    continue
                try:
                    future.set_result(operation())
                except BaseException as exc:
                    future.set_exception(exc)
            finally:
                self._queue.task_done()


_WORKER_POOL = _DaemonWorkerPool(worker_count=MAX_WORKERS, queue_size=MAX_PENDING_TASKS)
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
) -> HistoricalActivityResult:
    market_code = _normalize_market(market)
    deadline = monotonic() + max(0.001, float(timeout_seconds))
    try:
        ak = akshare_module if akshare_module is not None else importlib.import_module("akshare")
    except Exception as exc:
        return _unavailable_result(detail_code=type(exc).__name__)

    universe_attempts = _AttemptCounter()
    universe_future = _WORKER_POOL.submit(
        lambda: _load_universe(
            ak=ak,
            market=market_code,
            limit=max(1, min(int(universe_limit), 200)),
            deadline=deadline,
            attempts=universe_attempts,
        ),
        deadline=deadline,
    )
    if universe_future is None:
        return _unavailable_result(
            detail_code="deadline_exceeded",
            timed_out=True,
            universe_attempts=universe_attempts.count(),
        )
    try:
        universe = universe_future.result(timeout=_remaining(deadline))
    except (FutureTimeoutError, _DeadlineExpired):
        universe_future.cancel()
        return _unavailable_result(
            detail_code="deadline_exceeded",
            timed_out=True,
            universe_attempts=universe_attempts.count(),
        )
    except Exception as exc:
        return _unavailable_result(
            detail_code=type(exc).__name__,
            universe_attempts=universe_attempts.count(),
        )

    requested = len(universe)
    coverage = _QueryCoverage()
    rows: list[dict[str, Any]] = []
    completed = 0
    deadline_hit = False
    workers = max(1, min(int(max_workers), MAX_WORKERS))
    candidates = iter(universe)
    pending: set[Future[Any]] = set()

    def submit_next() -> bool:
        nonlocal deadline_hit
        try:
            candidate = next(candidates)
        except StopIteration:
            return False
        future = _WORKER_POOL.submit(
            lambda candidate=candidate: _load_candidate(
                ak=ak,
                market=market_code,
                market_date=market_date,
                candidate=candidate,
                coverage=coverage,
                deadline=deadline,
            ),
            deadline=deadline,
        )
        if future is None:
            deadline_hit = True
            return False
        pending.add(future)
        return True

    for _ in range(workers):
        if not submit_next():
            break

    try:
        while pending:
            remaining = deadline - monotonic()
            if remaining <= 0:
                deadline_hit = True
                break
            done, _ = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
            if not done:
                deadline_hit = True
                break
            for future in done:
                pending.remove(future)
                completed += 1
                try:
                    row, candidate_timed_out = future.result()
                except _DeadlineExpired:
                    deadline_hit = True
                    row = None
                    candidate_timed_out = True
                except Exception:
                    row = None
                    candidate_timed_out = False
                deadline_hit = deadline_hit or candidate_timed_out
                if row is not None:
                    rows.append(row)
            while len(pending) < workers and submit_next():
                pass
    finally:
        for future in pending:
            future.cancel()

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


def _load_universe(
    *,
    ak: Any,
    market: str,
    limit: int,
    deadline: float,
    attempts: _AttemptCounter,
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
        attempts.increment()
        return loader()

    for attempt in range(MAX_ATTEMPTS):
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
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise _DeadlineExpired()
            sleep(min(0.1, remaining))
    else:
        if last_error is not None:
            raise last_error

    candidates: list[dict[str, Any]] = []
    for row in records:
        provider_symbol = _text(_first_value(row, "代码", "symbol", "Symbol"))
        name = _text(_first_value(row, "名称", "股票简称", "name", "Name"))
        if not provider_symbol or not name or _excluded_security(market, provider_symbol, name, row):
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


def _load_candidate(
    *,
    ak: Any,
    market: str,
    market_date: date,
    candidate: dict[str, Any],
    coverage: _QueryCoverage,
    deadline: float,
) -> tuple[dict[str, Any] | None, bool]:
    rows, timed_out = _load_history_with_retry(
        ak=ak,
        market=market,
        symbol=candidate["provider_symbol"],
        market_date=market_date,
        deadline=deadline,
        on_first_request=lambda: coverage.mark_queried(candidate["provider_symbol"]),
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
            "provider": AKSHARE_PROVIDER,
            "metric": f"exact_date_turnover_filtered_change_pct_min_{int(TURNOVER_THRESHOLDS[market])}",
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
) -> tuple[list[dict[str, Any]], bool]:
    start_date = (market_date - timedelta(days=HISTORY_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end_date = market_date.strftime("%Y%m%d")
    loader_name = {"CN": "stock_zh_a_hist", "HK": "stock_hk_hist", "US": "stock_us_hist"}[market]
    loader = getattr(ak, loader_name)
    request_started = False

    def load_once() -> Any:
        nonlocal request_started
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
        if monotonic() >= deadline:
            return [], True
        try:
            rows = _frame_records(_call_under_host_gate(load_once, deadline=deadline))
            if rows:
                return rows, False
        except _DeadlineExpired:
            return [], True
        except Exception as exc:
            if not _retryable_error(exc):
                return [], False
        if attempt + 1 < MAX_ATTEMPTS:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return [], True
            sleep(min(0.1, remaining))
    return [], monotonic() >= deadline


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


def _excluded_security(market: str, code: str, name: str, row: dict[str, Any]) -> bool:
    if market == "CN":
        return "ST" in name.upper() or "退" in name
    if market == "US":
        upper_name = name.upper()
        security_type = _text(_first_value(row, "证券类型", "类型", "type", "Type")).upper()
        return any(word in upper_name for word in ("WARRANT", " WT", "RIGHT")) or any(
            word in security_type for word in ("WARRANT", "RIGHT")
        )
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
