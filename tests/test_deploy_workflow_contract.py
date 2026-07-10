from __future__ import annotations

from pathlib import Path
from unittest import TestCase


class DeployWorkflowContractTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")

    def test_uses_immutable_sha_image_and_build_cache(self) -> None:
        self.assertIn("investment-knowledge-app:${{ github.sha }}", self.workflow)
        self.assertIn("cache-from: type=gha", self.workflow)
        self.assertIn("cache-to: type=gha,mode=max", self.workflow)

    def test_does_not_bundle_pgvector_or_use_broad_prune(self) -> None:
        self.assertNotIn("docker save pgvector", self.workflow)
        self.assertNotIn("docker system prune", self.workflow)
        self.assertNotIn("docker volume prune", self.workflow)

    def test_runs_remote_preflight_before_archive_upload(self) -> None:
        self.assertLess(self.workflow.index("deploy_preflight.py"), self.workflow.index("scp-action"))

    def test_manual_dispatch_limits_ref_and_carries_emergency_reason(self) -> None:
        self.assertIn("target_ref:", self.workflow)
        self.assertIn("emergency_reason:", self.workflow)
        self.assertIn("main or a 40-character SHA", self.workflow)
        self.assertIn("'^(main|[0-9a-f]{40})$'", self.workflow)

    def test_delegates_non_image_modes_to_ops_api_contract(self) -> None:
        self.assertIn("/deploy/status", self.workflow)
        self.assertIn("/deploy", self.workflow)
        self.assertIn("targeted_quick", self.workflow)
        self.assertIn("config_restart", self.workflow)
        self.assertIn("mode", self.workflow)
        self.assertIn("targets", self.workflow)

    def test_full_image_uploads_only_immutable_app_image_archive(self) -> None:
        self.assertIn("dist/investment-knowledge-app-${{ github.sha }}.tar.gz", self.workflow)
        self.assertNotIn("dist/investment-knowledge-release.tar.gz", self.workflow)
        self.assertNotIn("investment-knowledge-images.tar.gz", self.workflow)
