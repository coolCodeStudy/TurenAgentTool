from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.research.validation import validate_research_draft


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a stock research draft JSON file.")
    parser.add_argument("draft_path", type=Path, help="Path to research draft JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )
    args = parser.parse_args()

    try:
        draft = json.loads(args.draft_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not isinstance(draft, dict):
        print("Draft must be a JSON object.", file=sys.stderr)
        raise SystemExit(1)

    result = validate_research_draft(draft)

    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if result.errors or (args.strict and result.warnings):
        raise SystemExit(1)

    print("Research draft validation passed.")


if __name__ == "__main__":
    main()
