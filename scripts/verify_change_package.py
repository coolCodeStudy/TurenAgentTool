from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHANGES_DIR = PROJECT_ROOT / "docs/changes"

REQUIRED_FILES = {
    "proposal.md": ("# ", "## Problem", "## Goal", "## Non-Goals", "## Source Links"),
    "requirements.md": ("# ", "## User Journeys", "## Acceptance Criteria", "## Degraded Behavior", "## Out Of Scope"),
    "design.md": ("# ", "## Approach", "## Files Or Surfaces", "## Data And State", "## Risks", "## Reviewer Gates"),
    "tasks.md": ("# ", "## Checklist", "## Verification Commands"),
    "handoff.md": ("# ", "## Coordinator Packet", "## Watch Contract", "## Return Gate"),
}

PROJECT_LINK_WORDS = (
    "Feature Registry",
    "Acceptance Queue",
    "Delivery Queue",
)


@dataclass(frozen=True)
class PackageFinding:
    package: str
    severity: str
    item: str
    detail: str
    next_action: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify repo-native change packages.")
    parser.add_argument("paths", nargs="*", help="Specific change package paths or names to verify.")
    parser.add_argument("--all", action="store_true", help="Verify all packages under docs/changes.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on findings.")
    args = parser.parse_args()

    packages = resolve_packages(args.paths, all_packages=args.all)
    findings: list[PackageFinding] = []
    for package in packages:
        findings.extend(verify_package(package))

    if args.json:
        print(json.dumps([asdict(finding) for finding in findings], ensure_ascii=False, indent=2))
    else:
        print_text_report(packages, findings)

    if args.strict and findings:
        raise SystemExit(1)


def resolve_packages(paths: list[str], *, all_packages: bool) -> list[Path]:
    if all_packages:
        if not CHANGES_DIR.exists():
            return []
        return sorted(
            path
            for path in CHANGES_DIR.iterdir()
            if path.is_dir() and not path.name.startswith("_")
        )

    if not paths:
        raise SystemExit("Pass one package path/name or use --all.")

    packages: list[Path] = []
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            direct = PROJECT_ROOT / path
            named = CHANGES_DIR / value
            path = direct if direct.exists() else named
        packages.append(path)
    return packages


def verify_package(package: Path) -> list[PackageFinding]:
    findings: list[PackageFinding] = []
    if not package.exists() or not package.is_dir():
        return [
            PackageFinding(
                package.name,
                "blocker",
                "missing_package",
                f"Change package does not exist: {package}",
                "Create the package under docs/changes/<change-id>/ or pass the correct path.",
            )
        ]

    package_name = package.name
    combined_text = ""
    for filename, headings in REQUIRED_FILES.items():
        path = package / filename
        if not path.exists():
            findings.append(
                PackageFinding(
                    package_name,
                    "blocker",
                    filename,
                    f"Missing required file `{filename}`.",
                    f"Create `{filename}` using docs/changes/_template/{filename}.",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        combined_text += "\n" + text
        for heading in headings:
            if heading not in text:
                findings.append(
                    PackageFinding(
                        package_name,
                        "major",
                        filename,
                        f"Missing required heading or marker `{heading}`.",
                        f"Add `{heading}` to `{path.relative_to(PROJECT_ROOT)}`.",
                    )
                )

    for word in PROJECT_LINK_WORDS:
        if word not in combined_text:
            findings.append(
                PackageFinding(
                    package_name,
                    "major",
                    "project_links",
                    f"Package does not mention `{word}`.",
                    "Link the package to current delivery truth, or state `not_applicable` with reason.",
                )
            )

    if "Watch Contract" in combined_text:
        for marker in ("Watched item", "Wake event", "Expected artifact", "Coordinator action"):
            if marker not in combined_text:
                findings.append(
                    PackageFinding(
                        package_name,
                        "major",
                        "watch_contract",
                        f"Watch Contract is missing `{marker}`.",
                        "Complete the watch contract so the coordinator can resume without chat history.",
                    )
                )
    return findings


def print_text_report(packages: list[Path], findings: list[PackageFinding]) -> None:
    print("# Change Package Verification")
    print()
    if packages:
        print("Packages:")
        for package in packages:
            print(f"- {package.relative_to(PROJECT_ROOT) if package.is_absolute() else package}")
        print()

    if not findings:
        print("- No change package issues found.")
        return

    for finding in findings:
        print(f"- [{finding.severity}] {finding.package} / {finding.item}: {finding.detail}")
        print(f"  Next: {finding.next_action}")


if __name__ == "__main__":
    main()
