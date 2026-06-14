from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.futu_provider import get_futu_positions
from investment_knowledge_mcp.research.jobs import create_research_job
from scripts.db_write_guard import db_target_summary, ensure_not_default_local_write


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Codex-first research jobs from current Futu holdings.")
    parser.add_argument("--provider", choices=["codex", "openai", "none"], default="codex")
    parser.add_argument(
        "--source-policy",
        choices=["official_only", "official_first", "broad_search", "user_sources"],
        default="broad_search",
    )
    parser.add_argument("--priority", choices=["low", "normal", "high"], default="normal")
    parser.add_argument("--include-existing", action="store_true", help="Also enqueue stocks already in the knowledge base.")
    parser.add_argument("--refresh", action="store_true", help="Refresh existing stock research when jobs run.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sender", default="codex")
    parser.add_argument("--source", default="codex")
    parser.add_argument("--summary-output", type=Path, default=PROJECT_ROOT / "drafts" / "research_jobs_summary.json")
    parser.add_argument(
        "--allow-local-db",
        action="store_true",
        help="Allow writes to the default local dev database target.",
    )
    args = parser.parse_args()

    ensure_not_default_local_write(allow_local_db=args.allow_local_db)
    print("Execution location: cloud_worker")
    run_schema()
    snapshot = get_futu_positions()
    positions = _active_positions(snapshot)
    if args.limit:
        positions = positions[: args.limit]

    created: list[dict[str, Any]] = []
    skipped_existing: list[dict[str, Any]] = []
    skipped_invalid: list[dict[str, Any]] = []

    for position in positions:
        code = str(position.get("code") or "")
        if "." not in code:
            skipped_invalid.append({"code": code, "reason": "missing market prefix"})
            continue
        market, symbol = code.split(".", 1)
        market = market.upper()
        symbol = symbol.upper()
        if not args.include_existing and repository.search_stock(symbol=symbol, market=market).get("stock"):
            skipped_existing.append({"symbol": symbol, "market": market, "name": position.get("stock_name")})
            continue
        job = create_research_job(
            symbol=symbol,
            market=market,
            name=position.get("stock_name"),
            priority=args.priority,
            source_policy=args.source_policy,
            provider=args.provider,
            auto_import=True,
            import_needs_review=False,
            refresh=args.refresh,
            source=args.source,
            sender=args.sender,
            execution_location="cloud_worker",
            created_from="script",
            requested_by=args.sender,
        )
        created.append(job)

    summary = {
        "created_count": len(created),
        "skipped_existing_count": len(skipped_existing),
        "skipped_invalid_count": len(skipped_invalid),
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_invalid": skipped_invalid,
    }
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DB target: {db_target_summary()}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Summary written to {args.summary_output}")


def _active_positions(payload: Any) -> list[dict[str, Any]]:
    if hasattr(payload, "positions"):
        positions = getattr(payload, "positions")
    elif isinstance(payload, dict):
        positions = payload.get("positions") or []
    else:
        positions = []

    rows: list[dict[str, Any]] = []
    for position in positions:
        try:
            qty = float(position.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty > 0:
            rows.append(position)
    return rows


if __name__ == "__main__":
    main()
