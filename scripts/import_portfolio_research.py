from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.futu_provider import get_futu_positions
from investment_knowledge_mcp.research.pipeline import (
    ResearchPipelineOptions,
    ResearchPipelineResult,
    run_single_stock_research,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate/import research drafts for current portfolio positions.")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "drafts")
    parser.add_argument("--provider", choices=["openai", "mock", "none"], default="openai")
    parser.add_argument("--auto-confirm-facts", action="store_true")
    parser.add_argument("--import", dest="auto_import", action="store_true", help="Import pass-audited drafts.")
    parser.add_argument("--import-needs-review", action="store_true", help="Also import needs_review drafts.")
    parser.add_argument("--refresh", action="store_true", help="Refresh stocks that already exist.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()

    run_schema()
    positions = get_futu_positions()
    rows = _active_positions(positions)
    if args.limit:
        rows = rows[: args.limit]

    options = ResearchPipelineOptions(
        output_dir=args.output_dir,
        provider=args.provider,
        auto_confirm_facts=args.auto_confirm_facts,
        auto_import=args.auto_import,
        import_needs_review=args.import_needs_review,
        refresh=args.refresh,
    )

    results: list[ResearchPipelineResult] = []
    for position in rows:
        symbol, market = _split_position_code(position["code"])
        name = position.get("stock_name")
        print(f"Processing {symbol} {market} {name or ''} ...", flush=True)
        result = run_single_stock_research(
            symbol=symbol,
            market=market,
            company_name=name,
            options=options,
        )
        results.append(result)
        print(f"- {result.status} audit={result.audit_status or '-'} {result.message}", flush=True)

    summary = _build_summary(results)
    output = args.summary_output or args.output_dir / "portfolio_research_import_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Summary written to {output}")


def _active_positions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for position in payload.get("positions") or []:
        try:
            qty = float(position.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty > 0:
            rows.append(position)
    return rows


def _split_position_code(code: str) -> tuple[str, str]:
    market, symbol = code.split(".", 1) if "." in code else ("", code)
    return symbol.upper(), market.upper()


def _build_summary(results: list[ResearchPipelineResult]) -> dict[str, Any]:
    imported = [result for result in results if result.status == "imported"]
    skipped = [result for result in results if result.status == "skipped_existing"]
    needs_review = [result for result in results if result.status == "needs_review"]
    failed = [result for result in results if result.status in {"failed", "failed_audit"}]
    drafted = [result for result in results if result.status == "drafted"]
    return {
        "total": len(results),
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "drafted_count": len(drafted),
        "needs_review_count": len(needs_review),
        "failed_count": len(failed),
        "imported": [result.to_summary() for result in imported],
        "skipped": [result.to_summary() for result in skipped],
        "needs_review": [result.to_summary() for result in needs_review],
        "failed": [result.to_summary() for result in failed],
        "drafted": [result.to_summary() for result in drafted],
    }


if __name__ == "__main__":
    main()
