from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import unittest
from unittest import mock
from urllib.error import HTTPError

from investment_knowledge_mcp import config as app_config
from investment_knowledge_mcp import ops_client, server


SHA = "a" * 40


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
        client = ops_client.OpsClient("http://ops.invalid", "test-token")

        with mock.patch.object(ops_client, "urlopen", side_effect=error):
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
        client = ops_client.OpsClient("http://ops.invalid", "test-token")

        with mock.patch.object(ops_client, "urlopen", side_effect=error):
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
        client = ops_client.OpsClient("http://ops.invalid", "test-token")

        with mock.patch.object(ops_client, "urlopen", side_effect=error):
            with self.assertRaises(ops_client.OpsClientError) as raised:
                client.post("/ops/deploy", {"ref": SHA})

        self.assertNotIn("do-not-print-this", str(raised.exception))
        self.assertEqual("[redacted-credential]", raised.exception.data["OPS_API_TOKEN"])
        self.assertEqual(42, raised.exception.data["deploy_event_id"])


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
        client.post.return_value = {"status": "completed", "deploy_event_id": 42}
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

    def test_render_describes_terminal_completion_and_status_handoff(self) -> None:
        with mock.patch.object(
            ops_client,
            "deploy_cloud_ref",
            return_value={
                "deploy_event_id": 42,
                "ref": SHA,
                "commit_sha": SHA,
                "mode": "targeted_quick",
                "status": "completed",
                "status_url": "/ops/deploy-status?id=42",
            },
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
        with mock.patch.object(server, "deploy_cloud_ref", return_value={"status": "completed"}) as deploy:
            result = server.cloud_deploy(
                SHA,
                mode="config_restart",
                targets=["weekly-review-web"],
                feature_routes=["/weekly-review"],
                source="mcp",
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
