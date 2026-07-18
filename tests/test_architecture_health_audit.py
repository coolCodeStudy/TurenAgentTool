from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

try:
    from scripts import audit_architecture_health
except ModuleNotFoundError:
    RouteDeclaration = None
    find_import_cycles = None
    module_size_findings = None
    render_json = None
    route_findings = None
else:
    RouteDeclaration = audit_architecture_health.RouteDeclaration
    collect_python_modules = audit_architecture_health.collect_python_modules
    find_import_cycles = audit_architecture_health.find_import_cycles
    module_size_findings = getattr(audit_architecture_health, "module_size_findings", None)
    render_json = audit_architecture_health.render_json
    route_findings = audit_architecture_health.route_findings

try:
    from scripts.install_architecture_code_health_skill import check_skill, install_skill
except (ImportError, ModuleNotFoundError):
    check_skill = None
    install_skill = None


class ArchitectureSkillCheckTests(TestCase):
    def test_matching_local_skill_is_current(self) -> None:
        self.assertIsNotNone(check_skill, "check_skill must be implemented")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.md"
            destination = root / "destination.md"
            source.write_text("tracked skill", encoding="utf-8")
            destination.write_text("tracked skill", encoding="utf-8")

            result = check_skill(source, destination)

        self.assertEqual(0, result.exit_code)
        self.assertEqual("local skill matches tracked source", result.message)

    def test_stale_or_missing_local_skill_is_reported_without_writing(self) -> None:
        self.assertIsNotNone(check_skill, "check_skill must be implemented")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.md"
            stale = root / "stale.md"
            missing = root / "missing" / "SKILL.md"
            source.write_text("tracked skill", encoding="utf-8")
            stale.write_text("old skill", encoding="utf-8")

            stale_result = check_skill(source, stale)
            missing_result = check_skill(source, missing)

            self.assertFalse(missing.parent.exists())

        self.assertEqual(1, stale_result.exit_code)
        self.assertEqual("local skill is stale", stale_result.message)
        self.assertEqual(1, missing_result.exit_code)
        self.assertEqual("local skill is missing", missing_result.message)

    def test_explicit_install_copies_only_the_tracked_skill(self) -> None:
        self.assertIsNotNone(install_skill, "install_skill must be implemented")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.md"
            destination = root / "local" / "SKILL.md"
            source.write_text("tracked skill", encoding="utf-8")

            result = install_skill(source, destination)

            self.assertEqual(0, result.exit_code)
            self.assertEqual("local skill installed from tracked source", result.message)
            self.assertEqual("tracked skill", destination.read_text(encoding="utf-8"))


class ArchitectureAuditTests(TestCase):
    def test_gateway_controller_web_import_cycle_is_absent_in_repository_graph(self) -> None:
        package_root = Path(__file__).resolve().parents[1] / "investment_knowledge_mcp"
        graph, parse_findings = collect_python_modules(package_root)

        self.assertEqual([], parse_findings)
        self.assertIn(
            "investment_knowledge_mcp.app_gateway",
            graph["investment_knowledge_mcp.weekly_review_web"],
        )
        matching = [
            cycle
            for cycle in find_import_cycles(graph)
            if "investment_knowledge_mcp.app_gateway" in cycle
            and "investment_knowledge_mcp.weekly_review_web" in cycle
        ]

        self.assertEqual([], matching)

    def test_large_module_is_report_only_with_a_bounded_slice(self) -> None:
        self.assertIsNotNone(module_size_findings, "module_size_findings must be implemented")

        findings = module_size_findings(
            {"investment_knowledge_mcp.large": 1_201, "investment_knowledge_mcp.small": 30},
            max_lines=1_000,
        )

        self.assertEqual(["ARCH-SIZE-001:investment_knowledge_mcp.large"], [finding.id for finding in findings])
        self.assertEqual("P1", findings[0].severity)
        self.assertEqual("module_responsibility_concentration", findings[0].kind)
        self.assertIn("1,201 lines", findings[0].evidence[0])
        self.assertEqual("Global PM / Architecture & Code Health Agent", findings[0].owner)

    def test_import_cycle_detection_is_sorted_and_reports_no_cycle_when_acyclic(self) -> None:
        self.assertIsNotNone(find_import_cycles, "find_import_cycles must be implemented")

        self.assertEqual([], find_import_cycles({"a": {"b"}, "b": set()}))
        self.assertEqual(
            [("a", "b", "a")],
            find_import_cycles({"b": {"a"}, "a": {"b"}}),
        )
        self.assertEqual(
            [("a", "b", "c", "a")],
            find_import_cycles({"a": {"b"}, "b": {"c"}, "c": {"a"}}),
        )

    def test_route_contract_findings_name_missing_test_and_owner(self) -> None:
        self.assertIsNotNone(RouteDeclaration, "RouteDeclaration must be implemented")
        self.assertIsNotNone(route_findings, "route_findings must be implemented")
        declarations = (
            RouteDeclaration(
                route="/command",
                owner_module="investment_knowledge_mcp.command_workbench",
                access_class="protected",
                contract_test="tests/test_web_experience.py",
            ),
            RouteDeclaration(
                route="/new",
                owner_module="investment_knowledge_mcp.unknown",
                access_class="public_read",
                contract_test="tests/test_missing_contract.py",
            ),
        )

        findings = route_findings(
            declarations,
            available_modules={"investment_knowledge_mcp.command_workbench"},
            repo_root=Path("/fixture"),
            existing_files={Path("tests/test_web_experience.py")},
        )

        self.assertEqual(
            ["ARCH-ROUTE-001", "ARCH-ROUTE-002"],
            [finding.id for finding in findings],
        )
        self.assertEqual("missing_owner_module", findings[0].kind)
        self.assertEqual("missing_contract_test", findings[1].kind)

    def test_json_output_has_stable_top_level_contract(self) -> None:
        self.assertIsNotNone(render_json, "render_json must be implemented")
        payload = json.loads(render_json([]))

        self.assertEqual(1, payload["format_version"])
        self.assertEqual({"p0": 0, "p1": 0}, payload["summary"])
        self.assertEqual([], payload["findings"])
