from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "docs/project-management/Feature-Registry.md"
ACCEPTANCE_QUEUE_PATH = PROJECT_ROOT / "docs/project-management/Acceptance-Queue.md"
PRODUCT_DIR = PROJECT_ROOT / "docs/product"
TECHPLAN_DIR = PROJECT_ROOT / "docs/techplans"
DAILY_LOG_DIR = PROJECT_ROOT / "docs/每日工作记录"


@dataclass(frozen=True)
class RegistryRow:
    feature: str
    product_doc: str
    prd_status: str
    technical_plan: str
    technical_status: str
    implementation: str
    evidence: str
    user_acceptance: str
    known_gaps: str
    next_action: str


@dataclass(frozen=True)
class AcceptanceRow:
    item_id: str
    feature: str
    surface: str
    status: str
    severity: str
    evidence: str
    findings: str
    next_action: str


@dataclass(frozen=True)
class Finding:
    category: str
    severity: str
    item: str
    detail: str
    next_action: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit delivery coordination, registry, acceptance, and documentation gates.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when blockers are found.",
    )
    parser.add_argument(
        "--handoff",
        action="store_true",
        help="Include worktree cleanliness checks for pre-handoff use.",
    )
    args = parser.parse_args()

    rows = parse_registry(REGISTRY_PATH)
    acceptance_rows = parse_acceptance_queue(ACCEPTANCE_QUEUE_PATH)
    findings = audit(rows, acceptance_rows, include_handoff=args.handoff)

    grouped = group_findings(findings)
    report = {
        "summary": {category: len(items) for category, items in grouped.items()},
        "findings": {category: [asdict(item) for item in items] for category, items in grouped.items()},
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(grouped)

    if args.strict and grouped.get("blocker"):
        raise SystemExit(1)


def audit(
    registry_rows: list[RegistryRow],
    acceptance_rows: list[AcceptanceRow],
    *,
    include_handoff: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(audit_routine_daily_logs())
    findings.extend(audit_registry_links(registry_rows))
    findings.extend(audit_prd_registration(registry_rows))

    for row in registry_rows:
        if row.prd_status in {"draft", "needs_review"}:
            findings.append(
                Finding(
                    "needs_product_decision",
                    "major",
                    row.feature,
                    f"PRD status is {row.prd_status}.",
                    row.next_action or "Resolve product decisions before implementation.",
                )
            )

        if row.prd_status == "ready" and row.technical_status == "missing":
            findings.append(
                Finding(
                    "needs_engineering",
                    "major",
                    row.feature,
                    "Ready PRD has no registered technical plan.",
                    row.next_action or "Create a technical plan before implementation.",
                )
            )

        if row.technical_status in {"ready", "partially_implemented"} and row.implementation in {
            "not_started",
            "in_progress",
            "needs_review",
        }:
            findings.append(
                Finding(
                    "needs_engineering",
                    "major",
                    row.feature,
                    (
                        f"Technical status is {row.technical_status}, but implementation is "
                        f"{row.implementation}."
                    ),
                    row.next_action or "Implement or update the delivery state with evidence.",
                )
            )

        if row.technical_status == "partially_implemented":
            tech_path = first_link_path(row.technical_plan, base=REGISTRY_PATH.parent)
            if tech_path and tech_path.exists():
                text = tech_path.read_text(encoding="utf-8")
                if "traceability" not in text.lower():
                    findings.append(
                        Finding(
                            "needs_engineering",
                            "major",
                            row.feature,
                            "Partially implemented technical plan does not mention implementation traceability.",
                            "Add an implementation traceability matrix or record why the plan does not need one.",
                        )
                    )

        if row.implementation == "deployed" and row.evidence not in {"deploy_verified", "test_passed"}:
            findings.append(
                Finding(
                    "blocker",
                    "major",
                    row.feature,
                    f"Implementation is deployed but evidence is {row.evidence}.",
                    "Add deployment or test evidence before presenting the feature as done.",
                )
            )

        if needs_acceptance_queue(row) and not has_acceptance_row(row, acceptance_rows):
            findings.append(
                Finding(
                    "needs_test",
                    "major",
                    row.feature,
                    "User-facing or cloud-served work appears to need an acceptance queue row.",
                    "Add or justify an Acceptance Queue entry before asking for user acceptance.",
                )
            )

    for row in acceptance_rows:
        if row.status in {"failed", "blocked", "needs_retest"}:
            findings.append(
                Finding(
                    "blocker",
                    row.severity or "major",
                    row.feature,
                    f"Acceptance test status is {row.status}.",
                    row.next_action or "Fix or retest before user acceptance.",
                )
            )
        elif row.status == "pending":
            findings.append(
                Finding(
                    "needs_test",
                    row.severity or "major",
                    row.feature,
                    "Independent acceptance testing is pending.",
                    row.next_action or "Run black-box acceptance testing.",
                )
            )

    if include_handoff:
        findings.extend(audit_worktree_cleanliness())

    return findings


def audit_routine_daily_logs() -> list[Finding]:
    if not DAILY_LOG_DIR.exists():
        return []
    files = sorted(path for path in DAILY_LOG_DIR.rglob("*") if path.is_file())
    if not files:
        return []
    relative = ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in files[:5])
    if len(files) > 5:
        relative += f", ... {len(files) - 5} more"
    return [
        Finding(
            "blocker",
            "major",
            "Routine daily logs",
            f"Routine daily log files exist: {relative}.",
            "Move durable content to the correct durable document or remove the routine log files.",
        )
    ]


def audit_registry_links(rows: Iterable[RegistryRow]) -> list[Finding]:
    findings: list[Finding] = []
    for row in rows:
        for label, value in (("Product doc", row.product_doc), ("Technical plan", row.technical_plan)):
            if value in {"missing", "not_applicable"}:
                continue
            for path in link_paths(value, base=REGISTRY_PATH.parent):
                if not path.exists():
                    findings.append(
                        Finding(
                            "docs_cleanup",
                            "major",
                            row.feature,
                            f"{label} link does not resolve: {path.relative_to(PROJECT_ROOT)}.",
                            "Fix the registry link or mark the document status explicitly.",
                        )
                    )
    return findings


def audit_prd_registration(rows: Iterable[RegistryRow]) -> list[Finding]:
    registered = registered_prd_filenames(rows)
    findings: list[Finding] = []
    for path in sorted(PRODUCT_DIR.glob("PRD*.md")):
        if path.name not in registered:
            findings.append(
                Finding(
                    "docs_cleanup",
                    "major",
                    path.name,
                    "PRD file is not represented in the Feature Registry.",
                    "Add a registry row or document why the PRD is not active delivery work.",
                )
            )
    return findings


def audit_worktree_cleanliness() -> list[Finding]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return []
    preview = "; ".join(lines[:8])
    if len(lines) > 8:
        preview += f"; ... {len(lines) - 8} more"
    return [
        Finding(
            "blocker",
            "major",
            "Worktree cleanliness",
            f"Worktree is dirty: {preview}.",
            "Commit, remove, or explicitly explain all dirty files before handoff.",
        )
    ]


def needs_acceptance_queue(row: RegistryRow) -> bool:
    if row.user_acceptance == "not_required":
        return False
    if row.implementation == "deployed":
        return True
    text = " ".join(
        [
            row.feature,
            row.product_doc,
            row.technical_plan,
            row.known_gaps,
            row.next_action,
        ]
    ).lower()
    return any(marker in text for marker in ["web", "cloud", "user-facing", "url"])


def has_acceptance_row(row: RegistryRow, acceptance_rows: Iterable[AcceptanceRow]) -> bool:
    row_tokens = feature_tokens(row.feature)
    for acceptance_row in acceptance_rows:
        acceptance_tokens = feature_tokens(acceptance_row.feature)
        if normalize(row.feature) == normalize(acceptance_row.feature):
            return True
        if len(row_tokens & acceptance_tokens) >= 2:
            return True
    return False


def parse_registry(path: Path) -> list[RegistryRow]:
    rows = parse_table(path, "| Feature | Product Doc | PRD Status |")
    parsed: list[RegistryRow] = []
    for cells in rows:
        if len(cells) != 10:
            raise SystemExit(f"Unexpected registry row shape ({len(cells)} cells): {' | '.join(cells)}")
        parsed.append(RegistryRow(*[clean_cell(cell) for cell in cells]))
    return parsed


def parse_acceptance_queue(path: Path) -> list[AcceptanceRow]:
    if not path.exists():
        return []
    rows = parse_table(path, "| ID | Feature | Surface | Status |")
    parsed: list[AcceptanceRow] = []
    for cells in rows:
        if len(cells) != 8:
            raise SystemExit(f"Unexpected acceptance row shape ({len(cells)} cells): {' | '.join(cells)}")
        parsed.append(AcceptanceRow(*[clean_cell(cell) for cell in cells]))
    return parsed


def parse_table(path: Path, header_prefix: str) -> list[list[str]]:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")

    table_rows: list[list[str]] = []
    in_table = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith(header_prefix):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            if table_rows:
                break
            continue
        table_rows.append(split_markdown_table_row(line))
    return table_rows


def split_markdown_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def feature_tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) >= 3}


