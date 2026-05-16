from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.command_router import handle_command
from investment_knowledge_mcp.db import run_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="InvestmentKnowledge command entrypoint.")
    parser.add_argument("command", nargs="+", help="Command text, for example: 分析 000660 KR")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "drafts",
        help="Directory for generated files.",
    )
    args = parser.parse_args()

    run_schema()
    result = handle_command(" ".join(args.command), output_dir=args.output_dir)
    print(result.message)
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
