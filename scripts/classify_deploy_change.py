from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

DeployMode = Literal["no_deploy", "quick", "full"]


NO_DEPLOY_PATTERNS = (
    "AGENTS.md",
    "*.md",
    "**/*.md",
    "docs/**",
    "tests/**",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "scripts/agent_preflight.py",
    "scripts/audit_agent_flow_health.py",
    "scripts/audit_delivery_state.py",
    "scripts/audit_prd_status.py",
    "scripts/classify_deploy_change.py",
    "scripts/evaluate_agent_flow_cases.py",
)

QUICK_DEPLOY_PATTERNS = (
    "db/**",
    "deploy/systemd/**",
    "investment_knowledge_mcp/**",
    "scripts/*.py",
    "scripts/*.sh",
)

FULL_DEPLOY_PATTERNS = (
    "Dockerfile",
    "Dockerfile.*",
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "requirements*.txt",
    "pyproject.toml",
    "poetry.lock",
    "package.json",
    "package-lock.json",
)

MODE_RANK: dict[DeployMode, int] = {
    "no_deploy": 0,
    "quick": 1,
    "full": 2,
}


@dataclass(frozen=True)
class ClassifiedFile:
    path: str
    deploy_mode: DeployMode
    reason: str


@dataclass(frozen=True)
class ClassificationResult:
    deploy_mode: DeployMode
    changed_files: tuple[str, ...]
    classified_files: tuple[ClassifiedFile, ...]


def classify_changed_files(files: Iterable[str]) -> ClassificationResult:
    normalized = tuple(_normalize_path(path) for path in files if _normalize_path(path))
    if not normalized:
        return ClassificationResult(
            deploy_mode="full",
            changed_files=(),
            classified_files=(),
        )

    classified = tuple(classify_file(path) for path in normalized)
    mode: DeployMode = "no_deploy"
    for item in classified:
        if MODE_RANK[item.deploy_mode] > MODE_RANK[mode]:
            mode = item.deploy_mode
    return ClassificationResult(
        deploy_mode=mode,
        changed_files=normalized,
        classified_files=classified,
    )


def classify_file(path: str) -> ClassifiedFile:
    normalized = _normalize_path(path)
    if _matches_any(normalized, FULL_DEPLOY_PATTERNS):
        return ClassifiedFile(normalized, "full", "image/dependency/compose or package metadata")
    if _matches_any(normalized, NO_DEPLOY_PATTERNS):
        return ClassifiedFile(normalized, "no_deploy", "docs/governance/tests/local audit-eval only")
    if _matches_any(normalized, QUICK_DEPLOY_PATTERNS):
        return ClassifiedFile(normalized, "quick", "runtime app/script/database change")
    return ClassifiedFile(normalized, "full", "unclassified path defaults to full deploy")


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _normalize_path(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify changed files as no_deploy, quick, or full deploy.",
    )
    parser.add_argument("files", nargs="*", help="Changed files to classify.")
    parser.add_argument(
        "--changed-files-file",
        type=Path,
        help="Read newline-delimited changed files from this file.",
    )
    parser.add_argument(
        "--manual-mode",
        choices=("auto", "no_deploy", "quick", "full"),
        default="auto",
        help="Manual workflow_dispatch override.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "github-output"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args()

    files = list(args.files)
    if args.changed_files_file:
        files.extend(args.changed_files_file.read_text(encoding="utf-8").splitlines())

    if args.manual_mode != "auto":
        result = ClassificationResult(
            deploy_mode=args.manual_mode,
            changed_files=(f"manual-{args.manual_mode}",),
            classified_files=(),
        )
    else:
        result = classify_changed_files(files)

    print_result(result, args.format)


def print_result(result: ClassificationResult, output_format: str) -> None:
    if output_format == "json":
        print(
            json.dumps(
                {
                    "deploy_mode": result.deploy_mode,
                    "changed_files": list(result.changed_files),
                    "classified_files": [
                        {
                            "path": item.path,
                            "deploy_mode": item.deploy_mode,
                            "reason": item.reason,
                        }
                        for item in result.classified_files
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if output_format == "github-output":
        print(f"deploy_mode={result.deploy_mode}")
        print("changed_files<<EOF")
        for path in result.changed_files:
            print(path)
        print("EOF")
        return

    print(f"Selected deployment mode: {result.deploy_mode}")
    if not result.classified_files:
        print("Changed files:")
        for path in result.changed_files:
            print(f"- {path}")
        return
    print("Classified files:")
    for item in result.classified_files:
        print(f"- {item.path}: {item.deploy_mode} ({item.reason})")


if __name__ == "__main__":
    main()
