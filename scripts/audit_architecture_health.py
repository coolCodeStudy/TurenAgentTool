from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path


CONTRACT_PATH = Path("docs/architecture/architecture-contract.md")
PACKAGE_NAME = "investment_knowledge_mcp"
ALLOWED_ACCESS_CLASSES = frozenset({"public_read", "protected", "public_read_protected_write"})
MODULE_OWNERS = {
    "investment_knowledge_mcp.command_router": "Command Workbench Feature Coordinator",
    "investment_knowledge_mcp.command_workbench": "Command Workbench Feature Coordinator",
    "investment_knowledge_mcp.daily_market_brief": "Daily Market Brief Feature Coordinator",
    "investment_knowledge_mcp.research.official_sources": "Research workflow Feature Coordinator",
    "investment_knowledge_mcp.repository": "Global PM / Architecture & Code Health Agent",
    "investment_knowledge_mcp.weekly_review": "Weekly Review Feature Coordinator",
    "investment_knowledge_mcp.weekly_review_web": "Frontend Experience System Feature Coordinator",
}


@dataclass(frozen=True)
class Finding:
    id: str
    severity: str
    kind: str
    evidence: tuple[str, ...]
    owner: str
    slice: str
    verification: str


@dataclass(frozen=True)
class RouteDeclaration:
    route: str
    owner_module: str
    access_class: str
    contract_test: str


def collect_python_modules(package_root: Path) -> tuple[dict[str, set[str]], list[Finding]]:
    graph: dict[str, set[str]] = {}
    findings: list[Finding] = []
    for source_path in sorted(package_root.rglob("*.py")):
        module = _module_name(package_root, source_path)
        graph[module] = set()
        try:
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        except (OSError, SyntaxError) as error:
            findings.append(
                Finding(
                    id=f"ARCH-PARSE-{module}",
                    severity="P1",
                    kind="unparseable_module",
                    evidence=(f"{source_path}: {error}",),
                    owner="Feature Coordinator for affected module",
                    slice=f"Repair syntax or source encoding in {source_path}",
                    verification=f"python3 -m py_compile {source_path}",
                )
            )
            continue
        graph[module].update(_imports_from_tree(tree))
    modules = set(graph)
    for imports in graph.values():
        imports.intersection_update(modules)
    return graph, findings


def find_import_cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    cycles: set[tuple[str, ...]] = set()
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            start = visiting.index(module)
            cycles.add(_canonical_cycle(visiting[start:] + [module]))
            return
        if module in visited:
            return
        visiting.append(module)
        for dependency in sorted(graph.get(module, ())):
            visit(dependency)
        visiting.pop()
        visited.add(module)

    for module in sorted(graph):
        visit(module)
    return sorted(cycles)


def module_size_findings(module_lines: dict[str, int], *, max_lines: int = 1_000) -> list[Finding]:
    findings: list[Finding] = []
    for module, line_count in sorted(module_lines.items()):
        if line_count <= max_lines:
            continue
        findings.append(
            Finding(
                id=f"ARCH-SIZE-001:{module}",
                severity="P1",
                kind="module_responsibility_concentration",
                evidence=(f"{module}: {line_count:,} lines (report threshold: {max_lines:,})",),
                owner=MODULE_OWNERS.get(module, "Global PM / Architecture & Code Health Agent"),
                slice="Extract one independently testable responsibility while preserving public contracts.",
                verification="python3 scripts/audit_architecture_health.py --repo . --format json",
            )
        )
    return findings


def parse_route_contract(contract_path: Path) -> tuple[RouteDeclaration, ...]:
    declarations: list[RouteDeclaration] = []
    for line in contract_path.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) != 6 or not cells[1].startswith("`"):
            continue
        declarations.append(
            RouteDeclaration(
                route=cells[1].strip("`"),
                owner_module=cells[2].strip("`"),
                access_class=cells[3].strip("`"),
                contract_test=cells[4].strip("`"),
            )
        )
    return tuple(declarations)


