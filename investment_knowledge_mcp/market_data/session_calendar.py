from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from investment_knowledge_mcp.market_data.models import SessionState


DEFAULT_USER_TZ = ZoneInfo("Asia/Singapore")
MARKET_TZ = {
    "CN": ZoneInfo("Asia/Shanghai"),
    "HK": ZoneInfo("Asia/Hong_Kong"),
    "US": ZoneInfo("America/New_York"),
}


def resolve_review_sessions(
    review_dt: datetime | None,
    mode: str | None,
    markets: list[str],
) -> dict[str, SessionState]:
    if review_dt is None:
        review_dt = datetime.now(DEFAULT_USER_TZ)
    if review_dt.tzinfo is None:
        review_dt = review_dt.replace(tzinfo=DEFAULT_USER_TZ)
    return {
        market: _resolve_market_session(market=market, review_dt=review_dt, forced_mode=mode)
        for market in markets
    }


def _resolve_market_session(market: str, review_dt: datetime, forced_mode: str | None) -> SessionState:
    normalized = market.upper()
    tz = MARKET_TZ.get(normalized, DEFAULT_USER_TZ)
    local_dt = review_dt.astimezone(tz)
    requested_user_date = review_dt.astimezone(DEFAULT_USER_TZ).date()
    session_date = _latest_weekday(local_dt.date())
    inferred_mode, is_open, elapsed = _infer_mode(normalized, local_dt)
    run_mode = forced_mode or inferred_mode
    if forced_mode in {"post_close", "pre_open", "intraday"}:
        session_date = _latest_weekday(requested_user_date)
    if forced_mode == "post_close":
        is_open = False
        elapsed = None
    elif forced_mode == "pre_open":
        is_open = False
        elapsed = None
    elif forced_mode == "intraday":
        is_open = True
        elapsed = elapsed if elapsed is not None else 0.5

    if forced_mode is None and normalized == "US" and local_dt.time() < time(16, 0):
        session_date = _latest_weekday(local_dt.date() - timedelta(days=1))
    label = _session_label(normalized, session_date, run_mode)
    return SessionState(
        market=normalized,
        session_date=session_date,
        run_mode=run_mode,
        label=label,
        timezone=str(tz),
        is_open=is_open,
        elapsed_session_ratio=elapsed,
    )


def _infer_mode(market: str, local_dt: datetime) -> tuple[str, bool, float | None]:
    current = local_dt.time()
    if market in {"CN", "HK"}:
        if current < time(9, 30):
            return "pre_open", False, None
        if time(9, 30) <= current <= time(12, 0):
            return "intraday", True, _ratio(current, [(time(9, 30), time(12, 0)), (time(13, 0), time(16, 0) if market == "HK" else time(15, 0))])
        if time(13, 0) <= current <= (time(16, 0) if market == "HK" else time(15, 0)):
            return "intraday", True, _ratio(current, [(time(9, 30), time(12, 0)), (time(13, 0), time(16, 0) if market == "HK" else time(15, 0))])
        return "post_close", False, None
    if market == "US":
        if current < time(9, 30):
            return "pre_open", False, None
        if time(9, 30) <= current <= time(16, 0):
            return "intraday", True, _ratio(current, [(time(9, 30), time(16, 0))])
        return "post_close", False, None
    return "post_close", False, None


def _ratio(current: time, windows: list[tuple[time, time]]) -> float:
    elapsed = 0
    total = 0
    for start, end in windows:
        span = _seconds_between(start, end)
        total += span
        if current >= end:
            elapsed += span
        elif current > start:
            elapsed += _seconds_between(start, current)
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, elapsed / total))


def _seconds_between(start: time, end: time) -> int:
    return (datetime.combine(date.today(), end) - datetime.combine(date.today(), start)).seconds


def _latest_weekday(value: date) -> date:
    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value


def _session_label(market: str, session_date: date, run_mode: str) -> str:
    market_label = {"CN": "A-share", "HK": "Hong Kong", "US": "U.S."}.get(market, market)
    return f"{market_label} {session_date.isoformat()} {run_mode}"
