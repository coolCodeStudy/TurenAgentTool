from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from typing import Any

from investment_knowledge_mcp.command_router import handle_command
from investment_knowledge_mcp.command_workbench import (
    command_workbench_auth_error_payload,
    execution_blocker,
    list_workbench_actions,
    parse_workbench_command,
    render_command_workbench_html,
)
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
        if self.path == "/command":
            self._write_html(HTTPStatus.OK, render_command_workbench_html())
            return
        if self.path == "/api/command-workbench/actions":
            self._write_json(HTTPStatus.OK, {"ok": True, "actions": list_workbench_actions()})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path in {"/api/command-workbench/parse", "/api/command-workbench/execute"}:
            if not self._require_authorized(workbench=True):
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

        text = str(payload.get("text") or "").strip()
        sender = _clean_optional_text(payload.get("sender"))
        source = _clean_optional_text(payload.get("source"))
        if not text:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "text is required"})
            return

        try:
            run_schema()
            result = handle_command(text)
            event = record_command_event(
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
        self._write_json(status, {"ok": result.ok, "message": result.message, "event_id": event.get("id")})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_workbench_parse(self, payload: dict[str, Any]) -> None:
        raw_input = str(payload.get("text") or "").strip()
        action_id = _clean_optional_text(payload.get("action_id"))
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        selected_target = payload.get("selected_target") if isinstance(payload.get("selected_target"), dict) else None
        preview = parse_workbench_command(
            raw_input,
            action_id=action_id,
            fields=fields,
            selected_target=selected_target,
        )
        event = _record_workbench_event(
            command=raw_input or f"[action] {action_id or 'unknown'}",
            ok=preview.get("status") == "parsed",
            message=f"parse status={preview.get('status')} action={preview.get('action_id')}",
            source="command-workbench.parse",
        )
        self._write_json(HTTPStatus.OK, {"ok": True, "preview": preview, "event_id": event.get("id") if event else None})

    def _handle_workbench_execute(self, payload: dict[str, Any]) -> None:
        raw_input = str(payload.get("text") or "").strip()
        action_id = _clean_optional_text(payload.get("action_id"))
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        selected_target = payload.get("selected_target") if isinstance(payload.get("selected_target"), dict) else None
        confirmed = bool(payload.get("confirmed"))
        preview = parse_workbench_command(
            raw_input,
            action_id=action_id,
            fields=fields,
            selected_target=selected_target,
        )
        blocker = execution_blocker(preview, confirmed=confirmed)
        if blocker:
            self._write_json(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": blocker, "preview": preview},
            )
            return

        exact_command = str(preview.get("exact_command") or "").strip()
        try:
            run_schema()
            result = handle_command(exact_command)
            event = record_command_event(
                command=exact_command,
                ok=result.ok,
                message=result.message,
                sender=_clean_optional_text(payload.get("sender")),
                source="command-workbench.execute",
            )
        except Exception as exc:
            message = f"command failed: {exc}"
            event = _record_workbench_event(
                command=exact_command,
                ok=False,
                message=message,
                source="command-workbench.execute",
            )
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "error": message,
                    "preview": preview,
                    "event_id": event.get("id") if event else None,
                    "executed_command": exact_command,
                    "raw_input": raw_input,
                },
            )
            return

        status = HTTPStatus.OK if result.ok else HTTPStatus.BAD_REQUEST
        self._write_json(
            status,
            {
                "ok": result.ok,
                "message": result.message,
                "preview": preview,
                "event_id": event.get("id"),
                "executed_command": exact_command,
                "raw_input": raw_input,
            },
        )

    def _require_authorized(self, *, workbench: bool = False) -> bool:
        token = get_config().command_api_token
        if not token:
            self._write_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": "COMMAND_API_TOKEN is not configured"},
            )
            return False
        if not _authorized(self.headers.get("Authorization"), self.headers.get("X-Command-Token"), token):
            payload = command_workbench_auth_error_payload() if workbench else {"ok": False, "error": "unauthorized"}
            self._write_json(HTTPStatus.UNAUTHORIZED, payload)
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


def _record_workbench_event(command: str, ok: bool, message: str, source: str) -> dict[str, Any] | None:
    try:
        return record_command_event(
            command=command,
            ok=ok,
            message=message,
            source=source,
            sender=None,
        )
    except Exception:
        return None


def main() -> None:
    config = get_config()
    server = ThreadingHTTPServer((config.command_api_host, config.command_api_port), CommandRequestHandler)
    print(f"Command API listening on {config.command_api_host}:{config.command_api_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
