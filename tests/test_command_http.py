from __future__ import annotations

from http import HTTPStatus
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest import mock

from investment_knowledge_mcp import command_http


class _JsonBodyHandler:
    def __init__(self, body: bytes, content_length: str | None) -> None:
        self.headers = {} if content_length is None else {"Content-Length": content_length}
        self.rfile = BytesIO(body)
        self.responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.responses.append((status, payload))


class CommandJsonBodyParserTests(unittest.TestCase):
    def test_shared_parser_accepts_a_json_object(self) -> None:
        handler = _JsonBodyHandler(b'{"text":"help"}', "15")
        reader = getattr(command_http, "read_command_json_body", None)

        self.assertIsNotNone(reader, "command HTTP must expose the shared JSON body parser")
        payload = reader(handler)

        self.assertEqual({"text": "help"}, payload)
        self.assertEqual([], handler.responses)

    def test_shared_parser_accepts_an_object_at_the_exact_body_limit(self) -> None:
        body = b'{"text":"' + (b"x" * (64 * 1024 - 11)) + b'"}'
        self.assertEqual(64 * 1024, len(body))
        handler = _JsonBodyHandler(body, str(len(body)))

        payload = command_http.read_command_json_body(handler)

        self.assertEqual(64 * 1024 - 11, len(payload["text"]))
        self.assertEqual([], handler.responses)

    def test_shared_parser_preserves_legacy_error_responses(self) -> None:
        cases = (
            (
                b"",
                None,
                HTTPStatus.LENGTH_REQUIRED,
                {"ok": False, "error": "Content-Length is required"},
            ),
            (
                b"",
                "not-an-integer",
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "invalid Content-Length"},
            ),
            (
                b"{}",
                str(64 * 1024 + 1),
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"ok": False, "error": "request too large"},
            ),
            (
                b"{",
                "1",
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "invalid JSON body"},
            ),
            (
                b"\xff",
                "1",
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "invalid JSON body"},
            ),
            (
                b"[]",
                "2",
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "JSON body must be an object"},
            ),
        )
        for body, content_length, status, response in cases:
            with self.subTest(content_length=content_length, body=body):
                handler = _JsonBodyHandler(body, content_length)
                reader = getattr(command_http, "read_command_json_body", None)

                self.assertIsNotNone(reader, "command HTTP must expose the shared JSON body parser")
                payload = reader(handler)

                self.assertIsNone(payload)
                self.assertEqual([(status, response)], handler.responses)

    def test_command_handler_still_serializes_json_responses(self) -> None:
        from investment_knowledge_mcp.command_api import CommandRequestHandler

        handler = object.__new__(CommandRequestHandler)
        handler.wfile = BytesIO()
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()

        handler._write_json(HTTPStatus.OK, {"ok": True})

        self.assertEqual(b'{"ok": true}', handler.wfile.getvalue())


