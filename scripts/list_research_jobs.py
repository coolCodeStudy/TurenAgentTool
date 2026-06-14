from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.research.jobs import list_research_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="List async research jobs.")
    parser.add_argument("--status", default="all", help="Job status, or all.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--verbose", action="store_true", help="Include full artifacts and raw job fields.")
    args = parser.parse_args()

    run_schema()
    status = None if args.status == "all" else args.status
    rows = list_research_jobs(status=status, limit=args.limit, verbose=args.verbose)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
