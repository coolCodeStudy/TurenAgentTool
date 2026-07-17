from __future__ import annotations

from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import scripts.ecs_ops_api as ops
from scripts.deploy_contract import DeployMode
from scripts.deploy_preflight import ResourceSnapshot
from scripts.deploy_release import DeployOutcome, DeployRequest
from scripts.deploy_state import DeploymentState, write_state
from scripts.deploy_support import CommandResult


TARGET_SHA = "b" * 40
PREVIOUS_SHA = "a" * 40


class OpsApiInstallLayoutTests(unittest.TestCase):
    def test_daily_market_brief_history_worker_is_in_ops_health_and_diagnostics(self) -> None:
        source = Path("scripts/ecs_ops_api.py").read_text(encoding="utf-8")

        self.assertEqual(
            "daily-market-brief-history-worker",
            ops.COMPOSE_SERVICES["daily-market-brief-history-worker"],
        )
        self.assertGreaterEqual(source.count('"daily-market-brief-history-worker"'), 3)

    def test_daily_market_brief_scheduler_is_in_ops_health_and_diagnostics(self) -> None:
        source = Path("scripts/ecs_ops_api.py").read_text(encoding="utf-8")

        self.assertEqual("daily-market-brief-scheduler", ops.COMPOSE_SERVICES["daily-market-brief-scheduler"])
        self.assertGreaterEqual(source.count('"daily-market-brief-scheduler"'), 3)

    def test_installed_ops_home_contains_runtime_import_closure(self) -> None:
        installer = Path("scripts/install_ops_api_on_ecs.sh").read_text(encoding="utf-8")
        match = re.search(r"OPS_API_MODULES=\((?P<body>.*?)\)", installer, re.DOTALL)
        self.assertIsNotNone(match, "installer must declare the copied Ops API module closure")
        modules = re.findall(r'"([^"]+\.py)"', match.group("body"))
        required = {
            "ecs_ops_api.py",
            "deploy_contract.py",
            "deploy_preflight.py",
            "deploy_release.py",
            "deploy_retention.py",
            "deploy_state.py",
            "deploy_support.py",
        }
        self.assertTrue(required.issubset(set(modules)))

        with TemporaryDirectory() as tmp:
            ops_home = Path(tmp) / "investment-ops"
            ops_home.mkdir()
            for module in modules:
                shutil.copy2(Path("scripts") / module, ops_home / module)

            env = {
                **os.environ,
                "PYTHONPATH": "",
                "INVESTMENT_APP_ROOT": str(Path(tmp) / "app"),
                "OPS_DEPLOY_REPO_DIR": str(Path(tmp) / "repo"),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import ecs_ops_api; import deploy_release; print(ecs_ops_api.APP_ROOT)",
                ],
                cwd=ops_home,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)


class FakeEngine:
    def __init__(self, outcome: DeployOutcome | None = None) -> None:
        self.requests: list[DeployRequest] = []
        self.outcome = outcome or DeployOutcome(
            ok=True,
            target_sha=TARGET_SHA,
            mode=DeployMode.TARGETED_QUICK,
            activated_services=("weekly-review-web",),
            rolled_back_services=(),
            message="deployment completed and remained healthy",
            audit_status="recorded",
            disk_used_after=41.5,
        )

    def deploy(self, request: DeployRequest) -> DeployOutcome:
        self.requests.append(request)
        return self.outcome


