from __future__ import annotations

import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent
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

    def test_control_plane_mutations_share_production_deploy_concurrency(self) -> None:
        self.assertIn("concurrency:", self.workflow)
        self.assertIn("group: production-deploy", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_control_plane_mutations_use_the_host_deploy_lock(self) -> None:
        self.assertIn('DEPLOY_LOCK_PATH="$APP_DIR/shared/deploy.lock"', self.workflow)
        shared_directory = 'install -d -m 0755 "$APP_DIR/shared"'
        self.assertIn(shared_directory, self.workflow)
        self.assertLess(
            self.workflow.index(shared_directory),
            self.workflow.index("run_under_deploy_lock()"),
        )
        self.assertIn("stop_ops_api_under_deploy_lock", self.workflow)
        self.assertIn(
            'flock --exclusive --wait 600 "$DEPLOY_LOCK_PATH"',
            self.workflow,
        )
        self.assertNotIn(
            "run_under_deploy_lock systemctl stop investment-ops-api.service || true",
            self.workflow,
        )
        self.assertNotIn(
            "run_under_deploy_lock systemctl disable --now investment-ops-api.service || true",
            self.workflow,
        )
        install_case = self.workflow.split("install)", 1)[1].split(";;", 1)[0]
        self.assertLess(
            install_case.index("stop_ops_api_under_deploy_lock"),
            install_case.index("bootstrap_ops_api_v2_on_ecs.sh"),
        )

    def test_ops_stop_handoff_distinguishes_absent_unit_from_real_failure(self) -> None:
        helper = self.workflow.split("mutate_ops_api_service_under_deploy_lock()", 1)[1].split("}", 1)[0]
        self.assertIn(
            "systemctl show investment-ops-api.service --property=LoadState --value",
            helper,
        )
        self.assertIn('"not-found"', helper)
        self.assertIn('"loaded"', helper)
        self.assertIn("systemctl stop investment-ops-api.service", helper)
        self.assertIn("systemctl is-active --quiet investment-ops-api.service", helper)
        self.assertNotIn("systemctl stop investment-ops-api.service || true", helper)

    def test_service_query_failure_propagates_from_stop_handoff_shell(self) -> None:
        result, commands = self._run_service_handoff("stop", "query-failure")

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(
            ["show investment-ops-api.service --property=LoadState --value"],
            commands,
        )

    def test_absent_unit_is_idempotent_for_stop_and_disable_shell(self) -> None:
        result, commands = self._run_service_handoff("disable", "not-found")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["show investment-ops-api.service --property=LoadState --value"],
            commands,
        )

    def test_ops_update_documents_two_phase_serialization_without_nested_lock(self) -> None:
        self.assertIn("Phase 1: drain and stop the existing Ops API while holding the host lock", self.workflow)
        self.assertIn("Phase 2: bootstrap reacquires the host lock after the Ops API is down", self.workflow)
        install_case = self.workflow.split("install)", 1)[1].split(";;", 1)[0]
        self.assertEqual(1, install_case.count("stop_ops_api_under_deploy_lock"))
        self.assertNotIn("run_under_deploy_lock bash", install_case)

    def _run_service_handoff(
        self,
        action: str,
        behavior: str,
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        function = self._workflow_function("mutate_ops_api_service_under_deploy_lock")
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            log_path = directory / "systemctl.log"
            systemctl = directory / "systemctl"
            systemctl.write_text(
                dedent(
                    """\
                    #!/usr/bin/env bash
                    printf '%s\\n' "$*" >> "$SYSTEMCTL_LOG"
                    case "$1:$SYSTEMCTL_BEHAVIOR" in
                      show:query-failure) exit 5 ;;
                      show:not-found) printf 'not-found\\n'; exit 0 ;;
                      show:loaded) printf 'loaded\\n'; exit 0 ;;
                      stop:*) exit 0 ;;
                      is-active:*) exit 3 ;;
                      disable:*) exit 0 ;;
                      *) exit 9 ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            script = dedent(
                f"""\
                run_under_deploy_lock() {{ "$@"; }}
                {function}
                mutate_ops_api_service_under_deploy_lock {action}
                """
            )
            result = subprocess.run(
                ["bash", "-c", script],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{directory}:{os.environ.get('PATH', '')}",
                    "SYSTEMCTL_LOG": str(log_path),
                    "SYSTEMCTL_BEHAVIOR": behavior,
                },
            )
            commands = log_path.read_text(encoding="utf-8").splitlines()
        return result, commands

    def _workflow_function(self, name: str) -> str:
        start = self.workflow.index(f"{name}()")
        end = self.workflow.index("\n            }", start) + len("\n            }")
        return dedent(self.workflow[start:end])

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
