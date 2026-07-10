from __future__ import annotations

import unittest

from scripts.classify_deploy_change import classify_changed_files


class DeployChangeClassifierTests(unittest.TestCase):
    def test_docs_and_agent_governance_changes_do_not_deploy(self) -> None:
        result = classify_changed_files(
            [
                "AGENTS.md",
                "docs/project-management/Agent-Operating-Model-Roadmap.md",
                "scripts/evaluate_agent_flow_cases.py",
                ".github/workflows/deploy.yml",
            ]
        )

        self.assertEqual("no_deploy", result.deploy_mode)

    def test_runtime_python_changes_use_quick_deploy(self) -> None:
        result = classify_changed_files(
            [
                "investment_knowledge_mcp/command_workbench.py",
                "scripts/deploy_from_local_checkout.sh",
            ]
        )

        self.assertEqual("quick", result.deploy_mode)

    def test_image_or_dependency_changes_require_full_deploy(self) -> None:
        result = classify_changed_files(["requirements.txt"])

        self.assertEqual("full", result.deploy_mode)

    def test_tests_only_changes_do_not_deploy(self) -> None:
        result = classify_changed_files(["tests/test_weekly_review_holder_attribution.py"])

        self.assertEqual("no_deploy", result.deploy_mode)

    def test_empty_auto_diff_defaults_to_full_for_safety(self) -> None:
        result = classify_changed_files([])

        self.assertEqual("full", result.deploy_mode)


if __name__ == "__main__":
    unittest.main()
