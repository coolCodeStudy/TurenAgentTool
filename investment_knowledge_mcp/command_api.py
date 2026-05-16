from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from typing import Any

from investment_knowledge_mcp.command_router import handle_command
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import record_command_event


MAX_BODY_BYTES = 64 * 1024


class CommandRequestHandler(BaseHTTPRequestHandler):
    server_version = "InvestmentKnowledgeCommandAPI/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(HTTPStatus.OK, {"ok": True})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/command":
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        token = get_config().command_api_token
        if not token:
            self._write_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": "COMMAND_API_TOKEN is not configured"},
            )
            return
        if not _authorized(self.headers.get("Authorization"), self.headers.get("X-Command-Token"), token):
            self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return

        payload = self._read_json_body()
        if payload is None:
            return

        text = str(payload.get("text") or "").strip()
        sender = _clean_optional_text(payload.get("sender"))
        source = _clean_optional_text(payload.get("source"))
        if not text:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "text is required"})
            return

        try:
            run_schema()
            result = handle_command(text)
            record_command_event(
                command=text,
                ok=result.ok,
                message=result.message,
                sender=sender,
                source=source,
            )
        except Exception as exc:
            message = f"command failed: {exc}"
            _record_failed_command(text, message, source=source, sender=sender)
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": message})
            return

        status = HTTPStatus.OK if result.ok else HTTPStatus.BAD_REQUEST
        self._write_json(status, {"ok": result.ok, "message": result.message})

    def log_message(self, format: str, *args: Any) -> None:
        return

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


def _authorized(authorization: str | None, command_token: str | None, expected_token: str) -> bool:
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ").strip()
        return hmac.compare_digest(supplied, expected_token)
    if command_token:
        return hmac.compare_digest(command_token.strip(), expected_token)
    return False


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _record_failed_command(command: str, message: str, source: str | None, sender: str | None) -> None:
    try:
        record_command_event(
            command=command,
            ok=False,
            message=message,
            sender=sender,
            source=source,
        )
    except Exception:
        return


def main() -> None:
    config = get_config()
    server = ThreadingHTTPServer((config.command_api_host, config.command_api_port), CommandRequestHandler)
    print(f"Command API listening on {config.command_api_host}:{config.command_api_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
