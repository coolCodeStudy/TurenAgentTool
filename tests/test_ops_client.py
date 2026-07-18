from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import inspect
import json
import os
from pathlib import Path
import threading
import unittest
from unittest import mock
from urllib.error import HTTPError

from investment_knowledge_mcp import config as app_config
from investment_knowledge_mcp import ops_client, server


SHA = "a" * 40


def _terminal_deploy_data(
    *,
    mode: str = "targeted_quick",
    status: str = "completed",
    requested_services: list[str] | None = None,
    affected_services: list[str] | None = None,
) -> dict[str, object]:
    no_deploy = mode == "no_deploy"
    requested = requested_services if requested_services is not None else ["weekly-review-web"]
    affected = affected_services if affected_services is not None else ([] if no_deploy else list(requested))
    health_status = "not_applicable" if no_deploy else "healthy"
    window_seconds = 0 if no_deploy else 30
    return {
        "deploy_event_id": 42,
        "ref": SHA,
        "commit_sha": SHA,
        "mode": mode,
        "status": status,
        "status_url": "/ops/deploy-status?id=42",
        "evidence": {
            "status": "not_required" if no_deploy else "succeeded",
            "requested_services": requested,
            "affected_services": affected,
            "stable_health": {
                "status": health_status,
                "window_seconds": window_seconds,
                "observed_seconds": window_seconds,
                "final_health": health_status,
            },
            "route_smoke": {
                "status": health_status,
                "routes": [],
                "checks": [],
            },
        },
        "return_to_coordinator": {
            "decision": "accept_and_route",
            "action": "Apply the Coordinator Return Gate.",
        },
    }


class OpsClientErrorContractTests(unittest.TestCase):
    def test_structured_http_error_is_parsed_without_exposing_raw_body(self) -> None:
        payload = {
            "ok": False,
            "error": "deployment_rejected",
            "message": "available memory is below the deployment reserve",
            "data": {
                "available_memory_bytes": 400_000_000,
                "return_to_coordinator": {
                    "decision": "blocked_with_owner",
                    "action": "Free memory and redispatch the same authoritative ref.",
                },
            },
        }
        error = HTTPError(
            "http://ops.invalid/ops/deploy",
            422,
            "Unprocessable Entity",
            {},
            BytesIO(json.dumps(payload).encode("utf-8")),
        )
        client = ops_client.OpsClient("http://127.0.0.1:8767", "test-token")

        with mock.patch.object(ops_client, "_open_no_redirect", side_effect=error):
            with self.assertRaises(ops_client.OpsClientError) as raised:
                client.post("/ops/deploy", {"ref": SHA})

        exc = raised.exception
        self.assertEqual(422, exc.http_status)
        self.assertEqual("deployment_rejected", exc.error_code)
        self.assertEqual(payload["message"], exc.message)
        self.assertEqual(payload["data"], exc.data)
        self.assertEqual(
            "Free memory and redispatch the same authoritative ref.",
            exc.next_action,
        )
        self.assertNotIn(json.dumps(payload), str(exc))

    def test_unstructured_http_error_never_echoes_secret_bearing_body(self) -> None:
        error = HTTPError(
            "http://ops.invalid/ops/deploy",
            500,
            "Internal Server Error",
            {},
            BytesIO(b"OPS_API_TOKEN=do-not-print-this"),
        )
        client = ops_client.OpsClient("http://127.0.0.1:8767", "test-token")

        with mock.patch.object(ops_client, "_open_no_redirect", side_effect=error):
            with self.assertRaises(ops_client.OpsClientError) as raised:
                client.post("/ops/deploy", {"ref": SHA})

        self.assertEqual("ops_api_http_error", raised.exception.error_code)
        self.assertNotIn("do-not-print-this", str(raised.exception))

    def test_structured_error_redacts_sensitive_key_values(self) -> None:
        payload = {
            "ok": False,
            "error": "deployment_rejected",
            "message": "token=do-not-print-this",
            "data": {"OPS_API_TOKEN": "do-not-print-this", "deploy_event_id": 42},
        }
        error = HTTPError(
            "http://ops.invalid/ops/deploy",
            422,
            "Unprocessable Entity",
            {},
            BytesIO(json.dumps(payload).encode("utf-8")),
        )
        client = ops_client.OpsClient("http://127.0.0.1:8767", "test-token")

        with mock.patch.object(ops_client, "_open_no_redirect", side_effect=error):
            with self.assertRaises(ops_client.OpsClientError) as raised:
                client.post("/ops/deploy", {"ref": SHA})

        self.assertNotIn("do-not-print-this", str(raised.exception))
        self.assertEqual("[redacted-credential]", raised.exception.data["OPS_API_TOKEN"])
        self.assertEqual(42, raised.exception.data["deploy_event_id"])

    def test_all_error_surfaces_redact_bearer_and_colon_delimited_secrets(self) -> None:
        secret = "do-not-print-this-secret"
        error = ops_client.OpsClientError(
            f"Authorization: Bearer {secret}",
            error_code="deployment_rejected",
            data={
                "context": {
                    "innocuous": f"Bearer {secret}",
                    "detail": f"OPS_API_TOKEN: {secret}",
                }
            },
            next_action=f"secret: {secret}",
        )

        rendered = json.dumps(error.as_payload(), ensure_ascii=False)
        self.assertNotIn(secret, rendered)
        self.assertEqual("deployment_rejected", error.error_code)


