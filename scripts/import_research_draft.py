from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import import_stock_research_draft
from scripts.db_write_guard import db_target_summary, ensure_not_default_local_write


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a stock research draft JSON file.")
    parser.add_argument("draft_path", type=Path, help="Path to research draft JSON.")
    parser.add_argument(
        "--confirmed",
        action="store_true",
        help="Mark imported sector relations and knowledge items as user-confirmed.",
    )
    parser.add_argument(
        "--allow-local-db",
        action="store_true",
        help="Allow writes to the default local dev database target.",
    )
    args = parser.parse_args()

    ensure_not_default_local_write(allow_local_db=args.allow_local_db)
    run_schema()
    draft = json.loads(args.draft_path.read_text(encoding="utf-8"))
    result = import_stock_research_draft(draft=draft, confirmed_by_user=args.confirmed)

    execution_location = "manual_import" if args.confirmed else "import_only"
    print("Research draft imported.")
    print(f"Execution location: {execution_location}")
    print(f"DB target: {db_target_summary()}")
    print(
        json.dumps(
            {
                "stock": result["stock"],
                "sector_relations": len(result["relations"]),
                "knowledge_items": len(result["knowledge_items"]),
                "user_insights": len(result["user_insights"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
