from __future__ import annotations

from http import HTTPStatus
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest import mock


class AppGatewayRouteTableTests(unittest.TestCase):
    def test_route_contract_rejects_unadmitted_access_value(self) -> None:
        from investment_knowledge_mcp.app_gateway import RouteContract

        with self.assertRaisesRegex(ValueError, "admitted AccessClass"):
            RouteContract("POST", "/unsafe", "command", "protected")  # type: ignore[arg-type]

    def test_route_ownership_table_is_complete_and_preserves_access_classes(self) -> None:
        from investment_knowledge_mcp.app_gateway import route_contracts
        from investment_knowledge_mcp.web_access import AccessClass

        actual = {
            (route.method, route.pattern): (route.owner, route.access)
            for route in route_contracts()
        }
        self.assertEqual(len(actual), len(route_contracts()), "route contracts must not contain duplicates")
        expected = {
            ("GET", "/"): ("weekly_review", AccessClass.PUBLIC_READ),
            ("GET", "/weekly-review"): ("weekly_review", AccessClass.PUBLIC_READ),
            ("GET", "/daily-market-brief"): ("daily_market_brief", AccessClass.PUBLIC_READ),
            ("GET", "/health"): ("gateway", AccessClass.PUBLIC_READ),
            ("GET", "/command"): ("command", AccessClass.PUBLIC_READ),
            ("GET", "/api/command-workbench/actions"): ("command", AccessClass.PUBLIC_READ),
            ("GET", "/api/weekly-review"): ("weekly_review", AccessClass.PUBLIC_READ),
            ("GET", "/api/daily-market-brief"): ("daily_market_brief", AccessClass.PUBLIC_READ),
            ("GET", "/api/daily-market-brief/dates"): ("daily_market_brief", AccessClass.PUBLIC_READ),
            ("GET", "/api/daily-market-brief/history-jobs"): ("daily_market_brief", AccessClass.PUBLIC_READ),
            ("GET", "/api/candidate-insights"): ("weekly_review", AccessClass.PROTECTED),
            ("POST", "/api/command-workbench/parse"): ("command", AccessClass.PROTECTED),
            ("POST", "/api/command-workbench/execute"): ("command", AccessClass.PROTECTED),
            ("POST", "/command"): ("command", AccessClass.PROTECTED),
            ("POST", "/api/weekly-review/generate"): ("weekly_review", AccessClass.PROTECTED),
            ("POST", "/api/weekly-review/refresh"): ("weekly_review", AccessClass.PROTECTED),
            ("POST", "/api/weekly-review/save"): ("weekly_review", AccessClass.PROTECTED),
            ("POST", "/api/daily-market-brief/generate"): ("daily_market_brief", AccessClass.PUBLIC_READ),
            ("POST", "/api/daily-market-brief/history-jobs"): ("daily_market_brief", AccessClass.PUBLIC_READ),
            ("POST", r"/api/candidate-insights/(\d+)/(confirm|reject)"): (
                "weekly_review",
                AccessClass.PROTECTED,
            ),
        }
        self.assertEqual(actual, expected)

    def test_query_string_is_not_part_of_route_matching(self) -> None:
        from investment_knowledge_mcp.app_gateway import resolve_route

        route = resolve_route("GET", "/api/daily-market-brief?market=HK&date=2026-06-22")

        self.assertIsNotNone(route)
        self.assertEqual(route.owner, "daily_market_brief")
        self.assertEqual(route.pattern, "/api/daily-market-brief")

    def test_dynamic_candidate_routes_match_only_the_admitted_shape(self) -> None:
        from investment_knowledge_mcp.app_gateway import resolve_route

        route = resolve_route("POST", "/api/candidate-insights/17/confirm")

        self.assertIsNotNone(route)
        self.assertEqual(route.owner, "weekly_review")
        self.assertIsNone(resolve_route("POST", "/api/candidate-insights/nope/confirm"))
        self.assertIsNone(resolve_route("POST", "/api/candidate-insights/17/delete"))


class _FakeHandler:
    def __init__(self, path: str, *, payload: dict[str, object] | None = None) -> None:
        self.path = path
        self.command = "POST" if path.startswith("/api/") and payload is not None else "GET"
        self.headers: dict[str, str] = {}
        self.payload = payload if payload is not None else {}
        self.calls: list[tuple[object, ...]] = []

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.calls.append(("json", status, payload))

    def _write_html(self, status: HTTPStatus, content: str) -> None:
        self.calls.append(("html", status, content))

    def _read_json_body(self) -> dict[str, object] | None:
        self.calls.append(("read",))
        return self.payload

    def _render_weekly_review_page(self) -> str:
        return "weekly-page"

    def _render_daily_market_brief_page(self) -> str:
        return "daily-page"

    def _handle_weekly_review_read(self, query: dict[str, object]) -> None:
        self.calls.append(("weekly_read", query))

    def _handle_daily_market_brief_read(self, query: dict[str, object]) -> None:
        self.calls.append(("daily_read", query))

    def _handle_candidate_insights(self, query: dict[str, object]) -> None:
        self.calls.append(("candidates", query))

    def _handle_workbench_parse(self, payload: dict[str, object]) -> None:
        self.calls.append(("command_parse", payload))


