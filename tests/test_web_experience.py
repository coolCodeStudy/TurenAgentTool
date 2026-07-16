import json
import shutil
import subprocess
from http import HTTPStatus
from types import SimpleNamespace
import unittest
from unittest import mock

from investment_knowledge_mcp.web_experience import (
    CANONICAL_ACCESS_KEY,
    access_error_payload,
    render_access_session_script,
    render_experience_css,
    render_primary_navigation,
)


def _run_access_script(assertions: str) -> None:
    node = shutil.which("node")
    if node is None:
        raise AssertionError("Node.js is required to verify the browser access helper")

    source = render_access_session_script().removeprefix("<script>").removesuffix("</script>")
    harness = f"""
const assert = require("node:assert/strict");

class LocalStorageStub {{
  constructor(entries = []) {{
    this.values = new Map(entries);
  }}

  getItem(key) {{
    return this.values.has(key) ? this.values.get(key) : null;
  }}

  setItem(key, value) {{
    this.values.set(key, String(value));
  }}

  removeItem(key) {{
    this.values.delete(key);
  }}
}}

const accessSource = {json.dumps(source)};
const installAccess = (entries = []) => {{
  global.window = {{localStorage: new LocalStorageStub(entries)}};
  eval(accessSource);
  return window.InvestmentKnowledgeAccess;
}};

{assertions}
process.stdout.write(JSON.stringify({{ok: true}}));
"""
    completed = subprocess.run(
        [node, "-e", harness],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Browser access behavior check failed with status {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    if json.loads(completed.stdout) != {"ok": True}:
        raise AssertionError("Browser access behavior check returned an invalid status result")


class WebExperienceTests(unittest.TestCase):
    def test_primary_navigation_has_stable_order_and_active_state(self) -> None:
        html = render_primary_navigation("weekly_review")
        self.assertLess(html.index("/daily-market-brief"), html.index("/weekly-review"))
        self.assertLess(html.index("/weekly-review"), html.index("/command"))
        self.assertIn('href="/weekly-review" aria-current="page"', html)

    def test_access_script_uses_canonical_and_both_legacy_keys(self) -> None:
        script = render_access_session_script()
        self.assertEqual("investment_knowledge_access_token", CANONICAL_ACCESS_KEY)
        self.assertIn("command_workbench_token", script)
        self.assertIn("weekly_review_web_token", script)
        self.assertIn("legacy_conflict", script)
        self.assertNotIn("console.log", script)

    def test_access_script_prefers_canonical_and_exposes_exact_status_only_api(self) -> None:
        _run_access_script(
            """
const access = installAccess([
  ["investment_knowledge_access_token", "synthetic-canonical"],
  ["command_workbench_token", "synthetic-legacy-a"],
  ["weekly_review_web_token", "synthetic-legacy-b"],
]);
const resolution = access.resolve();
assert.deepEqual(resolution, {status: "ready"});
assert.deepEqual(Object.keys(resolution), ["status"]);
assert.deepEqual(Object.keys(access), [
  "resolve",
  "getToken",
  "remember",
  "forget",
  "authorizationHeaders",
  "classifyResponse",
]);
assert.equal(
  access.getToken() === window.localStorage.getItem("investment_knowledge_access_token"),
  true,
);
assert.equal(
  access.getToken() !== window.localStorage.getItem("command_workbench_token"),
  true,
);
"""
        )

    def test_access_script_migrates_one_legacy_value(self) -> None:
        _run_access_script(
            """
const access = installAccess([["command_workbench_token", "synthetic-one"]]);
assert.deepEqual(access.resolve(), {status: "ready"});
assert.equal(window.localStorage.values.has("investment_knowledge_access_token"), true);
assert.equal(window.localStorage.values.has("command_workbench_token"), false);
assert.equal(window.localStorage.values.has("weekly_review_web_token"), false);
assert.equal(access.getToken() === "synthetic-one", true);
"""
        )

    def test_access_script_migrates_matching_legacy_values(self) -> None:
        _run_access_script(
            """
const access = installAccess([
  ["command_workbench_token", "synthetic-match"],
  ["weekly_review_web_token", "synthetic-match"],
]);
assert.deepEqual(access.resolve(), {status: "ready"});
assert.equal(window.localStorage.values.has("investment_knowledge_access_token"), true);
assert.equal(window.localStorage.values.has("command_workbench_token"), false);
assert.equal(window.localStorage.values.has("weekly_review_web_token"), false);
assert.equal(access.getToken() === "synthetic-match", true);
"""
        )

    def test_access_script_preserves_conflicting_legacy_values_without_guessing(self) -> None:
        _run_access_script(
            """
const access = installAccess([
  ["command_workbench_token", "synthetic-first"],
  ["weekly_review_web_token", "synthetic-second"],
]);
assert.deepEqual(access.resolve(), {status: "legacy_conflict"});
assert.equal(window.localStorage.values.has("investment_knowledge_access_token"), false);
assert.equal(window.localStorage.values.has("command_workbench_token"), true);
assert.equal(window.localStorage.values.has("weekly_review_web_token"), true);
assert.equal(access.getToken().length === 0, true);
"""
        )

    def test_access_script_remembers_forgets_and_builds_private_headers(self) -> None:
        _run_access_script(
            """
const access = installAccess();
assert.deepEqual(access.resolve(), {status: "missing"});
assert.deepEqual(access.remember("synthetic-current"), {status: "ready"});
assert.equal(window.localStorage.values.has("investment_knowledge_access_token"), true);
const headers = access.authorizationHeaders();
assert.equal(Object.keys(headers).length === 1, true);
assert.equal(Object.prototype.hasOwnProperty.call(headers, "Authorization"), true);
assert.equal(typeof headers.Authorization === "string", true);
assert.deepEqual(access.forget(), {status: "missing"});
assert.equal(window.localStorage.values.size === 0, true);
assert.equal(Object.keys(access.authorizationHeaders()).length === 0, true);
"""
        )

    def test_access_script_classifies_recoverable_responses(self) -> None:
        _run_access_script(
            """
const access = installAccess();
assert.deepEqual(
  access.classifyResponse(401, {error: "access_required"}),
  {status: "access_required"},
);
assert.deepEqual(
  access.classifyResponse(401, {error: "access_rejected"}),
  {status: "access_rejected"},
);
assert.deepEqual(
  access.classifyResponse(503, {error: "access_not_configured"}),
  {status: "access_not_configured"},
);
assert.deepEqual(access.classifyResponse(403, {}), {status: "access_rejected"});
assert.deepEqual(access.classifyResponse(500, {}), {status: "request_failed"});
assert.deepEqual(access.classifyResponse(200, {}), {status: "ready"});
"""
        )

    def test_access_errors_are_distinct_and_recoverable(self) -> None:
        required = access_error_payload("access_required")
        rejected = access_error_payload("access_rejected")
        unavailable = access_error_payload("access_not_configured")
        self.assertNotEqual(required["error"], rejected["error"])
        self.assertNotEqual(rejected["error"], unavailable["error"])
        self.assertTrue(required["recovery"]["next_action"])

    def test_access_error_messages_use_english_source_copy(self) -> None:
        expected_messages = {
            "access_required": "Private access is required for this operation.",
            "access_rejected": "The saved access credential was rejected. Enter the current credential and try again.",
            "access_not_configured": "Private access is temporarily unavailable because the service is not configured.",
            "request_failed": "The request failed. Try again.",
        }
        for code, expected_message in expected_messages.items():
            with self.subTest(code=code):
                self.assertEqual(expected_message, access_error_payload(code)["message"])

    def test_css_contains_shared_focus_and_compact_contracts(self) -> None:
        css = render_experience_css()
        self.assertIn(":focus-visible", css)
        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn("--experience-accent", css)

    def test_command_uses_shared_shell_and_canonical_access(self) -> None:
        from investment_knowledge_mcp.command_workbench import render_command_workbench_html

        html = render_command_workbench_html()
        self.assertIn('href="/command" aria-current="page"', html)
        self.assertIn("investment_knowledge_access_token", html)
        self.assertNotIn('id="api-token"', html)
        self.assertIn('id="access-panel"', html)
        self.assertIn('role="alert"', html)

    def test_command_api_authorization_reports_distinct_access_errors(self) -> None:
        from investment_knowledge_mcp import command_api

        cases = (
            ({}, "configured-token", HTTPStatus.UNAUTHORIZED, "access_required"),
            ({"Authorization": "Bearer synthetic-invalid"}, "configured-token", HTTPStatus.UNAUTHORIZED, "access_rejected"),
            ({}, None, HTTPStatus.SERVICE_UNAVAILABLE, "access_not_configured"),
        )
        for headers, configured_token, expected_status, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                handler = object.__new__(command_api.CommandRequestHandler)
                handler.headers = headers
                handler._write_json = mock.Mock()
                config = SimpleNamespace(command_api_token=configured_token)
                with mock.patch.object(command_api, "get_config", return_value=config):
                    self.assertFalse(handler._require_authorized())

                status, payload = handler._write_json.call_args.args
                self.assertEqual(expected_status, status)
                self.assertEqual(expected_error, payload["error"])

    def test_weekly_command_authorization_reports_distinct_access_errors(self) -> None:
        from investment_knowledge_mcp import weekly_review_web

        cases = (
            ({}, "configured-token", HTTPStatus.UNAUTHORIZED, "access_required"),
            ({"Authorization": "Bearer synthetic-invalid"}, "configured-token", HTTPStatus.UNAUTHORIZED, "access_rejected"),
            ({}, None, HTTPStatus.SERVICE_UNAVAILABLE, "access_not_configured"),
        )
        for headers, configured_token, expected_status, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                handler = object.__new__(weekly_review_web.WeeklyReviewWebHandler)
                handler.headers = headers
                handler._write_json = mock.Mock()
                config = SimpleNamespace(
                    command_api_token=configured_token,
                    weekly_review_web_token=None,
                )
                with mock.patch.object(weekly_review_web, "get_config", return_value=config):
                    self.assertFalse(handler._authorized_for_command_workbench())

                status, payload = handler._write_json.call_args.args
                self.assertEqual(expected_status, status)
                self.assertEqual(expected_error, payload["error"])
