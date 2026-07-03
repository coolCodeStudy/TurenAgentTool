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
    parser.add_argument(
        "--feature",
        help="Filter findings to one feature name, PRD, technical plan, or acceptance queue item.",
    )
    parser.add_argument(
        "--handoff-packet",
        metavar="FEATURE",
        help="Print a Delivery Coordinator handoff packet for the named feature.",
    )
    parser.add_argument(
        "--dispatch-prompt",
        metavar="FEATURE",
        help="Print the next-role prompt suitable for Delivery Coordinator dispatch.",
    )
    args = parser.parse_args()

    rows = parse_registry(REGISTRY_PATH)
    acceptance_rows = parse_acceptance_queue(ACCEPTANCE_QUEUE_PATH)
    findings = audit(rows, acceptance_rows, include_handoff=args.handoff)

    if args.handoff_packet or args.dispatch_prompt:
        query = args.handoff_packet or args.dispatch_prompt
        row = find_registry_row(rows, query)
        if row is None:
            raise SystemExit(f"No Feature Registry row matched: {query}")
        matching_acceptance = find_acceptance_row(row, acceptance_rows)
        packet = build_handoff_packet(
            row,
            matching_acceptance,
            matching_findings(row, findings),
        )
        if args.dispatch_prompt:
            prompt = build_dispatch_prompt(packet)
            if args.json:
                print(json.dumps({"dispatch_prompt": prompt, "handoff_packet": packet}, ensure_ascii=False, indent=2))
            else:
                print(prompt)
            return
        if args.json:
            print(json.dumps(packet, ensure_ascii=False, indent=2))
        else:
            print_handoff_packet(packet)
        return

    if args.feature:
        rows = [row for row in rows if matches_feature(row, args.feature)]
        matching_features = {row.feature for row in rows}
        matching_acceptance_rows = [
            row
            for row in acceptance_rows
            if matches_acceptance(row, args.feature)
            or any(row_matches_acceptance_feature(registry_row, row) for registry_row in rows)
        ]
        matching_features.update(row.feature for row in matching_acceptance_rows)
        findings = [
            finding
            for finding in findings
            if matches_text(finding.item, args.feature) or finding.item in matching_features
        ]

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
    for acceptance_row in acceptance_rows:
        if row_matches_acceptance_feature(row, acceptance_row):
            return True
    return False


def row_matches_acceptance_feature(row: RegistryRow, acceptance_row: AcceptanceRow) -> bool:
    row_tokens = feature_tokens(row.feature)
    acceptance_tokens = feature_tokens(acceptance_row.feature)
    return normalize(row.feature) == normalize(acceptance_row.feature) or len(row_tokens & acceptance_tokens) >= 2


