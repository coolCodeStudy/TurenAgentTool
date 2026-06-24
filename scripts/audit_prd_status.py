from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "docs/project-management/Feature-Registry.md"
PRODUCT_DIR = PROJECT_ROOT / "docs/product"


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit PRD delivery status from Feature Registry and product docs.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Print all registry rows instead of only unfinished PRD work.",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Also print in-progress, draft, and needs-review PRD queues.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    args = parser.parse_args()

    rows = parse_registry(REGISTRY_PATH)
    prd_files = sorted(PRODUCT_DIR.glob("PRD*.md"))
    registered_prds = registered_prd_filenames(rows)
    unregistered_prds = [path for path in prd_files if path.name not in registered_prds]

    report = {
        "not_started_prds": [asdict(row) for row in rows if row.implementation == "not_started"],
        "ready_prds_without_implementation_completion": [
            asdict(row)
            for row in rows
            if row.prd_status == "ready"
            and row.implementation not in {"local_verified", "deployed", "not_applicable"}
            and row.implementation != "not_started"
        ],
        "draft_or_needs_review_prds": [
            asdict(row) for row in rows if row.prd_status in {"draft", "needs_review"}
        ],
        "unregistered_prd_files": [str(path.relative_to(PROJECT_ROOT)) for path in unregistered_prds],
        "all_registry_rows": [asdict(row) for row in rows],
    }

    if args.json:
        if not args.all and not args.review:
            report = {
                "not_started_prds": report["not_started_prds"],
                "unregistered_prd_files": report["unregistered_prd_files"],
            }
        elif not args.all:
            report = {key: value for key, value in report.items() if key != "all_registry_rows"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print_text_report(report, include_review=args.review or args.all, include_all=args.all)


def parse_registry(path: Path) -> list[RegistryRow]:
    if not path.exists():
        raise SystemExit(f"Missing registry: {path}")

    rows: list[RegistryRow] = []
    in_registry_table = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("| Feature | Product Doc | PRD Status |"):
            in_registry_table = True
            continue
        if not in_registry_table:
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            if rows:
                break
            continue

        cells = split_markdown_table_row(line)
        if len(cells) != 10:
            raise SystemExit(f"Unexpected registry row shape ({len(cells)} cells): {line}")
        rows.append(RegistryRow(*[strip_markdown(cell) for cell in cells]))

    return rows


def split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def strip_markdown(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def registered_prd_filenames(rows: Iterable[RegistryRow]) -> set[str]:
    filenames: set[str] = set()
    for row in rows:
        for target in re.findall(r"\]\(([^)]+)\)", row.product_doc):
            name = Path(target).name
            if name.startswith("PRD"):
                filenames.add(name)
    return filenames


def print_text_report(report: dict[str, object], *, include_review: bool, include_all: bool) -> None:
    print("# PRD Status Audit")
    print()
    print_section("Not Started PRDs", report["not_started_prds"])
    print_unregistered(report["unregistered_prd_files"])
    if include_review:
        print_section("Ready PRDs Without Implementation Completion", report["ready_prds_without_implementation_completion"])
        print_section("Draft Or Needs-Review PRDs", report["draft_or_needs_review_prds"])
    if include_all:
        print_section("All Registry Rows", report["all_registry_rows"])


def print_section(title: str, items: object) -> None:
    rows = list(items)  # type: ignore[arg-type]
    print(f"## {title}")
    if not rows:
        print("- none")
        print()
        return

    for row in rows:
        print(f"- {row['feature']}")
        print(f"  PRD: {row['product_doc']}")
        print(
            "  Status: "
            f"prd={row['prd_status']}, tech={row['technical_status']}, "
            f"implementation={row['implementation']}, evidence={row['evidence']}, "
            f"user_acceptance={row['user_acceptance']}"
        )
        if row["known_gaps"] and row["known_gaps"] != "No active technical implementation expected.":
            print(f"  Gap: {row['known_gaps']}")
        if row["next_action"]:
            print(f"  Next: {row['next_action']}")
    print()


def print_unregistered(items: object) -> None:
    paths = list(items)  # type: ignore[arg-type]
    print("## Unregistered PRD Files")
    if not paths:
        print("- none")
        print()
        return
    for path in paths:
        print(f"- {path}")
    print()


if __name__ == "__main__":
    main()
