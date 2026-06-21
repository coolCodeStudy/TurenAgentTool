from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.decision_data_probe import probe_futu_decision_data, render_probe_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Futu decision-data coverage for a stock.")
    parser.add_argument("symbol", help="Stock symbol, for example 000660.")
    parser.add_argument("market", help="Market code, for example KR.")
    args = parser.parse_args()
    print(render_probe_result(probe_futu_decision_data(symbol=args.symbol, market=args.market)))


if __name__ == "__main__":
    main()
