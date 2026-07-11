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

    def test_control_plane_install_is_explicit_to_avoid_business_deploy_races(self) -> None:
        self.assertNotIn("push:", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn('MODE="${{ inputs.mode }}"', self.workflow)

    def test_bootstrap_initializes_deploy_baseline_before_ops_api_install(self) -> None:
        bootstrap = Path("scripts/bootstrap_ops_api_v2_on_ecs.sh").read_text(encoding="utf-8")
        initialize_position = bootstrap.index("bootstrap_deploy_baseline.py")
        install_position = bootstrap.index("install_ops_api_on_ecs.sh")
        self.assertLess(initialize_position, install_position)

    def test_lockout_recovery_is_an_explicit_bootstrap_mode(self) -> None:
        self.assertIn("recover-lockout", self.workflow)
        self.assertIn("RECOVER_DEPLOY_LOCKOUT=true", self.workflow)
        bootstrap = Path("scripts/bootstrap_ops_api_v2_on_ecs.sh").read_text(encoding="utf-8")
        self.assertIn("--recover-lockout", bootstrap)

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