class OpsClientTransportSecurityTests(unittest.TestCase):
    def test_only_clean_private_http_base_urls_are_accepted(self) -> None:
        valid = (
            "http://127.0.0.1:8767",
            "http://127.1.2.3",
            "http://10.2.3.4:8767/",
            "http://172.16.2.3:8767",
            "http://192.168.5.4:8767",
            "http://host.docker.internal:8767",
            "http://[::1]:8767",
        )
        invalid = (
            "https://127.0.0.1:8767",
            "http://example.com:8767",
            "http://8.8.8.8:8767",
            "http://169.254.169.254:8767",
            "http://192.0.2.1:8767",
            "http://198.18.0.1:8767",
            "http://240.0.0.1:8767",
            "http://0.0.0.0:8767",
            "http://localhost:8767",
            "http://user:pass@127.0.0.1:8767",
            "http://127.0.0.1:8767?token=value",
            "http://127.0.0.1:8767#fragment",
            "http://127.0.0.1:8767/ops",
            "http://127.0.0.1:99999",
            "ftp://127.0.0.1:8767",
        )

        for url in valid:
            with self.subTest(valid=url):
                self.assertEqual(url.rstrip("/"), ops_client.OpsClient(url, "token").base_url)
        for url in invalid:
            with self.subTest(invalid=url):
                with self.assertRaises(ops_client.OpsClientError) as raised:
                    ops_client.OpsClient(url, "token")
                self.assertEqual("ops_api_url_invalid", raised.exception.error_code)

    def test_authorization_is_never_forwarded_across_redirect(self) -> None:
        received_authorization: list[str | None] = []

        class TargetHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                received_authorization.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true,"data":{}}')

            def log_message(self, _format: str, *args: object) -> None:
                return

        target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
        target_thread = threading.Thread(target=target.serve_forever, daemon=True)
        target_thread.start()

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{target.server_port}/capture")
                self.end_headers()

            def log_message(self, _format: str, *args: object) -> None:
                return

        redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        redirect_thread = threading.Thread(target=redirect.serve_forever, daemon=True)
        redirect_thread.start()
        try:
            client = ops_client.OpsClient(f"http://127.0.0.1:{redirect.server_port}", "private-token")
            with self.assertRaises(ops_client.OpsClientError) as raised:
                client.get("/redirect")
            self.assertEqual("ops_api_http_error", raised.exception.error_code)
            self.assertEqual([], received_authorization)
        finally:
            redirect.shutdown()
            redirect.server_close()
            target.shutdown()
            target.server_close()
            redirect_thread.join(timeout=2)
            target_thread.join(timeout=2)

    def test_success_response_requires_literal_true_and_object_data(self) -> None:
        invalid_payloads = (
            {"ok": 1, "data": {}},
            {"ok": "true", "data": {}},
            {"ok": True, "data": []},
            {"ok": True},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ops_client.OpsClientError) as raised:
                    ops_client._response_data(payload)
                self.assertEqual("ops_api_invalid_response", raised.exception.error_code)


