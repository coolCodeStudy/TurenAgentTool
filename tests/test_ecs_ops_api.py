from __future__ import annotations

from contextlib import contextmanager, nullcontext
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
import hashlib
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
from scripts.deploy_state import DeploymentEvent, DeploymentState, write_event, write_state
from scripts.deploy_support import CommandResult


TARGET_SHA = "b" * 40
PREVIOUS_SHA = "a" * 40


def _archive_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def _managed_archive(sha: str = TARGET_SHA):
    with NamedTemporaryFile(
        prefix=f"investment-knowledge-app-{sha}-test-",
        suffix=".tar.gz",
        dir="/tmp",
        delete=False,
    ) as handle:
        handle.write(b"candidate image archive")
        path = Path(handle.name)
    try:
        yield path
    finally:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            path.rmdir()


class OpsApiInstallLayoutTests(unittest.TestCase):
    def test_ops_server_and_installer_require_dedicated_ops_credential(self) -> None:
        source = Path("scripts/ecs_ops_api.py").read_text(encoding="utf-8")
        installer = Path("scripts/install_ops_api_on_ecs.sh").read_text(encoding="utf-8")
        bootstrap = Path("scripts/bootstrap_ops_api_v2_on_ecs.sh").read_text(encoding="utf-8")

        self.assertIn('TOKEN = os.getenv("OPS_API_TOKEN") or ""', source)
        self.assertNotIn("COMMAND_API_TOKEN", source)
        self.assertIn('OPS_API_TOKEN=${OPS_API_TOKEN:-}', installer)
        self.assertIn("OPS_API_TOKEN is required.", installer)
        self.assertNotIn("COMMAND_API_TOKEN", installer)
        self.assertIn('OPS_API_TOKEN="$OPS_API_TOKEN"', bootstrap)

    def test_default_artifact_staging_is_under_independent_ops_home(self) -> None:
        source = Path("scripts/ecs_ops_api.py").read_text(encoding="utf-8")

        self.assertIn('OPS_HOME = Path(os.getenv("OPS_HOME", "/opt/investment-ops"))', source)
        self.assertIn('str(OPS_HOME / "deploy-artifacts")', source)
        self.assertNotIn('str(APP_ROOT / "shared" / "deploy-artifacts")', source)

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
    def __init__(
        self,
        outcome: DeployOutcome | None = None,
        *,
        write_success_event: bool = True,
    ) -> None:
        self.requests: list[DeployRequest] = []
        self.write_success_event = write_success_event
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
        if (
            self.write_success_event
            and self.outcome.ok
            and self.outcome.mode is not DeployMode.NO_DEPLOY
            and request.external_event_id
            and not (
                ops.DEPLOY_EVENTS_DIR / f"{request.external_event_id}.json"
            ).exists()
        ):
            write_event(
                ops.DEPLOY_EVENTS_DIR,
                DeploymentEvent(
                    event_id=request.external_event_id,
                    requested_mode=request.requested_mode.value,
                    computed_mode=self.outcome.mode.value,
                    deployed_sha=self.outcome.target_sha,
                    target_sha=self.outcome.target_sha,
                    changed_image_inputs=(),
                    targets=request.requested_targets,
                    preflight={},
                    archive_bytes=None,
                    image_count_before=0,
                    image_count_after=0,
                    disk_used_before=0.0,
                    disk_used_after=0.0,
                    target_durations_ms={target: 1 for target in request.requested_targets},
                    rollback_status="not_needed|cleanup:complete|archive_cleanup:complete",
                    cleanup_reclaimed_bytes=0,
                    emergency_override=False,
                    emergency_reason=None,
                    final_health="healthy",
                    started_at="2026-07-10T00:00:00+00:00",
                    completed_at="2026-07-10T00:00:30+00:00",
                    source=request.source,
                    requested_by=request.requested_by,
                    feature_routes=request.feature_routes,
                    stability_seconds=30,
                    affected_services=self.outcome.activated_services,
                    route_smoke_checks=("weekly-review-web:/health",),
                    archive_sha256=request.archive_sha256,
                    artifact_cleanup_status=(
                        "complete"
                        if request.archive_path is not None
                        else "not_applicable"
                    ),
                ),
            )
        return self.outcome


class EcsOpsApiDeployTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events_tmp = TemporaryDirectory()
        self.events_patch = patch.object(
            ops,
            "DEPLOY_EVENTS_DIR",
            Path(self.events_tmp.name),
            create=True,
        )
        self.events_patch.start()
        self.ops_home = Path(self.events_tmp.name) / "ops-home"
        self.ops_home.mkdir(mode=0o700)
        self.ops_home_patch = patch.object(ops, "OPS_HOME", self.ops_home, create=True)
        self.ops_home_patch.start()
        self.artifacts_dir = self.ops_home / "deploy-artifacts"
        self.artifacts_patch = patch.object(
            ops,
            "DEPLOY_ARTIFACTS_DIR",
            self.artifacts_dir,
            create=True,
        )
        self.artifacts_patch.start()

    def tearDown(self) -> None:
        self.artifacts_patch.stop()
        self.ops_home_patch.stop()
        self.events_patch.stop()
        self.events_tmp.cleanup()

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
            event_id = payload["data"]["deploy_event_id"]
            get_status, get_payload = self._get_json(
                f"/ops/deploy-status?id={event_id}"
            )

        self.assertEqual(422, status)
        self.assertEqual("deployment_rejected", payload["error"])
        self.assertEqual(200, get_status)
        self.assertEqual(payload["data"]["evidence"], get_payload["data"])

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
                archive_context = (
                    _managed_archive() if expected_mode is DeployMode.FULL_IMAGE else nullcontext(None)
                )
                with archive_context as archive:
                    if archive is not None:
                        payload["ref"] = TARGET_SHA
                        payload["archive_path"] = str(archive)
                        payload["archive_sha256"] = _archive_sha256(archive)

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

        with _managed_archive() as archive:
            with (
                patch.object(ops, "_resolve_deploy_source_policy", return_value=TARGET_SHA, create=True),
                patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
            ):
                status, response = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "full",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                        "archive_sha256": _archive_sha256(archive),
                    }
                )

        self.assertEqual(200, status)
        self.assertTrue(response["ok"])
        self.assertEqual(DeployMode.FULL_IMAGE, engine.requests[0].requested_mode)

    def test_full_image_archive_path_is_sha_bound_regular_tmp_file(self) -> None:
        engine = FakeEngine()
        outside_dir = TemporaryDirectory()
        outside = Path(outside_dir.name) / f"investment-knowledge-app-{TARGET_SHA}-outside.tar.gz"
        outside.write_bytes(b"outside")
        try:
            with _managed_archive(PREVIOUS_SHA) as mismatched, _managed_archive() as symlink_path, _managed_archive() as directory_path:
                symlink_target = Path(symlink_path.parent) / f"symlink-target-{symlink_path.name}"
                symlink_target.write_bytes(b"target")
                symlink_path.unlink()
                symlink_path.symlink_to(symlink_target)
                directory_path.unlink()
                directory_path.mkdir()
                cases = (
                    "relative-archive.tar.gz",
                    str(outside),
                    str(mismatched),
                    str(symlink_path),
                    str(directory_path),
                )
                for archive_path in cases:
                    with self.subTest(archive_path=archive_path):
                        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
                            status, payload = self._post_json(
                                "/deploy",
                                {
                                    "ref": TARGET_SHA,
                                    "mode": "full_image",
                                    "targets": ["weekly-review-web"],
                                    "archive_path": archive_path,
                                    "archive_sha256": "0" * 64,
                                },
                            )
                        self.assertEqual(422, status)
                        self.assertEqual("deployment_rejected", payload["error"])
                self.assertEqual([], engine.requests)
                self.assertTrue(outside.exists())
                self.assertTrue(symlink_target.exists())
                symlink_target.unlink()
        finally:
            outside_dir.cleanup()

    def test_full_image_requires_explicit_sha_even_with_valid_archive(self) -> None:
        engine = FakeEngine()

        with _managed_archive() as archive:
            with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": "main",
                        "mode": "full_image",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                    },
                )

        self.assertEqual(422, status)
        self.assertEqual("deployment_rejected", payload["error"])
        self.assertEqual([], engine.requests)

    def test_full_image_requires_lowercase_archive_sha256_before_dispatch(self) -> None:
        engine = FakeEngine()
        invalid_digests = (None, "A" * 64, "a" * 63, "not-a-digest")

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            for digest in invalid_digests:
                with self.subTest(digest=digest):
                    with _managed_archive() as archive:
                        payload = {
                            "ref": TARGET_SHA,
                            "mode": "full_image",
                            "targets": ["weekly-review-web"],
                            "archive_path": str(archive),
                        }
                        if digest is not None:
                            payload["archive_sha256"] = digest
                        status, response = self._post_json("/deploy", payload)

                    self.assertEqual(422, status)
                    self.assertEqual("deployment_rejected", response["error"])

        self.assertEqual([], engine.requests)

    def test_digest_mismatch_rejects_claim_before_engine_dispatch(self) -> None:
        engine = FakeEngine()
        with _managed_archive() as archive:
            with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "full_image",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                        "archive_sha256": "0" * 64,
                    },
                )

        self.assertEqual(503, status)
        self.assertEqual("deployment_artifact_claim_failed", payload["error"])
        self.assertEqual([], engine.requests)
        self.assertFalse(any(self.artifacts_dir.iterdir()))

    def test_sensitive_feature_route_is_rejected_before_dispatch_without_leak(self) -> None:
        engine = FakeEngine()

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            status, payload = self._post_json(
                "/deploy",
                {
                    "ref": TARGET_SHA,
                    "mode": "targeted_quick",
                    "targets": ["weekly-review-web"],
                    "feature_routes": ["/health?access_token=do-not-leak"],
                },
            )

        self.assertEqual(422, status)
        self.assertEqual("deployment_rejected", payload["error"])
        self.assertEqual([], engine.requests)
        self.assertNotIn("do-not-leak", json.dumps(payload))

    def test_noncanonical_or_control_feature_routes_are_rejected_before_dispatch(self) -> None:
        engine = FakeEngine()
        invalid_routes = (
            " /health",
            "/health ",
            "/health\x00hidden",
            "/health\tnext",
            "/weekly-review//detail",
            "/weekly-review/../health",
            "/café",
        )

        with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
            for route in invalid_routes:
                with self.subTest(route=repr(route)):
                    status, payload = self._post_json(
                        "/deploy",
                        {
                            "ref": TARGET_SHA,
                            "mode": "targeted_quick",
                            "targets": ["weekly-review-web"],
                            "feature_routes": [route],
                        },
                    )
                    self.assertEqual(422, status)
                    self.assertEqual("deployment_rejected", payload["error"])

        self.assertEqual([], engine.requests)

    def test_missing_success_event_is_audit_blocked_without_fabricated_evidence(self) -> None:
        engine = FakeEngine(write_success_event=False)

        with (
            patch.object(ops, "_new_deploy_event_id", return_value=42),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, response = self._post_json(
                "/deploy",
                {
                    "ref": TARGET_SHA,
                    "mode": "targeted_quick",
                    "targets": ["weekly-review-web"],
                    "source": "github_actions",
                    "requested_by": "github_run_123",
                },
            )

        self.assertEqual(503, status)
        self.assertEqual("audit_persistence_failed", response["error"])
        self.assertEqual(
            "blocked_with_owner",
            response["data"]["return_to_coordinator"]["decision"],
        )
        self.assertNotIn("deploy_event_id", response["data"])
        self.assertNotIn("status_url", response["data"])
        self.assertFalse((Path(self.events_tmp.name) / "42.json").exists())

    def test_engine_build_failure_precedes_event_allocation_and_cleans_upload(self) -> None:
        with _managed_archive() as archive:
            with (
                patch.object(ops, "_new_deploy_event_id", wraps=ops._new_deploy_event_id) as event_id,
                patch.object(
                    ops,
                    "build_deployment_engine",
                    side_effect=RuntimeError("TOKEN=engine-secret"),
                    create=True,
                ),
            ):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "full_image",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                        "archive_sha256": _archive_sha256(archive),
                    },
                )
                self.assertFalse(archive.exists())

        self.assertEqual(503, status)
        self.assertEqual("deployment_engine_unavailable", payload["error"])
        self.assertEqual("removed", payload["data"]["archive_cleanup"])
        self.assertNotIn("deploy_event_id", payload["data"])
        self.assertNotIn("status_url", payload["data"])
        self.assertNotIn("engine-secret", json.dumps(payload))
        event_id.assert_not_called()

    def test_busy_request_claims_then_cleans_only_its_private_archive(self) -> None:
        engine = FakeEngine()
        self.assertTrue(ops.DEPLOY_MUTEX.acquire(blocking=False))
        try:
            with _managed_archive() as archive:
                with (
                    patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                    patch.object(
                        ops,
                        "_claim_validated_upload",
                        wraps=ops._claim_validated_upload,
                    ) as claim,
                    patch.object(
                        ops,
                        "_cleanup_validated_upload",
                        side_effect=AssertionError("busy path must not delete the shared upload"),
                    ),
                ):
                    status, payload = self._post_json(
                        "/deploy",
                        {
                            "ref": TARGET_SHA,
                            "mode": "full_image",
                            "targets": ["weekly-review-web"],
                            "archive_path": str(archive),
                            "archive_sha256": _archive_sha256(archive),
                        },
                    )
                    self.assertFalse(archive.exists())
                    claim.assert_called_once()
        finally:
            ops.DEPLOY_MUTEX.release()

        self.assertEqual(409, status)
        self.assertEqual("deployment_busy", payload["error"])
        self.assertEqual("removed", payload["data"]["archive_cleanup"])
        self.assertEqual([], engine.requests)
        self.assertFalse(any(self.artifacts_dir.iterdir()))

    def test_duplicate_claim_collision_never_deletes_winning_artifact(self) -> None:
        with _managed_archive() as archive:
            digest = _archive_sha256(archive)
            first = ops._validate_full_image_archive(TARGET_SHA, archive, digest)
            second = ops._validate_full_image_archive(TARGET_SHA, archive, digest)
            with (
                patch.object(ops.time, "time_ns", return_value=123456789),
                patch.object(ops.secrets, "token_hex", return_value="fixedcollision"),
            ):
                winner = ops._claim_validated_upload(first)
                with self.assertRaises(ops.DeployApiError):
                    ops._claim_validated_upload(second)

            self.assertTrue(winner.path.is_file())
            self.assertEqual(b"candidate image archive", winner.path.read_bytes())
            self.assertEqual([winner.path], list(self.artifacts_dir.iterdir()))
            self.assertEqual("removed", ops._cleanup_claimed_upload(winner))

    def test_claim_copies_to_new_inode_and_source_fd_mutation_cannot_change_private_bytes(self) -> None:
        with _managed_archive() as archive:
            original = archive.read_bytes()
            digest = _archive_sha256(archive)
            validated = ops._validate_full_image_archive(TARGET_SHA, archive, digest)
            with archive.open("r+b") as writable_source:
                source_inode = os.fstat(writable_source.fileno()).st_ino
                claimed = ops._claim_validated_upload(validated)
                writable_source.seek(0)
                writable_source.write(b"mutated after claim")
                writable_source.truncate()
                writable_source.flush()

            self.assertNotEqual(source_inode, claimed.inode)
            self.assertEqual(original, claimed.path.read_bytes())
            self.assertEqual(digest, _archive_sha256(claimed.path))
            self.assertEqual(digest, claimed.archive_sha256)
            self.assertEqual("removed", ops._cleanup_claimed_upload(claimed))

    def test_claim_stream_copy_does_not_depend_on_cross_filesystem_hard_link(self) -> None:
        with _managed_archive() as archive:
            digest = _archive_sha256(archive)
            validated = ops._validate_full_image_archive(TARGET_SHA, archive, digest)
            with patch.object(
                ops.os,
                "link",
                side_effect=OSError("EXDEV simulated cross-filesystem boundary"),
            ):
                claimed = ops._claim_validated_upload(validated)

            self.assertEqual(digest, _archive_sha256(claimed.path))
            self.assertEqual("removed", ops._cleanup_claimed_upload(claimed))

    def test_claim_failure_with_private_cleanup_failure_is_typed_and_blocked(self) -> None:
        engine = FakeEngine()
        def fail_artifact_fchmod(fd: int, mode: int) -> None:
            del fd, mode
            raise OSError("TOKEN=chmod-secret")

        try:
            with _managed_archive() as archive:
                with (
                    patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                    patch.object(ops.os, "fchmod", side_effect=fail_artifact_fchmod),
                    patch.object(ops, "_remove_exact_private_artifact", return_value="failed"),
                ):
                    status, payload = self._post_json(
                        "/deploy",
                        {
                            "ref": TARGET_SHA,
                            "mode": "full_image",
                            "targets": ["weekly-review-web"],
                            "archive_path": str(archive),
                            "archive_sha256": _archive_sha256(archive),
                        },
                    )

            self.assertEqual(503, status)
            self.assertEqual("deployment_artifact_cleanup_failed", payload["error"])
            self.assertEqual("blocked_with_owner", payload["data"]["return_to_coordinator"]["decision"])
            basename = payload["data"]["artifact_basename"]
            self.assertRegex(basename, rf"investment-knowledge-app-{TARGET_SHA}-.*\.tar\.gz")
            self.assertIn(basename, payload["data"]["return_to_coordinator"]["action"])
            self.assertEqual("failed", payload["data"]["archive_cleanup"])
            self.assertNotIn("chmod-secret", json.dumps(payload))
            self.assertEqual([], engine.requests)
        finally:
            if self.artifacts_dir.exists():
                for artifact in self.artifacts_dir.iterdir():
                    artifact.unlink(missing_ok=True)

    def test_claim_rejects_symlinked_ops_home(self) -> None:
        engine = FakeEngine()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_home = root / "real-home"
            real_home.mkdir()
            symlink_home = root / "ops-home"
            symlink_home.symlink_to(real_home, target_is_directory=True)
            with _managed_archive() as archive:
                with (
                    patch.object(ops, "DEPLOY_ARTIFACTS_DIR", symlink_home / "deploy-artifacts"),
                    patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                ):
                    status, payload = self._post_json(
                        "/deploy",
                        {
                            "ref": TARGET_SHA,
                            "mode": "full_image",
                            "targets": ["weekly-review-web"],
                            "archive_path": str(archive),
                            "archive_sha256": _archive_sha256(archive),
                        },
                    )

        self.assertEqual(503, status)
        self.assertEqual("deployment_artifact_claim_failed", payload["error"])
        self.assertEqual([], engine.requests)

    def test_claim_rejects_staging_parent_not_owned_by_service_uid(self) -> None:
        engine = FakeEngine()
        with _managed_archive() as archive:
            with (
                patch.object(ops, "_effective_service_uid", return_value=os.geteuid() + 1, create=True),
                patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
            ):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "full_image",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                        "archive_sha256": _archive_sha256(archive),
                    },
                )

        self.assertEqual(503, status)
        self.assertEqual("deployment_artifact_claim_failed", payload["error"])
        self.assertEqual([], engine.requests)

    def test_event_allocation_failure_after_claim_cleans_private_artifact(self) -> None:
        engine = FakeEngine()
        with _managed_archive() as archive:
            with (
                patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                patch.object(
                    ops,
                    "_new_deploy_event_id",
                    side_effect=RuntimeError("TOKEN=event-secret"),
                ),
            ):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "full_image",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                        "archive_sha256": _archive_sha256(archive),
                    },
                )
                self.assertFalse(archive.exists())

        self.assertEqual(503, status)
        self.assertEqual("deployment_event_allocation_failed", payload["error"])
        self.assertNotIn("deploy_event_id", payload["data"])
        self.assertNotIn("status_url", payload["data"])
        self.assertNotIn("event-secret", json.dumps(payload))
        self.assertEqual([], engine.requests)
        self.assertFalse(any(self.artifacts_dir.glob("*.tar.gz")))

    def test_archive_swap_during_atomic_claim_leaves_no_private_symlink(self) -> None:
        engine = FakeEngine()
        victim = Path("/tmp") / f"claim-victim-{os.getpid()}-{threading.get_ident()}"
        victim.write_bytes(b"victim survives")
        real_open = os.open

        try:
            with _managed_archive() as archive:
                swapped = False

                def swap_then_open(
                    path: object,
                    flags: int,
                    mode: int = 0o777,
                ) -> int:
                    nonlocal swapped
                    source_path = Path(path)
                    if source_path == archive and not swapped:
                        swapped = True
                        source_path.unlink()
                        source_path.symlink_to(victim)
                    return real_open(path, flags, mode)

                with (
                    patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                    patch.object(ops, "_new_deploy_event_id", wraps=ops._new_deploy_event_id) as event_id,
                    patch.object(ops.os, "open", side_effect=swap_then_open),
                ):
                    status, payload = self._post_json(
                        "/deploy",
                        {
                            "ref": TARGET_SHA,
                            "mode": "full_image",
                            "targets": ["weekly-review-web"],
                            "archive_path": str(archive),
                            "archive_sha256": _archive_sha256(archive),
                        },
                    )

            self.assertEqual(503, status)
            self.assertEqual("deployment_artifact_claim_failed", payload["error"])
            self.assertEqual(b"victim survives", victim.read_bytes())
            self.assertFalse(any(self.artifacts_dir.iterdir()))
            self.assertEqual([], engine.requests)
            event_id.assert_not_called()
        finally:
            victim.unlink(missing_ok=True)

    def test_host_lock_rejection_cleans_claimed_private_archive_and_records_it(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha="",
                mode=DeployMode.FULL_IMAGE,
                activated_services=(),
                rolled_back_services=(),
                message="deployment lock could not be acquired",
                archive_cleanup="deferred_lock_unavailable",
            )
        )

        with _managed_archive() as archive:
            with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "full_image",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                        "archive_sha256": _archive_sha256(archive),
                    },
                )
                self.assertFalse(archive.exists())

        claimed = engine.requests[0].archive_path
        self.assertIsNotNone(claimed)
        self.assertEqual(self.artifacts_dir, claimed.parent)
        self.assertEqual(0o700, self.artifacts_dir.stat().st_mode & 0o777)
        self.assertFalse(claimed.exists())
        self.assertEqual(409, status)
        self.assertEqual(
            "removed_after_lock_rejection",
            payload["data"]["outcome"]["archive_cleanup"],
        )
        self.assertEqual(
            "removed_after_lock_rejection",
            payload["data"]["evidence"]["metadata"]["archive_cleanup"],
        )

    def test_tmp_path_swap_after_claim_cannot_change_loaded_or_deleted_artifact(self) -> None:
        victim = Path("/tmp") / f"artifact-victim-{os.getpid()}-{threading.get_ident()}"
        victim.write_bytes(b"victim survives")
        original_path: Path | None = None

        class SwapEngine:
            def __init__(self) -> None:
                self.requests: list[DeployRequest] = []
                self.loaded = b""

            def deploy(self, request: DeployRequest) -> DeployOutcome:
                self.requests.append(request)
                assert request.archive_path is not None
                assert original_path is not None
                original_path.symlink_to(victim)
                self.loaded = request.archive_path.read_bytes()
                return DeployOutcome(
                    ok=False,
                    target_sha=TARGET_SHA,
                    mode=DeployMode.FULL_IMAGE,
                    activated_services=(),
                    rolled_back_services=(),
                    message="deployment resource preflight failed",
                )

        engine = SwapEngine()
        try:
            with _managed_archive() as archive:
                original_path = archive
                with patch.object(ops, "build_deployment_engine", return_value=engine, create=True):
                    status, _payload = self._post_json(
                        "/deploy",
                        {
                            "ref": TARGET_SHA,
                            "mode": "full_image",
                            "targets": ["weekly-review-web"],
                            "archive_path": str(archive),
                            "archive_sha256": _archive_sha256(archive),
                        },
                    )
                self.assertEqual(422, status)
                self.assertEqual(b"candidate image archive", engine.loaded)
                self.assertTrue(original_path.is_symlink())
                self.assertEqual(b"victim survives", victim.read_bytes())
                claimed = engine.requests[0].archive_path
                self.assertIsNotNone(claimed)
                self.assertEqual(self.artifacts_dir, claimed.parent)
                self.assertFalse(claimed.exists())
        finally:
            if original_path is not None and original_path.is_symlink():
                original_path.unlink()
            victim.unlink(missing_ok=True)

    def test_no_deploy_persists_truthful_not_required_terminal_event(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=True,
                target_sha=TARGET_SHA,
                mode=DeployMode.NO_DEPLOY,
                activated_services=(),
                rolled_back_services=(),
                message="server classification requires no deployment",
            )
        )

        with (
            patch.object(ops, "_new_deploy_event_id", return_value=43),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, response = self._post_json(
                "/deploy",
                {"ref": TARGET_SHA, "mode": "no_deploy", "targets": []},
            )
            get_status, get_response = self._get_json("/ops/deploy-status?id=43")

        self.assertEqual(200, status)
        self.assertEqual(200, get_status)
        evidence = response["data"]["evidence"]
        self.assertEqual("not_required", evidence["status"])
        self.assertEqual("not_applicable", evidence["stable_health"]["status"])
        self.assertEqual(0, evidence["stable_health"]["window_seconds"])
        self.assertEqual(0, evidence["stable_health"]["observed_seconds"])
        self.assertEqual("not_applicable", evidence["route_smoke"]["status"])
        self.assertEqual(evidence, get_response["data"])

    def test_event_persistence_failure_returns_typed_audit_blocker_without_status_claim(self) -> None:
        engine = FakeEngine(
            DeployOutcome(
                ok=False,
                target_sha="",
                mode=DeployMode.TARGETED_QUICK,
                activated_services=(),
                rolled_back_services=(),
                message="deployment lock could not be acquired",
                archive_cleanup="deferred_lock_unavailable",
            )
        )

        with (
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
            patch.object(ops, "write_event", side_effect=OSError("TOKEN=do-not-leak"), create=True),
        ):
            status, payload = self._post_json(
                "/deploy",
                {"ref": TARGET_SHA, "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )

        self.assertEqual(503, status)
        self.assertEqual("audit_persistence_failed", payload["error"])
        self.assertEqual("blocked_with_owner", payload["data"]["return_to_coordinator"]["decision"])
        self.assertNotIn("deploy_event_id", payload["data"])
        self.assertNotIn("status_url", payload["data"])
        self.assertNotIn("do-not-leak", json.dumps(payload))

    def test_cleanup_event_rewrite_failure_is_audit_incomplete_and_blocked(self) -> None:
        event_id = 44
        (Path(self.events_tmp.name) / f"{event_id}.json").write_text(
            json.dumps(
                {
                    "event_id": str(event_id),
                    "requested_mode": "targeted_quick",
                    "computed_mode": "targeted_quick",
                    "deployed_sha": TARGET_SHA,
                    "target_sha": TARGET_SHA,
                    "targets": ["weekly-review-web"],
                    "affected_services": ["weekly-review-web"],
                    "feature_routes": ["/daily-market-brief"],
                    "preflight": {"available_memory_bytes": 1024**3},
                    "rollback_status": "not_needed|cleanup:pending|archive_cleanup:pending",
                    "final_health": "healthy",
                    "stability_seconds": 30,
                    "started_at": "2026-07-10T00:00:00+00:00",
                    "completed_at": "2026-07-10T00:00:30+00:00",
                }
            ),
            encoding="utf-8",
        )
        engine = FakeEngine(
            DeployOutcome(
                ok=True,
                target_sha=TARGET_SHA,
                mode=DeployMode.TARGETED_QUICK,
                activated_services=("weekly-review-web",),
                rolled_back_services=(),
                message="deployment completed and remained healthy; post-success cleanup incomplete",
                audit_status="cleanup_event_failed",
                cleanup_status="release_completed|image_not_applicable|archive_not_applicable|event_failed",
            )
        )

        with (
            patch.object(ops, "_new_deploy_event_id", return_value=event_id),
            patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
        ):
            status, payload = self._post_json(
                "/deploy",
                {"ref": TARGET_SHA, "mode": "targeted_quick", "targets": ["weekly-review-web"]},
            )
            get_status, get_payload = self._get_json(f"/ops/deploy-status?id={event_id}")

        self.assertEqual(503, status)
        self.assertEqual("audit_incomplete", payload["error"])
        self.assertEqual("audit_incomplete", payload["data"]["evidence"]["status"])
        self.assertEqual("healthy", payload["data"]["evidence"]["stable_health"]["status"])
        self.assertEqual("blocked_with_owner", payload["data"]["return_to_coordinator"]["decision"])
        self.assertEqual(200, get_status)
        self.assertEqual("audit_incomplete", get_payload["data"]["status"])

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
            event_id = payload["data"]["deploy_event_id"]
            get_status, get_payload = self._get_json(
                f"/ops/deploy-status?id={event_id}"
            )

        self.assertEqual(409, status)
        self.assertEqual("deployment_busy", payload["error"])
        self.assertEqual(1, len(engine.requests))
        self.assertEqual(200, get_status)
        self.assertEqual(payload["data"]["evidence"], get_payload["data"])
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

    def test_two_failed_cleanup_attempts_persist_audit_blocker_for_post_and_get(self) -> None:
        event_id = 91
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
        calls = 0

        def fail_cleanup(_upload: object) -> str:
            nonlocal calls
            calls += 1
            return "failed"

        try:
            with _managed_archive() as archive:
                digest = _archive_sha256(archive)
                with (
                    patch.object(ops, "_new_deploy_event_id", return_value=event_id),
                    patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                    patch.object(ops, "_cleanup_claimed_upload", side_effect=fail_cleanup),
                ):
                    status, payload = self._post_json(
                        "/deploy",
                        {
                            "ref": TARGET_SHA,
                            "mode": "full_image",
                            "targets": ["weekly-review-web"],
                            "archive_path": str(archive),
                            "archive_sha256": digest,
                        },
                    )
                    get_status, get_payload = self._get_json(
                        f"/ops/deploy-status?id={event_id}"
                    )

            self.assertEqual(2, calls)
            self.assertEqual(503, status)
            self.assertEqual("deployment_artifact_cleanup_failed", payload["error"])
            self.assertEqual("blocked_with_owner", payload["data"]["return_to_coordinator"]["decision"])
            self.assertEqual("audit_incomplete", payload["data"]["evidence"]["status"])
            self.assertEqual("failed", payload["data"]["evidence"]["metadata"]["artifact_cleanup_status"])
            self.assertEqual(200, get_status)
            self.assertEqual(payload["data"]["evidence"], get_payload["data"])
        finally:
            if self.artifacts_dir.exists():
                for artifact in self.artifacts_dir.iterdir():
                    artifact.unlink(missing_ok=True)

    def test_cleanup_retry_success_is_persisted_before_accept_and_route(self) -> None:
        event_id = 92
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
        real_cleanup = ops._cleanup_claimed_upload
        calls = 0

        def retry_cleanup(upload: object) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                return "failed"
            return real_cleanup(upload)

        with _managed_archive() as archive:
            digest = _archive_sha256(archive)
            with (
                patch.object(ops, "_new_deploy_event_id", return_value=event_id),
                patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                patch.object(ops, "_cleanup_claimed_upload", side_effect=retry_cleanup),
            ):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "full_image",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                        "archive_sha256": digest,
                    },
                )
                get_status, get_payload = self._get_json(
                    f"/ops/deploy-status?id={event_id}"
                )

        self.assertEqual(2, calls)
        self.assertEqual(200, status)
        self.assertEqual("accept_and_route", payload["data"]["return_to_coordinator"]["decision"])
        self.assertEqual("removed_after_dispatch", payload["data"]["evidence"]["metadata"]["artifact_cleanup_status"])
        self.assertEqual(200, get_status)
        self.assertEqual(payload["data"]["evidence"], get_payload["data"])

    def test_cleanup_event_update_failure_uses_durable_post_get_audit_overlay(self) -> None:
        event_id = 93
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

        with _managed_archive() as archive:
            digest = _archive_sha256(archive)
            with (
                patch.object(ops, "_new_deploy_event_id", return_value=event_id),
                patch.object(ops, "build_deployment_engine", return_value=engine, create=True),
                patch.object(
                    ops,
                    "update_event_artifact_cleanup",
                    side_effect=OSError("TOKEN=event-rewrite-secret"),
                ),
            ):
                status, payload = self._post_json(
                    "/deploy",
                    {
                        "ref": TARGET_SHA,
                        "mode": "full_image",
                        "targets": ["weekly-review-web"],
                        "archive_path": str(archive),
                        "archive_sha256": digest,
                    },
                )
                get_status, get_payload = self._get_json(
                    f"/ops/deploy-status?id={event_id}"
                )

        self.assertEqual(503, status)
        self.assertEqual("audit_persistence_failed", payload["error"])
        self.assertEqual(event_id, payload["data"]["deploy_event_id"])
        self.assertEqual(
            f"/ops/deploy-status?id={event_id}",
            payload["data"]["status_url"],
        )
        self.assertEqual(
            "blocked_with_owner",
            payload["data"]["return_to_coordinator"]["decision"],
        )
        self.assertEqual("audit_incomplete", payload["data"]["evidence"]["status"])
        self.assertEqual(TARGET_SHA, payload["data"]["evidence"]["commit_sha"])
        self.assertEqual(
            "healthy",
            payload["data"]["evidence"]["stable_health"]["status"],
        )
        self.assertEqual(
            "removed_after_dispatch",
            payload["data"]["evidence"]["metadata"]["artifact_cleanup_status"],
        )
        self.assertEqual(200, get_status)
        self.assertEqual(payload["data"]["evidence"], get_payload["data"])
        overlay = json.loads(
            (Path(self.events_tmp.name) / f"{event_id}.audit-incomplete.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {
                "schema_version": 1,
                "event_id": str(event_id),
                "status": "audit_incomplete",
                "reason": "artifact_cleanup_event_update_failed",
                "artifact_cleanup_status": "removed_after_dispatch",
            },
            overlay,
        )
        self.assertNotIn("event-rewrite-secret", json.dumps(payload))

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

    def test_shared_event_parser_preserves_legacy_archive_cleanup_format(self) -> None:
        event = ops._shared_event_status_payload(
            {
                "requested_mode": "full_image",
                "computed_mode": "full_image",
                "deployed_sha": TARGET_SHA,
                "target_sha": TARGET_SHA,
                "targets": ["weekly-review-web"],
                "rollback_status": "not_needed|cleanup:release_completed|image_completed|archive_removed",
                "final_health": "healthy",
                "started_at": "2026-07-10T00:00:00+00:00",
                "completed_at": "2026-07-10T00:01:00+00:00",
            },
            "42",
        )

        self.assertEqual("removed", event["metadata"]["archive_cleanup"])

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
