from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import os
import re
from typing import Any
from urllib.parse import urlparse

from investment_knowledge_mcp.command_workbench import (
    list_workbench_actions,
    render_command_workbench_html,
)
from investment_knowledge_mcp.command_http import (
    CommandHttpRequest,
    execute_command_request,
    read_command_json_body,
)
from investment_knowledge_mcp.daily_market_brief_controller import (
    dispatch_daily_market_brief_get,
    dispatch_daily_market_brief_post,
)
from investment_knowledge_mcp.http_access import authorize_http
from investment_knowledge_mcp.web_access import AccessClass
from investment_knowledge_mcp.weekly_review_controller import (
    dispatch_weekly_review_get,
    dispatch_weekly_review_post,
)


@dataclass(frozen=True)
class RouteContract:
    method: str
    pattern: str
    owner: str
    access: AccessClass
    dynamic: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.access, AccessClass):
            raise ValueError("route access must be an admitted AccessClass")

    def matches(self, method: str, path: str) -> bool:
        if method.upper() != self.method:
            return False
        if self.dynamic:
            return re.fullmatch(self.pattern, path) is not None
        return self.pattern == path


_ROUTES = (
    RouteContract("GET", "/", "weekly_review", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/weekly-review", "weekly_review", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/assets/weekly-review.js", "weekly_review", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/daily-market-brief", "daily_market_brief", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/assets/daily-market-brief.js", "daily_market_brief", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/health", "gateway", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/command", "command", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/api/command-workbench/actions", "command", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/api/weekly-review", "weekly_review", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/api/daily-market-brief", "daily_market_brief", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/api/daily-market-brief/dates", "daily_market_brief", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/api/daily-market-brief/history-jobs", "daily_market_brief", AccessClass.PUBLIC_READ),
    RouteContract("GET", "/api/candidate-insights", "weekly_review", AccessClass.PROTECTED),
    RouteContract("POST", "/api/command-workbench/parse", "command", AccessClass.PROTECTED),
    RouteContract("POST", "/api/command-workbench/execute", "command", AccessClass.PROTECTED),
    RouteContract("POST", "/command", "command", AccessClass.PROTECTED),
    RouteContract("POST", "/api/weekly-review/generate", "weekly_review", AccessClass.PROTECTED),
    RouteContract("POST", "/api/weekly-review/refresh", "weekly_review", AccessClass.PROTECTED),
    RouteContract("POST", "/api/weekly-review/save", "weekly_review", AccessClass.PROTECTED),
    RouteContract("POST", "/api/daily-market-brief/generate", "daily_market_brief", AccessClass.PUBLIC_READ),
    RouteContract("POST", "/api/daily-market-brief/history-jobs", "daily_market_brief", AccessClass.PUBLIC_READ),
    RouteContract(
        "POST",
        r"/api/candidate-insights/(\d+)/(confirm|reject)",
        "weekly_review",
        AccessClass.PROTECTED,
        dynamic=True,
    ),
)


def route_contracts() -> tuple[RouteContract, ...]:
    return _ROUTES


def resolve_route(method: str, request_target: str) -> RouteContract | None:
    path = urlparse(request_target).path
    return next((route for route in _ROUTES if route.matches(method, path)), None)


def dispatch_get(handler: Any) -> None:
    parsed = urlparse(handler.path)
    route = resolve_route("GET", handler.path)
    if route is None:
        _write_not_found(handler)
        return
    if not authorize_http(handler, route.access):
        return
    if route.owner == "weekly_review":
        dispatch_weekly_review_get(handler, parsed)
        return
    if route.owner == "daily_market_brief":
        dispatch_daily_market_brief_get(handler, parsed)
        return
    if parsed.path == "/health":
        handler._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "app_release_sha": os.getenv("APP_RELEASE_SHA") or "",
                "daily_market_brief_route": True,
            },
        )
        return
    if parsed.path == "/command":
        handler._write_html(HTTPStatus.OK, render_command_workbench_html())
        return
    handler._write_json(HTTPStatus.OK, {"ok": True, "actions": list_workbench_actions()})


def dispatch_post(handler: Any) -> None:
    parsed = urlparse(handler.path)
    route = resolve_route("POST", handler.path)
    if route is None:
        _write_not_found(handler)
        return
    if not authorize_http(handler, route.access):
        return
    if route.owner == "weekly_review":
        dispatch_weekly_review_post(handler, parsed)
        return
    if route.owner == "daily_market_brief":
        dispatch_daily_market_brief_post(handler, parsed)
        return
    if parsed.path == "/command":
        payload = read_command_json_body(handler)
    else:
        payload = handler._read_json_body()
    if payload is None:
        return
    if parsed.path == "/command":
        response = execute_command_request(
            CommandHttpRequest(
                body=payload,
                source=payload.get("source"),
                sender=payload.get("sender"),
            )
        )
        handler._write_json(response.status, response.payload)
        return
    if parsed.path == "/api/command-workbench/parse":
        handler._handle_workbench_parse(payload)
    else:
        handler._handle_workbench_execute(payload)


def _write_not_found(handler: Any) -> None:
    handler._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
