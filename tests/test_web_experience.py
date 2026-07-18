import json
import re
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


def _run_command_script(assertions: str, *, storage_denied: bool = False) -> None:
    from investment_knowledge_mcp.command_workbench import render_command_workbench_html

    node = shutil.which("node")
    if node is None:
        raise AssertionError("Node.js is required to verify Command Workbench browser behavior")

    scripts = re.findall(r"<script>(.*?)</script>", render_command_workbench_html(), re.DOTALL)
    if len(scripts) != 2:
        raise AssertionError("Command Workbench must render the shared access script and one page script")

    harness = r"""
const assert = require("node:assert/strict");

class LocalStorageStub {
  constructor() { this.values = new Map(); }
  getItem(key) {
    if (__STORAGE_DENIED__) throw new DOMException("denied", "SecurityError");
    return this.values.has(key) ? this.values.get(key) : null;
  }
  setItem(key, value) {
    if (__STORAGE_DENIED__) throw new DOMException("denied", "SecurityError");
    this.values.set(key, String(value));
  }
  removeItem(key) {
    if (__STORAGE_DENIED__) throw new DOMException("denied", "SecurityError");
    this.values.delete(key);
  }
}

const makeNode = () => ({
  value: "",
  hidden: false,
  disabled: false,
  innerHTML: "",
  textContent: "",
  listeners: {},
  addEventListener(type, callback) { this.listeners[type] = callback; },
  focus() {},
});

const selectors = [
  "#smart-input", "#parse", "#access-panel", "#access-message", "#access-token",
  "#access-continue", "#access-forget", "#access-credential-fields", "#request-retry",
  "#preview", "#catalog", "#pinned", "#recent", "#form-section", "#form-title",
  "#form", "#result",
];
const nodes = new Map(selectors.map((selector) => [selector, makeNode()]));
nodes.get("#access-panel").hidden = true;
nodes.get("#access-credential-fields").hidden = true;
nodes.get("#request-retry").hidden = true;

const localStorage = new LocalStorageStub();
global.window = {localStorage};
global.localStorage = localStorage;
global.document = {
  querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, makeNode());
    return nodes.get(selector);
  },
};

const response = (status, payload) => ({
  status,
  ok: status >= 200 && status < 300,
  async json() { return payload; },
});
let fetchHandler = async () => response(200, {ok: true, actions: []});
global.fetch = (...args) => fetchHandler(...args);

const accessSource = __ACCESS_SOURCE__;
const commandSource = __COMMAND_SOURCE__;
eval(accessSource);
eval(commandSource + "\nglobalThis.workbench = {state, parseSmartInput, runPreview, continueWithAccess};");

const flush = () => new Promise((resolve) => setImmediate(resolve));

(async () => {
  await flush();
  await flush();
  __ASSERTIONS__
  process.stdout.write(JSON.stringify({ok: true}));
})().catch((error) => {
  process.stderr.write(String(error && error.stack ? error.stack : error));
  process.exitCode = 1;
});
"""
    harness = (
        harness.replace("__ACCESS_SOURCE__", json.dumps(scripts[0]))
        .replace("__COMMAND_SOURCE__", json.dumps(scripts[1]))
        .replace("__STORAGE_DENIED__", json.dumps(storage_denied))
        .replace("__ASSERTIONS__", assertions)
    )
    completed = subprocess.run(
        [node, "-e", harness],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Command Workbench behavior check failed with status {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    if json.loads(completed.stdout) != {"ok": True}:
        raise AssertionError("Command Workbench behavior check returned an invalid status result")


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

    def test_access_script_degrades_safely_when_browser_storage_is_denied(self) -> None:
        _run_access_script(
            """
const deniedStorage = {
  getItem() { throw new DOMException("denied", "SecurityError"); },
  setItem() { throw new DOMException("denied", "SecurityError"); },
  removeItem() { throw new DOMException("denied", "SecurityError"); },
};
global.window = {localStorage: deniedStorage};
eval(accessSource);
const access = window.InvestmentKnowledgeAccess;
assert.deepEqual(access.resolve(), {status: "missing"});
assert.deepEqual(access.remember("synthetic-memory-only"), {status: "ready"});
assert.deepEqual(access.resolve(), {status: "ready"});
assert.equal(Object.prototype.hasOwnProperty.call(access.authorizationHeaders(), "Authorization"), true);
assert.deepEqual(access.forget(), {status: "missing"});
assert.equal(Object.keys(access.authorizationHeaders()).length, 0);
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
        self.assertIn(".experience-skip-link", css)
        self.assertIn(".table-scroll", css)

    def test_command_uses_shared_shell_and_canonical_access(self) -> None:
        from investment_knowledge_mcp.command_workbench import render_command_workbench_html

        html = render_command_workbench_html()
        self.assertIn('href="/command" aria-current="page"', html)
        self.assertIn("investment_knowledge_access_token", html)
        self.assertNotIn('id="api-token"', html)
        self.assertIn('id="access-panel"', html)
        self.assertIn('role="alert"', html)
        self.assertIn('<a class="experience-skip-link" href="#main-content">', html)
        self.assertIn('<header class="page-header">', html)
        self.assertIn('<main id="main-content"', html)
        self.assertEqual(1, html.count("<main"))
        self.assertEqual(1, html.count("<h1"))

    def test_command_installs_handlers_when_browser_storage_is_denied(self) -> None:
        _run_command_script(
            r"""
assert.equal(typeof nodes.get("#parse").listeners.click, "function");
assert.equal(typeof nodes.get("#access-continue").listeners.click, "function");
nodes.get("#smart-input").value = "系统状态";
await workbench.parseSmartInput();
assert.equal(nodes.get("#access-panel").hidden, true);
""",
            storage_denied=True,
        )

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

    def test_command_parse_retry_reuses_immutable_endpoint_and_serialized_payload(self) -> None:
        _run_command_script(
            r"""
const requests = [];
fetchHandler = async (url, options) => {
  requests.push({url, body: options.body});
  if (requests.length === 1) {
    return response(401, {error: "access_required", message: "Private access is required."});
  }
  return response(200, {ok: true, preview: {status: "parsed", raw_input: "original command"}});
};

nodes.get("#smart-input").value = "original command";
await workbench.parseSmartInput();
nodes.get("#smart-input").value = "edited after failure";
nodes.get("#access-token").value = "synthetic-current";
workbench.continueWithAccess();
await flush();
await flush();

assert.equal(requests.length, 2);
assert.equal(requests[0].url, "/api/command-workbench/parse");
assert.equal(requests[1].url, requests[0].url);
assert.equal(requests[1].body, requests[0].body);
assert.equal(JSON.parse(requests[1].body).text, "original command");
"""
        )

    def test_command_execute_retry_survives_preview_clear_with_same_serialized_payload(self) -> None:
        _run_command_script(
            r"""
const requests = [];
fetchHandler = async (url, options) => {
  requests.push({url, body: options.body});
  if (requests.length === 1) {
    return response(401, {error: "access_required", message: "Private access is required."});
  }
  return response(200, {ok: true, message: "completed", executed_command: "系统状态"});
};

workbench.state.preview = {
  raw_input: "系统状态",
  action_id: "system_status",
  fields: {},
  target: null,
};
nodes.get("#smart-input").value = "系统状态";
await workbench.runPreview();
nodes.get("#smart-input").value = "edited after failure";
nodes.get("#smart-input").listeners.input({});
assert.equal(workbench.state.preview, null);
nodes.get("#access-token").value = "synthetic-current";
workbench.continueWithAccess();
await flush();
await flush();

assert.equal(requests.length, 2);
assert.equal(requests[0].url, "/api/command-workbench/execute");
assert.equal(requests[1].url, requests[0].url);
assert.equal(requests[1].body, requests[0].body);
assert.equal(JSON.parse(requests[1].body).text, "系统状态");
"""
        )

    def test_command_recovery_modes_keep_access_and_request_actions_distinct(self) -> None:
        _run_command_script(
            r"""
const cases = [
  [401, "access_required", false, true, true, "copy:access_required"],
  [401, "access_rejected", false, true, true, "copy:access_rejected"],
  [503, "access_not_configured", true, true, false, "copy:access_not_configured"],
  [500, "request_failed", true, false, true, "The request failed. Try again."],
];
for (const [status, error, credentialsHidden, retryHidden, hasPending, expectedMessage] of cases) {
  fetchHandler = async () => response(status, {error, message: `copy:${error}`});
  nodes.get("#smart-input").value = `command:${error}`;
  await workbench.parseSmartInput();
  assert.equal(nodes.get("#access-panel").hidden, false);
  assert.equal(nodes.get("#access-message").textContent, expectedMessage);
  assert.equal(nodes.get("#access-credential-fields").hidden, credentialsHidden);
  assert.equal(nodes.get("#request-retry").hidden, retryHidden);
  assert.equal(workbench.state.pendingRequest !== null, hasPending);
}

nodes.get("#access-token").value = "synthetic-must-not-be-stored";
fetchHandler = async () => response(200, {ok: true, preview: {status: "parsed"}});
nodes.get("#request-retry").listeners.click();
await flush();
await flush();
assert.equal(localStorage.values.has("investment_knowledge_access_token"), false);
"""
        )

    def test_command_409_preview_blocker_flows_through_execution_result_handler(self) -> None:
        _run_command_script(
            r"""
const blockerPreview = {
  status: "parsed",
  raw_input: "本周复盘",
  action_id: "weekly_current",
  fields: {},
  target: null,
  supports_execution: true,
  confirmation_required: true,
};
let requestCount = 0;
fetchHandler = async () => {
  requestCount += 1;
  return response(409, {
    ok: false,
    error: "Confirmation is required before running this command.",
    preview: blockerPreview,
  });
};
workbench.state.preview = {
  ...blockerPreview,
  confirmation_required: false,
};

await workbench.runPreview();

assert.equal(requestCount, 1);
assert.deepEqual(workbench.state.preview, blockerPreview);
assert.match(nodes.get("#result").innerHTML, /Confirmation is required/);
assert.equal(nodes.get("#access-panel").hidden, true);
assert.equal(nodes.get("#request-retry").hidden, true);
assert.equal(workbench.state.pendingRequest, null);
"""
        )

    def test_command_400_preview_result_is_completed_without_duplicate_retry(self) -> None:
        _run_command_script(
            r"""
const failedPreview = {
  status: "parsed",
  raw_input: "系统状态",
  action_id: "system_status",
  fields: {},
  target: null,
  supports_execution: true,
  confirmation_required: false,
};
let requestCount = 0;
fetchHandler = async () => {
  requestCount += 1;
  return response(400, {
    ok: false,
    message: "The command completed with a business failure.",
    preview: failedPreview,
    executed_command: "系统状态",
    raw_input: "系统状态",
    event_id: 41,
  });
};
workbench.state.preview = failedPreview;

await workbench.runPreview();

assert.equal(requestCount, 1);
assert.deepEqual(workbench.state.preview, failedPreview);
assert.match(nodes.get("#result").innerHTML, /completed with a business failure/);
const recent = JSON.parse(localStorage.getItem("command_workbench_recent"));
assert.equal(recent.length, 1);
assert.equal(recent[0].exact_command, "系统状态");
assert.equal(recent[0].ok, false);
assert.equal(nodes.get("#access-panel").hidden, true);
assert.equal(nodes.get("#request-retry").hidden, true);
assert.equal(workbench.state.pendingRequest, null);
"""
        )

    def test_command_accessibility_and_recovery_markup_is_explicit(self) -> None:
        from investment_knowledge_mcp.command_workbench import render_command_workbench_html

        html = render_command_workbench_html()
        self.assertIn('<label for="smart-input"', html)
        self.assertIn('id="result" role="status" aria-live="polite"', html)
        self.assertIn('id="access-credential-fields"', html)
        self.assertIn('id="request-retry"', html)
        self.assertIn("access_required", html)
        self.assertIn("access_rejected", html)
        self.assertIn("access_not_configured", html)
        self.assertIn("request_failed", html)
        self.assertRegex(html, r"input, select, button, textarea\s*\{[^}]*min-height:\s*44px")

    def test_command_candidate_groups_use_dividers_without_nested_cards(self) -> None:
        from investment_knowledge_mcp.command_workbench import render_command_workbench_html

        html = render_command_workbench_html()
        candidate_css = html.split(".candidate {", 1)[1].split("}", 1)[0]
        self.assertNotIn("border:", candidate_css)
        self.assertNotIn("border-radius", candidate_css)
        self.assertNotIn("background:", candidate_css)
        self.assertIn("border-top", candidate_css)
