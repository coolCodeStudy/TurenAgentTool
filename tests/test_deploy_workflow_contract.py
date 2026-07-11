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

    def test_no_deploy_classification_runs_before_ops_credentials_or_status(self) -> None:
        early = self.workflow.index("Classify credential-free no_deploy plan")
        authoritative = self.workflow.index("Build server-authoritative deployment plan")
        early_block = self.workflow[early:authoritative]

        self.assertLess(early, self.workflow.index("OPS_API_TOKEN"))
        self.assertLess(early, self.workflow.index("/deploy/status"))
        self.assertNotIn("OPS_API_TOKEN", early_block)
        self.assertNotIn("/deploy/status", early_block)
        self.assertIn("steps.early_plan.outputs.mode != 'no_deploy'", self.workflow)
        self.assertIn('if [ "$REQUESTED_MODE" = "no_deploy" ]; then', early_block)

    def test_auto_push_plan_uses_server_authoritative_current_sha(self) -> None:
        early = self.workflow.index("Classify credential-free no_deploy plan")
        authoritative = self.workflow.index("Build server-authoritative deployment plan")
        early_block = self.workflow[early:authoritative]
        authoritative_block = self.workflow[authoritative:]

        self.assertNotIn("--base-sha \"$GITHUB_EVENT_BEFORE\"", early_block)
        self.assertNotIn('early_mode', early_block)
        self.assertIn("/deploy/status", authoritative_block)
        self.assertIn("--base-sha \"$base_sha\"", authoritative_block)

    def test_full_image_uploads_only_immutable_app_image_archive(self) -> None:
        self.assertIn("dist/investment-knowledge-app-${{ github.sha }}.tar.gz", self.workflow)
        self.assertNotIn("dist/investment-knowledge-release.tar.gz", self.workflow)
        self.assertNotIn("investment-knowledge-images.tar.gz", self.workflow)