class CommandHttpControllerTests(unittest.TestCase):
    def request(self, body: dict[str, object], *, source: str = "test.source", sender: object = None):
        return command_http.CommandHttpRequest(body=body, source=source, sender=sender)

    def test_direct_command_success_records_cleaned_request_metadata(self) -> None:
        with (
            mock.patch.object(command_http, "run_schema") as run_schema,
            mock.patch.object(command_http, "handle_command", return_value=SimpleNamespace(ok=True, message="completed")) as handle,
            mock.patch.object(command_http, "record_command_event", return_value={"id": 17}) as record,
        ):
            response = command_http.execute_command_request(
                self.request({"text": "  system status  "}, source="direct.source", sender="  operator  ")
            )

        self.assertEqual(HTTPStatus.OK, response.status)
        self.assertEqual({"ok": True, "message": "completed", "event_id": 17}, response.payload)
        run_schema.assert_called_once_with()
        handle.assert_called_once_with("system status")
        record.assert_called_once_with(
            command="system status",
            ok=True,
            message="completed",
            sender="operator",
            source="direct.source",
        )

    def test_direct_command_cleans_optional_source_before_recording(self) -> None:
        with (
            mock.patch.object(command_http, "run_schema"),
            mock.patch.object(command_http, "handle_command", return_value=SimpleNamespace(ok=True, message="completed")),
            mock.patch.object(command_http, "record_command_event", return_value={"id": 17}) as record,
        ):
            for source in (None, "  ", "  direct.source  "):
                response = command_http.execute_command_request(
                    command_http.CommandHttpRequest(body={"text": "system status"}, source=source)
                )
                self.assertEqual(HTTPStatus.OK, response.status)

        self.assertEqual(
            [None, None, "direct.source"],
            [call.kwargs["source"] for call in record.call_args_list],
        )

    def test_direct_command_rejects_blank_text_without_running_dependencies(self) -> None:
        with (
            mock.patch.object(command_http, "run_schema") as run_schema,
            mock.patch.object(command_http, "handle_command") as handle,
        ):
            response = command_http.execute_command_request(self.request({"text": "  "}))

        self.assertEqual(HTTPStatus.BAD_REQUEST, response.status)
        self.assertEqual({"ok": False, "error": "text is required"}, response.payload)
        run_schema.assert_not_called()
        handle.assert_not_called()

    def test_direct_command_exception_is_sanitized_and_records_safe_failed_event(self) -> None:
        raw_error = "postgresql://admin:fake-password@db/private"
        with (
            mock.patch.object(command_http, "run_schema", side_effect=RuntimeError(raw_error)),
            mock.patch.object(command_http, "record_command_event", return_value={"id": 18}) as record,
        ):
            response = command_http.execute_command_request(
                self.request({"text": "system status"}, source="direct.source", sender="sender")
            )

        self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, response.status)
        self.assertEqual(
            {"ok": False, "error": command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE},
            response.payload,
        )
        self.assertNotIn(raw_error, str(response.payload))
        record.assert_called_once_with(
            command="system status",
            ok=False,
            message=command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE,
            sender="sender",
            source="direct.source",
        )

    def test_parse_returns_preview_when_event_recording_fails(self) -> None:
        preview = {"status": "parsed", "action_id": "system", "exact_command": "system status"}
        with (
            mock.patch.object(command_http, "parse_workbench_command", return_value=preview) as parse,
            mock.patch.object(command_http, "record_command_event", side_effect=RuntimeError("audit unavailable")) as record,
        ):
            response = command_http.execute_workbench_request(
                self.request({"text": "status"}, source="parse.source"), execute=False
            )

        self.assertEqual(HTTPStatus.OK, response.status)
        self.assertEqual({"ok": True, "preview": preview, "event_id": None}, response.payload)
        parse.assert_called_once_with("status", action_id=None, fields={}, selected_target=None)
        record.assert_called_once_with(
            command="status",
            ok=True,
            message="parse status=parsed action=system",
            sender=None,
            source="parse.source",
        )

    def test_parse_parser_exception_returns_safe_failure_and_records_action_fallback(self) -> None:
        raw_error = "postgresql://admin:fake-password@db/private"
        with (
            mock.patch.object(command_http, "parse_workbench_command", side_effect=RuntimeError(raw_error)),
            mock.patch.object(command_http, "record_command_event", return_value={"id": 21}) as record,
        ):
            response = command_http.execute_workbench_request(
                self.request(
                    {"text": "", "action_id": "  system  "},
                    source="  parse.source  ",
                    sender="  parser  ",
                ),
                execute=False,
            )

        self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, response.status)
        self.assertEqual(
            {"ok": False, "error": command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE},
            response.payload,
        )
        self.assertNotIn(raw_error, str(response.payload))
        record.assert_called_once_with(
            command="[action] system",
            ok=False,
            message=command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE,
            sender="parser",
            source="parse.source",
        )

    def test_execute_parser_exception_returns_safe_failure_and_records_raw_input(self) -> None:
        raw_error = "token=leaked postgres://admin:fake-password@db/private"
        with (
            mock.patch.object(command_http, "parse_workbench_command", side_effect=RuntimeError(raw_error)),
            mock.patch.object(command_http, "record_command_event", return_value={"id": 22}) as record,
        ):
            response = command_http.execute_workbench_request(
                self.request({"text": "  raw command  "}, source="execute.source", sender="executor"),
                execute=True,
            )

        self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, response.status)
        self.assertEqual(
            {"ok": False, "error": command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE},
            response.payload,
        )
        self.assertNotIn(raw_error, str(response.payload))
        record.assert_called_once_with(
            command="raw command",
            ok=False,
            message=command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE,
            sender="executor",
            source="execute.source",
        )

    def test_execute_returns_blocker_without_schema_or_command(self) -> None:
        preview = {"status": "needs_field", "recovery_message": "Choose an action."}
        with (
            mock.patch.object(command_http, "parse_workbench_command", return_value=preview),
            mock.patch.object(command_http, "execution_blocker", return_value="Choose an action."),
            mock.patch.object(command_http, "run_schema") as run_schema,
            mock.patch.object(command_http, "handle_command") as handle,
        ):
            response = command_http.execute_workbench_request(self.request({"text": "status"}), execute=True)

        self.assertEqual(HTTPStatus.CONFLICT, response.status)
        self.assertEqual({"ok": False, "error": "Choose an action.", "preview": preview}, response.payload)
        run_schema.assert_not_called()
        handle.assert_not_called()

    def test_execute_blocker_exception_returns_safe_failure_and_records_event(self) -> None:
        raw_error = "password=fake-password SELECT * FROM private_table"
        preview = {"status": "parsed", "exact_command": "exact command"}
        with (
            mock.patch.object(command_http, "parse_workbench_command", return_value=preview),
            mock.patch.object(command_http, "execution_blocker", side_effect=RuntimeError(raw_error)),
            mock.patch.object(command_http, "record_command_event", return_value={"id": 23}) as record,
        ):
            response = command_http.execute_workbench_request(
                self.request({"text": "raw command"}, source="  blocker.source  ", sender="  blocker  "),
                execute=True,
            )

        self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, response.status)
        self.assertEqual(
            {"ok": False, "error": command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE},
            response.payload,
        )
        self.assertNotIn(raw_error, str(response.payload))
        record.assert_called_once_with(
            command="raw command",
            ok=False,
            message=command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE,
            sender="blocker",
            source="blocker.source",
        )

    def test_execute_runs_exact_command_and_uses_request_source(self) -> None:
        preview = {"status": "parsed", "exact_command": "exact command"}
        with (
            mock.patch.object(command_http, "parse_workbench_command", return_value=preview),
            mock.patch.object(command_http, "execution_blocker", return_value=None),
            mock.patch.object(command_http, "run_schema"),
            mock.patch.object(command_http, "handle_command", return_value=SimpleNamespace(ok=True, message="done")) as handle,
            mock.patch.object(command_http, "record_command_event", return_value={"id": 19}) as record,
        ):
            response = command_http.execute_workbench_request(
                self.request({"text": "raw command", "confirmed": True}, source="weekly-review-web.command-workbench.execute", sender="  user "),
                execute=True,
            )

        self.assertEqual(HTTPStatus.OK, response.status)
        self.assertEqual(
            {
                "ok": True,
                "message": "done",
                "preview": preview,
                "event_id": 19,
                "executed_command": "exact command",
                "raw_input": "raw command",
            },
            response.payload,
        )
        handle.assert_called_once_with("exact command")
        record.assert_called_once_with(
            command="exact command",
            ok=True,
            message="done",
            sender="user",
            source="weekly-review-web.command-workbench.execute",
        )

    def test_execute_exception_is_sanitized_with_response_context(self) -> None:
        preview = {"status": "parsed", "exact_command": "exact command"}
        with (
            mock.patch.object(command_http, "parse_workbench_command", return_value=preview),
            mock.patch.object(command_http, "execution_blocker", return_value=None),
            mock.patch.object(command_http, "run_schema", side_effect=RuntimeError("private database failure")),
            mock.patch.object(command_http, "record_command_event", return_value={"id": 20}) as record,
        ):
            response = command_http.execute_workbench_request(
                self.request({"text": "raw command"}, source="execute.source"), execute=True
            )

        self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, response.status)
        self.assertEqual(
            {
                "ok": False,
                "error": command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE,
                "preview": preview,
                "event_id": 20,
                "executed_command": "exact command",
                "raw_input": "raw command",
            },
            response.payload,
        )
        record.assert_called_once_with(
            command="exact command",
            ok=False,
            message=command_http.PUBLIC_WORKBENCH_FAILURE_MESSAGE,
            sender=None,
            source="execute.source",
        )


if __name__ == "__main__":
    unittest.main()
