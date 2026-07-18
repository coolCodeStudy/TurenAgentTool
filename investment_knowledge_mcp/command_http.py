from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
import json
from typing import Any, Mapping

from investment_knowledge_mcp.command_router import handle_command, safe_public_command_message
from investment_knowledge_mcp.command_workbench import execution_blocker, parse_workbench_command
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import record_command_event


PUBLIC_WORKBENCH_FAILURE_MESSAGE = "Command execution failed. Please retry later."
MAX_COMMAND_BODY_BYTES = 64 * 1024


def read_command_json_body(handler: Any) -> dict[str, Any] | None:
    content_length = handler.headers.get("Content-Length")
    if content_length is None:
        handler._write_json(
            HTTPStatus.LENGTH_REQUIRED,
            {"ok": False, "error": "Content-Length is required"},
        )
        return None

    try:
        length = int(content_length)
    except ValueError:
        handler._write_json(
            HTTPStatus.BAD_REQUEST,
            {"ok": False, "error": "invalid Content-Length"},
        )
        return None

    if length > MAX_COMMAND_BODY_BYTES:
        handler._write_json(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            {"ok": False, "error": "request too large"},
        )
        return None

    raw_body = handler.rfile.read(length)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        handler._write_json(
            HTTPStatus.BAD_REQUEST,
            {"ok": False, "error": "invalid JSON body"},
        )
        return None

    if not isinstance(payload, dict):
        handler._write_json(
            HTTPStatus.BAD_REQUEST,
            {"ok": False, "error": "JSON body must be an object"},
        )
        return None
    return payload


@dataclass(frozen=True)
class CommandHttpRequest:
    body: Mapping[str, object]
    source: str | None
    sender: str | None = None


@dataclass(frozen=True)
class CommandHttpResponse:
    status: HTTPStatus
    payload: dict[str, object]


def execute_command_request(request: CommandHttpRequest) -> CommandHttpResponse:
    text = str(request.body.get("text") or "").strip()
    if not text:
        return CommandHttpResponse(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "text is required"})

    sender = _clean_optional_text(request.sender)
    source = _clean_optional_text(request.source)
    try:
        run_schema()
        result = handle_command(text)
        message = safe_public_command_message(result, PUBLIC_WORKBENCH_FAILURE_MESSAGE)
        event_id = _record_event_id(
            command=text,
            ok=result.ok,
            message=message,
            sender=sender,
            source=source,
        )
    except Exception:
        _record_event_id(
            command=text,
            ok=False,
            message=PUBLIC_WORKBENCH_FAILURE_MESSAGE,
            sender=sender,
            source=source,
        )
        return CommandHttpResponse(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {"ok": False, "error": PUBLIC_WORKBENCH_FAILURE_MESSAGE},
        )

    status = HTTPStatus.OK if result.ok else HTTPStatus.BAD_REQUEST
    return CommandHttpResponse(status, {"ok": result.ok, "message": message, "event_id": event_id})


def execute_workbench_request(
    request: CommandHttpRequest,
    *,
    execute: bool,
) -> CommandHttpResponse:
    raw_input = str(request.body.get("text") or "").strip()
    action_id = _clean_optional_text(request.body.get("action_id"))
    sender = _clean_optional_text(request.sender)
    source = _clean_optional_text(request.source)
    fields = request.body.get("fields") if isinstance(request.body.get("fields"), dict) else {}
    selected_target = request.body.get("selected_target") if isinstance(request.body.get("selected_target"), dict) else None
    event_command = raw_input or f"[action] {action_id or 'unknown'}"
    try:
        preview = parse_workbench_command(
            raw_input,
            action_id=action_id,
            fields=fields,
            selected_target=selected_target,
        )
    except Exception:
        return _safe_workbench_failure_response(command=event_command, sender=sender, source=source)

    if not execute:
        event_id = _record_event_id(
            command=event_command,
            ok=preview.get("status") == "parsed",
            message=f"parse status={preview.get('status')} action={preview.get('action_id')}",
            sender=sender,
            source=source,
        )
        return CommandHttpResponse(HTTPStatus.OK, {"ok": True, "preview": preview, "event_id": event_id})

    try:
        blocker = execution_blocker(preview, confirmed=bool(request.body.get("confirmed")))
    except Exception:
        return _safe_workbench_failure_response(command=event_command, sender=sender, source=source)
    if blocker:
        return CommandHttpResponse(HTTPStatus.CONFLICT, {"ok": False, "error": blocker, "preview": preview})

    exact_command = str(preview.get("exact_command") or "").strip()
    try:
        run_schema()
        result = handle_command(exact_command)
        message = safe_public_command_message(result, PUBLIC_WORKBENCH_FAILURE_MESSAGE)
        event_id = _record_event_id(
            command=exact_command,
            ok=result.ok,
            message=message,
            sender=sender,
            source=source,
        )
    except Exception:
        event_id = _record_event_id(
            command=exact_command,
            ok=False,
            message=PUBLIC_WORKBENCH_FAILURE_MESSAGE,
            sender=sender,
            source=source,
        )
        return CommandHttpResponse(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {
                "ok": False,
                "error": PUBLIC_WORKBENCH_FAILURE_MESSAGE,
                "preview": preview,
                "event_id": event_id,
                "executed_command": exact_command,
                "raw_input": raw_input,
            },
        )

    status = HTTPStatus.OK if result.ok else HTTPStatus.BAD_REQUEST
    return CommandHttpResponse(
        status,
        {
            "ok": result.ok,
            "message": message,
            "preview": preview,
            "event_id": event_id,
            "executed_command": exact_command,
            "raw_input": raw_input,
        },
    )


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _safe_workbench_failure_response(
    *,
    command: str,
    sender: str | None,
    source: str | None,
) -> CommandHttpResponse:
    _record_event_id(
        command=command,
        ok=False,
        message=PUBLIC_WORKBENCH_FAILURE_MESSAGE,
        sender=sender,
        source=source,
    )
    return CommandHttpResponse(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        {"ok": False, "error": PUBLIC_WORKBENCH_FAILURE_MESSAGE},
    )


def _record_event_id(
    *,
    command: str,
    ok: bool,
    message: str,
    sender: str | None,
    source: str | None,
) -> int | None:
    try:
        event = record_command_event(
            command=command,
            ok=ok,
            message=message,
            sender=sender,
            source=source,
        )
    except Exception:
        return None
    return event.get("id") if isinstance(event, dict) else None