class DeployRequestContractTests(unittest.TestCase):
    def test_full_image_modes_are_rejected_before_client_or_network_dispatch(self) -> None:
        for mode in ("full", "full_image"):
            with self.subTest(mode=mode):
                with mock.patch.object(ops_client, "get_ops_deploy_client") as get_client:
                    with self.assertRaises(ops_client.OpsClientError) as raised:
                        ops_client.deploy_cloud_ref(SHA, mode=mode)

                get_client.assert_not_called()
                self.assertEqual("full_image_requires_workflow", raised.exception.error_code)
                self.assertIn("GitHub Actions", raised.exception.next_action or "")

    def test_invalid_request_fields_fail_before_client_dispatch(self) -> None:
        cases = (
            ({"ref": "feature/not-authoritative"}, "source_policy_rejected"),
            ({"ref": SHA, "mode": "rolling"}, "deployment_request_invalid"),
            ({"ref": SHA, "targets": ["../worker"]}, "deployment_request_invalid"),
            ({"ref": SHA, "targets": ["postgres"]}, "deployment_request_invalid"),
            ({"ref": SHA, "targets": ["unknown-service"]}, "deployment_request_invalid"),
            ({"ref": SHA, "mode": "no_deploy", "targets": ["mcp"]}, "deployment_request_invalid"),
            ({"ref": SHA, "feature_routes": ["https://example.test/health"]}, "deployment_request_invalid"),
            ({"ref": SHA, "feature_routes": ["/token/secret"]}, "deployment_request_invalid"),
            ({"ref": SHA, "source": "unknown_channel"}, "deployment_request_invalid"),
            ({"ref": SHA, "requested_by": "OPS_API_TOKEN=secret"}, "deployment_request_invalid"),
        )

        for kwargs, expected_code in cases:
            with self.subTest(kwargs=kwargs):
                with mock.patch.object(ops_client, "get_ops_deploy_client") as get_client:
                    with self.assertRaises(ops_client.OpsClientError) as raised:
                        ops_client.deploy_cloud_ref(**kwargs)
                get_client.assert_not_called()
                self.assertEqual(expected_code, raised.exception.error_code)

    def test_supported_fields_are_canonicalized_and_forwarded(self) -> None:
        client = mock.Mock()
        client.post.return_value = _terminal_deploy_data(
            requested_services=["command-api", "weekly-review-web"],
            affected_services=["command-api", "weekly-review-web"],
        )
        with mock.patch.object(ops_client, "get_ops_deploy_client", return_value=client):
            result = ops_client.deploy_cloud_ref(
                SHA.upper(),
                mode="quick",
                targets=["weekly-review-web", "command-api", "weekly-review-web"],
                feature_routes=["/weekly-review", "/health", "/weekly-review"],
                source="mcp",
                requested_by="weekly-review-coordinator",
            )

        self.assertEqual("completed", result["status"])
        client.post.assert_called_once_with(
            "/ops/deploy",
            {
                "ref": SHA,
                "mode": "targeted_quick",
                "targets": ["command-api", "weekly-review-web"],
                "feature_routes": ["/weekly-review", "/health"],
                "source": "mcp",
                "requested_by": "weekly-review-coordinator",
            },
        )

    def test_deploy_rejects_async_or_incomplete_success_contracts(self) -> None:
        cases = (
            {"status": "running", "deploy_event_id": 42},
            {"status": "completed", "deploy_event_id": 42},
            {**_terminal_deploy_data(), "deploy_event_id": None},
            {**_terminal_deploy_data(), "deploy_event_id": True},
            {**_terminal_deploy_data(), "status_url": "https://public.invalid/event/42"},
            {**_terminal_deploy_data(), "evidence": {}},
            {
                **_terminal_deploy_data(),
                "return_to_coordinator": {"decision": "pending", "action": "Wait."},
            },
        )
        for response in cases:
            with self.subTest(response=response):
                client = mock.Mock()
                client.post.return_value = response
                with mock.patch.object(ops_client, "get_ops_deploy_client", return_value=client):
                    with self.assertRaises(ops_client.OpsClientError) as raised:
                        ops_client.deploy_cloud_ref(SHA, targets=["weekly-review-web"])
                self.assertEqual("deployment_contract_invalid", raised.exception.error_code)

    def test_no_deploy_accepts_explicit_not_applicable_terminal_evidence(self) -> None:
        client = mock.Mock()
        client.post.return_value = _terminal_deploy_data(
            mode="no_deploy",
            requested_services=[],
            affected_services=[],
        )
        with mock.patch.object(ops_client, "get_ops_deploy_client", return_value=client):
            result = ops_client.deploy_cloud_ref(SHA, mode="no_deploy")
        self.assertEqual("not_required", result["evidence"]["status"])

    def test_render_describes_terminal_completion_and_status_handoff(self) -> None:
        with mock.patch.object(
            ops_client,
            "deploy_cloud_ref",
            return_value=_terminal_deploy_data(),
        ):
            rendered = ops_client.render_cloud_deploy(SHA)

        self.assertIn("云端部署已完成", rendered)
        self.assertNotIn("已启动", rendered)
        self.assertIn("/ops/deploy-status?id=42", rendered)