def find_registry_row(rows: Iterable[RegistryRow], query: str) -> RegistryRow | None:
    exact_matches = [row for row in rows if normalize(row.feature) == normalize(query)]
    if exact_matches:
        return exact_matches[0]
    matches = [row for row in rows if matches_feature(row, query)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        names = ", ".join(row.feature for row in matches)
        raise SystemExit(f"Multiple Feature Registry rows matched {query!r}: {names}")
    return None


def find_acceptance_row(row: RegistryRow, acceptance_rows: Iterable[AcceptanceRow]) -> AcceptanceRow | None:
    matches = [
        acceptance_row
        for acceptance_row in acceptance_rows
        if row_matches_acceptance_feature(row, acceptance_row)
    ]
    if not matches:
        return None
    priority = {
        "failed": 0,
        "blocked": 1,
        "needs_retest": 2,
        "pending": 3,
        "passed": 4,
        "not_required": 5,
    }
    return sorted(matches, key=lambda item: priority.get(item.status, 99))[0]


def matching_findings(row: RegistryRow, findings: Iterable[Finding]) -> list[Finding]:
    row_tokens = feature_tokens(row.feature)
    return [
        finding
        for finding in findings
        if finding.item == row.feature
        or len(row_tokens & feature_tokens(finding.item)) >= 2
    ]


def build_handoff_packet(
    row: RegistryRow,
    acceptance_row: AcceptanceRow | None,
    findings: list[Finding],
) -> dict[str, str]:
    next_owner = infer_next_owner(row, acceptance_row, findings)
    acceptance_required = "yes" if needs_acceptance_queue(row) else "no"
    acceptance_row_ref = (
        f"{acceptance_row.item_id} ({acceptance_row.status}, {acceptance_row.severity})"
        if acceptance_row
        else "not_applicable" if acceptance_required == "no" else "missing"
    )
    blockers = "; ".join(f"{finding.category}: {finding.detail}" for finding in findings)
    if acceptance_row and acceptance_row.status in {"failed", "blocked", "needs_retest", "pending"}:
        blockers = append_text(blockers, f"acceptance: {acceptance_row.status} - {acceptance_row.findings}")

    return {
        "Task": f"Advance {row.feature} to the next delivery state.",
        "Coordinator": "Delivery Coordinator",
        "Current owner": next_owner,
        "Source PRD": row.product_doc,
        "Technical plan": row.technical_plan,
        "Feature Registry row": row.feature,
        "Acceptance Queue row": acceptance_row_ref,
        "Branch or worktree": "Create a dedicated task worktree for non-trivial edits; use main only for lightweight docs/status integration.",
        "Scope": row.next_action or "Review the linked PRD, technical plan, registry row, and acceptance state.",
        "Out of scope": "Do not mark user acceptance as accepted; do not silently change PRD scope; do not create routine daily logs.",
        "Acceptance criteria": "Use the linked PRD acceptance criteria; if missing or unclear, route to Product Agent before implementation.",
        "Verification required": infer_verification_required(row),
        "Acceptance testing required": acceptance_required,
        "Known gaps or blockers": blockers or row.known_gaps or "none registered",
        "User decisions needed": infer_user_decisions(row, findings),
        "Next owner": next_owner,
        "Expected handoff result": infer_expected_handoff(row, acceptance_row, next_owner),
    }


def build_dispatch_prompt(packet: dict[str, str]) -> str:
    role = packet["Next owner"]
    feature = packet["Feature Registry row"]
    sections = [
        f"You are the {role} for {feature}.",
        "",
        "Use the Delivery Handoff packet below as your source of truth.",
        "",
        "Mandatory repo workflow:",
        "- Run `.venv/bin/python scripts/agent_preflight.py` first unless this is a tiny factual check.",
        "- Check `git status --short --branch` before edits.",
        "- Use a dedicated task worktree for non-trivial code, deployment, or broad documentation edits.",
        "- Read the linked PRD, technical plan, Feature Registry row, and Acceptance Queue row when applicable.",
        "- Do not create routine daily logs.",
        "- Do not mark user acceptance as accepted.",
        "- Update Feature Registry, Acceptance Queue, Delivery Queue, or technical-plan traceability when your work changes delivery state.",
        "- For cloud-served or browser-tested work, make a concrete deploy decision before handoff: `self_deploy`, `dispatch_deploy_owner`, `blocked`, or `not_required`; do not use vague owners such as `Coordinator/Ops`, `someone`, `later`, or `after deploy`.",
        "- Run narrow verification and document any verification limit.",
        "- Check `docs/lesson-capture-protocol.md` before handoff; record only durable lessons that pass the quality bar, otherwise state `Lessons: none`.",
        "- Commit and push after completing the work unless explicitly told to keep it local.",
        "- Return your result to the Delivery Coordinator; your pushed branch or final message is a returned role result, not delivery closure.",
        "",
        "Definition of done:",
        "- The expected handoff result below is satisfied or a precise blocker is recorded.",
        "- The worktree is clean or every dirty file is explained.",
        "- The final response states branch, commit SHA, verification, registry/queue updates, remaining gaps, `Lessons recorded: ...` or `Lessons: none; ...`, push result, and worktree cleanliness.",
        "- The final response includes a `Return to Coordinator` block naming the recommended next owner, next handoff, deploy needed yes/no/not_applicable, and deploy decision.",
        "",
        "## Delivery Handoff",
        "",
    ]
    sections.extend(f"- {key}: {value}" for key, value in packet.items())
    return "\n".join(sections)


def infer_next_owner(
    row: RegistryRow,
    acceptance_row: AcceptanceRow | None,
    findings: Iterable[Finding],
) -> str:
    categories = {finding.category for finding in findings}
    if row.prd_status in {"draft", "needs_review", "missing"} or "needs_product_decision" in categories:
        return "Product Agent"
    if acceptance_row and acceptance_row.status in {"failed", "blocked", "needs_retest"}:
        return "Development Agent"
    if row.technical_status == "missing" or row.implementation in {"not_started", "in_progress", "needs_review"}:
        return "Development Agent"
    if acceptance_row and acceptance_row.status == "pending":
        return "Acceptance Testing Agent"
    if needs_acceptance_queue(row) and acceptance_row is None:
        return "Acceptance Testing Agent"
    return "Project Management Agent"


def infer_verification_required(row: RegistryRow) -> str:
    if row.implementation in {"not_started", "in_progress", "needs_review"}:
        return "Define and run the technical-plan verification before handoff."
    if row.implementation == "deployed":
        return "Keep deployment evidence current; run cloud/user-surface checks when behavior changes."
    if row.technical_status == "missing":
        return "Technical plan verification section must be created before implementation."
    return "Run narrow local verification or explain why verification is not applicable."


def infer_user_decisions(row: RegistryRow, findings: Iterable[Finding]) -> str:
    if row.prd_status in {"draft", "needs_review", "missing"}:
        return "Product scope or source-of-truth decision is required."
    if any(finding.category == "needs_product_decision" for finding in findings):
        return "Product decision is required before implementation or acceptance."
    if row.user_acceptance in {"pending", "needs_reacceptance"}:
        return "User acceptance is required only after implementation, verification, and acceptance testing pass."
    return "none registered"


def infer_expected_handoff(
    row: RegistryRow,
    acceptance_row: AcceptanceRow | None,
    next_owner: str,
) -> str:
    if next_owner == "Product Agent":
        return "PRD status is ready, deprecated, superseded, or explicitly blocked with a product decision."
    if next_owner == "Development Agent" and row.technical_status == "missing":
        return "Technical plan is created and Feature Registry is updated."
    if next_owner == "Development Agent":
        return "Implementation or fix is committed, verified, registry is updated, acceptance row is moved to needs_retest when applicable, and deploy decision is explicit."
    if next_owner == "Acceptance Testing Agent":
        status = acceptance_row.status if acceptance_row else "pending"
        return f"Acceptance Queue moves from {status} to passed, failed, or blocked with evidence."
    return "Registry and queue states are reconciled with evidence."


def append_text(prefix: str, suffix: str) -> str:
    return f"{prefix}; {suffix}" if prefix else suffix


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


def matches_feature(row: RegistryRow, query: str) -> bool:
    values = [
        row.feature,
        row.product_doc,
        row.technical_plan,
        row.prd_status,
        row.technical_status,
        row.implementation,
        row.evidence,
        row.user_acceptance,
        row.known_gaps,
        row.next_action,
    ]
    return any(matches_text(value, query) for value in values)


def matches_acceptance(row: AcceptanceRow, query: str) -> bool:
    values = [
        row.item_id,
        row.feature,
        row.surface,
        row.status,
        row.severity,
        row.evidence,
        row.findings,
        row.next_action,
    ]
    return any(matches_text(value, query) for value in values)


def matches_text(value: str, query: str) -> bool:
    return normalize(query) in normalize(value)


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


def print_handoff_packet(packet: dict[str, str]) -> None:
    print("## Delivery Handoff")
    print()
    for key, value in packet.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(1)
