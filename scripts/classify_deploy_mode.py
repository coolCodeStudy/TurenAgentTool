#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Iterable


FULL_DEPLOY_FILES = {
    "Dockerfile": "container image definition",
    "requirements.txt": "Python dependency set",
    "docker-compose.prod.yml": "production service/image structure",
}

QUICK_DEPLOY_PREFIXES = {
    "db/": "database scripts or schema",
    "deploy/systemd/": "systemd deployment helper",
    "docs/": "documentation",
    "investment_knowledge_mcp/": "application source code",
    "tests/": "test-only code",
}

QUICK_DEPLOY_SUFFIXES = {
    ".md": "markdown documentation",
}

QUICK_DEPLOY_GLOBS = {
    ".github/workflows/*.yaml": "GitHub Actions workflow",
    ".github/workflows/*.yml": "GitHub Actions workflow",
    "scripts/*.py": "Python script",
    "scripts/*.sh": "shell script",
}


@dataclass(frozen=True)
class Classification:
    file: str
    deploy_class: str
    reason: str


def normalize_changed_file(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def classify_file(path: str) -> Classification:
    normalized = normalize_changed_file(path)
    if normalized in FULL_DEPLOY_FILES:
        return Classification(normalized, "full", FULL_DEPLOY_FILES[normalized])

    for prefix, reason in QUICK_DEPLOY_PREFIXES.items():
        if normalized.startswith(prefix):
            return Classification(normalized, "quick", reason)

    for suffix, reason in QUICK_DEPLOY_SUFFIXES.items():
        if normalized.endswith(suffix):
            return Classification(normalized, "quick", reason)

    for pattern, reason in QUICK_DEPLOY_GLOBS.items():
        if fnmatchcase(normalized, pattern):
            return Classification(normalized, "quick", reason)

    return Classification(normalized, "full", "unclassified production-impact risk")


def classify_deploy_mode(paths: Iterable[str]) -> tuple[str, list[Classification]]:
    classifications = [classify_file(path) for path in paths if normalize_changed_file(path)]
    if not classifications:
        return "full", []
    mode = "full" if any(item.deploy_class == "full" for item in classifications) else "quick"
    return mode, classifications


def load_paths(args: argparse.Namespace) -> list[str]:
    paths = list(args.paths)
    if args.from_file:
        with open(args.from_file, "r", encoding="utf-8") as handle:
            paths.extend(handle.read().splitlines())
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify changed files into quick or full deploy mode.")
    parser.add_argument("paths", nargs="*", help="Changed file paths to classify.")
    parser.add_argument("--from-file", help="Read newline-delimited changed file paths from a file.")
    parser.add_argument("--mode-only", action="store_true", help="Print only the selected deploy mode.")
    args = parser.parse_args()

    mode, classifications = classify_deploy_mode(load_paths(args))

    if args.mode_only:
        print(mode)
        return 0

    if classifications:
        for item in classifications:
            label = "quick-compatible" if item.deploy_class == "quick" else "requires full deploy"
            print(f"Classifying changed file: {item.file}")
            print(f"  -> {label} ({item.reason})")
    else:
        print("No changed files detected.")
        print("  -> requires full deploy (conservative fallback)")
    print(f"Selected deployment mode: {mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
