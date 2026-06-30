from __future__ import annotations

import unittest

from scripts.classify_deploy_mode import classify_deploy_mode, classify_file


class DeployModeClassifierTests(unittest.TestCase):
    def test_tests_only_changes_are_quick_compatible(self) -> None:
        mode, classifications = classify_deploy_mode(["tests/test_weekly_review_holder_attribution.py"])

        self.assertEqual(mode, "quick")
        self.assertEqual(classifications[0].deploy_class, "quick")

    def test_docs_and_app_code_are_quick_compatible(self) -> None:
        mode, classifications = classify_deploy_mode(
            [
                "docs/product/Delivery-Coordinator-Protocol.md",
                "investment_knowledge_mcp/weekly_review.py",
                "scripts/deploy_from_local_checkout.sh",
                ".github/workflows/deploy.yml",
                "db/schema.sql",
            ]
        )

        self.assertEqual(mode, "quick")
        self.assertTrue(all(item.deploy_class == "quick" for item in classifications))

    def test_dependency_and_compose_changes_require_full_deploy(self) -> None:
        for path in ["Dockerfile", "requirements.txt", "docker-compose.prod.yml"]:
            with self.subTest(path=path):
                self.assertEqual(classify_file(path).deploy_class, "full")

    def test_mixed_changes_require_full_deploy(self) -> None:
        mode, classifications = classify_deploy_mode(
            ["tests/test_weekly_review_holder_attribution.py", "requirements.txt"]
        )

        self.assertEqual(mode, "full")
        self.assertEqual([item.deploy_class for item in classifications], ["quick", "full"])

    def test_unknown_files_require_full_deploy(self) -> None:
        mode, classifications = classify_deploy_mode(["docker-compose.yml"])

        self.assertEqual(mode, "full")
        self.assertEqual(classifications[0].reason, "unclassified production-impact risk")

    def test_empty_change_set_requires_full_deploy(self) -> None:
        mode, classifications = classify_deploy_mode([])

        self.assertEqual(mode, "full")
        self.assertEqual(classifications, [])


if __name__ == "__main__":
    unittest.main()
