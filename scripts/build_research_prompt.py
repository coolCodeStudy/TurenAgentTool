from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PROMPT_TEMPLATE_PATH = PROJECT_ROOT / "prompts" / "stock_research_draft_prompt.md"


def default_output_path(draft_path: Path) -> Path:
    return draft_path.with_suffix(".prompt.md")


def pretty_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_prompt(draft: dict, template: str) -> str:
    sources = draft.get("sources", [])
    return (
        template.replace("{{DRAFT_JSON}}", pretty_json(draft))
        .replace("{{SOURCES_JSON}}", pretty_json(sources))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a model prompt from a research draft skeleton.")
    parser.add_argument("draft_path", type=Path, help="Path to draft skeleton JSON.")
    parser.add_argument(
        "--template",
        type=Path,
        default=PROMPT_TEMPLATE_PATH,
        help="Prompt template path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output prompt path. Defaults to replacing .json with .prompt.md.",
    )
    args = parser.parse_args()

    draft = json.loads(args.draft_path.read_text(encoding="utf-8"))
    template = args.template.read_text(encoding="utf-8")
    prompt = build_prompt(draft=draft, template=template)

    output_path = args.output or default_output_path(args.draft_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")
    print(f"Research prompt written to {output_path}")


if __name__ == "__main__":
    main()
