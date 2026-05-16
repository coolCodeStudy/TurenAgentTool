from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import record_user_insight


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a user investment insight.")
    parser.add_argument(
        "target_type",
        choices=["stock", "sector", "portfolio", "strategy"],
        help="Insight target type.",
    )
    parser.add_argument("insight", help="Original user insight text.")
    parser.add_argument("--target-id", type=int, help="Resolved target id for advanced use.")
    parser.add_argument("--symbol", help="Stock symbol when target_type=stock.")
    parser.add_argument("--market", help="Market code when target_type=stock.")
    parser.add_argument(
        "--sector-path",
        nargs="+",
        help="Sector path when target_type=sector, for example 科技 半导体 存储芯片.",
    )
    parser.add_argument("--summary", help="Normalized summary.")
    parser.add_argument("--tag", action="append", default=[], help="Insight tag. Can be repeated.")
    args = parser.parse_args()

    run_schema()
    insight = record_user_insight(
        target_type=args.target_type,
        target_id=args.target_id,
        symbol=args.symbol,
        market=args.market,
        sector_path=args.sector_path,
        insight=args.insight,
        normalized_summary=args.summary,
        tags=args.tag,
    )
    print("User insight recorded.")
    print(
        {
            "id": insight["id"],
            "target_type": insight["target_type"],
            "target_id": insight["target_id"],
            "tags": insight["tags"],
        }
    )


if __name__ == "__main__":
    main()
