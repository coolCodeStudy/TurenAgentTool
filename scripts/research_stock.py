from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.research.draft_builder import build_stock_research_draft
from investment_knowledge_mcp.research.providers import collect_with_optional_providers
from scripts.build_research_prompt import PROMPT_TEMPLATE_PATH, build_prompt
from scripts.create_research_draft import default_output_path


def enriched_output_path(draft_path: Path) -> Path:
    return draft_path.with_suffix(".enriched.json")


def prompt_output_path(draft_path: Path) -> Path:
    return draft_path.with_suffix(".prompt.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the first-stage stock research workflow.")
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
        "--draft-output",
        type=Path,
        help="Output draft skeleton path.",
    )
    parser.add_argument(
        "--prompt-output",
        type=Path,
        help="Output prompt path.",
    )
    args = parser.parse_args()

    bundle = collect_with_optional_providers(
        symbol=args.symbol,
        market=args.market,
        company_name=args.name,
        manual_source_file=args.manual_source_file,
        source_urls=args.source_url,
    )
    draft = build_stock_research_draft(bundle)

    draft_path = args.draft_output or default_output_path(bundle.symbol, bundle.market)
    prompt_path = args.prompt_output or prompt_output_path(draft_path)
    enriched_path = enriched_output_path(draft_path)

    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    prompt = build_prompt(draft=draft, template=template)
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")

    print("Research workflow prepared.")
    print(f"- Draft skeleton: {draft_path}")
    print(f"- Model prompt: {prompt_path}")
    print()
    print("Next steps:")
    print(f"1. Give the prompt to a model and save the completed JSON as: {enriched_path}")
    print(f"2. Validate it: python scripts/validate_research_draft.py {enriched_path}")
    print(f"3. Import it after user confirmation: python scripts/import_research_draft.py {enriched_path} --confirmed")


if __name__ == "__main__":
    main()