class McpDeployContractTests(unittest.TestCase):
    def test_render_mode_returns_structured_failure(self) -> None:
        error = ops_client.OpsClientError(
            "Full image transport is unavailable from MCP.",
            error_code="full_image_requires_workflow",
            next_action="Use the GitHub Actions deploy workflow.",
        )
        with mock.patch.object(server, "render_cloud_deploy", side_effect=error):
            result = server.cloud_deploy(SHA, mode="full", render=True)

        self.assertFalse(result["ok"])
        self.assertEqual("full_image_requires_workflow", result["error"])
        self.assertEqual("Use the GitHub Actions deploy workflow.", result["next_action"])

    def test_raw_mode_returns_structured_failure(self) -> None:
        error = ops_client.OpsClientError(
            "Deployment was rejected.",
            http_status=422,
            error_code="deployment_rejected",
            data={"deploy_event_id": 42},
            next_action="Apply the failed deployment Return Gate.",
        )
        with mock.patch.object(server, "deploy_cloud_ref", side_effect=error):
            result = server.cloud_deploy(SHA, render=False)

        self.assertFalse(result["ok"])
        self.assertEqual(422, result["http_status"])
        self.assertEqual({"deploy_event_id": 42}, result["data"])

    def test_mcp_forwards_supported_deploy_evidence_fields(self) -> None:
        with mock.patch.object(server, "deploy_cloud_ref", return_value=_terminal_deploy_data()) as deploy:
            result = server.cloud_deploy(
                SHA,
                mode="config_restart",
                targets=["weekly-review-web"],
                feature_routes=["/weekly-review"],
                requested_by="weekly-review-coordinator",
                render=False,
            )

        self.assertTrue(result["ok"])
        deploy.assert_called_once_with(
            ref=SHA,
            mode="config_restart",
            targets=["weekly-review-web"],
            feature_routes=["/weekly-review"],
            source="mcp",
            requested_by="weekly-review-coordinator",
        )

    def test_mcp_source_is_fixed_and_not_caller_controlled(self) -> None:
        self.assertNotIn("source", inspect.signature(server.cloud_deploy).parameters)


class OpsContainerConfigurationContractTests(unittest.TestCase):
    def test_host_and_container_ops_urls_are_separate(self) -> None:
        env_example = Path(".env.example").read_text(encoding="utf-8")
        compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

        self.assertIn("OPS_API_URL=http://127.0.0.1:8767", env_example)
        self.assertIn("MCP_OPS_API_URL=http://host.docker.internal:8767", env_example)
        self.assertNotIn("OPS_API_URL: ${OPS_API_URL:-", compose)
        self.assertIn(
            "OPS_API_URL: ${MCP_OPS_API_URL:-http://host.docker.internal:8767}",
            compose,
        )

    def test_ops_credentials_do_not_fall_back_to_browser_or_command_token(self) -> None:
        with (
            mock.patch.object(app_config, "load_env_file"),
            mock.patch.dict(os.environ, {"COMMAND_API_TOKEN": "separate-command-token"}, clear=True),
        ):
            config = app_config.get_config()

        self.assertEqual("separate-command-token", config.command_api_token)
        self.assertIsNone(config.ops_api_token)
        compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
        self.assertNotIn("OPS_API_TOKEN: ${OPS_API_TOKEN:-${COMMAND_API_TOKEN:-}}", compose)
        self.assertIn("OPS_API_TOKEN: ${OPS_API_TOKEN:-}", compose)

    def test_production_env_generator_creates_a_distinct_ops_token(self) -> None:
        from scripts import generate_prod_env

        rendered = generate_prod_env._render_env(
            postgres_user="postgres",
            postgres_password="postgres-secret",
            postgres_db="investment_kg",
            command_api_token="command-secret",
            ops_api_token="ops-secret",
            dingtalk_secret="",
            dingtalk_send_webhook="",
            dingtalk_send_secret="",
            dingtalk_stream_client_id="",
            dingtalk_stream_client_secret="",
            dingtalk_stream_write_allowed_senders="",
            dingtalk_stream_allow_write=False,
            futu_opend_host="127.0.0.1",
            futu_opend_port="11112",
            futu_security_firm="FUTUSECURITIES",
            futu_trade_market="HK",
            futu_trade_env="REAL",
            futu_account_id="0",
            futu_account_index="0",
            futu_position_cache_seconds="20",
            futu_position_refresh_cache="true",
            openai_api_key="",
            openai_model="gpt-5.2",
            pip_index_url="https://pypi.org/simple",
        )
        self.assertIn("COMMAND_API_TOKEN=command-secret", rendered)
        self.assertIn("OPS_API_TOKEN=ops-secret", rendered)

    def test_deploy_timeout_is_documented_and_propagated_to_containers(self) -> None:
        env_example = Path(".env.example").read_text(encoding="utf-8")
        compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")

        self.assertIn("OPS_API_DEPLOY_TIMEOUT_SECONDS=600", env_example)
        self.assertIn(
            "OPS_API_DEPLOY_TIMEOUT_SECONDS: ${OPS_API_DEPLOY_TIMEOUT_SECONDS:-600}",
            compose,
        )


if __name__ == "__main__":
    unittest.main()
