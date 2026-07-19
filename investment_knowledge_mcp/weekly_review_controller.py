from __future__ import annotations

from http import HTTPStatus
import re
from typing import Any
from urllib.parse import ParseResult, parse_qs


def dispatch_weekly_review_get(handler: Any, parsed: ParseResult) -> bool:
    if parsed.path in {"/", "/weekly-review"}:
        handler._write_html(HTTPStatus.OK, handler._render_weekly_review_page())
        return True
    if parsed.path == "/assets/weekly-review.js":
        handler._write_javascript(HTTPStatus.OK, handler._render_weekly_review_script())
        return True
    if parsed.path == "/api/weekly-review":
        handler._handle_weekly_review_read(parse_qs(parsed.query))
        return True
    if parsed.path == "/api/candidate-insights":
        handler._handle_candidate_insights(parse_qs(parsed.query))
        return True
    return False


def dispatch_weekly_review_post(handler: Any, parsed: ParseResult) -> bool:
    weekly_routes = {
        "/api/weekly-review/generate": ("_handle_weekly_review_generate", {"force": False}),
        "/api/weekly-review/refresh": ("_handle_weekly_review_generate", {"force": True}),
        "/api/weekly-review/save": ("_handle_weekly_review_save", {}),
    }
    route = weekly_routes.get(parsed.path)
    if route is not None:
        payload = handler._read_json_body()
        if payload is not None:
            callback_name, keywords = route
            callback = getattr(handler, callback_name)
            callback(payload, **keywords)
        return True

    candidate_match = re.fullmatch(r"/api/candidate-insights/(\d+)/(confirm|reject)", parsed.path)
    if candidate_match is None:
        return False
    handler._handle_candidate_decision(
        candidate_id=int(candidate_match.group(1)),
        action=candidate_match.group(2),
    )
    return True
