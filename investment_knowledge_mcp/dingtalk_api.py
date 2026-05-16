from __future__ import annotations

import base64
import hashlib
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from typing import Any
from urllib.parse import unquote

from investment_knowledge_mcp.command_router import handle_command
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import record_command_event


MAX_BODY_BYTES = 64 * 1024
MAX_REPLY_CHARS = 3500


class DingTalkRequestHandler(BaseHTTPRequestHandler):
    server_version = "InvestmentKnowledgeDingTalkAPI/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(HTTPStatus.OK, {"ok": True})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/dingtalk/webhook":
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        config = get_config()
        if not _verify_signature(
            timestamp=self.headers.get("timestamp") or self.headers.get("X-DingTalk-Timestamp"),
            sign=self.headers.get("sign") or self.headers.get("X-DingTalk-Sign"),
            secret=config.dingtalk_outgoing_secret,
        ):
            self._write_json(HTTPStatus.UNAUTHORIZED, _text_reply("钉钉签名校验失败。"))
            return

        payload = self._read_json_body()
        if payload is None:
            return

        command = _extract_command(payload)
        sender = _extract_sender(payload)
        if not command:
            self._write_json(HTTPStatus.OK, _text_reply("目前只支持文本消息，例如：分析 000660 KR"))
            return

        if not config.dingtalk_allow_write_commands and not _is_query_command(command):
            message = "钉钉入口当前只开放查询类指令：分析 000660 KR、查看候选心得、帮助。写入和确认类指令请先走本地 CLI。"
            _record_event(command=command, ok=False, message=message, sender=sender)
            self._write_json(HTTPStatus.OK, _text_reply(message))
            return

        try:
            run_schema()
            result = handle_command(command)
            _record_event(command=command, ok=result.ok, message=result.message, sender=sender)
        except Exception as exc:
            message = f"指令执行失败：{exc}"
            _record_event(command=command, ok=False, message=message, sender=sender)
            self._write_json(HTTPStatus.OK, _text_reply(message))
            return

        self._write_json(HTTPStatus.OK, _text_reply(result.message))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._write_json(HTTPStatus.LENGTH_REQUIRED, _text_reply("Content-Length is required."))
            return None

        try:
            length = int(content_length)
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, _text_reply("invalid Content-Length."))
            return None

        if length > MAX_BODY_BYTES:
            self._write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, _text_reply("request too large."))
            return None

        raw_body = self.rfile.read(length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(HTTPStatus.BAD_REQUEST, _text_reply("invalid JSON body."))
            return None

        if not isinstance(payload, dict):
            self._write_json(HTTPStatus.BAD_REQUEST, _text_reply("JSON body must be an object."))
            return None
        return payload

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _verify_signature(timestamp: str | None, sign: str | None, secret: str | None) -> bool:
    if not secret:
        return True
    if not timestamp or not sign:
        return False

    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(unquote(sign), expected)


def _extract_command(payload: dict[str, Any]) -> str:
    msgtype = str(payload.get("msgtype") or "").strip()
    if msgtype == "text":
        text = payload.get("text")
        if isinstance(text, dict):
            return _clean_command(text.get("content"))
    if msgtype == "audio":
        content = payload.get("content")
        if isinstance(content, dict):
            return _clean_command(content.get("recognition"))
    return ""


def _clean_command(value: Any) -> str:
    if value is None:
        return ""
    command = str(value).strip()
    command = re.sub(r"^(?:@\S+\s*)+", "", command).strip()
    return command


def _extract_sender(payload: dict[str, Any]) -> str | None:
    for key in ("senderStaffId", "senderNick", "senderId"):
        value = payload.get(key)
        if value:
            return str(value).strip()
    return None


def _is_query_command(command: str) -> bool:
    cleaned = command.strip()
    return bool(
        re.fullmatch(r"(?:分析|analyze)\s+\S+\s+\S+", cleaned, flags=re.IGNORECASE)
        or cleaned in {"查看候选心得", "候选心得", "list candidates", "candidates", "帮助", "help", "?"}
    )


def _record_event(command: str, ok: bool, message: str, sender: str | None) -> None:
    try:
        record_command_event(
            command=command,
            ok=ok,
            message=message,
            sender=sender,
            source="dingtalk",
        )
    except Exception:
        return


def _text_reply(content: str) -> dict[str, Any]:
    return {
        "msgtype": "text",
        "text": {
            "content": _truncate_reply(content),
        },
    }


def _truncate_reply(content: str) -> str:
    if len(content) <= MAX_REPLY_CHARS:
        return content
    return content[:MAX_REPLY_CHARS] + "\n\n...内容过长，已截断。"


def main() -> None:
    config = get_config()
    server = ThreadingHTTPServer((config.dingtalk_api_host, config.dingtalk_api_port), DingTalkRequestHandler)
    print(f"DingTalk API listening on {config.dingtalk_api_host}:{config.dingtalk_api_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
