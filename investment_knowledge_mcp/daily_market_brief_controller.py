from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import ParseResult, parse_qs


def dispatch_daily_market_brief_get(handler: Any, parsed: ParseResult) -> bool:
    if parsed.path == "/daily-market-brief":
        handler._write_html(HTTPStatus.OK, handler._render_daily_market_brief_page())
        return True
    if parsed.path == "/assets/daily-market-brief.js":
        handler._write_javascript(HTTPStatus.OK, handler._render_daily_market_brief_script())
        return True
    routes = {
        "/api/daily-market-brief": "_handle_daily_market_brief_read",
        "/api/daily-market-brief/dates": "_handle_daily_market_brief_dates",
        "/api/daily-market-brief/history-jobs": "_handle_daily_market_brief_history_jobs_read",
    }
    callback_name = routes.get(parsed.path)
    if callback_name is None:
        return False
    callback = getattr(handler, callback_name)
    callback(parse_qs(parsed.query))
    return True


def dispatch_daily_market_brief_post(handler: Any, parsed: ParseResult) -> bool:
    routes = {
        "/api/daily-market-brief/generate": "_handle_daily_market_brief_generate",
        "/api/daily-market-brief/history-jobs": "_handle_daily_market_brief_history_job_create",
    }
    callback_name = routes.get(parsed.path)
    if callback_name is None:
        return False
    callback = getattr(handler, callback_name)
    payload = handler._read_json_body()
    if payload is not None:
        callback(payload)
    return True
