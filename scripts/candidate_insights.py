from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import (
    confirm_candidate_insight,
    list_candidate_insights,
    reject_candidate_insight,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage candidate user insights.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List candidate insights.")
    list_parser.add_argument("--status", default="pending", help="pending, confirmed, rejected, or all.")
    list_parser.add_argument("--target-type", help="Filter by target type.")

    confirm_parser = subparsers.add_parser("confirm", help="Confirm a candidate insight.")
    confirm_parser.add_argument("candidate_id", type=int)

    reject_parser = subparsers.add_parser("reject", help="Reject a candidate insight.")
    reject_parser.add_argument("candidate_id", type=int)

    args = parser.parse_args()
    run_schema()

    if args.command == "list":
        status = None if args.status == "all" else args.status
        candidates = list_candidate_insights(status=status, target_type=args.target_type)
        if not candidates:
            print("No candidate insights found.")
            return
        for candidate in candidates:
            print(
                f"[{candidate['id']}] {candidate['status']} "
                f"{candidate['target_type']}:{candidate['target_id']} "
                f"{candidate['insight']}"
            )
        return

    if args.command == "confirm":
        result = confirm_candidate_insight(args.candidate_id)
        print("Candidate insight confirmed.")
        print(
            {
                "candidate_id": result["candidate"]["id"],
                "user_insight_id": result["user_insight"]["id"],
            }
        )
        return

    if args.command == "reject":
        candidate = reject_candidate_insight(args.candidate_id)
        print("Candidate insight rejected.")
        print({"candidate_id": candidate["id"], "status": candidate["status"]})


if __name__ == "__main__":
    main()
