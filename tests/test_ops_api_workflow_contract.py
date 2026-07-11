from __future__ import annotations

from pathlib import Path
from unittest import TestCase


class OpsApiWorkflowContractTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = Path(".github/workflows/ops-api.yml").read_text(encoding="utf-8")

    def test_bootstraps_full_control_plane_from_exact_workflow_sha(self) -> None:
        self.assertIn("scripts/bootstrap_ops_api_v2_on_ecs.sh", self.workflow)
        self.assertIn('BOOTSTRAP_REF="${{ github.sha }}"', self.workflow)
        self.assertIn("/opt/investment-ops", self.workflow)

    def test_does_not_copy_single_ops_module_into_application_directory(self) -> None:
        self.assertNotIn('sudo cp "$UPLOAD_DIR/ecs_ops_api.py"', self.workflow)
        self.assertNotIn('source: "scripts/ecs_ops_api.py', self.workflow)

    def test_private_health_verification_reads_root_environment_with_sudo(self) -> None:
        self.assertIn("Verify private Ops API health", self.workflow)
        self.assertIn("sudo /bin/bash -c", self.workflow)
        self.assertNotIn(
            'if [ -f /etc/investment-knowledge/ops-api.env ]; then\n              . /etc/investment-knowledge/ops-api.env',
            self.workflow,
        )
