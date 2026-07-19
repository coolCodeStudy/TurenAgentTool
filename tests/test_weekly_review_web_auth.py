from __future__ import annotations

from contextlib import ExitStack
from http import HTTPStatus
import http.client
import json
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from investment_knowledge_mcp import http_access
from investment_knowledge_mcp import weekly_review_web as web


WEEK_START = "2026-06-22"


class WeeklyReviewWebAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._patches = ExitStack()
        self._patches.enter_context(
            mock.patch.object(
                http_access,
                "get_config",
                return_value=SimpleNamespace(
                    app_access_token="configured-access-token",
                    weekly_review_web_token="configured-access-token",
                    command_api_token="configured-access-token",
                ),
            )
        )
        self._patches.enter_context(mock.patch.object(web, "run_schema"))
        self._patches.enter_context(
            mock.patch.object(
                web.repository,
                "get_review_report",
                return_value={
                    "id": 42,
                    "report_type": "weekly",
                    "summary": "# 本周复盘 2026-06-22 ~ 2026-06-28",
                    "portfolio_snapshot": {
                        "holder_attribution": [
                            {
                                "code": "HK.02476",
                                "name": "胜宏科技",
                                "weekly_pl": -6920.0,
                                "attribution_verdict": "mixed",
                                "cause_candidates": [],
                            }
                        ]
                    },
                },
            )
        )
        self._patches.enter_context(mock.patch.object(web, "get_daily_market_brief_report", return_value=None))
        self._patches.enter_context(mock.patch.object(web.repository, "list_candidate_insights", return_value=[]))
        self.server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.WeeklyReviewWebHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        self._patches.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=2)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = dict(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_weekly_review_read_is_public_even_when_write_tokens_are_configured(self) -> None:
        status, headers, body = self.request(
            "GET",
            f"/api/weekly-review?week_start={WEEK_START}",
        )

        payload = json.loads(body)
        self.assertEqual(HTTPStatus.OK, status)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertTrue(payload["ok"])
        self.assertEqual("existing", payload["status"])
        self.assertEqual("HK.02476", payload["context"]["holder_attribution"][0]["code"])

    def test_weekly_review_privileged_apis_reject_tokenless_requests(self) -> None:
        requests = (
            ("POST", "/api/weekly-review/generate", {"week_start": WEEK_START}, "access_required"),
            ("POST", "/api/weekly-review/refresh", {"week_start": WEEK_START, "force": True}, "access_required"),
            ("POST", "/api/weekly-review/save", {"week_start": WEEK_START, "markdown": "report"}, "access_required"),
            ("GET", "/api/candidate-insights?status=pending", None, "access_required"),
            ("POST", "/api/candidate-insights/1/confirm", None, "access_required"),
            ("POST", "/api/candidate-insights/1/reject", None, "access_required"),
            ("POST", "/api/command-workbench/parse", {"text": "本周复盘"}, "access_required"),
            ("POST", "/api/command-workbench/execute", {"text": "本周复盘"}, "access_required"),
        )

        for method, path, payload, expected_error in requests:
            with self.subTest(method=method, path=path):
                status, _, body = self.request(method, path, payload=payload)
                self.assertEqual(HTTPStatus.UNAUTHORIZED, status)
                response = json.loads(body)
                self.assertEqual(expected_error, response["error"])
                self.assertTrue(response["recovery"]["next_action"])

    def test_weekly_review_privileged_matrix_distinguishes_invalid_and_unconfigured_access(self) -> None:
        requests = (
            ("POST", "/api/weekly-review/generate", {"week_start": WEEK_START}),
            ("POST", "/api/weekly-review/refresh", {"week_start": WEEK_START, "force": True}),
            ("POST", "/api/weekly-review/save", {"week_start": WEEK_START, "markdown": "report"}),
            ("GET", "/api/candidate-insights?status=pending", None),
            ("POST", "/api/candidate-insights/1/confirm", None),
            ("POST", "/api/candidate-insights/1/reject", None),
            ("POST", "/api/command-workbench/execute", {"text": "本周复盘"}),
        )
        cases = (
            (
                SimpleNamespace(
                    app_access_token="configured-access-token",
                    weekly_review_web_token="configured-access-token",
                    command_api_token="configured-access-token",
                ),
                {"Authorization": "Bearer synthetic-invalid"},
                HTTPStatus.UNAUTHORIZED,
                "access_rejected",
            ),
            (
                SimpleNamespace(
                    app_access_token=None,
                    weekly_review_web_token=None,
                    command_api_token=None,
                ),
                {},
                HTTPStatus.SERVICE_UNAVAILABLE,
                "access_not_configured",
            ),
        )
        for config, headers, expected_status, expected_error in cases:
            for method, path, payload in requests:
                with self.subTest(error=expected_error, method=method, path=path):
                    with mock.patch.object(http_access, "get_config", return_value=config):
                        status, _, body = self.request(method, path, payload=payload, headers=headers)
                    self.assertEqual(expected_status, status)
                    response = json.loads(body)
                    self.assertEqual(expected_error, response["error"])
                    self.assertTrue(response["recovery"]["next_action"])

    def test_valid_token_reaches_privileged_weekly_generate_handler(self) -> None:
        status, _, body = self.request(
            "POST",
            "/api/weekly-review/generate",
            payload={"week_start": WEEK_START},
            headers={"Authorization": "Bearer configured-access-token"},
        )

        payload = json.loads(body)
        self.assertEqual(HTTPStatus.OK, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("existing", payload["status"])

    def test_legacy_token_headers_reach_privileged_weekly_generate_handler(self) -> None:
        for headers in (
            {"X-Command-Token": "configured-access-token"},
            {"X-Weekly-Review-Token": "configured-access-token"},
        ):
            with self.subTest(headers=headers):
                status, _, body = self.request(
                    "POST",
                    "/api/weekly-review/generate",
                    payload={"week_start": WEEK_START},
                    headers=headers,
                )

                payload = json.loads(body)
                self.assertEqual(HTTPStatus.OK, status)
                self.assertTrue(payload["ok"])

    def test_valid_token_reaches_every_privileged_weekly_handler(self) -> None:
        def write_ok(handler: web.WeeklyReviewWebHandler, *args: object, **kwargs: object) -> None:
            handler._write_json(HTTPStatus.OK, {"ok": True})

        requests = (
            ("POST", "/api/weekly-review/generate", {"week_start": WEEK_START}),
            ("POST", "/api/weekly-review/refresh", {"week_start": WEEK_START, "force": True}),
            ("POST", "/api/weekly-review/save", {"week_start": WEEK_START, "markdown": "report"}),
            ("GET", "/api/candidate-insights?status=pending", None),
            ("POST", "/api/candidate-insights/1/confirm", None),
            ("POST", "/api/candidate-insights/1/reject", None),
            ("POST", "/api/command-workbench/execute", {"text": "本周复盘"}),
        )
        with (
            mock.patch.object(web.WeeklyReviewWebHandler, "_handle_weekly_review_generate", write_ok),
            mock.patch.object(web.WeeklyReviewWebHandler, "_handle_weekly_review_save", write_ok),
            mock.patch.object(web.WeeklyReviewWebHandler, "_handle_candidate_insights", write_ok),
            mock.patch.object(web.WeeklyReviewWebHandler, "_handle_candidate_decision", write_ok),
            mock.patch.object(web.WeeklyReviewWebHandler, "_handle_workbench_execute", write_ok),
        ):
            for method, path, payload in requests:
                with self.subTest(method=method, path=path):
                    status, _, body = self.request(
                        method,
                        path,
                        payload=payload,
                        headers={"Authorization": "Bearer configured-access-token"},
                    )
                    self.assertEqual(HTTPStatus.OK, status)
                    self.assertTrue(json.loads(body)["ok"])

    def test_public_weekly_review_page_keeps_reads_public_and_has_protected_recovery(self) -> None:
        status, headers, body = self.request("GET", "/weekly-review")

        html = body.decode("utf-8")
        self.assertEqual(HTTPStatus.OK, status)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn('data-slot="attribution"', html)
        self.assertIn('<script src="/assets/weekly-review.js"></script>', html)
        script = web.render_weekly_review_script()
        self.assertIn("/api/weekly-review", script)
        self.assertNotIn("api-token", html)
        self.assertIn('id="weekly-recovery"', html)
        self.assertIn('id="weekly-generate"', html)
        self.assertIn('id="weekly-access-panel"', html)
        self.assertNotIn("/api/candidate-insights", html)
        self.assertIn("loadGeneration: 0", script)
        self.assertIn("const controller = new AbortController();", script)
        self.assertIn("读取超时，请重试。", script)
        self.assertIn("function cancelReviewLoad()", script)
        self.assertIn('document.documentElement) document.documentElement.dataset.experienceReady = "true";', script)

    def test_public_weekly_page_uses_shared_shell_with_recovery_only_token_control(self) -> None:
        html = web.render_weekly_review_workbench_html()

        self.assertEqual(1, html.count('aria-label="主导航"'))
        self.assertIn('href="/weekly-review" aria-current="page"', html)
        self.assertIn('href="/daily-market-brief"', html)
        self.assertIn('href="/command"', html)
        daily_index = html.index('href="/daily-market-brief"')
        weekly_index = html.index('href="/weekly-review" aria-current="page"')
        command_index = html.index('href="/command"')
        self.assertLess(daily_index, weekly_index)
        self.assertLess(weekly_index, command_index)

        local_nav_marker = '<nav class="nav" aria-label="On this page">'
        self.assertIn(local_nav_marker, html)
        local_nav = html.split(local_nav_marker, 1)[1].split("</nav>", 1)[0]
        self.assertEqual(3, local_nav.count("<a "))
        self.assertEqual(3, local_nav.count('href="#'))
        self.assertNotIn('href="/', local_nav)
        self.assertIn('href="#holdings"', local_nav)
        self.assertIn('href="#markdown"', local_nav)
        self.assertIn('href="#source-status"', local_nav)

        self.assertNotIn('id="api-token"', html)
        self.assertIn('id="weekly-access-token"', html)
        self.assertNotIn("configured-access-token", html)
        self.assertIn("公开只读", html)
        self.assertIn('<a class="experience-skip-link" href="#main-content">', html)
        self.assertIn('<header class="page-header">', html)
        self.assertIn('<main id="main-content"', html)
        self.assertEqual(1, html.count("<main"))
        self.assertEqual(1, html.count("<h1"))
        self.assertIn('<label for="week-date">复盘周', html)
        self.assertIn('<label for="market-filter">市场筛选', html)
        self.assertIn('<label for="status-filter">持仓状态筛选', html)
        self.assertIn('id="message" class="notice" role="status"', html)
        self.assertIn('id="error-message" class="notice error" role="alert"', html)
        script = web.render_weekly_review_script()
        self.assertIn("message.hidden = false;", script)
        self.assertIn("message.hidden = true;", script)
        self.assertIn('role="region" aria-label="', script)
        self.assertIn('tabindex="0"', script)
        self.assertIn('class="table-scroll"', script)
        self.assertRegex(html, r"input, select, button\s*\{[^}]*min-height:\s*40px")
        compact_css = html.split("@media (max-width: 760px)", 1)[1].split("</style>", 1)[0]
        self.assertIn("input, select, button { min-height: 44px; }", compact_css)

    def test_public_weekly_script_asset_uses_access_only_for_generation(self) -> None:
        status, headers, body = self.request("GET", "/assets/weekly-review.js")

        script = body.decode("utf-8")
        self.assertEqual(HTTPStatus.OK, status)
        self.assertIn("application/javascript", headers["Content-Type"])
        self.assertIn('document.documentElement) document.documentElement.dataset.experienceReady = "true";', script)
        self.assertIn("/api/weekly-review", script)
        self.assertNotIn("api-token", script)
        self.assertIn("access.authorizationHeaders()", script)
        self.assertIn('fetch("/api/weekly-review/generate"', script)

    def test_daily_market_brief_read_remains_public_when_tokens_are_configured(self) -> None:
        status, _, body = self.request("GET", "/api/daily-market-brief?market=HK&date=2026-06-22")

        payload = json.loads(body)
        self.assertEqual(HTTPStatus.OK, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("missing", payload["status"])

    def test_public_daily_script_asset_remains_tokenless(self) -> None:
        from investment_knowledge_mcp import weekly_review_web as web

        html = web.render_daily_market_brief_html()
        script = web.render_daily_market_brief_script()

        self.assertIn('<script src="/assets/daily-market-brief.js"></script>', html)
        self.assertIn('document.documentElement) document.documentElement.dataset.experienceReady = "true";', script)
        self.assertIn("/api/daily-market-brief", script)
        self.assertNotIn("api-token", html)
        self.assertNotIn("api-token", script)

    def test_candidate_read_fails_closed_without_configured_tokens_while_weekly_read_stays_public(self) -> None:
        config = SimpleNamespace(
            app_access_token=None,
            weekly_review_web_token=None,
            command_api_token=None,
        )
        with mock.patch.object(http_access, "get_config", return_value=config):
            weekly_status, _, weekly_body = self.request(
                "GET",
                f"/api/weekly-review?week_start={WEEK_START}",
            )
            candidate_status, _, candidate_body = self.request(
                "GET",
                "/api/candidate-insights?status=pending",
            )

        self.assertEqual(HTTPStatus.OK, weekly_status)
        self.assertTrue(json.loads(weekly_body)["ok"])
        self.assertEqual(HTTPStatus.SERVICE_UNAVAILABLE, candidate_status)
        self.assertEqual("access_not_configured", json.loads(candidate_body)["error"])


class WeeklyReviewPublicReadContractTests(unittest.TestCase):
    def test_weekly_public_read_contract_stays_tokenless(self) -> None:
        script = web.render_weekly_review_script()
        public_read = script.split("function loadReview", 1)[1].split("function generateReview", 1)[0]
        self.assertNotIn("Authorization", public_read)


if __name__ == "__main__":
    unittest.main()
