from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.events.renderer import render_scan_result
from investment_knowledge_mcp.events.scanner import scan_portfolio_events, scan_stock_events, scan_symbols_events
from investment_knowledge_mcp.serialization import to_jsonable


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan US portfolio SEC event filings.")
    parser.add_argument("--symbol", help="Single ticker to scan.")
    parser.add_argument("--symbols", help="Comma-separated tickers to scan.")
    parser.add_argument("--market", default="US", help="Market code, defaults to US.")
    parser.add_argument("--days", type=int, default=30, help="Lookback days.")
    parser.add_argument("--portfolio", action="store_true", help="Scan current US portfolio positions from Futu.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write scan results to database.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON instead of Markdown.")
    args = parser.parse_args()

    persist = not args.dry_run
    if args.portfolio:
        result = scan_portfolio_events(days=args.days, persist=persist)
    elif args.symbol:
        result = scan_stock_events(symbol=args.symbol, market=args.market, days=args.days, persist=persist)
    elif args.symbols:
        symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
        result = scan_symbols_events(symbols=symbols, market=args.market, days=args.days, persist=persist)
    else:
        parser.error("one of --portfolio, --symbol, or --symbols is required")

    if args.json:
        print(json.dumps(to_jsonable(asdict(result)), ensure_ascii=False, indent=2))
    else:
        print(render_scan_result(result))


if __name__ == "__main__":
    main()