class EcsOpsApiDeployTests(unittest.TestCase):
    def test_handler_leaves_authoritative_source_resolution_to_locked_engine(self) -> None:
        engine = FakeEngine()

        with (
            patch.object(
                ops,
                "_resolve_deploy_source_policy",
                side_effect=AssertionError("handler must not resolve outside the engine lock"),
                create=True,
            ),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            result = ops.deploy_ref(
                {
                    "ref": TARGET_SHA,
                    "mode": "targeted_quick",
                    "targets": ["weekly-review-web"],
                    "source": "github_actions",
                    "requested_by": "weekly_review_coordinator",
                }
            )

        self.assertEqual(TARGET_SHA, result["commit_sha"])
        self.assertEqual(TARGET_SHA, engine.requests[0].requested_ref)
        self.assertEqual("github_actions", engine.requests[0].source)
        self.assertEqual("weekly_review_coordinator", engine.requests[0].requested_by)

    def test_secret_shaped_deploy_labels_are_rejected_before_engine_dispatch(self) -> None:
        engine = FakeEngine()

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {
                    "ref": TARGET_SHA,
                    "mode": "targeted_quick",
                    "targets": ["weekly-review-web"],
                    "source": "github_actions",
                    "requested_by": "TOKEN=hidden-value",
                },
            )

        self.assertEqual(422, status)
        self.assertEqual("deployment_rejected", payload["error"])
        self.assertEqual([], engine.requests)
        self.assertNotIn("hidden-value", json.dumps(payload))

    def test_invalid_non_secret_deploy_label_is_rejected_before_dispatch(self) -> None:
        engine = FakeEngine()

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            with self.assertRaisesRegex(ops.DeployApiError, "source"):
                ops.deploy_ref(
                    {
                        "ref": TARGET_SHA,
                        "mode": "targeted_quick",
                        "targets": ["weekly-review-web"],
                        "source": "invalid label with spaces",
                    }
                )

        self.assertEqual([], engine.requests)

    def test_deploy_source_must_use_explicit_allowlist(self) -> None:
        engine = FakeEngine()

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            with self.assertRaisesRegex(ops.DeployApiError, "source"):
                ops.deploy_ref(
                    {
                        "ref": TARGET_SHA,
                        "mode": "targeted_quick",
                        "targets": ["weekly-review-web"],
                        "source": "rogue_dispatcher",
                    }
                )

        self.assertEqual([], engine.requests)

    def test_api_rejects_synthetic_credential_label_shapes(self) -> None:
        engine = FakeEngine()
        shapes = (
            "github_pat_" + "A" * 24,
            "sk-" + "B" * 32,
            "AKIA" + "C" * 16,
            "eyJ" + "D" * 12 + "." + "E" * 12 + "." + "F" * 12,
        )

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            for index, label in enumerate(shapes):
                with self.subTest(shape=index):
                    with self.assertRaisesRegex(ops.DeployApiError, "requested_by"):
                        ops.deploy_ref(
                            {
                                "ref": TARGET_SHA,
                                "mode": "targeted_quick",
                                "targets": ["weekly-review-web"],
                                "source": "github_actions",
                                "requested_by": label,
                            }
                        )

        self.assertEqual([], engine.requests)

    def test_locked_source_rejection_returns_typed_integration_recovery(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha="",
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment failed; inspect the product-safe deployment event",
                audit_status="recorded",
                failure_category="source_policy_rejected",
            )
        )

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {"ref": TARGET_SHA, "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(400, status)
        self.assertEqual("source_policy_rejected", payload["error"])
        self.assertRegex(
            payload["message"],
            r"integrate.*authoritative main.*push.*new main tip",
        )
        self.assertEqual((), engine.requests[0].feature_routes)

    def test_lockout_without_a_target_is_not_misclassified_as_source_policy(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha="",
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment is locked out pending manual recovery",
                manual_recovery={"action": "inspect durable lockout evidence"},
            )
        )

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {"ref": TARGET_SHA, "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(422, status)
        self.assertEqual("deployment_rejected", payload["error"])

    def test_repository_failure_without_source_category_is_not_misclassified(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha="",
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment failed; inspect the product-safe deployment event",
                audit_status="recorded",
            )
        )

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {"ref": TARGET_SHA, "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(422, status)
        self.assertEqual("deployment_rejected", payload["error"])

    def test_manual_recovery_and_audit_failure_override_source_policy_guidance(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha="",
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment is locked out pending manual recovery",
                manual_recovery={"action": "inspect durable lockout evidence"},
                audit_status="failed_durable",
                failure_category="source_policy_rejected",
            )
        )

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {"ref": TARGET_SHA, "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(422, status)
        self.assertEqual("deployment_rejected", payload["error"])
        self.assertIn("locked out", payload["message"])
        self.assertNotIn("authoritative main", payload["message"])
        self.assertEqual(
            "inspect durable lockout evidence",
            payload["data"]["outcome"]["manual_recovery"]["action"],
        )

    def test_deploy_recomputes_plan_and_dispatches_shared_engine(self) -> None:
        engine = FakeEngine()

        with (
            patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
            patch.object(ops, "_run_git", side_effect=AssertionError("legacy shell deploy path should not run")),
        ):
            result = ops.deploy_ref(
                {
                    "ref": "main",
                    "mode": "targeted_quick",
                    "targets": ["weekly-review-web"],
                }
            )

        self.assertEqual("completed", result["status"])
        self.assertEqual(TARGET_SHA, result["commit_sha"])
        self.assertEqual(DeployMode.TARGETED_QUICK, engine.requests[0].requested_mode)
        self.assertEqual(("weekly-review-web",), engine.requests[0].requested_targets)

    def test_legacy_quick_alias_maps_to_targeted_quick(self) -> None:
        engine = FakeEngine()

        with (
            patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            ops.deploy_ref({"ref": "main", "mode": "quick", "targets": ["weekly-review-web"]})

        self.assertEqual(DeployMode.TARGETED_QUICK, engine.requests[0].requested_mode)

    def test_http_deploy_endpoint_dispatches_all_canonical_modes(self) -> None:
        cases = (
            ("no_deploy", DeployMode.NO_DEPLOY, []),
            ("targeted_quick", DeployMode.TARGETED_QUICK, ["weekly-review-web"]),
            ("config_restart", DeployMode.CONFIG_RESTART, ["weekly-review-web"]),
            ("full_image", DeployMode.FULL_IMAGE, ["weekly-review-web"]),
        )

        for raw_mode, expected_mode, targets in cases:
            with self.subTest(mode=raw_mode):
                engine = FakeEngine(
                    DeployOutcome(
                        ok=True,
                        target_sha=TARGET_SHA,
                        mode=expected_mode,
                        activated_services=tuple(targets),
                        rolled_back_services=(),
                        message="deployment completed and remained healthy",
                    )
                )
                payload: dict[str, object] = {
                    "ref": "main",
                    "mode": raw_mode,
                    "targets": targets,
                }
                if expected_mode is DeployMode.FULL_IMAGE:
                    payload["archive_path"] = "/tmp/candidate-image.tar"

                with (
                    patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
                    patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                ):
                    status, response = self._post_json("/deploy", payload)

                self.assertEqual(200, status)
                self.assertTrue(response["ok"])
                data = response["data"]
                self.assertEqual("completed", data["status"])
                self.assertEqual(expected_mode.value, data["mode"])
                self.assertEqual(expected_mode, engine.requests[0].requested_mode)
                self.assertEqual(tuple(targets), engine.requests[0].requested_targets)

    def test_http_deploy_endpoint_maps_legacy_full_alias_when_retained(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=True,
                target_sha=TARGET_SHA,
                mode=DeployMode.FULL_IMAGE,
                activated_services=("weekly-review-web",),
                rolled_back_services=(),
                message="deployment completed and remained healthy",
            )
        )

        with (
            patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, response = self._post_json(
                "/deploy",
                {
                    "ref": "main",
                    "mode": "full",
                    "targets": ["weekly-review-web"],
                    "archive_path": "/tmp/candidate-image.tar",
                }
            )

        self.assertEqual(200, status)
        self.assertTrue(response["ok"])
        self.assertEqual(DeployMode.FULL_IMAGE, engine.requests[0].requested_mode)

    def test_legacy_ops_deploy_response_preserves_event_status_contract(self) -> None:
        engine = FakeEngine()

        with (
            patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, response = self._post_json(
                "/ops/deploy",
                {"ref": "main", "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(200, status)
        data = response["data"]
        self.assertIsInstance(data["deploy_event_id"], int)
        self.assertGreater(data["deploy_event_id"], 0)
        self.assertEqual(f"/ops/deploy-status?id={data['deploy_event_id']}", data["status_url"])
        self.assertEqual(str(data["deploy_event_id"]), engine.requests[0].external_event_id)

    def test_http_deploy_endpoint_keeps_quick_alias_coverage(self) -> None:
        engine = FakeEngine()

        with (
            patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, response = self._post_json(
                "/deploy",
                {"ref": "main", "mode": "quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(200, status)
        self.assertTrue(response["ok"])
        self.assertEqual(DeployMode.TARGETED_QUICK, engine.requests[0].requested_mode)

    def test_feature_ref_is_rejected_before_worker_dispatch(self) -> None:
        engine = FakeEngine()

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {
                    "ref": "feature/daily",
                    "mode": "full_image",
                    "emergency_reason": "urgent production repair with evidence",
                },
            )

        self.assertEqual(400, status)
        self.assertEqual("source_policy_rejected", payload["error"])
        self.assertEqual([], engine.requests)

    def test_active_deployment_lock_returns_409_before_engine_dispatch(self) -> None:
        engine = FakeEngine()
        self.assertTrue(ops.DEPLOY_MUTEX.acquire(blocking=False))
        try:
            with (
                patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
                patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
            ):
                status, payload = self._post_json(
                    "/ops/deploy",
                    {"ref": "main", "mode": "targeted_quick", "targets": ["weekly-review-web"]},
                )
        finally:
            ops.DEPLOY_MUTEX.release()

        self.assertEqual(409, status)
        self.assertEqual("deployment_busy", payload["error"])
        self.assertEqual([], engine.requests)

    def test_shared_engine_lock_contention_returns_409(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha="",
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment lock could not be acquired password=secret",
                archive_cleanup="deferred_lock_unavailable",
            )
        )

        with (
            patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, payload = self._post_json(
                "/deploy",
                {"ref": "main", "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(409, status)
        self.assertEqual("deployment_busy", payload["error"])
        self.assertEqual(1, len(engine.requests))
        text = json.dumps(payload)
        self.assertNotIn("secret", text)

    def test_product_safe_engine_rejection_returns_422_and_sanitizes_message(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha=TARGET_SHA,
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment resource preflight failed password=secret SSL: CERTIFICATE_VERIFY_FAILED",
            )
        )

        with (
            patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, payload = self._post_json(
                "/deploy",
                {"ref": "main", "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(422, status)
        text = json.dumps(payload)
        self.assertIn("deployment_rejected", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("CERTIFICATE_VERIFY_FAILED", text)
        data = payload["data"]
        self.assertIsInstance(data["deploy_event_id"], int)
        self.assertEqual(
            f"/ops/deploy-status?id={data['deploy_event_id']}",
            data["status_url"],
        )
        self.assertEqual("reject_and_return", data["return_to_coordinator"]["decision"])
        self.assertEqual("failed", data["evidence"]["status"])
        self.assertEqual(["weekly-review-web"], data["evidence"]["requested_services"])
        self.assertEqual([], data["evidence"]["affected_services"])

    def test_low_memory_failure_returns_durable_actual_and_required_evidence(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha=TARGET_SHA,
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment resource preflight failed: available memory must be at least 512 MiB",
                audit_status="recorded",
            )
        )
        with TemporaryDirectory() as tmp:
            events_dir = Path(tmp)
            (events_dir / "42.json").write_text(
                json.dumps(
                    {
                        "event_id": "42",
                        "requested_mode": "targeted_quick",
                        "computed_mode": "targeted_quick",
                        "deployed_sha": None,
                        "target_sha": TARGET_SHA,
                        "targets": ["weekly-review-web"],
                        "affected_services": [],
                        "feature_routes": ["/weekly-review"],
                        "preflight": {
                            "available_memory_bytes": 400 * 1024**2,
                            "required_available_memory_bytes": 512 * 1024**2,
                            "minimum_available_memory_bytes": 400 * 1024**2,
                        },
                        "rollback_status": "not_started",
                        "final_health": "unhealthy",
                        "stability_seconds": 30,
                        "started_at": "2026-07-10T00:00:00+00:00",
                        "completed_at": "2026-07-10T00:00:01+00:00",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(ops, "DEPLOY_EVENTS_DIR", events_dir, create=True),
                patch.object(ops, "_new_deploy_event_id", return_value=42),
                patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
            ):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "targeted_quick",
                        "targets": ["weekly-review-web"],
                        "feature_routes": ["/weekly-review"],
                    },
                )

        self.assertEqual(422, status)
        evidence = payload["data"]["evidence"]
        self.assertEqual(400 * 1024**2, evidence["preflight"]["available_memory_bytes"])
        self.assertEqual(
            512 * 1024**2,
            evidence["preflight"]["required_available_memory_bytes"],
        )
        self.assertEqual([], evidence["affected_services"])
        self.assertEqual("failed", evidence["route_smoke"]["status"])
        self.assertEqual(0, evidence["stable_health"]["observed_seconds"])

    def test_terminal_success_returns_durable_evidence_and_coordinator_action(self) -> None:
        engine = FakeEngine()

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {
                    "ref": TARGET_SHA,
                    "mode": "targeted_quick",
                    "targets": ["weekly-review-web"],
                    "feature_routes": ["/weekly-review"],
                },
            )

        self.assertEqual(200, status)
        data = payload["data"]
        self.assertEqual("completed", data["status"])
        self.assertEqual("accept_and_route", data["return_to_coordinator"]["decision"])
        self.assertEqual("succeeded", data["evidence"]["status"])
        self.assertEqual(["weekly-review-web"], data["evidence"]["requested_services"])
        self.assertEqual(["weekly-review-web"], data["evidence"]["affected_services"])
        self.assertEqual(["/weekly-review"], data["evidence"]["feature_routes"])
        self.assertEqual("healthy", data["evidence"]["route_smoke"]["status"])

    def test_full_image_without_image_diff_requires_emergency_reason(self) -> None:
        engine = FakeEngine()

        with (
            patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, payload = self._post_json(
                "/deploy",
                {"ref": "main", "mode": "full_image", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(422, status)
        self.assertEqual("deployment_rejected", payload["error"])
        self.assertEqual([], engine.requests)

    def test_stale_sha_is_rejected_by_the_locked_engine(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha="",
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment failed; inspect the product-safe deployment event",
                audit_status="recorded",
                failure_category="source_policy_rejected",
            )
        )

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {"ref": TARGET_SHA, "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(400, status)
        self.assertEqual("source_policy_rejected", payload["error"])
        self.assertEqual(1, len(engine.requests))

    def test_deploy_status_exposes_state_resources_and_sanitized_last_outcome(self) -> None:
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            state_path = directory / "deploy-state.json"
            events_dir = directory / "events"
            events_dir.mkdir()
            write_state(
                state_path,
                DeploymentState(
                    schema_version=1,
                    current_sha=TARGET_SHA,
                    previous_sha=PREVIOUS_SHA,
                    current_image=f"investment-knowledge-app:{TARGET_SHA}",
                    previous_image=f"investment-knowledge-app:{PREVIOUS_SHA}",
                    active_release=f"/releases/{TARGET_SHA}",
                    previous_release=f"/releases/{PREVIOUS_SHA}",
                    last_mode="targeted_quick",
                    requested_ref="main",
                    resolved_ref=TARGET_SHA,
                    targets=("weekly-review-web",),
                    last_event_id="evt-1",
                    started_at="2026-07-10T00:00:00+00:00",
                    completed_at="2026-07-10T00:01:00+00:00",
                    preflight={"disk_used_percent": 40.0},
                    final_health="healthy",
                ),
            )
            (events_dir / "evt-1.json").write_text(
                json.dumps(
                    {
                        "event_id": "evt-1",
                        "requested_mode": "targeted_quick",
                        "targets": ["weekly-review-web"],
                        "final_health": "unhealthy password=secret",
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(ops, "DEPLOY_STATE_PATH", state_path, create=True),
                patch.object(ops, "DEPLOY_EVENTS_DIR", events_dir, create=True),
                patch.object(
                    ops,
                    "collect_deploy_resources",
                    return_value=ResourceSnapshot(
                        free_disk_bytes=16 * 1024**3,
                        disk_used_percent=42.0,
                        available_memory_bytes=2 * 1024**3,
                    ),
                    create=True,
                ),
            ):
                status, payload = self._get_json("/deploy/status")

        self.assertEqual(200, status)
        data = payload["data"]
        self.assertEqual(TARGET_SHA, data["current_sha"])
        self.assertEqual(PREVIOUS_SHA, data["previous_sha"])
        self.assertEqual("targeted_quick", data["active_mode"])
        self.assertEqual(["weekly-review-web"], data["targets"])
        self.assertEqual(42.0, data["resources"]["disk_used_percent"])
        self.assertEqual(80.0, data["resource_thresholds"]["max_disk_used_percent"])
        self.assertNotIn("state_path", data)
        self.assertNotIn("release_root", data)
        self.assertNotIn("lock_path", data)
        self.assertNotIn("secret", json.dumps(data["last_outcome"]))

    def test_read_deploy_event_returns_json_object(self) -> None:
        payload = '{"id": 42, "status": "started"}'
        with patch.object(ops, "_run", return_value=CommandResult(0, payload, "")):
            self.assertEqual(ops.read_deploy_event(42), {"id": 42, "status": "started"})

    def test_generated_event_id_is_accepted_by_the_stable_status_url(self) -> None:
        event_id = ops._new_deploy_event_id()

        with patch.object(
            ops,
            "read_deploy_event",
            return_value={"id": event_id, "status": "succeeded"},
        ) as read_event:
            status, payload = self._get_json(f"/ops/deploy-status?id={event_id}")

        self.assertEqual(200, status)
        self.assertEqual(event_id, payload["data"]["id"])
        read_event.assert_called_once_with(event_id)

    def test_read_deploy_event_bridges_shared_engine_event_file(self) -> None:
        with TemporaryDirectory() as tmp:
            events_dir = Path(tmp)
            (events_dir / "42.json").write_text(
                json.dumps(
                    {
                        "event_id": "42",
                        "requested_mode": "targeted_quick",
                        "computed_mode": "targeted_quick",
                        "deployed_sha": TARGET_SHA,
                        "target_sha": TARGET_SHA,
                        "targets": ["weekly-review-web"],
                        "source": "github_actions",
                        "requested_by": "weekly_review_coordinator",
                        "preflight": {"disk_used_percent": 40.0},
                        "rollback_status": "not_needed",
                        "final_health": "healthy",
                        "started_at": "2026-07-10T00:00:00+00:00",
                        "completed_at": "2026-07-10T00:00:02+00:00",
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(ops, "DEPLOY_EVENTS_DIR", events_dir, create=True),
                patch.object(ops, "_run", side_effect=AssertionError("shared event file should satisfy status read")),
            ):
                event = ops.read_deploy_event(42)

        self.assertEqual(42, event["id"])
        self.assertEqual("targeted_quick", event["deploy_mode"])
        self.assertEqual("succeeded", event["status"])
        self.assertEqual(TARGET_SHA, event["commit_sha"])
        self.assertEqual(2.0, event["duration_seconds"])
        self.assertEqual("github_actions", event["metadata"]["source"])
        self.assertEqual("weekly_review_coordinator", event["metadata"]["requested_by"])

    def test_command_error_summary_prefers_traceback_exception_tail(self) -> None:
        text = "\n".join(
            [
                "Traceback (most recent call last):",
                "  File \"/app/scripts/record_deploy_event.py\", line 1, in <module>",
                "    main()",
                "RuntimeError: deploy_events relation is unavailable",
            ]
        )

        self.assertEqual(
            ops._summarize_command_error(text),
            "RuntimeError: deploy_events relation is unavailable",
        )

    def _post_json(self, path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        return self._request_json("POST", path, payload)

    def _get_json(self, path: str) -> tuple[int, dict[str, object]]:
        return self._request_json("GET", path, None)

    def _request_json(
        self, method: str, path: str, payload: dict[str, object] | None
    ) -> tuple[int, dict[str, object]]:
        with _ops_server():
            body = json.dumps(payload).encode("utf-8") if payload is not None else None
            connection = HTTPConnection("127.0.0.1", _ops_server.port, timeout=5)
            try:
                connection.request(
                    method,
                    path,
                    body=body,
                    headers={
                        "Authorization": "Bearer test-token",
                        "Content-Type": "application/json",
                    },
                )
                response = connection.getresponse()
                response_body = response.read().decode("utf-8")
                return response.status, json.loads(response_body)
            finally:
                connection.close()


@contextmanager
def _ops_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ops.OpsRequestHandler)
    _ops_server.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    with patch.object(ops, "TOKEN", "test-token"):
        thread.start()
        try:
            yield
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


_ops_server.port = 0


if __name__ == "__main__":
    unittest.main()
