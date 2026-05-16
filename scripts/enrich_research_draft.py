from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.model_providers.base import EnrichmentRequest
from investment_knowledge_mcp.model_providers.factory import create_model_provider
from investment_knowledge_mcp.research.validation import validate_research_draft
from scripts.build_research_prompt import PROMPT_TEMPLATE_PATH, build_prompt


def default_output_path(draft_path: Path) -> Path:
    return draft_path.with_suffix(".enriched.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich a research draft using a model provider.")
    parser.add_argument("draft_path", type=Path, help="Path to research draft skeleton JSON.")
    parser.add_argument(
        "--provider",
        choices=["mock", "openai"],
        default="mock",
        help="Model provider to use. Defaults to mock.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=PROMPT_TEMPLATE_PATH,
        help="Prompt template path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output enriched draft path. Defaults to replacing .json with .enriched.json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation warnings as failures.",
    )
    args = parser.parse_args()

    draft = json.loads(args.draft_path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        print("Draft must be a JSON object.", file=sys.stderr)
        raise SystemExit(1)

    template = args.template.read_text(encoding="utf-8")
    prompt = build_prompt(draft=draft, template=template)
    provider = create_model_provider(args.provider)
    enriched = provider.enrich_research_draft(EnrichmentRequest(draft=draft, prompt=prompt))

    result = validate_research_draft(enriched)
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if result.errors or (args.strict and result.warnings):
        raise SystemExit(1)

    output_path = args.output or default_output_path(args.draft_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Enriched research draft written to {output_path}")


if __name__ == "__main__":
    main()
