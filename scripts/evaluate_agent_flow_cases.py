from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audit_agent_flow_health import (
    AcceptanceRow,
    DeliveryRow,
    RegistryRow,
    audit_flow_health,
    group_findings,
)


DEFAULT_CASES_PATH = PROJECT_ROOT / "docs/project-management/agent-flow-eval-cases.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run regression eval cases for multi-agent flow health rules.",
    )
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES_PATH),
        help="Path to agent-flow eval cases JSON.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    result = run_cases(Path(args.cases))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text_result(result)

    if result["failed"]:
        raise SystemExit(1)


def run_cases(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = []
    failed = []
    for case in payload.get("cases", []):
        case_result = run_case(case)
        results.append(case_result)
        if not case_result["passed"]:
            failed.append(case_result["id"])
    return {
        "cases_path": str(path),
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": failed,
        "results": results,
    }


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    today = datetime.strptime(case["today"], "%Y-%m-%d").date()
    findings = audit_flow_health(
        [DeliveryRow(**row) for row in case.get("delivery_rows", [])],
        [AcceptanceRow(**row) for row in case.get("acceptance_rows", [])],
        [RegistryRow(**row) for row in case.get("registry_rows", [])],
        stale_days=2,
        today=today,
        include_history=True,
    )
    grouped = group_findings(findings)
    actual_categories = set(grouped)
    expected_categories = set(case.get("expected_categories", []))
    missing = sorted(expected_categories - actual_categories)
    unexpected = sorted(actual_categories - expected_categories)
    return {
        "id": case["id"],
        "description": case.get("description", ""),
        "passed": not missing and not unexpected,
        "expected_categories": sorted(expected_categories),
        "actual_categories": sorted(actual_categories),
        "missing_categories": missing,
        "unexpected_categories": unexpected,
        "findings": {
            category: [asdict(finding) for finding in category_findings]
            for category, category_findings in grouped.items()
        },
    }


def print_text_result(result: dict[str, Any]) -> None:
    print("# Agent Flow Eval")
    print()
    print(f"- Cases: {result['total']}")
    print(f"- Passed: {result['passed']}")
    print(f"- Failed: {len(result['failed'])}")
    print()
    for case in result["results"]:
        status = "PASS" if case["passed"] else "FAIL"
        print(f"## {status}: {case['id']}")
        if case["description"]:
            print(f"- {case['description']}")
        print(f"- Expected: {', '.join(case['expected_categories']) or 'none'}")
        print(f"- Actual: {', '.join(case['actual_categories']) or 'none'}")
        if case["missing_categories"]:
            print(f"- Missing: {', '.join(case['missing_categories'])}")
        if case["unexpected_categories"]:
            print(f"- Unexpected: {', '.join(case['unexpected_categories'])}")
        print()


if __name__ == "__main__":
    main()
