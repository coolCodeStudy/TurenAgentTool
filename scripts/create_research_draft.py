from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.research.draft_builder import build_stock_research_draft
from investment_knowledge_mcp.research.models import merge_research_bundles
from investment_knowledge_mcp.research.official_sources import OfficialResearchProvider
from investment_knowledge_mcp.research.providers import collect_with_optional_providers


def default_output_path(symbol: str, market: str) -> Path:
    safe_symbol = symbol.strip().replace("/", "_").replace(".", "_").upper()
    safe_market = market.strip().replace("/", "_").replace(".", "_").upper()
    return PROJECT_ROOT / "drafts" / f"{safe_symbol}_{safe_market}_research_draft.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a stock research draft skeleton.")
    parser.add_argument("symbol", help="Stock symbol, for example 000660.")
    parser.add_argument("market", help="Market code, for example KR, HK, US, SH, SZ.")
    parser.add_argument("--name", help="Company display name.")
    parser.add_argument(
        "--manual-source-file",
        type=Path,
        help="Optional JSON file containing curated source documents.",
    )
    parser.add_argument(
        "--source-url",
        action="append",
        default=[],
        help="Optional public webpage source as KEY=URL. Can be repeated.",
    )
    parser.add_argument(
        "--official",
        action="store_true",
        help="Collect official sources from HKEX, SEC, issuer pages, or company IR before building the draft.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output draft JSON path. Defaults to drafts/<SYMBOL>_<MARKET>_research_draft.json.",
    )
    args = parser.parse_args()

    bundle = collect_with_optional_providers(
        symbol=args.symbol,
        market=args.market,
        company_name=args.name,
        manual_source_file=args.manual_source_file,
        source_urls=args.source_url,
    )
    if args.official:
        official_bundle = OfficialResearchProvider().collect(
            symbol=bundle.symbol,
            market=bundle.market,
            company_name=bundle.company_name,
        )
        bundle = merge_research_bundles(bundle, official_bundle)
    draft = build_stock_research_draft(bundle)

    output_path = args.output or default_output_path(bundle.symbol, bundle.market)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("execution_location: local_codex")
    print(f"Research draft skeleton written to {output_path}")


if __name__ == "__main__":
    main()
