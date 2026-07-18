from __future__ import annotations

from http import HTTPStatus
from types import SimpleNamespace
import unittest
from unittest import mock

from investment_knowledge_mcp.http_access import authorize_http
from investment_knowledge_mcp.web_access import AccessClass


class _Handler:
    def __init__(self, *, method: str = "POST", headers: dict[str, str] | None = None) -> None:
        self.command = method
        self.headers = headers or {}
        self.responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.responses.append((status, payload))


def _config(
    *,
    app: str | None = None,
    command: str | None = None,
    weekly: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        app_access_token=app,
        command_api_token=command,
        weekly_review_web_token=weekly,
    )


class AuthorizeHttpTests(unittest.TestCase):
    def _authorize(
        self,
        handler: _Handler,
        config: SimpleNamespace,
        access_class: AccessClass = AccessClass.PROTECTED,
    ) -> bool:
        with mock.patch("investment_knowledge_mcp.http_access.get_config", return_value=config):
            return authorize_http(handler, access_class)

    def test_missing_configuration_writes_service_unavailable_error(self) -> None:
        handler = _Handler()

        self.assertFalse(self._authorize(handler, _config()))

        self.assertEqual(
            [(HTTPStatus.SERVICE_UNAVAILABLE, mock.ANY)],
            [(status, mock.ANY) for status, _ in handler.responses],
        )
        self.assertEqual("access_not_configured", handler.responses[0][1]["error"])

    def test_missing_credential_writes_unauthorized_required_error(self) -> None:
        handler = _Handler()

        self.assertFalse(self._authorize(handler, _config(app="canonical-token")))

        self.assertEqual(HTTPStatus.UNAUTHORIZED, handler.responses[0][0])
        self.assertEqual("access_required", handler.responses[0][1]["error"])

    def test_rejected_credential_writes_unauthorized_rejected_error(self) -> None:
        handler = _Handler(headers={"Authorization": "Bearer synthetic-invalid"})

        self.assertFalse(self._authorize(handler, _config(app="canonical-token")))

        self.assertEqual(HTTPStatus.UNAUTHORIZED, handler.responses[0][0])
        self.assertEqual("access_rejected", handler.responses[0][1]["error"])

    def test_canonical_token_is_accepted_from_every_compatible_header(self) -> None:
        headers = (
            {"Authorization": "bEaReR canonical-token"},
            {"X-Command-Token": "canonical-token"},
            {"X-Weekly-Review-Token": "canonical-token"},
        )
        for request_headers in headers:
            with self.subTest(headers=request_headers):
                handler = _Handler(headers=request_headers)

                self.assertTrue(self._authorize(handler, _config(app="canonical-token")))
                self.assertEqual([], handler.responses)

    def test_equal_legacy_aliases_and_legacy_headers_remain_compatible(self) -> None:
        for request_headers in (
            {"X-Command-Token": "shared-token"},
            {"X-Weekly-Review-Token": "shared-token"},
        ):
            with self.subTest(headers=request_headers):
                handler = _Handler(headers=request_headers)

                self.assertTrue(
                    self._authorize(handler, _config(command="shared-token", weekly="shared-token"))
                )
                self.assertEqual([], handler.responses)

    def test_conflicting_aliases_fail_closed_without_secret_values(self) -> None:
        handler = _Handler(headers={"X-Command-Token": "command-secret"})

        self.assertFalse(
            self._authorize(handler, _config(app="canonical-secret", command="command-secret"))
        )

        status, payload = handler.responses[0]
        self.assertEqual(HTTPStatus.SERVICE_UNAVAILABLE, status)
        self.assertEqual("access_not_configured", payload["error"])
        rendered = repr(payload)
        self.assertNotIn("canonical-secret", rendered)
        self.assertNotIn("command-secret", rendered)

    def test_public_read_protected_write_get_is_allowed_without_configuration(self) -> None:
        handler = _Handler(method="GET")

        self.assertTrue(
            self._authorize(handler, _config(), AccessClass.PUBLIC_READ_PROTECTED_WRITE)
        )

        self.assertEqual([], handler.responses)


if __name__ == "__main__":
    unittest.main()
