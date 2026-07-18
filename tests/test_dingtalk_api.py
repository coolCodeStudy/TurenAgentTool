from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock


def _load_dingtalk_api():
    command_router = ModuleType("investment_knowledge_mcp.command_router")
    command_router.handle_command = mock.Mock(
        return_value=SimpleNamespace(ok=True, message="completed")
    )
    command_router.is_query_command = mock.Mock(return_value=True)

    config = ModuleType("investment_knowledge_mcp.config")
    config.get_config = mock.Mock(
        return_value=SimpleNamespace(
            dingtalk_outgoing_secret="configured-secret",
            dingtalk_allow_write_commands=False,
        )
    )

    db = ModuleType("investment_knowledge_mcp.db")
    db.run_schema = mock.Mock()

    repository = ModuleType("investment_knowledge_mcp.repository")
    repository.record_command_event = mock.Mock()

    module_name = "investment_knowledge_mcp.dingtalk_api"
    sys.modules.pop(module_name, None)
    with mock.patch.dict(
        sys.modules,
        {
            command_router.__name__: command_router,
            config.__name__: config,
            db.__name__: db,
            repository.__name__: repository,
        },
    ):
        return importlib.import_module(module_name)


class DingTalkApiUsageLoggingTests(unittest.TestCase):
    def test_authenticated_webhook_logs_only_sanitized_usage_metadata(self) -> None:
        api = _load_dingtalk_api()
        handler = object.__new__(api.DingTalkRequestHandler)
        handler.path = "/dingtalk/webhook"
        handler.headers = {}
        handler._read_json_body = lambda: {
            "msgtype": "text",
            "text": {"content": "sensitive-command-text"},
            "senderStaffId": "sensitive-sender-id",
        }
        handler._write_json = mock.Mock()

        with (
            mock.patch.object(api, "_verify_signature", return_value=True),
            self.assertLogs("investment_knowledge_mcp.dingtalk_api", level="INFO") as captured,
        ):
            handler.do_POST()

        log_output = "\n".join(captured.output)
        self.assertIn("event=dingtalk_http_webhook_received", log_output)
        self.assertIn("msgtype=text", log_output)
        self.assertIn("command_present=true", log_output)
        self.assertIn("sender_present=true", log_output)
        self.assertNotIn("sensitive-command-text", log_output)
        self.assertNotIn("sensitive-sender-id", log_output)
        self.assertNotIn("configured-secret", log_output)


if __name__ == "__main__":
    unittest.main()
