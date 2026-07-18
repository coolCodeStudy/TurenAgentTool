from __future__ import annotations

from http import HTTPStatus
from typing import Protocol

from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.web_access import (
    AccessClass,
    AccessError,
    BrowserAccessConfig,
    authorize_request,
    extract_bearer_token,
)
from investment_knowledge_mcp.web_experience import access_error_payload


class HttpAccessHandler(Protocol):
    command: str
    headers: object

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None: ...


def authorize_http(handler: HttpAccessHandler, access_class: AccessClass) -> bool:
    """Apply the browser access policy and write its safe HTTP error response."""
    config = get_config()
    configured = BrowserAccessConfig.resolve(
        getattr(config, "app_access_token", None),
        getattr(config, "command_api_token", None),
        getattr(config, "weekly_review_web_token", None),
    )
    headers = handler.headers
    supplied_tokens = (
        extract_bearer_token(headers.get("Authorization")),
        headers.get("X-Command-Token"),
        headers.get("X-Weekly-Review-Token"),
    )
    decision = authorize_request(
        access_class,
        method=handler.command,
        configured=configured,
        supplied_tokens=supplied_tokens,
    )
    if decision.allowed:
        return True

    error_code = decision.error_code
    if error_code is AccessError.NOT_CONFIGURED:
        status = HTTPStatus.SERVICE_UNAVAILABLE
    else:
        status = HTTPStatus.UNAUTHORIZED
    handler._write_json(status, access_error_payload(error_code.value))
    return False
