from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.repository import propose_candidate_insight


def main() -> None:
    parser = argparse.ArgumentParser(description="Propose a candidate user insight for confirmation.")
    parser.add_argument(
        "target_type",
        choices=["stock", "sector", "portfolio", "strategy"],
        help="Candidate insight target type.",
    )
    parser.add_argument("insight", help="Candidate insight text.")
    parser.add_argument("--target-id", type=int, help="Resolved target id for advanced use.")
    parser.add_argument("--symbol", help="Stock symbol when target_type=stock.")
    parser.add_argument("--market", help="Market code when target_type=stock.")
    parser.add_argument(
        "--sector-path",
        nargs="+",
        help="Sector path when target_type=sector, for example AI基础设施 AI服务器供应链 高带宽内存.",
    )
    parser.add_argument("--summary", help="Normalized summary.")
    parser.add_argument("--reason", help="Why the system proposed this candidate.")
    parser.add_argument("--tag", action="append", default=[], help="Candidate tag. Can be repeated.")
    args = parser.parse_args()

    run_schema()
    candidate = propose_candidate_insight(
        target_type=args.target_type,
        target_id=args.target_id,
        symbol=args.symbol,
        market=args.market,
        sector_path=args.sector_path,
        insight=args.insight,
        normalized_summary=args.summary,
        tags=args.tag,
        reason=args.reason,
    )
    print("Candidate insight proposed.")
    print(
        {
            "id": candidate["id"],
            "target_type": candidate["target_type"],
            "target_id": candidate["target_id"],
            "status": candidate["status"],
            "tags": candidate["tags"],
        }
    )


if __name__ == "__main__":
    main()