def route_findings(
    declarations: tuple[RouteDeclaration, ...],
    *,
    available_modules: set[str],
    repo_root: Path,
    existing_files: set[Path] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for declaration in sorted(declarations, key=lambda item: item.route):
        if declaration.access_class not in ALLOWED_ACCESS_CLASSES:
            findings.append(_route_finding("ARCH-ROUTE-000", "invalid_access_class", declaration, "Declare an allowed access class."))
        if declaration.owner_module not in available_modules:
            findings.append(_route_finding("ARCH-ROUTE-001", "missing_owner_module", declaration, "Point at an existing module or create the declared owner."))
        test_path = Path(declaration.contract_test)
        exists = test_path in existing_files if existing_files is not None else (repo_root / test_path).is_file()
        if not exists:
            findings.append(_route_finding("ARCH-ROUTE-002", "missing_contract_test", declaration, "Add the declared route contract test or correct its path."))
    return sorted(findings, key=lambda finding: (finding.id, finding.evidence))


def audit_repository(repo: Path) -> list[Finding]:
    package_root = repo / PACKAGE_NAME
    contract_path = repo / CONTRACT_PATH
    if not package_root.is_dir():
        raise ValueError(f"package root is missing: {package_root}")
    if not contract_path.is_file():
        raise ValueError(f"architecture contract is missing: {contract_path}")
    graph, findings = collect_python_modules(package_root)
    findings.extend(module_size_findings(_module_line_counts(package_root)))
    for cycle in find_import_cycles(graph):
        findings.append(
            Finding(
                id="ARCH-IMPORT-001",
                severity="P1",
                kind="import_cycle",
                evidence=(" -> ".join(cycle),),
                owner="Feature Coordinator for affected modules",
                slice="Break the import cycle through an explicit lower-level boundary.",
                verification="python3 scripts/audit_architecture_health.py --repo . --format json",
            )
        )
    findings.extend(route_findings(parse_route_contract(contract_path), available_modules=set(graph), repo_root=repo))
    return sorted(findings, key=lambda finding: (finding.id, finding.evidence))


def render_json(findings: list[Finding]) -> str:
    summary = {"p0": sum(finding.severity == "P0" for finding in findings), "p1": sum(finding.severity == "P1" for finding in findings)}
    return json.dumps({"format_version": 1, "summary": summary, "findings": [asdict(finding) for finding in findings]}, ensure_ascii=False, indent=2)


def render_markdown(findings: list[Finding]) -> str:
    lines = ["# Architecture Health Audit", "", f"P0: {sum(finding.severity == 'P0' for finding in findings)}", f"P1: {sum(finding.severity == 'P1' for finding in findings)}", ""]
    if not findings:
        lines.append("No findings.")
    for finding in findings:
        lines.extend((f"## {finding.id}: {finding.kind}", f"- Severity: {finding.severity}", f"- Evidence: {'; '.join(finding.evidence)}", f"- Owner: {finding.owner}", f"- Smallest slice: {finding.slice}", f"- Verification: {finding.verification}", ""))
    return "\n".join(lines)


def _module_name(package_root: Path, source_path: Path) -> str:
    relative = source_path.relative_to(package_root).with_suffix("")
    parts = (PACKAGE_NAME, *relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports_from_tree(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name == PACKAGE_NAME or alias.name.startswith(f"{PACKAGE_NAME}."))
        elif isinstance(node, ast.ImportFrom) and node.module and (node.module == PACKAGE_NAME or node.module.startswith(f"{PACKAGE_NAME}.")):
            imports.add(node.module)
    return imports


def _module_line_counts(package_root: Path) -> dict[str, int]:
    return {
        _module_name(package_root, source_path): len(source_path.read_text(encoding="utf-8").splitlines())
        for source_path in sorted(package_root.rglob("*.py"))
    }


def _canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
    core = cycle[:-1]
    rotations = [core[index:] + core[:index] for index in range(len(core))]
    selected = min(rotations)
    return tuple(selected + [selected[0]])


def _route_finding(identifier: str, kind: str, declaration: RouteDeclaration, slice_text: str) -> Finding:
    return Finding(
        id=identifier,
        severity="P1",
        kind=kind,
        evidence=(f"{declaration.route}: owner={declaration.owner_module}, access={declaration.access_class}, test={declaration.contract_test}",),
        owner="Feature Coordinator for declared browser route",
        slice=slice_text,
        verification="python3 scripts/audit_architecture_health.py --repo . --format json",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit repository architecture contracts without network or credentials.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    try:
        findings = audit_repository(args.repo.resolve())
    except ValueError as error:
        parser.error(str(error))
    print(render_json(findings) if args.format == "json" else render_markdown(findings))


if __name__ == "__main__":
    main()
