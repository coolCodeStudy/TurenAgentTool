from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    read_command_json_body,
)
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.http_access import authorize_http
from investment_knowledge_mcp.web_access import AccessClass


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
            if not authorize_http(self, AccessClass.PROTECTED):
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

        if not authorize_http(self, AccessClass.PROTECTED):
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

    def _read_json_body(self) -> dict[str, Any] | None:
        return read_command_json_body(self)

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


def main() -> None:
    config = get_config()
    server = ThreadingHTTPServer((config.command_api_host, config.command_api_port), CommandRequestHandler)
    print(f"Command API listening on {config.command_api_host}:{config.command_api_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