def registered_prd_filenames(rows: Iterable[RegistryRow]) -> set[str]:
    filenames: set[str] = set()
    for row in rows:
        for target in re.findall(r"\]\(([^)]+)\)", row.product_doc):
            name = Path(target).name
            if name.startswith("PRD"):
                filenames.add(name)
    return filenames


def link_paths(value: str, *, base: Path) -> list[Path]:
    paths: list[Path] = []
    for target in re.findall(r"\]\(([^)]+)\)", value):
        if target.startswith(("http://", "https://", "#")):
            continue
        paths.append((base / target).resolve())
    return paths


def first_link_path(value: str, *, base: Path) -> Path | None:
    paths = link_paths(value, base=base)
    return paths[0] if paths else None


def group_findings(findings: Iterable[Finding]) -> dict[str, list[Finding]]:
    order = ["blocker", "needs_product_decision", "needs_engineering", "needs_test", "docs_cleanup"]
    grouped = {category: [] for category in order}
    for finding in findings:
        grouped.setdefault(finding.category, []).append(finding)
    return {category: items for category, items in grouped.items() if items}


def print_text_report(grouped: dict[str, list[Finding]]) -> None:
    print("# Delivery State Audit")
    print()
    if not grouped:
        print("- No delivery-state gaps found.")
        return

    for category, findings in grouped.items():
        title = category.replace("_", " ").title()
        print(f"## {title}")
        for finding in findings:
            print(f"- [{finding.severity}] {finding.item}: {finding.detail}")
            if finding.next_action:
                print(f"  Next: {finding.next_action}")
        print()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(1)