class AppGatewayDispatchTests(unittest.TestCase):
    def test_mixed_access_post_is_decided_by_shared_policy_before_body_read(self) -> None:
        from investment_knowledge_mcp import app_gateway
        from investment_knowledge_mcp.web_access import AccessClass

        route = app_gateway.RouteContract(
            "POST",
            "/synthetic-mixed",
            "command",
            AccessClass.PUBLIC_READ_PROTECTED_WRITE,
        )
        handler = _FakeHandler("/synthetic-mixed", payload={"text": "must-not-read"})
        handler.command = "POST"
        with (
            mock.patch.object(app_gateway, "_ROUTES", (route,)),
            mock.patch.object(app_gateway, "authorize_http", return_value=False) as authorize,
        ):
            app_gateway.dispatch_post(handler)

        authorize.assert_called_once_with(handler, AccessClass.PUBLIC_READ_PROTECTED_WRITE)
        self.assertEqual([], handler.calls)

    def test_representative_weekly_and_daily_routes_delegate_without_moving_business_logic(self) -> None:
        from investment_knowledge_mcp.app_gateway import dispatch_get

        weekly = _FakeHandler("/api/weekly-review?week_start=2026-07-13")
        daily = _FakeHandler("/api/daily-market-brief?market=HK")

        dispatch_get(weekly)
        dispatch_get(daily)

        self.assertEqual(weekly.calls, [("weekly_read", {"week_start": ["2026-07-13"]})])
        self.assertEqual(daily.calls, [("daily_read", {"market": ["HK"]})])

    def test_page_routes_render_through_handler_owned_methods(self) -> None:
        from investment_knowledge_mcp.app_gateway import dispatch_get

        weekly = _FakeHandler("/weekly-review")
        daily = _FakeHandler("/daily-market-brief")

        dispatch_get(weekly)
        dispatch_get(daily)

        self.assertEqual([("html", HTTPStatus.OK, "weekly-page")], weekly.calls)
        self.assertEqual([("html", HTTPStatus.OK, "daily-page")], daily.calls)

    def test_health_and_unknown_payloads_are_unchanged(self) -> None:
        from investment_knowledge_mcp.app_gateway import dispatch_get

        health = _FakeHandler("/health")
        missing = _FakeHandler("/missing")
        with mock.patch.dict("os.environ", {"APP_RELEASE_SHA": "abc123"}, clear=False):
            dispatch_get(health)
        dispatch_get(missing)

        self.assertEqual(
            health.calls,
            [
                (
                    "json",
                    HTTPStatus.OK,
                    {"ok": True, "app_release_sha": "abc123", "daily_market_brief_route": True},
                )
            ],
        )
        self.assertEqual(
            missing.calls,
            [("json", HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})],
        )

    def test_protected_command_post_uses_existing_auth_and_handler_method(self) -> None:
        from investment_knowledge_mcp.app_gateway import dispatch_post

        handler = _FakeHandler("/api/command-workbench/parse", payload={"text": "本周复盘"})
        with mock.patch("investment_knowledge_mcp.app_gateway.authorize_http", return_value=True) as authorize:
            dispatch_post(handler)

        authorize.assert_called_once()
        self.assertEqual(handler.calls, [("read",), ("command_parse", {"text": "本周复盘"})])

    def test_protected_weekly_route_authorizes_exactly_once_at_gateway(self) -> None:
        from investment_knowledge_mcp.app_gateway import dispatch_get

        handler = _FakeHandler("/api/candidate-insights?status=pending")
        with mock.patch("investment_knowledge_mcp.app_gateway.authorize_http", return_value=True) as authorize:
            dispatch_get(handler)

        authorize.assert_called_once()
        self.assertEqual(handler.calls, [("candidates", {"status": ["pending"]})])

    def test_direct_command_post_uses_existing_controller_with_legacy_request_metadata(self) -> None:
        from investment_knowledge_mcp import app_gateway
        from investment_knowledge_mcp.command_http import CommandHttpResponse

        handler = _FakeHandler(
            "/command",
            payload={"text": "system status", "source": "legacy-client", "sender": "operator"},
        )
        response = CommandHttpResponse(HTTPStatus.OK, {"ok": True, "message": "done", "event_id": 7})
        with (
            mock.patch.object(app_gateway, "authorize_http", return_value=True),
            mock.patch.object(app_gateway, "read_command_json_body", return_value=handler.payload) as read,
            mock.patch.object(app_gateway, "execute_command_request", return_value=response) as execute,
        ):
            app_gateway.dispatch_post(handler)

        read.assert_called_once_with(handler)
        request = execute.call_args.args[0]
        self.assertEqual(handler.payload, request.body)
        self.assertEqual("legacy-client", request.source)
        self.assertEqual("operator", request.sender)
        self.assertEqual(
            handler.calls,
            [("json", HTTPStatus.OK, {"ok": True, "message": "done", "event_id": 7})],
        )

    def test_direct_command_post_body_errors_match_legacy_command_handler(self) -> None:
        from investment_knowledge_mcp import app_gateway, command_api
        from investment_knowledge_mcp.weekly_review_web import WeeklyReviewWebHandler

        cases = (
            (
                b"",
                None,
                mock.call(
                    HTTPStatus.LENGTH_REQUIRED,
                    {"ok": False, "error": "Content-Length is required"},
                ),
            ),
            (
                b"",
                "invalid",
                mock.call(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "invalid Content-Length"},
                ),
            ),
            (
                b"{}",
                str(64 * 1024 + 1),
                mock.call(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"ok": False, "error": "request too large"},
                ),
            ),
            (
                b"{",
                "1",
                mock.call(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "invalid JSON body"},
                ),
            ),
            (
                b"[]",
                "2",
                mock.call(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "JSON body must be an object"},
                ),
            ),
        )
        for body, content_length, expected in cases:
            with self.subTest(body=body, content_length=content_length):
                results = []
                for handler_type, auth_target in (
                    (command_api.CommandRequestHandler, command_api),
                    (WeeklyReviewWebHandler, app_gateway),
                ):
                    handler = object.__new__(handler_type)
                    handler.path = "/command"
                    handler.command = "POST"
                    handler.headers = (
                        {} if content_length is None else {"Content-Length": content_length}
                    )
                    handler.rfile = BytesIO(body)
                    handler._write_json = mock.Mock()
                    with mock.patch.object(auth_target, "authorize_http", return_value=True):
                        handler.do_POST()
                    results.append(handler._write_json.call_args_list)

                self.assertEqual(results[0], results[1])
                self.assertEqual([expected], results[0])

    def test_gateway_exports_dispatch_only_and_production_handler_owns_http_methods(self) -> None:
        from investment_knowledge_mcp import app_gateway
        from investment_knowledge_mcp.weekly_review_web import WeeklyReviewWebHandler

        self.assertFalse(hasattr(app_gateway, "AppGatewayHandler"))
        self.assertIn("dispatch_get", WeeklyReviewWebHandler.do_GET.__code__.co_names)
        self.assertIn("dispatch_post", WeeklyReviewWebHandler.do_POST.__code__.co_names)

    def test_production_handler_render_methods_delegate_existing_renderers(self) -> None:
        from investment_knowledge_mcp import weekly_review_web as web

        handler = object.__new__(web.WeeklyReviewWebHandler)
        with (
            mock.patch.object(web, "render_weekly_review_workbench_html", return_value="weekly") as weekly,
            mock.patch.object(web, "render_daily_market_brief_html", return_value="daily") as daily,
        ):
            self.assertEqual("weekly", handler._render_weekly_review_page())
            self.assertEqual("daily", handler._render_daily_market_brief_page())

        weekly.assert_called_once_with()
        daily.assert_called_once_with()

    def test_main_starts_the_gateway_handler(self) -> None:
        from investment_knowledge_mcp import weekly_review_web as web

        config = SimpleNamespace(weekly_review_web_host="127.0.0.1", weekly_review_web_port=8769)
        server = mock.Mock()
        with (
            mock.patch.object(web, "get_config", return_value=config),
            mock.patch.object(web, "ThreadingHTTPServer", return_value=server) as server_type,
        ):
            web.main()

        server_type.assert_called_once_with(("127.0.0.1", 8769), web.WeeklyReviewWebHandler)
        server.serve_forever.assert_called_once_with()

    def test_route_state_repr_contains_no_configured_token(self) -> None:
        from investment_knowledge_mcp.app_gateway import route_contracts

        sentinel = "do-not-store-this-token"
        with mock.patch.dict("os.environ", {"APP_ACCESS_TOKEN": sentinel}, clear=False):
            state = repr(route_contracts())

        self.assertNotIn(sentinel, state)


if __name__ == "__main__":
    unittest.main()
