from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import ParseResult, parse_qs

from .release import (
    EarningsBriefNotFound,
    build_public_projection,
    list_catalog,
    load_release,
)
from .web import render_javascript, render_page


def dispatch_earnings_brief_get(handler: Any, parsed: ParseResult) -> None:
    if parsed.path == "/earnings-brief-studio":
        handler._write_html(HTTPStatus.OK, render_page())
        return
    if parsed.path == "/assets/earnings-brief-studio.js":
        handler._write_javascript(HTTPStatus.OK, render_javascript())
        return
    if parsed.path == "/api/earnings-briefs":
        handler._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "schema_version": "earnings_brief_catalog.v1",
                "catalog": list_catalog(),
            },
        )
        return
    query = parse_qs(parsed.query, keep_blank_values=True)
    company_id = _single(query, "company_id")
    period_id = _single(query, "period_id")
    if not company_id or not period_id:
        handler._write_json(
            HTTPStatus.BAD_REQUEST,
            {"ok": False, "error": "company_id_and_period_id_required"},
        )
        return
    try:
        release = load_release(company_id, period_id)
    except EarningsBriefNotFound:
        handler._write_json(
            HTTPStatus.NOT_FOUND,
            {"ok": False, "error": "earnings_brief_not_found", "catalog": list_catalog()},
        )
        return
    handler._write_json(HTTPStatus.OK, build_public_projection(release))


def _single(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    return values[0].strip() if len(values) == 1 else ""
