from __future__ import annotations

from http import HTTPStatus
from types import SimpleNamespace
import unittest
from unittest import mock

from investment_knowledge_mcp import command_http


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
