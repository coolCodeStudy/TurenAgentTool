from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from typing import Any

from investment_knowledge_mcp.command_workbench import (
    list_workbench_actions,
    render_command_workbench_html,
)
from investment_knowledge_mcp.command_http import (
    CommandHttpRequest,
    execute_command_request,
    execute_workbench_request,
)
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.web_experience import access_error_payload


MAX_BODY_BYTES = 64 * 1024


class CommandRequestHandler(BaseHTTPRequestHandler):
    server_version = "InvestmentKnowledgeCommandAPI/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(HTTPStatus.OK, {"ok": True})
            return
        if self.path == "/command":
            self._write_html(HTTPStatus.OK, render_command_workbench_html())
            return
        if self.path == "/api/command-workbench/actions":
            self._write_json(HTTPStatus.OK, {"ok": True, "actions": list_workbench_actions()})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path in {"/api/command-workbench/parse", "/api/command-workbench/execute"}:
            if not self._require_authorized():
                return
            payload = self._read_json_body()
            if payload is None:
                return
            if self.path == "/api/command-workbench/parse":
                self._handle_workbench_parse(payload)
            else:
                self._handle_workbench_execute(payload)
            return

        if self.path != "/command":
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        if not self._require_authorized():
            return

        payload = self._read_json_body()
        if payload is None:
            return

        response = execute_command_request(
            CommandHttpRequest(
                body=payload,
                source=payload.get("source"),
                sender=payload.get("sender"),
            )
        )
        self._write_json(response.status, response.payload)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_workbench_parse(self, payload: dict[str, Any]) -> None:
        response = execute_workbench_request(
            CommandHttpRequest(
                body=payload,
                source="command-workbench.parse",
                sender=payload.get("sender"),
            ),
            execute=False,
        )
        self._write_json(response.status, response.payload)

    def _handle_workbench_execute(self, payload: dict[str, Any]) -> None:
        response = execute_workbench_request(
            CommandHttpRequest(
                body=payload,
                source="command-workbench.execute",
                sender=payload.get("sender"),
            ),
            execute=True,
        )
        self._write_json(response.status, response.payload)

    def _require_authorized(self) -> bool:
        configured_token = get_config().command_api_token
        supplied_token = _supplied_command_token(
            self.headers.get("Authorization"),
            self.headers.get("X-Command-Token"),
        )
        if not configured_token:
            self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, access_error_payload("access_not_configured"))
            return False
        if not supplied_token:
            self._write_json(HTTPStatus.UNAUTHORIZED, access_error_payload("access_required"))
            return False
        if not hmac.compare_digest(supplied_token, configured_token):
            self._write_json(HTTPStatus.UNAUTHORIZED, access_error_payload("access_rejected"))
            return False
        return True

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._write_json(HTTPStatus.LENGTH_REQUIRED, {"ok": False, "error": "Content-Length is required"})
            return None

        try:
            length = int(content_length)
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid Content-Length"})
            return None

        if length > MAX_BODY_BYTES:
            self._write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "request too large"})
            return None

        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid JSON body"})
            return None

        if not isinstance(payload, dict):
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "JSON body must be an object"})
            return None
        return payload

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, status: HTTPStatus, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _supplied_command_token(authorization: str | None, command_token: str | None) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    if command_token:
        return command_token.strip()
    return ""


def main() -> None:
    config = get_config()
    server = ThreadingHTTPServer((config.command_api_host, config.command_api_port), CommandRequestHandler)
    print(f"Command API listening on {config.command_api_host}:{config.command_api_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
