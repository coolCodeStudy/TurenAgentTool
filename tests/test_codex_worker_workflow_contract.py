from pathlib import Path
from unittest import TestCase


class CodexWorkerWorkflowContractTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = Path(".github/workflows/codex-worker.yml").read_text(
            encoding="utf-8"
        )

    def test_gate_a_is_an_explicit_read_only_mode(self) -> None:
        self.assertIn("- gate-a", self.workflow)
        self.assertIn("name: Trading Agent Gate A read-only inspection", self.workflow)
        self.assertIn("if: inputs.mode == 'gate-a'", self.workflow)
        self.assertGreaterEqual(
            self.workflow.count("if: inputs.mode != 'gate-a'"),
            2,
        )

    def test_gate_a_does_not_run_host_mutation_steps(self) -> None:
        gate_a = self.workflow.split(
            "name: Trading Agent Gate A read-only inspection", 1
        )[1].split("name: Upload Codex worker files", 1)[0]

        for forbidden in (
            "sudo cp",
            "sudo install",
            "sudo mkdir",
            "systemctl start",
            "systemctl stop",
            "systemctl restart",
            "systemctl enable",
            "systemctl disable",
            "docker compose",
        ):
            self.assertNotIn(forbidden, gate_a)

    def test_gate_a_probes_ephemeral_search_only_codex_contract(self) -> None:
        gate_a = self.workflow.split(
            "name: Trading Agent Gate A read-only inspection", 1
        )[1].split("name: Upload Codex worker files", 1)[0]

        for required in (
            "login status",
            "--ephemeral",
            "--ignore-user-config",
            "--disable shell_tool",
            "--search",
            "--sandbox read-only",
            "native web search",
            "/etc/hostname",
        ):
            self.assertIn(required, gate_a)

    def test_gate_a_reports_boundaries_without_printing_auth_material(self) -> None:
        gate_a = self.workflow.split(
            "name: Trading Agent Gate A read-only inspection", 1
        )[1].split("name: Upload Codex worker files", 1)[0]

        for required in (
            "CODEX_HOME",
            "CODEX_BIN",
            "ActiveState",
            "SubState",
            "ExecStart",
            "nproc",
            "free -b",
            "df -B1",
            "127.0.0.1:8010/command",
            "InvestmentKnowledgeAccess",
        ):
            self.assertIn(required, gate_a)
        self.assertNotIn("cat \"$WORKER_ENV\"", gate_a)
        self.assertNotIn("CODEX_WORKER_DATABASE_URL=", gate_a)
        self.assertNotIn("OPENAI_API_KEY=", gate_a)
