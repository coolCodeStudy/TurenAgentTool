from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.research.source_facts import extract_source_facts


def default_output_path(draft_path: Path) -> Path:
    return draft_path.with_name(draft_path.stem.replace("_research_draft", "") + "_source_facts.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract simple source facts from a research draft.")
    parser.add_argument("draft_path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    draft = json.loads(args.draft_path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise SystemExit("Draft must be a JSON object.")
    facts = extract_source_facts(draft)
    output = args.output or default_output_path(args.draft_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Source facts written to {output}")


if __name__ == "__main__":
    main()
