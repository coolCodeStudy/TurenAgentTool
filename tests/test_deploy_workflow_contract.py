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
        setup = self.workflow.index("docker/setup-buildx-action@v3")
        build = self.workflow.index("docker/build-push-action@v6")
        self.assertLess(setup, build)

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

    def test_uses_private_ssh_tunnel_instead_of_public_ops_api_variable(self) -> None:
        self.assertNotIn("vars.OPS_API_URL", self.workflow)
        self.assertNotIn("OPS_API_URL and OPS_API_TOKEN", self.workflow)
        self.assertEqual(3, self.workflow.count("sshpass -e ssh"))
        self.assertEqual(3, self.workflow.count("ECS_SSH_KNOWN_HOSTS: ${{ secrets.ECS_SSH_KNOWN_HOSTS }}"))
        self.assertEqual(3, self.workflow.count("StrictHostKeyChecking=yes"))
        self.assertEqual(3, self.workflow.count("--connect-timeout 3 --max-time 5"))
        self.assertIn("OPS_API_URL: http://127.0.0.1:18767", self.workflow)

    def test_private_tunnel_precedes_every_ops_api_call(self) -> None:
        plan_tunnel = self.workflow.index("Open private Ops API SSH tunnel")
        plan_call = self.workflow.index("Build server-authoritative deployment plan")
        shared_job = self.workflow.index("  shared_deploy:")
        shared_tunnel = self.workflow.index("Open private Ops API SSH tunnel", shared_job)
        shared_call = self.workflow.index("Delegate deployment to Ops API", shared_job)
        full_job = self.workflow.index("  full_image:")
        full_tunnel = self.workflow.index("Open private Ops API SSH tunnel", full_job)
        full_call = self.workflow.index("Delegate full image deployment to Ops API", full_job)

        self.assertLess(plan_tunnel, plan_call)
        self.assertLess(shared_tunnel, shared_call)
        self.assertLess(full_tunnel, full_call)

    def test_actions_uses_dedicated_ops_credential_without_command_token_fallback(self) -> None:
        self.assertIn("OPS_API_TOKEN: ${{ secrets.OPS_API_TOKEN }}", self.workflow)
        self.assertNotIn("secrets.OPS_API_TOKEN || secrets.COMMAND_API_TOKEN", self.workflow)
        self.assertNotIn("OPS_API_TOKEN or COMMAND_API_TOKEN is required", self.workflow)

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
        self.assertIn(
            "dist/investment-knowledge-app-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}.tar.gz",
            self.workflow,
        )
        self.assertNotIn("dist/investment-knowledge-release.tar.gz", self.workflow)
        self.assertNotIn("investment-knowledge-images.tar.gz", self.workflow)

    def test_full_image_binds_archive_sha256_into_ops_payload(self) -> None:
        full_block = self.workflow[self.workflow.index("  full_image:"):]

        self.assertIn('archive_sha256="$(sha256sum "$archive" | awk \'{print $1}\')"', full_block)
        self.assertIn('echo "archive_sha256=$archive_sha256" >> "$GITHUB_OUTPUT"', full_block)
        self.assertIn("ARCHIVE_SHA256: ${{ steps.archive.outputs.archive_sha256 }}", full_block)
        self.assertIn('"archive_sha256": os.environ["ARCHIVE_SHA256"]', full_block)

    def test_request_only_shared_deploy_does_not_checkout_code(self) -> None:
        shared_start = self.workflow.index("  shared_deploy:")
        full_start = self.workflow.index("  full_image:")
        shared_block = self.workflow[shared_start:full_start]

        self.assertNotIn("actions/checkout", shared_block)
        self.assertNotIn("docker/build", shared_block)

    def test_full_image_preserves_github_buildx_cache_and_archive_transport(self) -> None:
        full_block = self.workflow[self.workflow.index("  full_image:"):]

        self.assertIn("docker/setup-buildx-action@v3", full_block)
        self.assertIn("docker/build-push-action@v6", full_block)
        self.assertIn("cache-from: type=gha", full_block)
        self.assertIn("cache-to: type=gha,mode=max", full_block)
        self.assertIn("docker save investment-knowledge-app:${{ github.sha }}", full_block)

    def test_ops_payloads_include_provenance_requester_and_daily_market_route(self) -> None:
        self.assertEqual(2, self.workflow.count('"source": "github_actions"'))
        self.assertEqual(2, self.workflow.count('f"github_run_{os.environ[\'GITHUB_RUN_ID\']}"'))
        self.assertGreaterEqual(self.workflow.count('"/daily-market-brief"'), 2)
        self.assertGreaterEqual(
            self.workflow.count("GITHUB_RUN_ID: ${{ github.run_id }}"),
            3,
        )

    def test_full_preflight_uses_isolated_run_scoped_tmp_checkout(self) -> None:
        full_start = self.workflow.index("  full_image:")
        preflight_start = self.workflow.index("Remote deploy_preflight.py resource gate", full_start)
        upload_start = self.workflow.index("Upload immutable application image archive", preflight_start)
        block = self.workflow[preflight_start:upload_start]

        self.assertIn("mktemp -d", block)
        self.assertIn("/tmp/investment-preflight-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}", block)
        self.assertIn("trap", block)
        self.assertIn("git clone", block)
        self.assertIn("checkout --detach \"$TARGET_SHA\"", block)
        self.assertNotIn("/opt/investment-knowledge-repo", block)
        self.assertNotIn("git -C \"$DEPLOY_REPO_DIR\" fetch", block)

    def test_full_image_always_cleans_only_the_exact_run_archive(self) -> None:
        full_block = self.workflow[self.workflow.index("  full_image:"):]
        delegate = full_block.index("Delegate full image deployment to Ops API")
        cleanup = full_block.index("Cleanup exact remote image archive")
        cleanup_block = full_block[cleanup:]

        self.assertLess(delegate, cleanup)
        self.assertIn("if: always()", cleanup_block)
        self.assertIn(
            "/tmp/investment-knowledge-app-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}.tar.gz",
            cleanup_block,
        )
        self.assertIn('rm -f -- "$REMOTE_ARCHIVE"', cleanup_block)
        self.assertNotIn("rm -rf /tmp", cleanup_block)
        self.assertNotIn("find /tmp", cleanup_block)
